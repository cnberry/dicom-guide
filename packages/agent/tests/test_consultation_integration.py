from __future__ import annotations

import hashlib
import io
import json
import struct
import sys
import threading
import zipfile
import zlib
from http import HTTPStatus
from http.client import HTTPConnection
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import (
    CTImageStorage,
    ExplicitVRLittleEndian,
    MRImageStorage,
    generate_uid,
)

from scanview_agent.catalog import build_catalog
from scanview_agent.cli import main, parser
from scanview_agent.consultation_packets import (
    CONSULTATION_KEY_IMAGE_IMPLEMENTATION,
    CONSULTATION_KEY_IMAGE_LIMITATIONS,
    consultation_packet_archive_bytes,
    consultation_packet_summary,
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


def _write_dicom(path: Path, *, modality: str, date: str) -> None:
    sop_class = MRImageStorage if modality == "MR" else CTImageStorage
    sop_uid = generate_uid()
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = sop_class
    meta.MediaStorageSOPInstanceUID = sop_uid
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    dataset = FileDataset(path, {}, file_meta=meta, preamble=b"\0" * 128)
    dataset.SOPClassUID = sop_class
    dataset.SOPInstanceUID = sop_uid
    dataset.StudyInstanceUID = generate_uid()
    dataset.SeriesInstanceUID = generate_uid()
    dataset.FrameOfReferenceUID = generate_uid()
    dataset.PatientName = "SYNTHETIC^CONSULTATION"
    dataset.PatientID = "CONSULTATION-TEST"
    dataset.StudyDate = date
    dataset.SeriesDate = date
    dataset.Modality = modality
    dataset.SeriesDescription = f"Synthetic {modality} reference"
    dataset.ProtocolName = "Synthetic consultation fixture"
    dataset.BodyPartExamined = "BRAIN"
    dataset.ImageType = ["ORIGINAL", "PRIMARY"]
    dataset.InstanceNumber = 1
    dataset.Rows = 2
    dataset.Columns = 2
    dataset.PixelSpacing = [1.0, 1.0]
    dataset.SliceThickness = 1.0
    dataset.ImagePositionPatient = [0.0, 0.0, 1.0]
    dataset.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
    dataset.SamplesPerPixel = 1
    dataset.PhotometricInterpretation = "MONOCHROME2"
    dataset.BitsAllocated = 16
    dataset.BitsStored = 12
    dataset.HighBit = 11
    dataset.PixelRepresentation = 0
    dataset.PixelData = b"\0" * 8
    dataset.save_as(path, enforce_file_format=True)


def _source(series: dict, study_id: str) -> dict:
    instance = series["instances"][0]
    value = {
        "study_id": study_id,
        "series_id": series["id"],
        "instance_id": instance["id"],
        "patient_context_id": series["patient_context_id"],
        "modality": series["modality"],
        "acquisition_date": series["acquisition_date"],
        "series_description": series["series_description"],
        "instance_number": instance["instance_number"],
    }
    if series.get("frame_of_reference_id") is not None:
        value["frame_of_reference_id"] = series["frame_of_reference_id"]
    return value


def _write_consultation_key_image(path: Path, *, slot: str, source: dict) -> dict:
    measurements = {
        "schema_version": "3.0.0",
        "created_at": "2026-08-28T00:00:00Z",
        "review_status": "unreviewed",
        "measurements": [],
        "limitations": ["Synthetic empty measurement evidence."],
    }
    measurement_bytes = (json.dumps(measurements, indent=2) + "\n").encode()
    png_bytes = _one_pixel_png()
    packet = {
        "schema_version": "1.0.0",
        "created_at": "2026-08-28T00:00:00Z",
        "review_status": "unreviewed",
        "artifact_type": "derived_display_consultation_key_image",
        "source": source,
        "display": {
            "selection_slot": slot,
            "stack_position": 1,
            "stack_count": 1,
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
        "implementation": dict(CONSULTATION_KEY_IMAGE_IMPLEMENTATION),
        "limitations": list(CONSULTATION_KEY_IMAGE_LIMITATIONS),
    }
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("key-image.json", json.dumps(packet, indent=2) + "\n")
        archive.writestr("key-image.png", png_bytes)
        archive.writestr("measurements.json", measurement_bytes)
    return packet


def _fixture(tmp_path: Path) -> tuple[Path, dict, dict, Path, Path]:
    root = tmp_path / "dicom"
    root.mkdir()
    _write_dicom(root / "mr", modality="MR", date="20260101")
    _write_dicom(root / "ct", modality="CT", date="20260201")
    catalog, registry = build_catalog(root, include_hashes=True)
    by_modality: dict[str, tuple[str, dict]] = {}
    for study in catalog["studies"]:
        for series in study["series"]:
            by_modality[series["modality"]] = (study["id"], series)
    view_a = tmp_path / "view-a.zip"
    view_b = tmp_path / "view-b.zip"
    _write_consultation_key_image(
        view_a,
        slot="view_a",
        source=_source(by_modality["MR"][1], by_modality["MR"][0]),
    )
    _write_consultation_key_image(
        view_b,
        slot="view_b",
        source=_source(by_modality["CT"][1], by_modality["CT"][0]),
    )
    return root, catalog, registry, view_a, view_b


def _transport(view_a: Path, view_b: Path) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("view-a.zip", view_a.read_bytes())
        archive.writestr("view-b.zip", view_b.read_bytes())
    return output.getvalue()


def _post(
    port: int,
    body: bytes,
    *,
    headers: dict[str, str],
) -> tuple[int, dict[str, str], bytes]:
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    connection.request("POST", "/v1/consultation-packets", body=body, headers=headers)
    response = connection.getresponse()
    result = response.status, dict(response.getheaders()), response.read()
    connection.close()
    return result


def test_consultation_schemas_validate_generated_sidecars_and_packet(
    tmp_path: Path,
) -> None:
    _, catalog, registry, view_a, view_b = _fixture(tmp_path)
    archive_bytes = consultation_packet_archive_bytes(
        view_a,
        view_b,
        catalog,
        registry,
        created_at="2026-08-28T01:02:03Z",
    )
    assert consultation_packet_summary(io.BytesIO(archive_bytes))["valid"] is True

    schema_root = Path(__file__).parents[3] / "schemas"
    key_schema = json.loads(
        (schema_root / "scanview-consultation-key-image-v1.schema.json").read_text()
    )
    packet_schema = json.loads(
        (
            schema_root
            / "scanview-clinician-consultation-packet-v1.schema.json"
        ).read_text()
    )
    Draft202012Validator.check_schema(key_schema)
    Draft202012Validator.check_schema(packet_schema)
    with zipfile.ZipFile(view_a) as archive:
        key_packet = json.loads(archive.read("key-image.json"))
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        packet = json.loads(archive.read("consultation-packet.json"))
    assert packet["relationship"]["distinct_source_studies"] is True
    Draft202012Validator(
        key_schema, format_checker=FormatChecker()
    ).validate(key_packet)
    Draft202012Validator(
        packet_schema, format_checker=FormatChecker()
    ).validate(packet)

    key_packet["display"]["selection_slot"] = "baseline"
    with pytest.raises(ValidationError):
        Draft202012Validator(key_schema).validate(key_packet)
    packet["candidate_interpretations"] = [{"text": "unsafe"}]
    with pytest.raises(ValidationError):
        Draft202012Validator(packet_schema).validate(packet)


def test_consultation_cli_assembles_and_validates_live_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root, _, _, view_a, view_b = _fixture(tmp_path)
    output = tmp_path / "consultation.zip"
    parsed = parser().parse_args(
        [
            "assemble-consultation-packet",
            str(root),
            str(view_a),
            str(view_b),
            "--output",
            str(output),
        ]
    )
    assert parsed.command == "assemble-consultation-packet"
    assert parsed.root == root

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "scanview-agent",
            "assemble-consultation-packet",
            str(root),
            str(view_a),
            str(view_b),
            "--output",
            str(output),
        ],
    )
    main()
    assembled = json.loads(capsys.readouterr().out)
    assert assembled["valid"] is True
    assert assembled["modality_relationship"] == "cross_modality"

    monkeypatch.setattr(
        sys,
        "argv",
        ["scanview-agent", "validate-consultation-packet", str(output)],
    )
    main()
    validated = json.loads(capsys.readouterr().out)
    assert validated["valid"] is True
    assert validated["longitudinal_comparison_authorized"] is False
    assert validated["response_assessment_authorized"] is False


