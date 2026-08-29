from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .agent_access_audit import agent_access_audit_summary
from .agent_consultation_plans import (
    agent_consultation_plan_summary,
    build_agent_consultation_plan,
    load_strict_json,
)
from .catalog import build_catalog
from .comparison import suggest_pairs
from .comparison_reviews import (
    amend_comparison_review,
    append_comparison_review,
    comparison_review_summary,
    write_comparison_review,
)
from .consultation_boards import (
    consultation_board_summary,
    write_consultation_board,
)
from .consultation_packets import (
    consultation_packet_summary,
    write_consultation_packet,
)
from .key_images import key_image_archive_summary
from .longitudinal_readiness import build_longitudinal_readiness
from .lesion_volume_comparisons import (
    lesion_volume_comparison_summary,
    write_lesion_volume_comparison,
)
from .lesion_volumes import lesion_volume_archive_summary
from .lesion_volume_reviews import lesion_volume_review_summary
from .measurements import (
    build_measurement_comparison,
    measurement_comparison_summary,
    measurement_packet_summary,
)
from .navigation import build_navigation_intent
from .presentation_states import (
    build_presentation_state_catalog,
    presentation_state_summary,
    registry_source_loader,
)
from .registration import (
    registration_bundle_summary,
    registration_doctor,
    run_rigid_registration,
)
from .registration_reviews import (
    import_registration_review,
    registration_review_summary,
    write_registration_review,
)
from .server import serve
from .visit_packets import visit_packet_summary, write_visit_packet


def _write_json(value: object, output: Path | None) -> None:
    payload = json.dumps(value, indent=2) + "\n"
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_name(f".{output.name}.{os.getpid()}.tmp")
        try:
            temporary.write_text(payload)
            temporary.chmod(0o600)
            temporary.replace(output)
        finally:
            temporary.unlink(missing_ok=True)
    else:
        print(payload, end="")


