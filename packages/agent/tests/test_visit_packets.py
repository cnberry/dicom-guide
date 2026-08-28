from __future__ import annotations

import hashlib
import io
import json
import stat
import struct
import threading
import zipfile
import zlib
from http import HTTPStatus
from http.client import HTTPConnection
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from scanview_agent.visit_packets import (
    EXPECTED_FILES,
    build_visit_packet,
    visit_packet_from_transport,
    visit_packet_summary,
    write_visit_packet,
)
from scanview_agent.server import create_server


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


def _write_key_image(
    path: Path,
    *,
    role: str,
    study_id: str,
    series_id: str,
    instance_id: str,
    patient_context_id: str,
    acquisition_date: str,
    modality: str = "MR",
) -> None:
    measurement_packet = {
        "schema_version": "3.0.0",
        "created_at": "2026-08-28T00:00:00Z",
        "review_status": "unreviewed",
        "measurements": [],
        "limitations": ["Synthetic empty measurement evidence."],
    }
    measurement_bytes = (json.dumps(measurement_packet, indent=2) + "\n").encode()
    png_bytes = _one_pixel_png()
    packet = {
        "schema_version": "2.0.0",
        "created_at": "2026-08-28T00:00:00Z",
        "review_status": "unreviewed",
        "artifact_type": "derived_display_key_image",
        "source": {
            "study_id": study_id,
            "series_id": series_id,
            "instance_id": instance_id,
            "patient_context_id": patient_context_id,
            "modality": modality,
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
            "measurement_count": 0,
            "tracking_ids": [],
            "sha256": hashlib.sha256(measurement_bytes).hexdigest(),
        },
        "implementation": {
            "name": "ScanView key-image exporter",
            "version": "0.2.0",
            "renderer": "Cornerstone3D 5.8.2",
        },
        "limitations": ["Synthetic unreviewed display derivative."],
    }
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("key-image.json", json.dumps(packet, indent=2) + "\n")
        archive.writestr("key-image.png", png_bytes)
        archive.writestr("measurements.json", measurement_bytes)


def _pair(tmp_path: Path, **followup_overrides: str) -> tuple[Path, Path]:
    baseline = tmp_path / "baseline.zip"
    followup = tmp_path / "followup.zip"
    _write_key_image(
        baseline,
        role="baseline",
        study_id="abcdef0123456789",
        series_id="0123456789abcdef",
        instance_id="fedcba9876543210",
        patient_context_id="1234567890abcdef",
        acquisition_date="20260101",
    )
    followup_values = {
        "role": "followup",
        "study_id": "bbcdef0123456789",
        "series_id": "1123456789abcdef",
        "instance_id": "0011223344556677",
        "patient_context_id": "1234567890abcdef",
        "acquisition_date": "20260201",
        "modality": "MR",
    }
    followup_values.update(followup_overrides)
    _write_key_image(followup, **followup_values)
    return baseline, followup


def _transport(baseline: Path, followup: Path) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("baseline.zip", baseline.read_bytes())
        archive.writestr("followup.zip", followup.read_bytes())
    return output.getvalue()


def test_visit_packet_round_trip_is_static_source_linked_and_schema_valid(
    tmp_path: Path,
) -> None:
    baseline, followup = _pair(tmp_path)
    output = tmp_path / "visit-packet.zip"

    packet = write_visit_packet(
        baseline,
        followup,
        output,
        created_at="2026-08-28T01:02:03Z",
    )
    summary = visit_packet_summary(output)

    assert summary == {
        "valid": True,
        "schema_version": "1.0.0",
        "review_status": "unreviewed",
        "artifact_type": "clinician_visit_packet",
        "modality": "MR",
        "elapsed_days": 31,
        "measurement_counts": {"baseline": 0, "followup": 0},
        "file_integrity": True,
        "component_integrity": True,
        "presentation_integrity": True,
        "errors": [],
    }
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    with zipfile.ZipFile(output) as archive:
        assert set(archive.namelist()) == EXPECTED_FILES
        review_html = archive.read("review.html").decode()
        assert "NO RESPONSE CONCLUSION GENERATED" in review_html
        assert "not registered or spatially aligned" in review_html
        assert "<script" not in review_html
        assert "https://" not in review_html
        assert "http://" not in review_html

    repository_root = Path(__file__).parents[3]
    schema = json.loads(
        (
            repository_root
            / "schemas"
            / "scanview-clinician-visit-packet-v1.schema.json"
        ).read_text()
    )
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(packet)
    key_image_schema = json.loads(
        (repository_root / "schemas" / "scanview-key-image-v2.schema.json").read_text()
    )
    with zipfile.ZipFile(baseline) as archive:
        baseline_packet = json.loads(archive.read("key-image.json"))
    Draft202012Validator.check_schema(key_image_schema)
    Draft202012Validator(
        key_image_schema, format_checker=FormatChecker()
    ).validate(baseline_packet)


