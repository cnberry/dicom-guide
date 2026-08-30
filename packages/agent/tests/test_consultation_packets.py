from __future__ import annotations

import hashlib
import io
import json
import stat
import struct
import zipfile
import zlib
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError

from dicom_guide import consultation_boards as boards
from dicom_guide import consultation_packets as consultation


CREATED_AT = "2026-08-28T01:02:03Z"
PATIENT_CONTEXT_ID = "1234567890abcdef"


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


def _source(
    slot: str,
    *,
    patient_context_id: str = PATIENT_CONTEXT_ID,
    modality: str | None = None,
    acquisition_date: str | None = None,
) -> dict[str, Any]:
    if slot == "view_a":
        return {
            "study_id": "abcdef0123456789",
            "series_id": "0123456789abcdef",
            "instance_id": "fedcba9876543210",
            "patient_context_id": patient_context_id,
            "modality": modality or "MR",
            # Deliberately later than view B: consultation slots are not timepoints.
            "acquisition_date": (
                "20261231" if acquisition_date is None else acquisition_date
            ),
            "series_description": "Synthetic <MR & source>",
            "instance_number": 2,
        }
    return {
        "study_id": "bbcdef0123456789",
        "series_id": "1123456789abcdef",
        "instance_id": "0011223344556677",
        "patient_context_id": patient_context_id,
        "modality": modality or "CT",
        "acquisition_date": "20200101" if acquisition_date is None else acquisition_date,
        "series_description": "Synthetic CT source",
        "instance_number": 7,
    }


def _measurement_bytes() -> bytes:
    packet = {
        "schema_version": "3.0.0",
        "created_at": "2026-08-28T00:00:00Z",
        "review_status": "unreviewed",
        "measurements": [],
        "limitations": ["Synthetic empty measurement evidence."],
    }
    return (json.dumps(packet, indent=2) + "\n").encode()