def _viewer_dist(explicit: Path | None) -> Path:
    candidates = [explicit] if explicit else [
        Path(__file__).resolve().parents[4] / "apps" / "viewer" / "dist",
        Path(__file__).resolve().parent / "ui",
    ]
    for candidate in candidates:
        if candidate and (candidate.expanduser() / "index.html").is_file():
            return candidate.expanduser()
    raise ValueError("viewer bundle is missing; run `pnpm build` or pass --ui-dist")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="scanview-agent")
    commands = root.add_subparsers(dest="command", required=True)

    manifest = commands.add_parser("manifest", help="Create a PHI-minimized local DICOM catalog")
    manifest.add_argument("root", type=Path)
    manifest.add_argument("--output", "-o", type=Path)
    manifest.add_argument("--no-hashes", action="store_true", help="Skip slower source SHA-256 hashing")
    manifest.add_argument("--include-relative-paths", action="store_true")

    candidates = commands.add_parser("candidates", help="Suggest, but never approve, series pairs")
    candidates.add_argument("manifest", type=Path)
    candidates.add_argument("--output", "-o", type=Path)

    readiness = commands.add_parser(
        "readiness",
        help="Create a local metadata-only longitudinal follow-up readiness report",
    )
    readiness.add_argument("manifest", type=Path)
    readiness.add_argument("--output", "-o", type=Path)

    create_consultation_plan = commands.add_parser(
        "create-consultation-plan",
        help="Bind agent-proposed exact native views to a local catalog for human review",
    )
    create_consultation_plan.add_argument("manifest", type=Path)
    create_consultation_plan.add_argument("request", type=Path)
    create_consultation_plan.add_argument("--output", "-o", type=Path, required=True)

    validate_consultation_plan = commands.add_parser(
        "validate-consultation-plan",
        help="Validate an unreviewed agent consultation plan against its exact catalog",
    )
    validate_consultation_plan.add_argument("manifest", type=Path)
    validate_consultation_plan.add_argument("plan", type=Path)

    presentation_states = commands.add_parser(
        "presentation-states",
        help="Extract a source-bound read-only DICOM GSPS catalog locally",
    )
    presentation_states.add_argument("root", type=Path)
    presentation_states.add_argument("--output", "-o", type=Path, required=True)

    validate_presentation_states = commands.add_parser(
        "validate-presentation-states",
        help="Revalidate a GSPS catalog against the exact local DICOM sources",
    )
    validate_presentation_states.add_argument("root", type=Path)
    validate_presentation_states.add_argument("artifact", type=Path)

    api = commands.add_parser("serve", help="Run the source-read-only loopback agent API")
    api.add_argument("root", type=Path)
    api.add_argument("--port", type=int, default=8765)
    api.add_argument("--token")
    api.add_argument("--no-hashes", action="store_true")
    api.add_argument("--registration-bundle", type=Path)
    api.add_argument("--registration-review", type=Path)
    api.add_argument(
        "--lesion-volume-comparison",
        type=Path,
        help="Accepted reviewed volume-comparison ZIP to display in two unregistered native spaces",
    )
    api.add_argument(
        "--agent-audit-log",
        type=Path,
        help="Optional owner-only append-only JSONL audit for sensitive bearer GET requests",
    )

    launch = commands.add_parser(
        "launch",
        help="Open one loopback-only workspace for the local UI and agent interface",
    )
    launch.add_argument("root", type=Path)
    launch.add_argument("--port", type=int, default=8765)
    launch.add_argument("--token")
    launch.add_argument("--no-hashes", action="store_true")
    launch.add_argument("--no-open", action="store_true")
    launch.add_argument("--ui-dist", type=Path)
    launch.add_argument("--registration-bundle", type=Path)
    launch.add_argument("--registration-review", type=Path)
    launch.add_argument(
        "--lesion-volume-comparison",
        type=Path,
        help="Accepted reviewed volume-comparison ZIP to display in two unregistered native spaces",
    )
    launch.add_argument(
        "--agent-audit-log",
        type=Path,
        help="Optional owner-only append-only JSONL audit for sensitive bearer GET requests",
    )
    launch.add_argument("--baseline-series", help="Exact opaque baseline series ID")
    launch.add_argument("--baseline-instance", help="Exact opaque baseline instance ID")
    launch.add_argument("--followup-series", help="Optional exact opaque follow-up series ID")
    launch.add_argument("--followup-instance", help="Optional exact opaque follow-up instance ID")

    viewer_link = commands.add_parser(
        "viewer-link",
        help="Create a one-use local viewer fragment for exact opaque source instances",
    )
    viewer_link.add_argument("manifest", type=Path)
    viewer_link.add_argument(
        "--baseline-series", required=True, help="Exact opaque series ID"
    )
    viewer_link.add_argument(
        "--baseline-instance", required=True, help="Exact opaque instance ID"
    )
    viewer_link.add_argument(
        "--followup-series", help="Optional exact opaque follow-up series ID"
    )
    viewer_link.add_argument(
        "--followup-instance", help="Optional exact opaque follow-up instance ID"
    )
    viewer_link.add_argument(
        "--base-url",
        help="Optional active loopback viewer origin, for example http://127.0.0.1:8765/",
    )
    viewer_link.add_argument("--output", "-o", type=Path)

    validate_measurements = commands.add_parser(
        "validate-measurements",
        help="Validate and summarize a local ScanView measurement evidence packet",
    )
    validate_measurements.add_argument("packet", type=Path)

    validate_key_image = commands.add_parser(
        "validate-key-image",
        help="Validate a local ScanView key-image archive and its integrity links",
    )
    validate_key_image.add_argument("archive", type=Path)

    validate_lesion_volume = commands.add_parser(
        "validate-lesion-volume",
        help=(
            "Validate a local manual DICOM SEG bundle against the exact native "
            "DICOM source and recompute its unreviewed volume"
        ),
    )
    validate_lesion_volume.add_argument("archive", type=Path)
    validate_lesion_volume.add_argument(
        "source_root",
        type=Path,
        help="Local DICOM root used to rehash and verify every referenced source instance",
    )

    validate_lesion_volume_review = commands.add_parser(
        "validate-lesion-volume-review",
        help=(
            "Validate a self-attested manual ROI boundary review, its nested "
            "DICOM SEG evidence, and every exact native source instance"
        ),
    )
    validate_lesion_volume_review.add_argument("archive", type=Path)
    validate_lesion_volume_review.add_argument(
        "source_root",
        type=Path,
        help="Local DICOM root used to rehash the nested evidence source set",
    )

    assemble_lesion_volume_comparison = commands.add_parser(
        "assemble-lesion-volume-comparison",
        help=(
            "Join two accepted source-bound boundary reviews using one explicit "
            "qualified pairing request and live DICOM chronology"
        ),
    )
    assemble_lesion_volume_comparison.add_argument("baseline_review", type=Path)
    assemble_lesion_volume_comparison.add_argument("followup_review", type=Path)
    assemble_lesion_volume_comparison.add_argument("pairing_request", type=Path)
    assemble_lesion_volume_comparison.add_argument(
        "source_root", type=Path, help="Exact local DICOM root containing both timepoints"
    )
    assemble_lesion_volume_comparison.add_argument(
        "--output", "-o", type=Path, required=True
    )

    validate_lesion_volume_comparison = commands.add_parser(
        "validate-lesion-volume-comparison",
        help=(
            "Recursively validate a reviewed manual ROI volume comparison, both "
            "nested reviews, and every exact local DICOM source"
        ),
    )
    validate_lesion_volume_comparison.add_argument("archive", type=Path)
    validate_lesion_volume_comparison.add_argument("source_root", type=Path)

    verify_agent_audit = commands.add_parser(
        "verify-agent-audit",
        help="Verify a local privacy-minimized hash-chained agent access audit",
    )
    verify_agent_audit.add_argument("audit_log", type=Path)

    assemble_visit_packet = commands.add_parser(
        "assemble-visit-packet",
        help="Assemble two validated same-modality key images for a clinical conversation",
    )
    assemble_visit_packet.add_argument("baseline_archive", type=Path)
    assemble_visit_packet.add_argument("followup_archive", type=Path)
    assemble_visit_packet.add_argument("--output", "-o", type=Path, required=True)

    validate_visit_packet = commands.add_parser(
        "validate-visit-packet",
        help="Validate a local ScanView clinician visit packet and all integrity links",
    )
    validate_visit_packet.add_argument("archive", type=Path)

    assemble_consultation_packet = commands.add_parser(
        "assemble-consultation-packet",
        help=(
            "Assemble two live-source-validated MR/CT reference views for a "
            "clinician discussion"
        ),
    )
    assemble_consultation_packet.add_argument(
        "root", type=Path, help="Local DICOM root used to verify exact source bytes"
    )
    assemble_consultation_packet.add_argument("view_a_archive", type=Path)
    assemble_consultation_packet.add_argument("view_b_archive", type=Path)
    assemble_consultation_packet.add_argument(
        "--output", "-o", type=Path, required=True
    )

    validate_consultation_packet = commands.add_parser(
        "validate-consultation-packet",
        help="Validate a local clinician consultation packet and all integrity links",
    )
    validate_consultation_packet.add_argument("archive", type=Path)

    assemble_consultation_board = commands.add_parser(
        "assemble-consultation-board",
        help=(
            "Assemble 2-8 labeled live-source-validated MR/CT reference views "
            "for a clinician discussion"
        ),
    )
    assemble_consultation_board.add_argument(
        "root", type=Path, help="Local DICOM root used to verify exact source bytes"
    )
    assemble_consultation_board.add_argument(
        "--item",
        action="append",
        nargs=2,
        metavar=("LABEL", "KEY_IMAGE_ARCHIVE"),
        required=True,
        help="Person-entered discussion label and neutral consultation key-image ZIP",
    )
    assemble_consultation_board.add_argument(
        "--output", "-o", type=Path, required=True
    )

    validate_consultation_board = commands.add_parser(
        "validate-consultation-board",
        help="Validate a local consultation evidence board and all integrity links",
    )
    validate_consultation_board.add_argument("archive", type=Path)

    compare_measurements = commands.add_parser(
        "compare-measurements",
        help="Compare two explicitly selected manual measurements without assigning response",
    )
    compare_measurements.add_argument("baseline_packet", type=Path)
    compare_measurements.add_argument("followup_packet", type=Path)
    compare_measurements.add_argument("--baseline-id", required=True)
    compare_measurements.add_argument("--followup-id", required=True)
    compare_measurements.add_argument(
        "--lesion-label",
        help="Optional human-entered working label; does not prove lesion identity",
    )
    compare_measurements.add_argument("--output", "-o", type=Path)
    validate_comparison = commands.add_parser(
        "validate-comparison",
        help="Validate and privacy-minimize a local unreviewed comparison draft",
    )
    validate_comparison.add_argument("comparison", type=Path)

    assemble_comparison_review = commands.add_parser(
        "assemble-comparison-review",
        help="Bind a visit packet and exact numeric comparison into a local review archive",
    )
    assemble_comparison_review.add_argument("visit_packet", type=Path)
    assemble_comparison_review.add_argument("comparison", type=Path)
    assemble_comparison_review.add_argument("--output", "-o", type=Path, required=True)

    validate_comparison_review = commands.add_parser(
        "validate-comparison-review",
        help="Validate and privacy-minimize a local comparison review archive",
    )
    validate_comparison_review.add_argument("archive", type=Path)

    record_comparison_review = commands.add_parser(
        "record-comparison-review",
        help="Create a new hash-linked archive containing a self-attested human review",
    )
    record_comparison_review.add_argument("archive", type=Path)
    record_comparison_review.add_argument("--output", "-o", type=Path, required=True)
    record_comparison_review.add_argument("--reviewer-name", required=True)
    record_comparison_review.add_argument("--reviewer-role", required=True)
    record_comparison_review.add_argument("--organization")
    record_comparison_review.add_argument(
        "--decision",
        required=True,
        choices=["accepted_for_discussion", "amendment_requested", "rejected"],
    )
    record_comparison_review.add_argument(
        "--same-lesion",
        required=True,
        choices=["confirmed", "uncertain", "not_confirmed"],
    )
    record_comparison_review.add_argument(
        "--acquisition-suitability",
        required=True,
        choices=["suitable", "uncertain", "not_suitable"],
    )
    record_comparison_review.add_argument(
        "--measurement-placement",
        required=True,
        choices=["accepted", "uncertain", "revision_needed"],
    )
    record_comparison_review.add_argument(
        "--response-criteria",
        required=True,
        choices=["selected", "uncertain", "not_applicable"],
    )
    record_comparison_review.add_argument("--note", required=True)
    record_comparison_review.add_argument(
        "--attest",
        action="store_true",
        help="Acknowledge that the review and identity are self-asserted",
    )

    amend_review = commands.add_parser(
        "amend-comparison-review",
        help="Create a new hash-linked archive with an amended comparison",
    )
    amend_review.add_argument("archive", type=Path)
    amend_review.add_argument("comparison", type=Path)
    amend_review.add_argument("--output", "-o", type=Path, required=True)
    amend_review.add_argument("--actor-name", required=True)
    amend_review.add_argument("--actor-role", required=True)
    amend_review.add_argument("--organization")
    amend_review.add_argument("--reason", required=True)
    amend_review.add_argument(
        "--attest",
        action="store_true",
        help="Acknowledge that the amendment and identity are self-asserted",
    )

    registration_check = commands.add_parser(
        "registration-doctor",
        help="Inspect the required local Slicer/BRAINSFit engine and launcher hash",
    )
    registration_check.add_argument("--slicer", type=Path)

    run_registration = commands.add_parser(
        "run-rigid-registration",
        help="Create one non-overwriting local moving-to-fixed registration pending QA",
    )
    run_registration.add_argument("root", type=Path)
    run_registration.add_argument("--fixed-series", required=True)
    run_registration.add_argument("--moving-series", required=True)
    run_registration.add_argument("--output", "-o", type=Path, required=True)
    run_registration.add_argument("--slicer", type=Path)
    run_registration.add_argument(
        "--expected-slicer-sha256",
        required=True,
        help=(
            "Expected SHA-256 for the selected local Slicer launcher; this does not "
            "authenticate its distributor"
        ),
    )
    run_registration.add_argument(
        "--timeout-seconds",
        type=int,
        default=7200,
        help="Bounded local execution timeout (60-86400 seconds)",
    )
    run_registration.add_argument(
        "--attest-series-selection",
        action="store_true",
        help="Acknowledge that a person selected these exact series; this is not clinical approval",
    )

    validate_registration = commands.add_parser(
        "validate-registration",
        help="Validate a local rigid-registration directory and its QA locks",
    )
    validate_registration.add_argument("directory", type=Path)

    review_registration = commands.add_parser(
        "review-registration",
        help="Open a browser-capability human QA preview for one pending registration bundle",
    )
    review_registration.add_argument("directory", type=Path)
    review_registration.add_argument("--port", type=int, default=8765)
    review_registration.add_argument("--token")
    review_registration.add_argument("--no-open", action="store_true")
    review_registration.add_argument("--ui-dist", type=Path)

    record_registration_review = commands.add_parser(
        "record-registration-review",
        help="Create one non-overwriting, hash-bound self-attested registration QA JSON record",
    )
    record_registration_review.add_argument("directory", type=Path)
    record_registration_review.add_argument("request", type=Path)
    record_registration_review.add_argument("--output", "-o", type=Path, required=True)
    record_registration_review.add_argument("--previous-review", type=Path)

    import_review = commands.add_parser(
        "import-registration-review",
        help="Validate and seal a downloaded QA record as one owner-only local file",
    )
    import_review.add_argument("directory", type=Path)
    import_review.add_argument("downloaded_review", type=Path)
    import_review.add_argument("--output", "-o", type=Path, required=True)

    validate_registration_review = commands.add_parser(
        "validate-registration-review",
        help="Validate a registration QA record and optionally its live source bundle",
    )
    validate_registration_review.add_argument("record", type=Path)
    validate_registration_review.add_argument("--registration-bundle", type=Path)
    return root