def test_visit_packet_transport_assembles_and_validates_without_filesystem_output(
    tmp_path: Path,
) -> None:
    baseline, followup = _pair(tmp_path)

    archive_bytes = visit_packet_from_transport(
        _transport(baseline, followup), created_at="2026-08-28T01:02:03Z"
    )
    summary = visit_packet_summary(io.BytesIO(archive_bytes))

    assert summary["valid"] is True
    assert summary["elapsed_days"] == 31
    assert {path.name for path in tmp_path.iterdir()} == {"baseline.zip", "followup.zip"}


def test_authenticated_same_origin_loopback_endpoint_returns_valid_packet_in_memory(
    tmp_path: Path,
) -> None:
    baseline, followup = _pair(tmp_path)
    transport = _transport(baseline, followup)
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
        "Content-Type": "application/vnd.scanview.visit-input+zip",
        "Accept": "application/zip",
    }
    try:
        connection = HTTPConnection("127.0.0.1", port, timeout=5)
        connection.request("POST", "/v1/visit-packets", body=transport, headers=headers)
        response = connection.getresponse()
        body = response.read()
        response_headers = dict(response.getheaders())
        connection.close()

        assert response.status == HTTPStatus.OK
        assert response_headers["Content-Type"] == "application/zip"
        assert response_headers["Cache-Control"] == "no-store"
        assert response_headers["Content-Disposition"].endswith('.zip"')
        assert visit_packet_summary(io.BytesIO(body))["valid"] is True
        assert {path.name for path in tmp_path.iterdir()} == {"baseline.zip", "followup.zip"}

        connection = HTTPConnection("127.0.0.1", port, timeout=5)
        connection.request(
            "POST",
            "/v1/visit-packets",
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


def test_visit_packet_transport_rejects_extra_or_malformed_members(tmp_path: Path) -> None:
    baseline, followup = _pair(tmp_path)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("baseline.zip", baseline.read_bytes())
        archive.writestr("followup.zip", followup.read_bytes())
        archive.writestr("unexpected.txt", b"not allowed")

    with pytest.raises(ValueError, match="exactly baseline.zip and followup.zip"):
        visit_packet_from_transport(output.getvalue())

    with pytest.raises(ValueError, match="could not be read"):
        visit_packet_from_transport(b"not a ZIP archive")


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"modality": "CT"}, "same MR or CT modality"),
        ({"patient_context_id": "2234567890abcdef"}, "matching opaque patient context"),
        ({"study_id": "abcdef0123456789"}, "distinct source studies"),
        ({"series_id": "0123456789abcdef"}, "distinct source series"),
        ({"acquisition_date": "20260101"}, "must precede"),
        ({"role": "baseline"}, "wrong viewport role"),
    ],
)
def test_visit_packet_refuses_unsafe_longitudinal_pairs(
    tmp_path: Path, overrides: dict[str, str], message: str
) -> None:
    baseline, followup = _pair(tmp_path, **overrides)

    with pytest.raises(ValueError, match=message):
        build_visit_packet(baseline, followup)


def test_visit_packet_detects_a_tampered_human_review_page(tmp_path: Path) -> None:
    baseline, followup = _pair(tmp_path)
    output = tmp_path / "visit-packet.zip"
    write_visit_packet(baseline, followup, output)

    with zipfile.ZipFile(output) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    files["review.html"] += b"tampered"
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)

    summary = visit_packet_summary(output)

    assert summary["valid"] is False
    assert summary["file_integrity"] is False
    assert summary["presentation_integrity"] is False
    assert "payload digests" in " ".join(summary["errors"])


def test_visit_packet_refuses_valid_legacy_key_image_without_patient_context(
    tmp_path: Path,
) -> None:
    baseline, followup = _pair(tmp_path)
    with zipfile.ZipFile(baseline) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    packet = json.loads(files["key-image.json"])
    packet["schema_version"] = "1.0.0"
    packet["source"].pop("study_id")
    packet["source"].pop("patient_context_id")
    packet["implementation"]["version"] = "0.1.0"
    files["key-image.json"] = (json.dumps(packet, indent=2) + "\n").encode()
    with zipfile.ZipFile(baseline, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)

    with pytest.raises(ValueError, match="key-image v2 patient/study context"):
        build_visit_packet(baseline, followup)
