from __future__ import annotations

import hashlib
import io
import json
import stat
import struct
import sys
import threading
import zipfile
import zlib
from http import HTTPStatus
from http.client import HTTPConnection
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from dicom_guide.cli import main
from dicom_guide.comparison_reviews import (
    EXPECTED_FILES,
    amend_comparison_review,
    append_comparison_review,
    comparison_review_from_transport,
    comparison_review_summary,
    write_comparison_review,
)
from dicom_guide.measurements import build_measurement_comparison
from dicom_guide.server import create_server
from dicom_guide.visit_packets import write_visit_packet


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + chunk_type
        + data
        + struct.pack(">I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)
    )


def _one_pixel_png() -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        + _png_chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00"))
        + _png_chunk(b"IEND", b"")
    )


def _measurement_packet(
    *,
    tracking_id: str,
    series_id: str,
    instance_id: str,
    long_axis: float,
    short_axis: float,
) -> dict:
    return {
        "schema_version": "3.0.0",
        "created_at": "2026-08-28T00:00:00Z",
        "review_status": "unreviewed",
        "measurements": [
            {
                "tracking_id": tracking_id,
                "type": "bidirectional",
                "review_status": "unreviewed",
                "source": {
                    "series_id": series_id,
                    "instance_id": instance_id,
                },
                "geometry": {
                    "coordinate_system": "DICOM patient LPS",
                    "world_points": [
                        [0, 0, 0],
                        [long_axis, 0, 0],
                        [0, 0, 0],
                        [0, short_axis, 0],
                    ],
                },
                "result": {
                    "long_axis": long_axis,
                    "short_axis": short_axis,
                    "product": long_axis * short_axis,
                    "unit": "mm",
                    "product_unit": "mm2",
                },
                "method": {
                    "name": "manual_perpendicular_bidirectional",
                    "implementation": "Cornerstone3D BidirectionalTool",
                },
                "limitations": ["Synthetic manual measurement for local testing."],
            }
        ],
        "limitations": ["Synthetic unreviewed measurement evidence."],
    }


def _write_key_image(
    path: Path,
    *,
    role: str,
    study_id: str,
    patient_context_id: str,
    acquisition_date: str,
    measurement_packet: dict,
) -> None:
    measurement = measurement_packet["measurements"][0]
    measurement_bytes = (json.dumps(measurement_packet, indent=2) + "\n").encode()
    png_bytes = _one_pixel_png()
    packet = {
        "schema_version": "2.0.0",
        "created_at": "2026-08-28T00:00:00Z",
        "review_status": "unreviewed",
        "artifact_type": "derived_display_key_image",
        "source": {
            "study_id": study_id,
            "series_id": measurement["source"]["series_id"],
            "instance_id": measurement["source"]["instance_id"],
            "patient_context_id": patient_context_id,
            "modality": "MR",
            "acquisition_date": acquisition_date,
            "series_description": "Synthetic axial post-contrast",
            "instance_number": 2,
        },
        "display": {
            "viewport_role": role,
            "stack_position": 2,
            "stack_count": 3,
            "source_kind": "loopback-service",
            "viewport_width_px": 512,
            "viewport_height_px": 512,
            "patient_orientation": {
                "left": "R",
                "right": "L",
                "top": "A",
                "bottom": "P",
            },
            "presentation": {
                "voi_range": {"lower": 0, "upper": 1000},
                "invert": False,
                "zoom": 1,
                "pan": [0, 0],
            },
        },
        "image": {
            "filename": "key-image.png",
            "mime_type": "image/png",
            "width_px": 1,
            "height_px": 1,
            "sha256": hashlib.sha256(png_bytes).hexdigest(),
        },
        "measurement_evidence": {
            "filename": "measurements.json",
            "schema_version": "3.0.0",
            "measurement_count": 1,
            "tracking_ids": [measurement["tracking_id"]],
            "sha256": hashlib.sha256(measurement_bytes).hexdigest(),
        },
        "implementation": {
            "name": "DICOM Guide key-image exporter",
            "version": "0.2.0",
            "renderer": "Cornerstone3D 5.8.2",
        },
        "limitations": ["Synthetic unreviewed display derivative."],
    }
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("key-image.json", json.dumps(packet, indent=2) + "\n")
        archive.writestr("key-image.png", png_bytes)
        archive.writestr("measurements.json", measurement_bytes)