def main() -> None:
    argument_parser = parser()
    args = argument_parser.parse_args()
    if (
        args.command in {"serve", "launch"}
        and args.registration_review is not None
        and args.registration_bundle is None
    ):
        argument_parser.error("--registration-review requires --registration-bundle")
    if args.command == "manifest":
        catalog, _ = build_catalog(
            args.root,
            include_hashes=not args.no_hashes,
            include_relative_paths=args.include_relative_paths,
            progress=lambda count: print(f"Indexed {count} files…", file=sys.stderr, flush=True),
        )
        _write_json(catalog, args.output)
    elif args.command == "candidates":
        catalog = json.loads(args.manifest.read_text())
        _write_json(suggest_pairs(catalog), args.output)
    elif args.command == "readiness":
        try:
            catalog = json.loads(args.manifest.read_text())
            report = build_longitudinal_readiness(catalog)
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as error:
            argument_parser.error(str(error))
        _write_json(report, args.output)
    elif args.command == "create-consultation-plan":
        try:
            catalog = load_strict_json(args.manifest.read_bytes())
            request = load_strict_json(args.request.read_bytes())
            plan = build_agent_consultation_plan(catalog, request)
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as error:
            argument_parser.error(str(error))
        _write_json(plan, args.output)
    elif args.command == "validate-consultation-plan":
        try:
            catalog = load_strict_json(args.manifest.read_bytes())
            plan = load_strict_json(args.plan.read_bytes())
        except (OSError, ValueError) as error:
            argument_parser.error(str(error))
        summary = agent_consultation_plan_summary(catalog, plan)
        _write_json(summary, None)
        if not summary["valid"]:
            raise SystemExit(1)
    elif args.command == "presentation-states":
        try:
            catalog, registry = build_catalog(
                args.root,
                include_hashes=True,
            )
            artifact = build_presentation_state_catalog(
                catalog,
                registry_source_loader(catalog, registry),
            )
        except (OSError, TypeError, ValueError) as error:
            argument_parser.error(str(error))
        _write_json(artifact, args.output)
    elif args.command == "validate-presentation-states":
        try:
            catalog, registry = build_catalog(args.root, include_hashes=True)
            loader = registry_source_loader(catalog, registry)
            artifact = load_strict_json(args.artifact.read_bytes())
        except (OSError, TypeError, ValueError) as error:
            argument_parser.error(str(error))
        summary = presentation_state_summary(catalog, loader, artifact)
        _write_json(summary, None)
        if not summary["valid"]:
            raise SystemExit(1)
    elif args.command == "serve":
        catalog, registry = build_catalog(args.root, include_hashes=not args.no_hashes)
        try:
            serve(
                catalog,
                registry,
                port=args.port,
                token=args.token,
                registration_bundle=args.registration_bundle,
                registration_review=args.registration_review,
                lesion_volume_comparison=args.lesion_volume_comparison,
                agent_audit_log=args.agent_audit_log,
                source_root=args.root,
            )
        except (OSError, ValueError) as error:
            argument_parser.error(str(error))
    elif args.command == "launch":
        try:
            ui_dist = _viewer_dist(args.ui_dist)
        except ValueError as error:
            argument_parser.error(str(error))
        catalog, registry = build_catalog(
            args.root,
            include_hashes=not args.no_hashes,
            progress=lambda count: count % 1000 == 0
            and print(f"Indexed {count} files…", file=sys.stderr, flush=True),
        )
        navigation_fragment = None
        requested_navigation = any(
            (
                args.baseline_series,
                args.baseline_instance,
                args.followup_series,
                args.followup_instance,
            )
        )
        if requested_navigation:
            if not args.baseline_series or not args.baseline_instance:
                argument_parser.error(
                    "launch navigation requires --baseline-series and --baseline-instance"
                )
            try:
                navigation_fragment = build_navigation_intent(
                    catalog,
                    baseline_series_id=args.baseline_series,
                    baseline_instance_id=args.baseline_instance,
                    followup_series_id=args.followup_series,
                    followup_instance_id=args.followup_instance,
                )["fragment"]
            except ValueError as error:
                argument_parser.error(str(error))
        try:
            serve(
                catalog,
                registry,
                port=args.port,
                token=args.token,
                ui_dist=ui_dist,
                open_browser=not args.no_open,
                navigation_fragment=navigation_fragment,
                registration_bundle=args.registration_bundle,
                registration_review=args.registration_review,
                lesion_volume_comparison=args.lesion_volume_comparison,
                agent_audit_log=args.agent_audit_log,
                source_root=args.root,
            )
        except (OSError, ValueError) as error:
            argument_parser.error(str(error))
    elif args.command == "viewer-link":
        try:
            catalog = json.loads(args.manifest.read_text())
            intent = build_navigation_intent(
                catalog,
                baseline_series_id=args.baseline_series,
                baseline_instance_id=args.baseline_instance,
                followup_series_id=args.followup_series,
                followup_instance_id=args.followup_instance,
                base_url=args.base_url,
            )
        except (OSError, ValueError) as error:
            argument_parser.error(str(error))
        _write_json(intent, args.output)
    elif args.command == "validate-measurements":
        packet = json.loads(args.packet.read_text())
        summary = measurement_packet_summary(packet)
        _write_json(summary, None)
        if not summary["valid"]:
            raise SystemExit(1)
    elif args.command == "validate-key-image":
        summary = key_image_archive_summary(args.archive)
        _write_json(summary, None)
        if not summary["valid"]:
            raise SystemExit(1)
    elif args.command == "validate-lesion-volume":
        summary = lesion_volume_archive_summary(args.archive, args.source_root)
        _write_json(summary, None)
        if not summary["valid"]:
            raise SystemExit(1)
    elif args.command == "validate-lesion-volume-review":
        summary = lesion_volume_review_summary(args.archive, args.source_root)
        _write_json(summary, None)
        if not summary["valid"]:
            raise SystemExit(1)
    elif args.command == "assemble-lesion-volume-comparison":
        try:
            summary = write_lesion_volume_comparison(
                args.baseline_review,
                args.followup_review,
                args.pairing_request,
                args.source_root,
                args.output,
            )
        except ValueError as error:
            argument_parser.error(str(error))
        _write_json(summary, None)
        if not summary["valid"]:
            raise SystemExit(1)
    elif args.command == "validate-lesion-volume-comparison":
        summary = lesion_volume_comparison_summary(args.archive, args.source_root)
        _write_json(summary, None)
        if not summary["valid"]:
            raise SystemExit(1)
    elif args.command == "verify-agent-audit":
        summary = agent_access_audit_summary(args.audit_log)
        _write_json(summary, None)
        if not summary["valid"]:
            raise SystemExit(1)
    elif args.command == "assemble-visit-packet":
        try:
            write_visit_packet(
                args.baseline_archive,
                args.followup_archive,
                args.output,
            )
        except ValueError as error:
            argument_parser.error(str(error))
        summary = visit_packet_summary(args.output)
        _write_json(summary, None)
        if not summary["valid"]:
            raise SystemExit(1)
    elif args.command == "validate-visit-packet":
        summary = visit_packet_summary(args.archive)
        _write_json(summary, None)
        if not summary["valid"]:
            raise SystemExit(1)
    elif args.command == "assemble-consultation-packet":
        try:
            write_consultation_packet(
                args.root,
                args.view_a_archive,
                args.view_b_archive,
                args.output,
            )
        except (OSError, ValueError) as error:
            argument_parser.error(str(error))
        summary = consultation_packet_summary(args.output)
        _write_json(summary, None)
        if not summary["valid"]:
            raise SystemExit(1)
    elif args.command == "validate-consultation-packet":
        summary = consultation_packet_summary(args.archive)
        _write_json(summary, None)
        if not summary["valid"]:
            raise SystemExit(1)
    elif args.command == "assemble-consultation-board":
        try:
            write_consultation_board(
                args.root,
                [(label, Path(archive)) for label, archive in args.item],
                args.output,
            )
        except (OSError, ValueError) as error:
            argument_parser.error(str(error))
        summary = consultation_board_summary(args.output)
        _write_json(summary, None)
        if not summary["valid"]:
            raise SystemExit(1)
    elif args.command == "validate-consultation-board":
        summary = consultation_board_summary(args.archive)
        _write_json(summary, None)
        if not summary["valid"]:
            raise SystemExit(1)
    elif args.command == "compare-measurements":
        baseline_packet = json.loads(args.baseline_packet.read_text())
        followup_packet = json.loads(args.followup_packet.read_text())
        try:
            comparison = build_measurement_comparison(
                baseline_packet,
                followup_packet,
                baseline_tracking_id=args.baseline_id,
                followup_tracking_id=args.followup_id,
                lesion_label=args.lesion_label,
            )
        except ValueError as error:
            argument_parser.error(str(error))
        _write_json(comparison, args.output)
    elif args.command == "validate-comparison":
        comparison = json.loads(args.comparison.read_text())
        summary = measurement_comparison_summary(comparison)
        _write_json(summary, None)
        if not summary["valid"]:
            raise SystemExit(1)
    elif args.command == "assemble-comparison-review":
        try:
            write_comparison_review(
                args.visit_packet,
                args.comparison,
                args.output,
            )
        except ValueError as error:
            argument_parser.error(str(error))
        summary = comparison_review_summary(args.output)
        _write_json(summary, None)
        if not summary["valid"]:
            raise SystemExit(1)
    elif args.command == "validate-comparison-review":
        summary = comparison_review_summary(args.archive)
        _write_json(summary, None)
        if not summary["valid"]:
            raise SystemExit(1)
    elif args.command == "record-comparison-review":
        try:
            append_comparison_review(
                args.archive,
                args.output,
                reviewer_name=args.reviewer_name,
                reviewer_role=args.reviewer_role,
                organization=args.organization,
                decision=args.decision,
                same_lesion_identity=args.same_lesion,
                acquisition_suitability=args.acquisition_suitability,
                measurement_placement=args.measurement_placement,
                response_criteria=args.response_criteria,
                note=args.note,
                attest=args.attest,
            )
        except ValueError as error:
            argument_parser.error(str(error))
        summary = comparison_review_summary(args.output)
        _write_json(summary, None)
        if not summary["valid"]:
            raise SystemExit(1)
    elif args.command == "amend-comparison-review":
        try:
            amend_comparison_review(
                args.archive,
                args.comparison,
                args.output,
                actor_name=args.actor_name,
                actor_role=args.actor_role,
                organization=args.organization,
                reason=args.reason,
                attest=args.attest,
            )
        except ValueError as error:
            argument_parser.error(str(error))
        summary = comparison_review_summary(args.output)
        _write_json(summary, None)
        if not summary["valid"]:
            raise SystemExit(1)
    elif args.command == "registration-doctor":
        _write_json(registration_doctor(args.slicer), None)
    elif args.command == "run-rigid-registration":
        catalog, registry = build_catalog(
            args.root,
            include_hashes=True,
            progress=lambda count: count % 1000 == 0
            and print(f"Indexed {count} files…", file=sys.stderr, flush=True),
        )
        try:
            run_rigid_registration(
                catalog,
                registry,
                source_root=args.root,
                fixed_series_id=args.fixed_series,
                moving_series_id=args.moving_series,
                output=args.output,
                slicer_executable=args.slicer,
                expected_slicer_sha256=args.expected_slicer_sha256,
                attest_series_selection=args.attest_series_selection,
                timeout_seconds=args.timeout_seconds,
            )
        except ValueError as error:
            argument_parser.error(str(error))
        summary = registration_bundle_summary(args.output)
        _write_json(summary, None)
        if not summary["valid"]:
            raise SystemExit(1)
    elif args.command == "validate-registration":
        summary = registration_bundle_summary(args.directory)
        _write_json(summary, None)
        if not summary["valid"]:
            raise SystemExit(1)
    elif args.command == "review-registration":
        try:
            ui_dist = _viewer_dist(args.ui_dist)
            serve(
                {
                    "schema_version": "1.0.0",
                    "source": {"dicom_instances": 0},
                    "studies": [],
                },
                {},
                port=args.port,
                token=args.token,
                ui_dist=ui_dist,
                open_browser=not args.no_open,
                registration_bundle=args.directory,
            )
        except ValueError as error:
            argument_parser.error(str(error))
    elif args.command == "record-registration-review":
        try:
            write_registration_review(
                args.directory,
                args.request,
                args.output,
                previous_review=args.previous_review,
            )
        except (OSError, ValueError) as error:
            argument_parser.error(str(error))
        summary = registration_review_summary(
            args.output,
            registration_directory=args.directory,
        )
        _write_json(summary, None)
        if not summary["valid"]:
            raise SystemExit(1)
    elif args.command == "import-registration-review":
        try:
            summary = import_registration_review(
                args.directory,
                args.downloaded_review,
                args.output,
            )
        except (OSError, ValueError) as error:
            argument_parser.error(str(error))
        _write_json(summary, None)
    elif args.command == "validate-registration-review":
        summary = registration_review_summary(
            args.record,
            registration_directory=args.registration_bundle,
        )
        _write_json(summary, None)
        if not summary["valid"]:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