def _key_image_bytes(source: dict[str, Any], slot: str) -> bytes:
    png_bytes = _one_pixel_png()
    measurement_bytes = _measurement_bytes()
    packet = {
        "schema_version": "1.0.0",
        "created_at": "2026-08-28T00:00:00Z",
        "review_status": "unreviewed",
        "artifact_type": "derived_display_consultation_key_image",
        "source": source,
        "display": {
            "selection_slot": slot,
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
        "implementation": dict(consultation.CONSULTATION_KEY_IMAGE_IMPLEMENTATION),
        "limitations": list(consultation.CONSULTATION_KEY_IMAGE_LIMITATIONS),
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("key-image.json", json.dumps(packet, indent=2) + "\n")
        archive.writestr("key-image.png", png_bytes)
        archive.writestr("measurements.json", measurement_bytes)
    return output.getvalue()


def _catalog_and_registry(
    tmp_path: Path, sources: tuple[dict[str, Any], ...]
) -> tuple[dict[str, Any], dict[str, Path]]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    studies: list[dict[str, Any]] = []
    registry: dict[str, Path] = {}
    for index, source in enumerate(sources):
        payload = (b"synthetic local DICOM source\0" + bytes([index])) * 8
        path = tmp_path / f"source-{index}.dcm"
        path.write_bytes(payload)
        registry[source["instance_id"]] = path
        studies.append(
            {
                "id": source["study_id"],
                "series": [
                    {
                        "id": source["series_id"],
                        "patient_context_id": source["patient_context_id"],
                        "modality": source["modality"],
                        "acquisition_date": source["acquisition_date"],
                        "series_description": source["series_description"],
                        "instances": [
                            {
                                "id": f"instance_{index}0000000000000000000",
                                "instance_number": source["instance_number"] - 1,
                            },
                            {
                                "id": source["instance_id"],
                                "instance_number": source["instance_number"],
                                "bytes": len(payload),
                                "sha256": hashlib.sha256(payload).hexdigest(),
                            },
                            {
                                "id": f"instance_{index}1111111111111111111",
                                "instance_number": source["instance_number"] + 1,
                            },
                        ],
                    }
                ],
            }
        )
    return {"schema_version": "1.0.0", "studies": studies}, registry


def _fixture(
    tmp_path: Path,
    *,
    source_a: dict[str, Any] | None = None,
    source_b: dict[str, Any] | None = None,
) -> tuple[Path, Path, dict[str, Any], dict[str, Path]]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    sources = (source_a or _source("view_a"), source_b or _source("view_b"))
    view_a = tmp_path / "view-a.zip"
    view_b = tmp_path / "view-b.zip"
    view_a.write_bytes(_key_image_bytes(sources[0], "view_a"))
    view_b.write_bytes(_key_image_bytes(sources[1], "view_b"))
    catalog, registry = _catalog_and_registry(tmp_path, sources)
    return view_a, view_b, catalog, registry


def _transport(view_a: Path, view_b: Path) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("view-a.zip", view_a.read_bytes())
        archive.writestr("view-b.zip", view_b.read_bytes())
    return output.getvalue()


def _archive_files(payload: bytes | Path) -> dict[str, bytes]:
    source: io.BytesIO | Path = io.BytesIO(payload) if isinstance(payload, bytes) else payload
    with zipfile.ZipFile(source) as archive:
        return {info.filename: archive.read(info) for info in archive.infolist()}


def _zip_files(files: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return output.getvalue()


def _board_fixture(
    tmp_path: Path,
) -> tuple[list[tuple[str, Path]], dict[str, Any], dict[str, Path]]:
    source_a = _source("view_a")
    source_b = _source("view_b")
    source_c = {
        **_source("view_a", acquisition_date="20261130"),
        "study_id": "cbcdef0123456789",
        "series_id": "2123456789abcdef",
        "instance_id": "1011223344556677",
        "series_description": "Synthetic second MR source",
        "instance_number": 4,
    }
    sources = (source_a, source_b, source_c)
    catalog, registry = _catalog_and_registry(tmp_path / "board-source", sources)
    items: list[tuple[str, Path]] = []
    for index, (label, source, slot) in enumerate(
        (
            ("MRI overview", source_a, "view_a"),
            ("CT bone reference", source_b, "view_b"),
            ("Ask about <area>", source_c, "view_a"),
        )
    ):
        path = tmp_path / f"board-item-{index + 1}.zip"
        path.write_bytes(_key_image_bytes(source, slot))
        items.append((label, path))
    return items, catalog, registry


def _board_transport(items: list[tuple[str, Path]]) -> bytes:
    manifest = {
        "schema_version": "1.0.0",
        "artifact_type": "consultation_board_input",
        "items": [
            {
                "archive": f"item-{index + 1:02d}.zip",
                "discussion_label": label,
            }
            for index, (label, _) in enumerate(items)
        ],
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("board-input.json", json.dumps(manifest) + "\n")
        for index, (_, path) in enumerate(items):
            archive.writestr(f"item-{index + 1:02d}.zip", path.read_bytes())
    return output.getvalue()


def _rewrite_key_image_source(path: Path, **changes: Any) -> None:
    files = _archive_files(path)
    packet = json.loads(files["key-image.json"])
    packet["source"].update(changes)
    files["key-image.json"] = (json.dumps(packet, indent=2) + "\n").encode()
    path.write_bytes(_zip_files(files))


def test_mr_ct_packet_is_source_bound_static_neutral_and_exact(tmp_path: Path) -> None:
    view_a, view_b, catalog, registry = _fixture(tmp_path)
    original_source_hashes = {
        instance_id: hashlib.sha256(path.read_bytes()).hexdigest()
        for instance_id, path in registry.items()
    }

    archive_bytes = consultation.consultation_packet_archive_bytes(
        view_a,
        view_b,
        catalog,
        registry,
        created_at=CREATED_AT,
    )
    summary = consultation.consultation_packet_summary(io.BytesIO(archive_bytes))
    files = _archive_files(archive_bytes)
    packet = json.loads(files["consultation-packet.json"])

    assert summary == {
        "valid": True,
        "schema_version": "1.0.0",
        "review_status": "unreviewed",
        "artifact_type": "clinician_consultation_packet",
        "modality_relationship": "cross_modality",
        "measurement_counts": {"view_a": 0, "view_b": 0},
        "file_integrity": True,
        "component_integrity": True,
        "presentation_integrity": True,
        "longitudinal_comparison_authorized": False,
        "response_assessment_authorized": False,
        "errors": [],
    }
    assert set(files) == consultation.EXPECTED_FILES
    assert set(packet["files"]) == set(consultation.PAYLOAD_MEDIA_TYPES)
    assert packet["computed_results"] == []
    assert packet["candidate_interpretations"] == []
    assert packet["relationship"] == {
        "selection_method": "explicit_two_view_selection",
        "same_patient_context": True,
        "modalities": ["MR", "CT"],
        "modality_relationship": "cross_modality",
        "distinct_source_studies": True,
        "same_source_instance": False,
        "temporal_relationship": "not_asserted",
        "registration_status": "not_registered",
        "spatial_relationship": "not_aligned",
        "longitudinal_comparison_authorized": False,
        "response_assessment_authorized": False,
    }
    assert [item["slot"] for item in packet["observations"]] == ["view_a", "view_b"]
    for observation in packet["observations"]:
        source = observation["source"]
        source_path = registry[source["instance_id"]]
        assert observation["source_anchor"] == {
            "catalog_match": True,
            "dicom_bytes": source_path.stat().st_size,
            "dicom_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        }
        assert "viewport_role" not in observation["display"]

    review_html = files["review.html"].decode()
    readme = files["README.txt"].decode()
    assert "SELECTED VIEW A" in review_html
    assert "SELECTED VIEW B" in review_html
    assert "NOT A COMPARISON" in review_html
    assert "no chronological role is assigned" in review_html
    assert "&lt;MR &amp; source&gt;" in review_html
    assert "<script" not in review_html.lower()
    assert "http://" not in review_html.lower()
    assert "https://" not in review_html.lower()
    assert ">BASELINE<" not in review_html.upper()
    assert ">FOLLOW-UP<" not in review_html.upper()
    assert "elapsed_days" not in json.dumps(packet)
    assert "baseline_acquisition_date" not in json.dumps(packet)
    assert "followup_acquisition_date" not in json.dumps(packet)
    assert "NOT A COMPARISON" in readme
    assert "No temporal relationship" in readme
    assert not any(path.suffix == ".dcm" for path in map(Path, files))
    assert original_source_hashes == {
        instance_id: hashlib.sha256(path.read_bytes()).hexdigest()
        for instance_id, path in registry.items()
    }


@pytest.mark.parametrize(
    ("modality_a", "modality_b", "date_a", "date_b"),
    [
        ("MR", "CT", "20261231", "20200101"),
        ("CT", "MR", "20200101", "20261231"),
        ("MR", "CT", None, None),
    ],
)
def test_consultation_selection_is_modality_order_and_date_independent(
    tmp_path: Path,
    modality_a: str,
    modality_b: str,
    date_a: str | None,
    date_b: str | None,
) -> None:
    source_a = _source("view_a", modality=modality_a, acquisition_date=date_a)
    source_b = _source("view_b", modality=modality_b, acquisition_date=date_b)
    if date_a is None:
        source_a["acquisition_date"] = None
    if date_b is None:
        source_b["acquisition_date"] = None
    view_a, view_b, catalog, registry = _fixture(
        tmp_path, source_a=source_a, source_b=source_b
    )

    packet, _ = consultation.build_consultation_packet(
        view_a, view_b, catalog, registry, created_at=CREATED_AT
    )

    assert packet["relationship"]["modalities"] == [modality_a, modality_b]
    assert packet["relationship"]["modality_relationship"] == "cross_modality"
    assert packet["relationship"]["temporal_relationship"] == "not_asserted"


def test_cross_patient_or_unsupported_modality_is_rejected(
    tmp_path: Path,
) -> None:
    source_b = _source("view_b", patient_context_id="2234567890abcdef")
    view_a, view_b, catalog, registry = _fixture(tmp_path / "patient", source_b=source_b)
    with pytest.raises(ValueError, match="matching opaque patient context"):
        consultation.build_consultation_packet(view_a, view_b, catalog, registry)

    unsupported = _source("view_b", modality="PT")
    view_a, view_b, catalog, registry = _fixture(
        tmp_path / "modality", source_b=unsupported
    )
    with pytest.raises(ValueError, match="one MR and one CT"):
        consultation.build_consultation_packet(view_a, view_b, catalog, registry)

    same_modality = _source("view_b", modality="MR")
    view_a, view_b, catalog, registry = _fixture(
        tmp_path / "same-modality", source_b=same_modality
    )
    with pytest.raises(ValueError, match="one MR and one CT"):
        consultation.build_consultation_packet(view_a, view_b, catalog, registry)


def test_same_source_study_is_rejected_at_the_backend_boundary(tmp_path: Path) -> None:
    source_a = _source("view_a")
    source_b = _source("view_b")
    source_b["study_id"] = source_a["study_id"]
    view_a, view_b, catalog, registry = _fixture(
        tmp_path, source_a=source_a, source_b=source_b
    )
    # Represent the shape emitted by build_catalog: one study containing both series.
    catalog["studies"][0]["series"].extend(catalog["studies"][1]["series"])
    catalog["studies"].pop(1)

    with pytest.raises(ValueError, match="two distinct source studies"):
        consultation.build_consultation_packet(view_a, view_b, catalog, registry)


def test_same_source_instance_is_rejected_at_the_backend_boundary(tmp_path: Path) -> None:
    source_a = _source("view_a")
    source_b = _source("view_b")
    source_b["instance_id"] = source_a["instance_id"]
    view_a, view_b, catalog, registry = _fixture(
        tmp_path, source_a=source_a, source_b=source_b
    )

    with pytest.raises(ValueError, match="two distinct source instances"):
        consultation.build_consultation_packet(view_a, view_b, catalog, registry)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("missing_study", "exact member"),
        ("metadata", "metadata disagrees"),
        ("missing_registry", "source is unavailable"),
        ("missing_hash", "source-hashed catalog"),
        ("invalid_hash", "source-hashed catalog"),
        ("missing_bytes", "source-hashed catalog"),
    ],
)
def test_catalog_membership_and_source_hash_are_mandatory(
    tmp_path: Path, mutation: str, message: str
) -> None:
    view_a, view_b, catalog, registry = _fixture(tmp_path)
    first_series = catalog["studies"][0]["series"][0]
    first_instance = first_series["instances"][1]
    if mutation == "missing_study":
        catalog["studies"].pop(0)
    elif mutation == "metadata":
        first_series["series_description"] = "different live catalog metadata"
    elif mutation == "missing_registry":
        registry.pop(_source("view_a")["instance_id"])
    elif mutation == "missing_hash":
        first_instance.pop("sha256")
    elif mutation == "invalid_hash":
        first_instance["sha256"] = "A" * 64
    else:
        first_instance.pop("bytes")

    with pytest.raises(ValueError, match=message):
        consultation.build_consultation_packet(view_a, view_b, catalog, registry)


def test_changed_or_symlinked_dicom_source_is_rejected(tmp_path: Path) -> None:
    view_a, view_b, catalog, registry = _fixture(tmp_path / "tamper")
    registry[_source("view_a")["instance_id"]].write_bytes(b"changed after cataloging")
    with pytest.raises(ValueError, match="changed after cataloging|integrity changed"):
        consultation.build_consultation_packet(view_a, view_b, catalog, registry)

    view_a, view_b, catalog, registry = _fixture(tmp_path / "symlink")
    instance_id = _source("view_a")["instance_id"]
    source_path = registry[instance_id]
    moved = source_path.with_name("actual-source.dcm")
    source_path.rename(moved)
    source_path.symlink_to(moved)
    with pytest.raises(ValueError, match="cannot be read safely"):
        consultation.build_consultation_packet(view_a, view_b, catalog, registry)


def test_component_and_transport_require_exact_unambiguous_members(
    tmp_path: Path,
) -> None:
    view_a, view_b, catalog, registry = _fixture(tmp_path)

    component_files = _archive_files(view_a)
    component_files["unexpected.txt"] = b"not allowed"
    view_a.write_bytes(_zip_files(component_files))
    with pytest.raises(ValueError, match="exactly the three supported files"):
        consultation.build_consultation_packet(view_a, view_b, catalog, registry)

    view_a.write_bytes(_key_image_bytes(_source("view_a"), "view_a"))
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("view-a.zip", view_a.read_bytes())
        archive.writestr("view-b.zip", view_b.read_bytes())
        archive.writestr("unexpected.txt", b"not allowed")
    with pytest.raises(ValueError, match="exactly view-a.zip and view-b.zip"):
        consultation.consultation_packet_from_transport(
            output.getvalue(), catalog, registry
        )

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("view-a.zip", view_a.read_bytes())
        archive.writestr("view-a.zip", view_a.read_bytes())
        archive.writestr("view-b.zip", view_b.read_bytes())
    with pytest.raises(ValueError, match="exactly view-a.zip and view-b.zip"):
        consultation.consultation_packet_from_transport(
            output.getvalue(), catalog, registry
        )


def test_transport_round_trip_is_in_memory_and_enforces_raw_size_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    view_a, view_b, catalog, registry = _fixture(tmp_path)
    before = {path.name for path in tmp_path.iterdir()}

    archive_bytes = consultation.consultation_packet_from_transport(
        _transport(view_a, view_b),
        catalog,
        registry,
        created_at=CREATED_AT,
    )

    assert consultation.consultation_packet_summary(io.BytesIO(archive_bytes))["valid"]
    assert {path.name for path in tmp_path.iterdir()} == before

    monkeypatch.setattr(
        consultation,
        "MAX_CONSULTATION_PACKET_TRANSPORT_BYTES",
        len(_transport(view_a, view_b)) - 1,
    )
    with pytest.raises(ValueError, match="exceeds the local safety limit"):
        consultation.consultation_packet_from_transport(
            _transport(view_a, view_b), catalog, registry
        )


def test_duplicate_key_json_is_rejected_in_component_and_packet(
    tmp_path: Path,
) -> None:
    view_a, view_b, catalog, registry = _fixture(tmp_path)
    files = _archive_files(view_a)
    files["key-image.json"] = files["key-image.json"].replace(
        b"{\n", b'{\n  "schema_version": "1.0.0",\n', 1
    )
    view_a.write_bytes(_zip_files(files))
    with pytest.raises(ValueError, match="component JSON is invalid"):
        consultation.build_consultation_packet(view_a, view_b, catalog, registry)

    view_a.write_bytes(_key_image_bytes(_source("view_a"), "view_a"))
    archive_bytes = consultation.consultation_packet_archive_bytes(
        view_a, view_b, catalog, registry, created_at=CREATED_AT
    )
    files = _archive_files(archive_bytes)
    files["consultation-packet.json"] = files["consultation-packet.json"].replace(
        b"{\n", b'{\n  "schema_version": "1.0.0",\n', 1
    )
    summary = consultation.consultation_packet_summary(
        io.BytesIO(_zip_files(files))
    )
    assert summary["valid"] is False
    assert "archive could not be read: ValueError" in summary["errors"]


@pytest.mark.parametrize(
    ("member", "integrity_key"),
    [
        ("review.html", "presentation_integrity"),
        ("view-a/key-image.png", "component_integrity"),
        ("view-b/measurements.json", "component_integrity"),
    ],
)
def test_payload_tamper_is_detected(
    tmp_path: Path, member: str, integrity_key: str
) -> None:
    view_a, view_b, catalog, registry = _fixture(tmp_path)
    archive_bytes = consultation.consultation_packet_archive_bytes(
        view_a, view_b, catalog, registry, created_at=CREATED_AT
    )
    files = _archive_files(archive_bytes)
    files[member] += b"tampered"

    summary = consultation.consultation_packet_summary(
        io.BytesIO(_zip_files(files))
    )

    assert summary["valid"] is False
    assert summary["file_integrity"] is False
    assert summary[integrity_key] is False
    assert "payload digests" in " ".join(summary["errors"])


def test_source_anchor_tamper_is_detected(tmp_path: Path) -> None:
    view_a, view_b, catalog, registry = _fixture(tmp_path)
    archive_bytes = consultation.consultation_packet_archive_bytes(
        view_a, view_b, catalog, registry, created_at=CREATED_AT
    )
    files = _archive_files(archive_bytes)
    packet = json.loads(files["consultation-packet.json"])
    packet["observations"][0]["source_anchor"]["dicom_sha256"] = "0" * 64
    files["consultation-packet.json"] = (
        json.dumps(packet, indent=2) + "\n"
    ).encode()

    summary = consultation.consultation_packet_summary(io.BytesIO(_zip_files(files)))

    assert summary["valid"] is False
    assert summary["presentation_integrity"] is False


def test_output_is_owner_only_and_existing_file_or_symlink_is_not_overwritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    view_a, view_b, catalog, registry = _fixture(tmp_path)
    monkeypatch.setattr(
        "dicom_guide.catalog.build_catalog",
        lambda _root, *, include_hashes: (catalog, registry),
    )
    output = tmp_path / "consultation.zip"

    consultation.write_consultation_packet(
        tmp_path / "dicom", view_a, view_b, output, created_at=CREATED_AT
    )

    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    original = output.read_bytes()
    with pytest.raises(FileExistsError):
        consultation.write_consultation_packet(
            tmp_path / "dicom", view_a, view_b, output, created_at=CREATED_AT
        )
    assert output.read_bytes() == original

    target = tmp_path / "symlink-target.zip"
    target.write_bytes(b"must remain unchanged")
    link = tmp_path / "existing-link.zip"
    link.symlink_to(target)
    with pytest.raises(FileExistsError):
        consultation.write_consultation_packet(
            tmp_path / "dicom", view_a, view_b, link, created_at=CREATED_AT
        )
    assert link.is_symlink()
    assert target.read_bytes() == b"must remain unchanged"


def test_summary_is_privacy_minimal(tmp_path: Path) -> None:
    view_a, view_b, catalog, registry = _fixture(tmp_path)
    archive_bytes = consultation.consultation_packet_archive_bytes(
        view_a, view_b, catalog, registry, created_at=CREATED_AT
    )

    summary = consultation.consultation_packet_summary(io.BytesIO(archive_bytes))
    serialized = json.dumps(summary, sort_keys=True)

    assert set(summary) == {
        "valid",
        "schema_version",
        "review_status",
        "artifact_type",
        "modality_relationship",
        "measurement_counts",
        "file_integrity",
        "component_integrity",
        "presentation_integrity",
        "longitudinal_comparison_authorized",
        "response_assessment_authorized",
        "errors",
    }
    for sensitive_value in (
        PATIENT_CONTEXT_ID,
        "abcdef0123456789",
        "0123456789abcdef",
        "fedcba9876543210",
        "20261231",
        "Synthetic <MR & source>",
        catalog["studies"][0]["series"][0]["instances"][1]["sha256"],
        str(registry[_source("view_a")["instance_id"]]),
    ):
        assert sensitive_value not in serialized


def test_summary_rejects_extra_duplicate_and_path_traversal_members(
    tmp_path: Path,
) -> None:
    view_a, view_b, catalog, registry = _fixture(tmp_path)
    archive_bytes = consultation.consultation_packet_archive_bytes(
        view_a, view_b, catalog, registry, created_at=CREATED_AT
    )
    files = _archive_files(archive_bytes)

    for extra_name in ("unexpected.txt", "../review.html"):
        mutated = dict(files)
        mutated[extra_name] = b"not allowed"
        summary = consultation.consultation_packet_summary(
            io.BytesIO(_zip_files(mutated))
        )
        assert summary["valid"] is False
        assert any("exactly the nine supported files" in error for error in summary["errors"])

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
        archive.writestr("review.html", files["review.html"])
    summary = consultation.consultation_packet_summary(io.BytesIO(output.getvalue()))
    assert summary["valid"] is False
    assert any("exactly the nine supported files" in error for error in summary["errors"])


def test_consultation_board_is_source_bound_static_neutral_and_schema_valid(
    tmp_path: Path,
) -> None:
    items, catalog, registry = _board_fixture(tmp_path)
    original_hashes = {
        instance_id: hashlib.sha256(path.read_bytes()).hexdigest()
        for instance_id, path in registry.items()
    }

    archive_bytes = boards.consultation_board_archive_bytes(
        items,
        catalog,
        registry,
        created_at=CREATED_AT,
    )
    summary = boards.consultation_board_summary(io.BytesIO(archive_bytes))
    files = _archive_files(archive_bytes)
    packet = json.loads(files["consultation-board.json"])

    assert summary == {
        "valid": True,
        "schema_version": "1.0.0",
        "review_status": "unreviewed",
        "artifact_type": "clinician_consultation_board",
        "item_count": 3,
        "modalities_present": ["MR", "CT"],
        "distinct_source_study_count": 3,
        "measurement_count": 0,
        "file_integrity": True,
        "component_integrity": True,
        "source_anchor_integrity": True,
        "presentation_integrity": True,
        "longitudinal_comparison_authorized": False,
        "response_assessment_authorized": False,
        "external_api_required": False,
        "errors": [],
    }
    assert packet["computed_results"] == []
    assert packet["candidate_interpretations"] == []
    assert packet["relationship"]["temporal_relationship"] == "not_asserted"
    assert packet["relationship"]["registration_status"] == "not_registered"
    assert [item["discussion_label"] for item in packet["observations"]] == [
        label for label, _ in items
    ]
    review = files["review.html"].decode()
    assert "Ask about &lt;area&gt;" in review
    assert "Ask about <area>" not in review
    assert "LABELS UNREVIEWED" in review
    assert "NO RESPONSE CONCLUSION" in review
    assert all(
        hashlib.sha256(path.read_bytes()).hexdigest() == original_hashes[instance_id]
        for instance_id, path in registry.items()
    )

    schema_path = (
        Path(__file__).parents[3]
        / "schemas"
        / "dicom-guide-clinician-consultation-board-v1.schema.json"
    )
    schema = json.loads(schema_path.read_text())
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(packet)
    packet["candidate_interpretations"] = [{"text": "unsafe"}]
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(packet)
    packet["candidate_interpretations"] = []
    packet["observations"][0]["discussion_label"] = "spoof\u202elabel"
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(packet)


def test_consultation_board_transport_and_privacy_minimized_summary(
    tmp_path: Path,
) -> None:
    items, catalog, registry = _board_fixture(tmp_path)
    archive_bytes = boards.consultation_board_from_transport(
        _board_transport(items),
        catalog,
        registry,
        created_at=CREATED_AT,
    )

    summary = boards.consultation_board_summary(io.BytesIO(archive_bytes))
    serialized = json.dumps(summary, sort_keys=True)

    assert summary["valid"] is True
    assert summary["item_count"] == 3
    for sensitive_value in (
        PATIENT_CONTEXT_ID,
        *(label for label, _ in items),
        *(instance_id for instance_id in registry),
        *(hashlib.sha256(path.read_bytes()).hexdigest() for path in registry.values()),
        *(str(path) for path in registry.values()),
    ):
        assert sensitive_value not in serialized


def test_consultation_board_refuses_invalid_sets_labels_and_transport(
    tmp_path: Path,
) -> None:
    items, catalog, registry = _board_fixture(tmp_path)

    with pytest.raises(ValueError, match="2 to 8"):
        boards.consultation_board_archive_bytes(items[:1], catalog, registry)
    with pytest.raises(ValueError, match="trimmed"):
        boards.consultation_board_archive_bytes(
            [(" leading label", items[0][1]), items[1]],
            catalog,
            registry,
        )
    with pytest.raises(ValueError, match="distinct source instances"):
        boards.consultation_board_archive_bytes(
            [items[0], ("Duplicate", items[0][1]), items[1]],
            catalog,
            registry,
        )

    files = _archive_files(_board_transport(items))
    files["unexpected.txt"] = b"not allowed"
    with pytest.raises(ValueError, match="unsupported files"):
        boards.consultation_board_from_transport(
            _zip_files(files),
            catalog,
            registry,
        )

    duplicate = io.BytesIO()
    with zipfile.ZipFile(duplicate, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, payload in _archive_files(_board_transport(items)).items():
            archive.writestr(name, payload)
        archive.writestr("item-01.zip", items[0][1].read_bytes())
    with pytest.raises(ValueError, match="ambiguous"):
        boards.consultation_board_from_transport(
            duplicate.getvalue(),
            catalog,
            registry,
        )


@pytest.mark.parametrize(
    ("mutations", "message"),
    [
        (
            [(2, {"patient_context_id": "2234567890abcdef"})],
            "matching opaque patient context",
        ),
        ([(1, {"modality": "MR"})], "at least one MR and one CT"),
        ([(2, {"modality": "PT"})], "at least one MR and one CT"),
        (
            [
                (1, {"study_id": "abcdef0123456789"}),
                (2, {"study_id": "abcdef0123456789"}),
            ],
            "at least two distinct source studies",
        ),
    ],
)
def test_consultation_board_relationship_gates_fail_closed(
    tmp_path: Path,
    mutations: list[tuple[int, dict[str, str]]],
    message: str,
) -> None:
    items, catalog, registry = _board_fixture(tmp_path)
    for index, changes in mutations:
        _rewrite_key_image_source(items[index][1], **changes)

    with pytest.raises(ValueError, match=message):
        boards.consultation_board_archive_bytes(items, catalog, registry)


def test_consultation_board_tamper_breaks_integrity_and_presentation(
    tmp_path: Path,
) -> None:
    items, catalog, registry = _board_fixture(tmp_path)
    archive_bytes = boards.consultation_board_archive_bytes(
        items,
        catalog,
        registry,
        created_at=CREATED_AT,
    )
    files = _archive_files(archive_bytes)
    packet = json.loads(files["consultation-board.json"])
    packet["observations"][0]["discussion_label"] = "Changed after assembly"
    files["consultation-board.json"] = (json.dumps(packet, indent=2) + "\n").encode()

    summary = boards.consultation_board_summary(io.BytesIO(_zip_files(files)))

    assert summary["valid"] is False
    assert summary["presentation_integrity"] is False


def test_consultation_board_source_anchor_tamper_fails_closed(tmp_path: Path) -> None:
    items, catalog, registry = _board_fixture(tmp_path)
    archive_bytes = boards.consultation_board_archive_bytes(
        items, catalog, registry, created_at=CREATED_AT
    )
    files = _archive_files(archive_bytes)
    packet = json.loads(files["consultation-board.json"])
    packet["observations"][0]["source_anchor"]["dicom_sha256"] = "0" * 64
    files["consultation-board.json"] = (json.dumps(packet, indent=2) + "\n").encode()

    summary = boards.consultation_board_summary(io.BytesIO(_zip_files(files)))

    assert summary["valid"] is False
    assert summary["source_anchor_integrity"] is False
    assert summary["presentation_integrity"] is False


def test_consultation_board_enforces_component_generated_and_transport_totals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    items, catalog, registry = _board_fixture(tmp_path)
    with zipfile.ZipFile(items[0][1]) as archive:
        component_total = sum(info.file_size for info in archive.infolist())
    monkeypatch.setattr(boards, "MAX_ARCHIVE_TOTAL_BYTES", component_total - 1)
    with pytest.raises(ValueError, match="key-image content exceeds"):
        boards.consultation_board_archive_bytes(items, catalog, registry)

    monkeypatch.setattr(boards, "MAX_ARCHIVE_TOTAL_BYTES", 128 * 1024 * 1024)
    monkeypatch.setattr(boards, "MAX_BOARD_ARCHIVE_BYTES", component_total + 1)
    with pytest.raises(ValueError, match="consultation-board (member|content) exceeds"):
        boards.consultation_board_archive_bytes(items, catalog, registry)

    all_component_bytes = 0
    for _, path in items:
        with zipfile.ZipFile(path) as archive:
            all_component_bytes += sum(info.file_size for info in archive.infolist())
    monkeypatch.setattr(boards, "MAX_BOARD_ARCHIVE_BYTES", all_component_bytes + 1)
    with pytest.raises(ValueError, match="consultation-board (member|content) exceeds"):
        boards.consultation_board_archive_bytes(items, catalog, registry)

    manifest = {
        "schema_version": "1.0.0",
        "artifact_type": "consultation_board_input",
        "items": [
            {
                "archive": f"item-{index + 1:02d}.zip",
                "discussion_label": f"Reference {index + 1}",
            }
            for index in range(8)
        ],
    }
    transport = io.BytesIO()
    with zipfile.ZipFile(transport, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("board-input.json", json.dumps(manifest))
        for index in range(8):
            archive.writestr(f"item-{index + 1:02d}.zip", b"A" * 4096)
    transport_bytes = transport.getvalue()
    assert len(transport_bytes) < 8 * 4096
    monkeypatch.setattr(boards, "MAX_BOARD_TRANSPORT_BYTES", 16 * 1024)
    with pytest.raises(ValueError, match="request content exceeds"):
        boards.consultation_board_from_transport(
            transport_bytes, catalog, registry
        )


def test_consultation_board_rejects_oversized_item_count_before_path_expansion(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="item count exceeds"):
        boards._expected_payload_paths(9)

    items, catalog, registry = _board_fixture(tmp_path)
    archive_bytes = boards.consultation_board_archive_bytes(
        items, catalog, registry, created_at=CREATED_AT
    )
    files = _archive_files(archive_bytes)
    packet = json.loads(files["consultation-board.json"])
    packet["observations"].extend([packet["observations"][0]] * 6)
    files["consultation-board.json"] = (json.dumps(packet, indent=2) + "\n").encode()

    summary = boards.consultation_board_summary(io.BytesIO(_zip_files(files)))

    assert summary["valid"] is False
    assert any("observations must contain 2 to 8" in error for error in summary["errors"])


def test_consultation_board_transport_rejects_duplicate_json_and_link_members(
    tmp_path: Path,
) -> None:
    items, catalog, registry = _board_fixture(tmp_path)
    files = _archive_files(_board_transport(items))
    files["board-input.json"] = files["board-input.json"].replace(
        b"{", b'{"schema_version":"1.0.0",', 1
    )
    with pytest.raises(ValueError, match="JSON is invalid"):
        boards.consultation_board_from_transport(
            _zip_files(files), catalog, registry
        )

    linked = io.BytesIO()
    with zipfile.ZipFile(linked, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("board-input.json", b"{}")
        info = zipfile.ZipInfo("item-01.zip")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(info, b"arbitrary-target")
    with pytest.raises(ValueError, match="linked consultation-board request"):
        boards.consultation_board_from_transport(
            linked.getvalue(), catalog, registry
        )


def test_write_consultation_board_is_owner_only_and_never_overwrites(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    items, catalog, registry = _board_fixture(tmp_path)
    monkeypatch.setattr(
        "dicom_guide.catalog.build_catalog",
        lambda _root, *, include_hashes: (catalog, registry),
    )
    output = tmp_path / "consultation-board.zip"

    boards.write_consultation_board(
        tmp_path / "dicom", items, output, created_at=CREATED_AT
    )

    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    original = output.read_bytes()
    with pytest.raises(FileExistsError):
        boards.write_consultation_board(
            tmp_path / "dicom", items, output, created_at=CREATED_AT
        )
    assert output.read_bytes() == original