def _sources(tmp_path: Path) -> tuple[Path, Path, dict, dict, dict]:
    baseline_packet = _measurement_packet(
        tracking_id="bidirectional:baseline",
        series_id="0123456789abcdef",
        instance_id="fedcba9876543210",
        long_axis=10,
        short_axis=4,
    )
    followup_packet = _measurement_packet(
        tracking_id="bidirectional:followup",
        series_id="1123456789abcdef",
        instance_id="0011223344556677",
        long_axis=8,
        short_axis=3,
    )
    baseline = tmp_path / "baseline.zip"
    followup = tmp_path / "followup.zip"
    _write_key_image(
        baseline,
        role="baseline",
        study_id="abcdef0123456789",
        patient_context_id="1234567890abcdef",
        acquisition_date="20260101",
        measurement_packet=baseline_packet,
    )
    _write_key_image(
        followup,
        role="followup",
        study_id="bbcdef0123456789",
        patient_context_id="1234567890abcdef",
        acquisition_date="20260201",
        measurement_packet=followup_packet,
    )
    visit_path = tmp_path / "visit.zip"
    write_visit_packet(
        baseline,
        followup,
        visit_path,
        created_at="2026-08-28T00:30:00Z",
    )
    comparison = build_measurement_comparison(
        baseline_packet,
        followup_packet,
        baseline_tracking_id="bidirectional:baseline",
        followup_tracking_id="bidirectional:followup",
        lesion_label="Target lesion A",
    )
    comparison["created_at"] = "2026-08-28T00:45:00Z"
    comparison_path = tmp_path / "comparison.json"
    comparison_path.write_text(json.dumps(comparison, indent=2) + "\n")
    return visit_path, comparison_path, baseline_packet, followup_packet, comparison


def _transport(tmp_path: Path, comparison_path: Path, *, extra: bool = False) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("baseline.zip", (tmp_path / "baseline.zip").read_bytes())
        archive.writestr("followup.zip", (tmp_path / "followup.zip").read_bytes())
        archive.writestr("comparison.json", comparison_path.read_bytes())
        if extra:
            archive.writestr("unexpected.txt", b"unsupported")
    return output.getvalue()


def test_review_packet_binds_visual_and_numeric_evidence_with_static_schema_valid_output(
    tmp_path: Path,
) -> None:
    visit_path, comparison_path, _, _, _ = _sources(tmp_path)
    output = tmp_path / "review.zip"

    record = write_comparison_review(
        visit_path,
        comparison_path,
        output,
        created_at="2026-08-28T01:00:00Z",
    )
    summary = comparison_review_summary(output)

    assert summary == {
        "valid": True,
        "schema_version": "1.0.0",
        "review_status": "unreviewed",
        "artifact_type": "comparison_review_record",
        "event_count": 1,
        "latest_event_type": "submitted_for_review",
        "modality": "MR",
        "parent_archive_link_present": False,
        "file_integrity": True,
        "source_integrity": True,
        "linkage_integrity": True,
        "event_integrity": True,
        "presentation_integrity": True,
        "errors": [],
    }
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    with zipfile.ZipFile(output) as archive:
        assert set(archive.namelist()) == EXPECTED_FILES
        review_html = archive.read("review.html").decode()
        assert "NO RESPONSE CONCLUSION GENERATED BY DICOM_GUIDE" in review_html
        assert "SELF-ATTESTED IDENTITY IS NOT CRYPTOGRAPHICALLY VERIFIED" in review_html
        assert "10.0 mm" in review_html
        assert "8.0 mm" in review_html
        assert "<script" not in review_html
        assert "https://" not in review_html
        assert "http://" not in review_html

    repository_root = Path(__file__).parents[3]
    schema = json.loads(
        (repository_root / "schemas" / "dicom-guide-comparison-review-v1.schema.json").read_text()
    )
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(record)
    with pytest.raises(ValueError, match="later than both source artifacts"):
        write_comparison_review(
            visit_path,
            comparison_path,
            tmp_path / "predated-review.zip",
            created_at="2026-08-28T00:40:00Z",
        )


