from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .catalog import build_catalog
from .comparison import suggest_pairs
from .key_images import key_image_archive_summary
from .measurements import build_measurement_comparison, measurement_packet_summary
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

    api = commands.add_parser("serve", help="Run the source-read-only loopback agent API")
    api.add_argument("root", type=Path)
    api.add_argument("--port", type=int, default=8765)
    api.add_argument("--token")
    api.add_argument("--no-hashes", action="store_true")

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

    compare_measurements = commands.add_parser(
        "compare-measurements",
        help="Compare two explicitly selected manual measurements without assigning response",
    )
    compare_measurements.add_argument("baseline_packet", type=Path)
    compare_measurements.add_argument("followup_packet", type=Path)
    compare_measurements.add_argument("--baseline-id", required=True)
    compare_measurements.add_argument("--followup-id", required=True)
    compare_measurements.add_argument("--output", "-o", type=Path)
    return root


def main() -> None:
    argument_parser = parser()
    args = argument_parser.parse_args()
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
    elif args.command == "serve":
        catalog, registry = build_catalog(args.root, include_hashes=not args.no_hashes)
        serve(catalog, registry, port=args.port, token=args.token)
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
        serve(
            catalog,
            registry,
            port=args.port,
            token=args.token,
            ui_dist=ui_dist,
            open_browser=not args.no_open,
        )
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
    elif args.command == "compare-measurements":
        baseline_packet = json.loads(args.baseline_packet.read_text())
        followup_packet = json.loads(args.followup_packet.read_text())
        try:
            comparison = build_measurement_comparison(
                baseline_packet,
                followup_packet,
                baseline_tracking_id=args.baseline_id,
                followup_tracking_id=args.followup_id,
            )
        except ValueError as error:
            argument_parser.error(str(error))
        _write_json(comparison, args.output)


if __name__ == "__main__":
    main()