def test_consultation_endpoint_enforces_auth_origin_media_type_and_live_sources(
    tmp_path: Path,
) -> None:
    _, catalog, registry, view_a, view_b = _fixture(tmp_path)
    transport = _transport(view_a, view_b)
    server = create_server(
        catalog,
        registry,
        port=0,
        token="consultation-session-token",
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_port
    base_headers = {
        "Authorization": "Bearer consultation-session-token",
        "Origin": f"http://127.0.0.1:{port}",
        "Content-Type": "application/vnd.scanview.consultation-input+zip",
        "Accept": "application/zip",
    }
    try:
        status, _, body = _post(
            port,
            transport,
            headers={
                "Origin": f"http://127.0.0.1:{port}",
                "Content-Type": "application/vnd.scanview.consultation-input+zip",
            },
        )
        assert status == HTTPStatus.UNAUTHORIZED
        assert json.loads(body) == {"error": "unauthorized"}

        status, _, body = _post(
            port,
            transport,
            headers={**base_headers, "Origin": "http://example.invalid"},
        )
        assert status == HTTPStatus.FORBIDDEN
        assert json.loads(body) == {"error": "same_origin_required"}

        status, _, body = _post(
            port,
            transport,
            headers={**base_headers, "Content-Type": "application/zip"},
        )
        assert status == HTTPStatus.UNSUPPORTED_MEDIA_TYPE
        assert json.loads(body) == {"error": "unsupported_media_type"}

        status, headers, body = _post(port, transport, headers=base_headers)
        assert status == HTTPStatus.OK
        assert headers["Content-Type"] == "application/zip"
        assert headers["Cache-Control"] == "no-store"
        assert headers["Content-Disposition"].startswith(
            'attachment; filename="scanview-consultation-packet-'
        )
        assert consultation_packet_summary(io.BytesIO(body))["valid"] is True

        status, _, body = _post(port, b"not a zip", headers=base_headers)
        assert status == HTTPStatus.UNPROCESSABLE_ENTITY
        error = json.loads(body)
        assert error["error"] == "invalid_consultation_packet_input"
        assert "could not be read" in error["detail"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