def test_three_member_transport_assembles_review_entirely_in_memory(tmp_path: Path) -> None:
    _, comparison_path, _, _, _ = _sources(tmp_path)
    before = {path.name for path in tmp_path.iterdir()}

    archive_bytes = comparison_review_from_transport(
        _transport(tmp_path, comparison_path),
        visit_created_at="2026-08-28T01:00:00Z",
        review_created_at="2026-08-28T01:01:00Z",
    )
    summary = comparison_review_summary(io.BytesIO(archive_bytes))

    assert summary["valid"] is True
    assert summary["event_count"] == 1
    assert {path.name for path in tmp_path.iterdir()} == before
    with pytest.raises(ValueError, match="exactly baseline.zip"):
        comparison_review_from_transport(_transport(tmp_path, comparison_path, extra=True))


def test_same_origin_review_endpoint_returns_no_store_archive_without_server_file(
    tmp_path: Path,
) -> None:
    _, comparison_path, _, _, _ = _sources(tmp_path)
    transport = _transport(tmp_path, comparison_path)
    before = {path.name for path in tmp_path.iterdir()}
    server = create_server(
        {"schema_version": "1.0.0", "studies": []},
        {},
        port=0,
        token="test-session-token",
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_port
    headers = {
        "Authorization": "Bearer test-session-token",
        "Origin": f"http://127.0.0.1:{port}",
        "Content-Type": "application/vnd.dicom-guide.comparison-review-input+zip",
        "Accept": "application/zip",
    }
    try:
        connection = HTTPConnection("127.0.0.1", port, timeout=5)
        connection.request(
            "POST", "/v1/comparison-reviews", body=transport, headers=headers
        )
        response = connection.getresponse()
        body = response.read()
        response_headers = dict(response.getheaders())
        connection.close()

        assert response.status == HTTPStatus.OK
        assert response_headers["Content-Type"] == "application/zip"
        assert response_headers["Cache-Control"] == "no-store"
        assert response_headers["Content-Disposition"].startswith(
            'attachment; filename="dicom-guide-comparison-review-'
        )
        assert comparison_review_summary(io.BytesIO(body))["valid"] is True
        assert {path.name for path in tmp_path.iterdir()} == before

        connection = HTTPConnection("127.0.0.1", port, timeout=5)
        connection.request(
            "POST",
            "/v1/comparison-reviews",
            body=transport,
            headers={**headers, "Origin": "http://example.invalid"},
        )
        forbidden = connection.getresponse()
        forbidden.read()
        connection.close()
        assert forbidden.status == HTTPStatus.FORBIDDEN
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_review_requires_exact_visible_source_measurement_join(tmp_path: Path) -> None:
    visit_path, _, baseline_packet, followup_packet, _ = _sources(tmp_path)
    mismatched = json.loads(json.dumps(followup_packet))
    mismatched["measurements"][0]["source"]["instance_id"] = "1111222233334444"
    comparison = build_measurement_comparison(
        baseline_packet,
        mismatched,
        baseline_tracking_id="bidirectional:baseline",
        followup_tracking_id="bidirectional:followup",
        lesion_label="Target lesion A",
    )
    comparison_path = tmp_path / "mismatched.json"
    comparison_path.write_text(json.dumps(comparison))

    with pytest.raises(ValueError, match="source disagrees"):
        write_comparison_review(visit_path, comparison_path, tmp_path / "unsafe.zip")


def test_self_attested_review_is_hash_linked_privacy_minimized_and_non_overwriting(
    tmp_path: Path,
) -> None:
    visit_path, comparison_path, _, _, _ = _sources(tmp_path)
    initial = tmp_path / "review-initial.zip"
    reviewed = tmp_path / "reviewed.zip"
    write_comparison_review(
        visit_path,
        comparison_path,
        initial,
        created_at="2026-08-28T01:00:00Z",
    )
    with pytest.raises(ValueError, match="--attest"):
        append_comparison_review(
            initial,
            reviewed,
            reviewer_name="Synthetic Reviewer",
            reviewer_role="Neurosurgeon",
            organization=None,
            decision="accepted_for_discussion",
            same_lesion_identity="confirmed",
            acquisition_suitability="suitable",
            measurement_placement="accepted",
            response_criteria="uncertain",
            note="This must not be recorded without attestation.",
            attest=False,
            created_at="2026-08-28T02:00:00Z",
        )

    record = append_comparison_review(
        initial,
        reviewed,
        reviewer_name="Synthetic Reviewer",
        reviewer_role="Neurosurgeon",
        organization="Example Hospital",
        decision="accepted_for_discussion",
        same_lesion_identity="confirmed",
        acquisition_suitability="suitable",
        measurement_placement="accepted",
        response_criteria="uncertain",
        note='Reviewed for discussion; literal <script>alert("test")</script> text must be escaped.',
        attest=True,
        created_at="2026-08-28T02:00:00Z",
    )
    summary = comparison_review_summary(reviewed)

    assert summary["valid"] is True
    assert summary["review_status"] == "accepted_for_discussion"
    assert summary["event_count"] == 2
    assert summary["latest_event_type"] == "clinician_review"
    assert summary["parent_archive_link_present"] is True
    assert record["parent_archive_sha256"] == hashlib.sha256(initial.read_bytes()).hexdigest()
    assert "Synthetic Reviewer" not in json.dumps(summary)
    assert "Neurosurgeon" not in json.dumps(summary)
    assert initial.is_file() and reviewed.is_file()
    with zipfile.ZipFile(reviewed) as archive:
        review_html = archive.read("review.html").decode()
        assert "Synthetic Reviewer" in review_html
        assert "self asserted unverified" in review_html
        assert "Person-entered note" in review_html
        assert "&lt;script&gt;" in review_html
        assert "<script" not in review_html
    with pytest.raises(ValueError, match="already exists"):
        append_comparison_review(
            initial,
            reviewed,
            reviewer_name="Synthetic Reviewer",
            reviewer_role="Neurosurgeon",
            organization=None,
            decision="rejected",
            same_lesion_identity="uncertain",
            acquisition_suitability="uncertain",
            measurement_placement="uncertain",
            response_criteria="uncertain",
            note="Duplicate output must fail.",
            attest=True,
            created_at="2026-08-28T03:00:00Z",
        )


def test_amendment_creates_new_parent_link_and_resets_review_state(tmp_path: Path) -> None:
    visit_path, comparison_path, baseline_packet, followup_packet, _ = _sources(tmp_path)
    initial = tmp_path / "initial.zip"
    requested = tmp_path / "amendment-requested.zip"
    amended = tmp_path / "amended.zip"
    write_comparison_review(
        visit_path,
        comparison_path,
        initial,
        created_at="2026-08-28T01:00:00Z",
    )
    append_comparison_review(
        initial,
        requested,
        reviewer_name="Synthetic Reviewer",
        reviewer_role="Neurosurgeon",
        organization=None,
        decision="amendment_requested",
        same_lesion_identity="uncertain",
        acquisition_suitability="suitable",
        measurement_placement="revision_needed",
        response_criteria="uncertain",
        note="Use a clearer working lesion label.",
        attest=True,
        created_at="2026-08-28T02:00:00Z",
    )
    new_comparison = build_measurement_comparison(
        baseline_packet,
        followup_packet,
        baseline_tracking_id="bidirectional:baseline",
        followup_tracking_id="bidirectional:followup",
        lesion_label="Target lesion A — enhancing component",
    )
    new_comparison["created_at"] = "2026-08-28T02:30:00Z"
    amended_comparison = tmp_path / "comparison-amended.json"
    amended_comparison.write_text(json.dumps(new_comparison, indent=2) + "\n")

    with pytest.raises(ValueError, match="later than the amended comparison"):
        amend_comparison_review(
            requested,
            amended_comparison,
            tmp_path / "predated-amendment.zip",
            actor_name="Synthetic Coordinator",
            actor_role="Care coordinator",
            organization=None,
            reason="This event time is intentionally invalid.",
            attest=True,
            created_at="2026-08-28T02:15:00Z",
        )

    record = amend_comparison_review(
        requested,
        amended_comparison,
        amended,
        actor_name="Synthetic Coordinator",
        actor_role="Care coordinator",
        organization=None,
        reason="Applied the requested working-label clarification; geometry is unchanged.",
        attest=True,
        created_at="2026-08-28T03:00:00Z",
    )
    summary = comparison_review_summary(amended)

    assert summary["valid"] is True
    assert summary["review_status"] == "unreviewed"
    assert summary["event_count"] == 3
    assert summary["latest_event_type"] == "comparison_amended"
    assert record["parent_archive_sha256"] == hashlib.sha256(requested.read_bytes()).hexdigest()
    repository_root = Path(__file__).parents[3]
    schema = json.loads(
        (repository_root / "schemas" / "dicom-guide-comparison-review-v1.schema.json").read_text()
    )
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(record)
    with zipfile.ZipFile(amended) as archive:
        embedded = json.loads(archive.read("comparison.json"))
        assert embedded["pairing"]["lesion_label"] == "Target lesion A — enhancing component"
        assert "Target lesion A — enhancing component" in archive.read("review.html").decode()


def test_review_validation_detects_payload_and_event_tampering(tmp_path: Path) -> None:
    visit_path, comparison_path, _, _, _ = _sources(tmp_path)
    output = tmp_path / "review.zip"
    write_comparison_review(
        visit_path,
        comparison_path,
        output,
        created_at="2026-08-28T01:00:00Z",
    )
    with zipfile.ZipFile(output) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    record = json.loads(files["review-record.json"])
    record["events"][0]["note"] = "Tampered note"
    files["review-record.json"] = (json.dumps(record, indent=2) + "\n").encode()
    files["review.html"] += b"tampered"
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)

    summary = comparison_review_summary(output)

    assert summary["valid"] is False
    assert summary["event_integrity"] is False
    assert summary["file_integrity"] is False
    assert summary["presentation_integrity"] is False
    assert "event_sha256" in " ".join(summary["errors"])


def test_comparison_review_cli_assembles_and_validates_privately(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    visit_path, comparison_path, _, _, _ = _sources(tmp_path)
    output = tmp_path / "review-cli.zip"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "dicom-guide",
            "assemble-comparison-review",
            str(visit_path),
            str(comparison_path),
            "--output",
            str(output),
        ],
    )

    main()

    summary = json.loads(capsys.readouterr().out)
    assert summary["valid"] is True
    assert "Target lesion A" not in json.dumps(summary)
    assert stat.S_IMODE(output.stat().st_mode) == 0o600

    reviewed = tmp_path / "reviewed-cli.zip"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "dicom-guide",
            "record-comparison-review",
            str(output),
            "--output",
            str(reviewed),
            "--reviewer-name",
            "Synthetic Reviewer",
            "--reviewer-role",
            "Neurosurgeon",
            "--decision",
            "amendment_requested",
            "--same-lesion",
            "uncertain",
            "--acquisition-suitability",
            "suitable",
            "--measurement-placement",
            "revision_needed",
            "--response-criteria",
            "uncertain",
            "--note",
            "Clarify the working lesion component.",
            "--attest",
        ],
    )

    main()

    reviewed_summary = json.loads(capsys.readouterr().out)
    assert reviewed_summary["valid"] is True
    assert reviewed_summary["review_status"] == "amendment_requested"
    assert "Synthetic Reviewer" not in json.dumps(reviewed_summary)
