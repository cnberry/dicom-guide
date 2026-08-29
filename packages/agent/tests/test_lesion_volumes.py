from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from pydicom import dcmread
from pydicom.dataset import Dataset, FileDataset, FileMetaDataset
from pydicom.sequence import Sequence
from pydicom.uid import (
    ExplicitVRLittleEndian,
    MRImageStorage,
    SegmentationStorage,
    generate_uid,
)

from scanview_agent.lesion_volumes import lesion_volume_archive_summary
from scanview_agent.lesion_volume_reviews import (
    ATTESTATION as REVIEW_ATTESTATION,
    LIMITATIONS as REVIEW_LIMITATIONS,
    lesion_volume_review_summary,
)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _code(value: str, meaning: str, scheme: str = "SCT") -> Dataset:
    item = Dataset()
    item.CodeValue = value
    item.CodingSchemeDesignator = scheme
    item.CodeMeaning = meaning
    return item


def _write_source(
    path: Path,
    *,
    study_uid: str,
    series_uid: str,
    frame_uid: str,
    sop_uid: str,
    position: float,
) -> None:
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = MRImageStorage
    meta.MediaStorageSOPInstanceUID = sop_uid
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    dataset = FileDataset(path.name, {}, file_meta=meta, preamble=b"\0" * 128)
    dataset.is_little_endian = True
    dataset.is_implicit_VR = False
    dataset.SOPClassUID = MRImageStorage
    dataset.SOPInstanceUID = sop_uid
    dataset.StudyInstanceUID = study_uid
    dataset.SeriesInstanceUID = series_uid
    dataset.FrameOfReferenceUID = frame_uid
    dataset.PatientID = "SYNTHETIC"
    dataset.Modality = "MR"
    dataset.Rows = 8
    dataset.Columns = 8
    dataset.PixelSpacing = [0.5, 0.75]
    dataset.SliceThickness = 1.5
    dataset.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
    dataset.ImagePositionPatient = [0, 0, position]
    dataset.SamplesPerPixel = 1
    dataset.PhotometricInterpretation = "MONOCHROME2"
    dataset.BitsAllocated = 16
    dataset.BitsStored = 12
    dataset.HighBit = 11
    dataset.PixelRepresentation = 0
    dataset.PixelData = bytes(8 * 8 * 2)
    dataset.save_as(path, enforce_file_format=True)


def _pack_frames(frames: list[bytes]) -> bytes:
    bits = b"".join(frames)
    output = bytearray((len(bits) + 7) // 8)
    for index, value in enumerate(bits):
        if value:
            output[index // 8] |= 1 << (index % 8)
    if len(output) % 2:
        output.append(0)
    return bytes(output)


def _write_seg(
    path: Path,
    *,
    study_uid: str,
    source_series_uid: str,
    frame_uid: str,
    source_uids: list[str],
    positions: list[float],
    artifact_id: str,
    tracking_uid: str,
    label: str,
) -> bytes:
    sop_uid = generate_uid()
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = SegmentationStorage
    meta.MediaStorageSOPInstanceUID = sop_uid
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    dataset = FileDataset(path.name, {}, file_meta=meta, preamble=b"\0" * 128)
    dataset.is_little_endian = True
    dataset.is_implicit_VR = False
    dataset.SOPClassUID = SegmentationStorage
    dataset.SOPInstanceUID = sop_uid
    dataset.StudyInstanceUID = study_uid
    dataset.SeriesInstanceUID = generate_uid()
    dataset.FrameOfReferenceUID = frame_uid
    dataset.Modality = "SEG"
    dataset.Rows = 8
    dataset.Columns = 8
    dataset.NumberOfFrames = 2
    dataset.SamplesPerPixel = 1
    dataset.PhotometricInterpretation = "MONOCHROME2"
    dataset.BitsAllocated = 1
    dataset.BitsStored = 1
    dataset.HighBit = 0
    dataset.PixelRepresentation = 0
    dataset.SegmentationType = "BINARY"
    dataset.SegmentsOverlap = "NO"

    shared = Dataset()
    pixel_measures = Dataset()
    pixel_measures.PixelSpacing = [0.5, 0.75]
    pixel_measures.SliceThickness = 1.5
    shared.PixelMeasuresSequence = Sequence([pixel_measures])
    plane_orientation = Dataset()
    plane_orientation.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
    shared.PlaneOrientationSequence = Sequence([plane_orientation])
    dataset.SharedFunctionalGroupsSequence = Sequence([shared])

    segment = Dataset()
    segment.SegmentNumber = 1
    segment.SegmentLabel = label
    segment.SegmentAlgorithmType = "MANUAL"
    segment.TrackingID = artifact_id
    segment.TrackingUID = tracking_uid
    segment.SegmentedPropertyCategoryCodeSequence = Sequence(
        [_code("49755003", "Morphologically Abnormal Structure")]
    )
    segment.SegmentedPropertyTypeCodeSequence = Sequence([_code("52988006", "Lesion")])
    dataset.SegmentSequence = Sequence([segment])

    frame_groups = []
    for source_index in (0, 2):
        group = Dataset()
        segment_identification = Dataset()
        segment_identification.ReferencedSegmentNumber = 1
        group.SegmentIdentificationSequence = Sequence([segment_identification])
        frame_content = Dataset()
        frame_content.DimensionIndexValues = [1, source_index + 1]
        group.FrameContentSequence = Sequence([frame_content])
        plane = Dataset()
        plane.ImagePositionPatient = [0, 0, positions[source_index]]
        group.PlanePositionSequence = Sequence([plane])
        derivation = Dataset()
        source = Dataset()
        source.ReferencedSOPClassUID = MRImageStorage
        source.ReferencedSOPInstanceUID = source_uids[source_index]
        source.PurposeOfReferenceCodeSequence = Sequence(
            [_code("121322", "Source Image for Image Processing Operation", "DCM")]
        )
        derivation.SourceImageSequence = Sequence([source])
        derivation.DerivationCodeSequence = Sequence(
            [_code("113076", "Segmentation", "DCM")]
        )
        group.DerivationImageSequence = Sequence([derivation])
        frame_groups.append(group)
    dataset.PerFrameFunctionalGroupsSequence = Sequence(frame_groups)

    referenced_series = Dataset()
    referenced_series.SeriesInstanceUID = source_series_uid
    referenced_series.ReferencedInstanceSequence = Sequence([])
    for source_uid in source_uids:
        reference = Dataset()
        reference.ReferencedSOPClassUID = MRImageStorage
        reference.ReferencedSOPInstanceUID = source_uid
        referenced_series.ReferencedInstanceSequence.append(reference)
    dataset.ReferencedSeriesSequence = Sequence([referenced_series])

    first = bytearray(64)
    first[0] = 1
    first[1] = 1
    third = bytearray(64)
    third[2] = 1
    dataset.PixelData = _pack_frames([bytes(first), bytes(third)])
    dataset.save_as(path, enforce_file_format=True)
    return path.read_bytes()


def _build_bundle(tmp_path: Path, positions: list[float] | None = None) -> tuple[Path, Path, dict]:
    source_root = tmp_path / "source"
    source_root.mkdir()
    positions = positions or [0.0, 2.0, 4.0]
    study_uid = generate_uid()
    series_uid = generate_uid()
    frame_uid = generate_uid()
    source_uids = [generate_uid() for _ in range(3)]
    source_items = []
    for index, (sop_uid, position) in enumerate(zip(source_uids, positions, strict=True)):
        path = source_root / f"source-{index}.dcm"
        _write_source(
            path,
            study_uid=study_uid,
            series_uid=series_uid,
            frame_uid=frame_uid,
            sop_uid=sop_uid,
            position=position,
        )
        payload = path.read_bytes()
        source_items.append(
            {
                "frame_index": index,
                "instance_id": f"{index + 1:016x}",
                "bytes": len(payload),
                "sha256": _sha256(payload),
                "rows": 8,
                "columns": 8,
                "pixel_spacing_mm": [0.5, 0.75],
                "image_orientation_patient": [1, 0, 0, 0, 1, 0],
                "image_position_patient": [0, 0, position],
            }
        )

    artifact_id = "seg_12345678-1234-4abc-8def-1234567890ab"
    tracking_uid = generate_uid()
    label = "Reviewer-defined region"
    seg_path = tmp_path / "segmentation.dcm"
    seg_bytes = _write_seg(
        seg_path,
        study_uid=study_uid,
        source_series_uid=series_uid,
        frame_uid=frame_uid,
        source_uids=source_uids,
        positions=positions,
        artifact_id=artifact_id,
        tracking_uid=tracking_uid,
        label=label,
    )
    dense = bytearray(8 * 8 * 3)
    dense[0] = 1
    dense[1] = 1
    dense[2 * 64 + 2] = 1
    source_lines = [
        f"{item['frame_index']}:{item['instance_id']}:{item['bytes']}:{item['sha256']}"
        for item in source_items
    ]
    slice_spacing = 2.0
    voxel_volume = 0.5 * 0.75 * slice_spacing
    evidence = {
        "schema_version": "1.0.0",
        "artifact_type": "scanview.lesion-volume-evidence",
        "artifact_id": artifact_id,
        "created_at": "2026-08-28T12:00:00.000Z",
        "state": "draft_unreviewed",
        "local_only": True,
        "sensitive": True,
        "deidentified": False,
        "source": {
            "patient_context_id": "0000000000000004",
            "study_id": "0000000000000001",
            "series_id": "0000000000000002",
            "frame_of_reference_id": "0000000000000003",
            "modality": "MR",
            "instance_count": 3,
            "instances": source_items,
            "source_set_sha256": _sha256(("\n".join(source_lines) + "\n").encode()),
        },
        "segment": {
            "segment_number": 1,
            "tracking_id": artifact_id,
            "tracking_uid": tracking_uid,
            "label": label,
            "target_definition": "Boundary manually painted for discussion; lesion identity is unreviewed.",
            "algorithm_type": "MANUAL",
            "property_category": {
                "value": "49755003",
                "scheme": "SCT",
                "meaning": "Morphologically Abnormal Structure",
            },
            "property_type": {"value": "52988006", "scheme": "SCT", "meaning": "Lesion"},
        },
        "geometry": {
            "grid_order": "source_volume_frame_row_column",
            "dimensions": [8, 8, 3],
            "pixel_spacing_mm": [0.5, 0.75],
            "projected_slice_spacing_mm": slice_spacing,
            "row_direction": [1, 0, 0],
            "column_direction": [0, 1, 0],
            "normal_direction": [0, 0, 1],
            "voxel_volume_mm3": voxel_volume,
            "geometry_matches_source": True,
            "resampled": False,
        },
        "measurement": {
            "status": "computed_unreviewed",
            "method": "binary_voxel_count_times_native_voxel_determinant",
            "foreground_voxel_count": 3,
            "volume_mm3": 3 * voxel_volume,
            "volume_ml": 3 * voxel_volume / 1000,
            "mask_pixel_sha256": _sha256(bytes(dense)),
            "boundary_uncertainty": "not_quantified",
        },
        "files": {
            "dicom_seg": {
                "filename": "segmentation.dcm",
                "bytes": len(seg_bytes),
                "sha256": _sha256(seg_bytes),
            }
        },
        "review": {"status": "unreviewed"},
        "permitted_uses": {
            "source_overlay": True,
            "mask_overlay": True,
            "exact_timepoint_volume": "computed_unreviewed_only",
            "longitudinal_link": False,
            "percent_change": False,
            "response_classification": False,
            "diagnosis": False,
            "clinical_conclusion": False,
        },
        "limitations": [
            "The boundary and lesion identity are unreviewed.",
            "The volume is geometry arithmetic, not a diagnosis.",
            "The artifact does not establish biological tumor burden.",
            "The artifact cannot classify treatment response.",
            "Acquisition and boundary differences can change a future measurement.",
        ],
    }
    archive = tmp_path / "lesion-volume.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("evidence.json", json.dumps(evidence, indent=2) + "\n")
        bundle.writestr("segmentation.dcm", seg_bytes)
        bundle.writestr("README.txt", "Sensitive local unreviewed lesion ROI evidence.\n")
    return archive, source_root, evidence


def test_validates_source_bound_sparse_binary_seg_and_recomputes_volume(tmp_path: Path) -> None:
    archive, source_root, evidence = _build_bundle(tmp_path)
    schema = json.loads(
        (
            Path(__file__).parents[3]
            / "schemas"
            / "scanview-lesion-volume-evidence-v1.schema.json"
        ).read_text()
    )
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(evidence)
    summary = lesion_volume_archive_summary(archive, source_root)

    assert summary == {
        "valid": True,
        "errors": [],
        "schema_version": "1.0.0",
        "artifact_type": "scanview.lesion-volume-evidence",
        "artifact_id": evidence["artifact_id"],
        "artifact_state": "draft_unreviewed",
        "validation_state": "source_validated_pending_review",
        "review_status": "unreviewed",
        "source_validated": True,
        "modality": "MR",
        "segment_count": 1,
        "computed_unreviewed_foreground_voxels": 3,
        "computed_unreviewed_volume_mm3": pytest.approx(2.25),
        "computed_unreviewed_volume_ml": pytest.approx(0.00225),
        "boundary_uncertainty": "not_quantified",
        "evidence_use": "exact_timepoint_unreviewed_only",
        "longitudinal_link": False,
        "percent_change": False,
        "response_classification": False,
        "diagnosis": False,
        "clinical_conclusion": False,
    }
    serialized = json.dumps(summary)
    assert "SYNTHETIC" not in serialized
    assert str(source_root) not in serialized
    assert evidence["segment"]["label"] not in serialized


def test_rejects_live_source_byte_tampering(tmp_path: Path) -> None:
    archive, source_root, _ = _build_bundle(tmp_path)
    with (source_root / "source-1.dcm").open("ab") as stream:
        stream.write(b"changed")

    summary = lesion_volume_archive_summary(archive, source_root)
    assert not summary["valid"]
    assert "an exact source instance is missing or its bytes changed" in summary["errors"]
    assert summary["computed_unreviewed_volume_mm3"] is None


def test_rejects_irregular_native_slice_spacing(tmp_path: Path) -> None:
    archive, source_root, _ = _build_bundle(tmp_path, positions=[0.0, 2.0, 5.0])
    summary = lesion_volume_archive_summary(archive, source_root)
    assert not summary["valid"]
    assert "source slice spacing is irregular or contains a gap" in summary["errors"]


def test_rejects_sidecar_volume_change(tmp_path: Path) -> None:
    archive, source_root, evidence = _build_bundle(tmp_path)
    evidence["measurement"]["volume_mm3"] = 999
    replacement = tmp_path / "changed.zip"
    with zipfile.ZipFile(archive) as original, zipfile.ZipFile(
        replacement, "w", compression=zipfile.ZIP_DEFLATED
    ) as changed:
        for name in ("segmentation.dcm", "README.txt"):
            changed.writestr(name, original.read(name))
        changed.writestr("evidence.json", json.dumps(evidence))

    summary = lesion_volume_archive_summary(replacement, source_root)
    assert not summary["valid"]
    assert "recomputed volume_mm3 does not match evidence.json" in summary["errors"]


def test_rejects_duplicate_sidecar_fields(tmp_path: Path) -> None:
    archive, source_root, evidence = _build_bundle(tmp_path)
    replacement = tmp_path / "duplicate-field.zip"
    duplicated = (
        b'{"schema_version":"1.0.0",'
        + json.dumps(evidence, separators=(",", ":")).encode()[1:]
    )
    with zipfile.ZipFile(archive) as original, zipfile.ZipFile(
        replacement, "w", compression=zipfile.ZIP_DEFLATED
    ) as changed:
        changed.writestr("evidence.json", duplicated)
        changed.writestr("segmentation.dcm", original.read("segmentation.dcm"))
        changed.writestr("README.txt", original.read("README.txt"))

    summary = lesion_volume_archive_summary(replacement, source_root)
    assert not summary["valid"]
    assert "evidence.json is not strict valid UTF-8 JSON" in summary["errors"]


def test_rejects_incomplete_dicom_reference_set(tmp_path: Path) -> None:
    archive, source_root, evidence = _build_bundle(tmp_path)
    with zipfile.ZipFile(archive) as original:
        dataset = dcmread(io.BytesIO(original.read("segmentation.dcm")))
        del dataset.ReferencedSeriesSequence[0].ReferencedInstanceSequence[-1]
        output = io.BytesIO()
        dataset.save_as(output, enforce_file_format=True)
        seg_bytes = output.getvalue()
        readme = original.read("README.txt")
    evidence["files"]["dicom_seg"] = {
        "filename": "segmentation.dcm",
        "bytes": len(seg_bytes),
        "sha256": _sha256(seg_bytes),
    }
    replacement = tmp_path / "incomplete-references.zip"
    with zipfile.ZipFile(replacement, "w", compression=zipfile.ZIP_DEFLATED) as changed:
        changed.writestr("evidence.json", json.dumps(evidence))
        changed.writestr("segmentation.dcm", seg_bytes)
        changed.writestr("README.txt", readme)

    summary = lesion_volume_archive_summary(replacement, source_root)
    assert not summary["valid"]
    assert "DICOM SEG referenced instances do not match the exact source set" in summary["errors"]


def test_rejects_per_frame_source_without_sop_class(tmp_path: Path) -> None:
    archive, source_root, evidence = _build_bundle(tmp_path)
    with zipfile.ZipFile(archive) as original:
        dataset = dcmread(io.BytesIO(original.read("segmentation.dcm")))
        del (
            dataset.PerFrameFunctionalGroupsSequence[0]
            .DerivationImageSequence[0]
            .SourceImageSequence[0]
            .ReferencedSOPClassUID
        )
        output = io.BytesIO()
        dataset.save_as(output, enforce_file_format=True)
        seg_bytes = output.getvalue()
        readme = original.read("README.txt")
    evidence["files"]["dicom_seg"] = {
        "filename": "segmentation.dcm",
        "bytes": len(seg_bytes),
        "sha256": _sha256(seg_bytes),
    }
    replacement = tmp_path / "missing-frame-sop-class.zip"
    with zipfile.ZipFile(replacement, "w", compression=zipfile.ZIP_DEFLATED) as changed:
        changed.writestr("evidence.json", json.dumps(evidence))
        changed.writestr("segmentation.dcm", seg_bytes)
        changed.writestr("README.txt", readme)

    summary = lesion_volume_archive_summary(replacement, source_root)
    assert not summary["valid"]
    assert "a DICOM SEG frame does not reference an exact source instance" in summary["errors"]


def test_rejects_missing_per_frame_derivation_semantics(tmp_path: Path) -> None:
    archive, source_root, evidence = _build_bundle(tmp_path)
    with zipfile.ZipFile(archive) as original:
        dataset = dcmread(io.BytesIO(original.read("segmentation.dcm")))
        derivation = dataset.PerFrameFunctionalGroupsSequence[0].DerivationImageSequence[0]
        del derivation.DerivationCodeSequence
        del derivation.SourceImageSequence[0].PurposeOfReferenceCodeSequence
        output = io.BytesIO()
        dataset.save_as(output, enforce_file_format=True)
        seg_bytes = output.getvalue()
        readme = original.read("README.txt")
    evidence["files"]["dicom_seg"] = {
        "filename": "segmentation.dcm",
        "bytes": len(seg_bytes),
        "sha256": _sha256(seg_bytes),
    }
    replacement = tmp_path / "missing-derivation-semantics.zip"
    with zipfile.ZipFile(replacement, "w", compression=zipfile.ZIP_DEFLATED) as changed:
        changed.writestr("evidence.json", json.dumps(evidence))
        changed.writestr("segmentation.dcm", seg_bytes)
        changed.writestr("README.txt", readme)

    summary = lesion_volume_archive_summary(replacement, source_root)
    assert not summary["valid"]
    assert "a DICOM SEG frame does not declare the Segmentation derivation code" in summary["errors"]
    assert (
        "a DICOM SEG frame does not declare the source-image processing purpose code"
        in summary["errors"]
    )


def test_rejects_seg_geometry_or_dimension_mismatch(tmp_path: Path) -> None:
    archive, source_root, evidence = _build_bundle(tmp_path)
    with zipfile.ZipFile(archive) as original:
        dataset = dcmread(io.BytesIO(original.read("segmentation.dcm")))
        dataset.SharedFunctionalGroupsSequence[0].PixelMeasuresSequence[0].PixelSpacing = [9, 9]
        dataset.PerFrameFunctionalGroupsSequence[0].FrameContentSequence[0].DimensionIndexValues = [1, 3]
        output = io.BytesIO()
        dataset.save_as(output, enforce_file_format=True)
        seg_bytes = output.getvalue()
        readme = original.read("README.txt")
    evidence["files"]["dicom_seg"] = {
        "filename": "segmentation.dcm",
        "bytes": len(seg_bytes),
        "sha256": _sha256(seg_bytes),
    }
    replacement = tmp_path / "wrong-seg-geometry.zip"
    with zipfile.ZipFile(replacement, "w", compression=zipfile.ZIP_DEFLATED) as changed:
        changed.writestr("evidence.json", json.dumps(evidence))
        changed.writestr("segmentation.dcm", seg_bytes)
        changed.writestr("README.txt", readme)

    summary = lesion_volume_archive_summary(replacement, source_root)
    assert not summary["valid"]
    assert "DICOM SEG pixel measures do not match the native source grid" in summary["errors"]
    assert (
        "a DICOM SEG frame dimension index does not match its source plane"
        in summary["errors"]
    )


def test_rejects_extra_archive_member(tmp_path: Path) -> None:
    archive, source_root, _ = _build_bundle(tmp_path)
    with zipfile.ZipFile(archive, "a") as bundle:
        bundle.writestr("unexpected.txt", "no")
    summary = lesion_volume_archive_summary(archive, source_root)
    assert not summary["valid"]
    assert summary["errors"] == [
        "archive must contain exactly evidence.json, segmentation.dcm, and README.txt"
    ]


def _build_review_bundle(
    tmp_path: Path,
    *,
    decision: str = "accepted_for_discussion",
) -> tuple[Path, Path, dict, dict]:
    evidence_archive, source_root, evidence = _build_bundle(tmp_path)
    evidence_bytes = evidence_archive.read_bytes()
    accepted = decision == "accepted_for_discussion"
    visible_decision = decision.replace("_", " ")
    review_page = (
        "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<title>Manual ROI review</title></head><body>"
        "<h1>SELF-ATTESTED REVIEW FOR DISCUSSION ONLY · IDENTITY NOT VERIFIED · "
        "NOT A DIAGNOSIS · NO LONGITUDINAL OR RESPONSE CONCLUSION</h1>"
        f"<p>{visible_decision}</p><p>Synthetic Reviewer</p><p>neuro oncologist</p>"
        "<p>Synthetic enhancing-tissue discussion region.</p>"
        "<p>Include contiguous synthetic signal.</p>"
        "<p>Exclude synthetic vessels, edema, and cavity.</p></body></html>\n"
    ).encode()
    readme = b"Sensitive local manual ROI boundary review.\n"
    checklist = {
        "original_images_reviewed": accepted,
        "full_boundary_reviewed": accepted,
        "all_three_planes_reviewed": accepted,
        "source_overlay_reviewed": accepted,
        "motion_considered": accepted,
        "partial_volume_considered": accepted,
        "treatment_effect_considered": accepted,
        "acquisition_protocol_considered": accepted,
    }
    record = {
        "schema_version": "1.0.0",
        "artifact_type": "scanview.lesion-volume-review",
        "review_id": "review_12345678-1234-4abc-8def-1234567890ab",
        "created_at": "2026-08-28T13:00:00.000Z",
        "review_status": decision,
        "local_only": True,
        "sensitive": True,
        "deidentified": False,
        "source_snapshot": {
            "evidence_artifact_id": evidence["artifact_id"],
            "patient_context_id": evidence["source"].get("patient_context_id"),
            "study_id": evidence["source"]["study_id"],
            "series_id": evidence["source"]["series_id"],
            "frame_of_reference_id": evidence["source"]["frame_of_reference_id"],
            "modality": evidence["source"]["modality"],
            "source_set_sha256": evidence["source"]["source_set_sha256"],
            "mask_pixel_sha256": evidence["measurement"]["mask_pixel_sha256"],
            "foreground_voxel_count": evidence["measurement"]["foreground_voxel_count"],
            "volume_mm3": evidence["measurement"]["volume_mm3"],
            "volume_ml": evidence["measurement"]["volume_ml"],
            "boundary_uncertainty": evidence["measurement"]["boundary_uncertainty"],
        },
        "reviewer": {
            "name": "Synthetic Reviewer",
            "role": "neuro_oncologist",
            "organization": "Synthetic clinic",
            "identity_verification": "self_asserted_unverified",
        },
        "review": {
            "decision": decision,
            "acquisition_suitability": "suitable" if accepted else "uncertain",
            "planes_reviewed": ["axial", "coronal", "sagittal"],
            "represented_tissue": "Synthetic enhancing-tissue discussion region.",
            "inclusion_criteria": "Include contiguous synthetic signal.",
            "exclusion_criteria": "Exclude synthetic vessels, edema, and cavity.",
            "note": "Synthetic review only.",
            "checklist": checklist,
        },
        "attestation": REVIEW_ATTESTATION,
        "permitted_uses": {
            "source_boundary_discussion": True,
            "reviewed_volume_for_discussion": accepted,
            "eligible_for_future_pairing_review": accepted,
            "longitudinal_link": False,
            "percent_change": False,
            "response_classification": False,
            "diagnosis": False,
            "clinical_conclusion": False,
        },
        "files": {
            "evidence_archive": {
                "filename": "evidence.zip",
                "bytes": len(evidence_bytes),
                "sha256": _sha256(evidence_bytes),
            },
            "review_page": {
                "filename": "review.html",
                "bytes": len(review_page),
                "sha256": _sha256(review_page),
            },
            "readme": {
                "filename": "README.txt",
                "bytes": len(readme),
                "sha256": _sha256(readme),
            },
        },
        "limitations": REVIEW_LIMITATIONS,
    }
    review_archive = tmp_path / "lesion-volume-review.zip"
    with zipfile.ZipFile(review_archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("review.json", json.dumps(record, indent=2) + "\n")
        bundle.writestr("evidence.zip", evidence_bytes)
        bundle.writestr("review.html", review_page)
        bundle.writestr("README.txt", readme)
    return review_archive, source_root, record, evidence


def _replace_review_member(
    archive: Path,
    destination: Path,
    *,
    record: dict | None = None,
    replacements: dict[str, bytes] | None = None,
) -> Path:
    replacements = replacements or {}
    with zipfile.ZipFile(archive) as original, zipfile.ZipFile(
        destination, "w", compression=zipfile.ZIP_DEFLATED
    ) as changed:
        for name in ("review.json", "evidence.zip", "review.html", "README.txt"):
            if name == "review.json" and record is not None:
                changed.writestr(name, json.dumps(record, indent=2) + "\n")
            else:
                changed.writestr(name, replacements.get(name, original.read(name)))
    return destination


def test_validates_self_attested_boundary_review_and_exact_nested_source(
    tmp_path: Path,
) -> None:
    archive, source_root, record, _ = _build_review_bundle(tmp_path)
    schema = json.loads(
        (
            Path(__file__).parents[3]
            / "schemas"
            / "scanview-lesion-volume-review-v1.schema.json"
        ).read_text()
    )
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(record)
    summary = lesion_volume_review_summary(archive, source_root)

    assert summary == {
        "valid": True,
        "errors": [],
        "schema_version": "1.0.0",
        "artifact_type": "scanview.lesion-volume-review",
        "review_status": "accepted_for_discussion",
        "identity_verification": "self_asserted_unverified",
        "source_validated": True,
        "boundary_review_self_attested": True,
        "reviewed_volume_for_discussion": True,
        "eligible_for_future_pairing_review": True,
        "computed_unreviewed_volume_ml": pytest.approx(0.00225),
        "longitudinal_link": False,
        "percent_change": False,
        "response_classification": False,
        "diagnosis": False,
        "clinical_conclusion": False,
        "evidence_use": "single_timepoint_reviewed_for_discussion_only",
    }
    serialized = json.dumps(summary)
    assert "Synthetic Reviewer" not in serialized
    assert "Synthetic clinic" not in serialized
    assert str(source_root) not in serialized
    assert record["source_snapshot"]["study_id"] not in serialized


def test_validates_revision_record_without_pairing_eligibility(tmp_path: Path) -> None:
    archive, source_root, _, _ = _build_review_bundle(
        tmp_path, decision="revision_requested"
    )
    summary = lesion_volume_review_summary(archive, source_root)
    assert summary["valid"]
    assert summary["review_status"] == "revision_requested"
    assert not summary["reviewed_volume_for_discussion"]
    assert not summary["eligible_for_future_pairing_review"]
    assert summary["evidence_use"] == "single_timepoint_revision_or_rejection_only"


def test_rejects_review_when_exact_nested_source_changes(tmp_path: Path) -> None:
    archive, source_root, _, _ = _build_review_bundle(tmp_path)
    with (source_root / "source-0.dcm").open("ab") as stream:
        stream.write(b"changed")
    summary = lesion_volume_review_summary(archive, source_root)
    assert not summary["valid"]
    assert "nested lesion-volume evidence is invalid against the exact source" in summary["errors"]
    assert summary["computed_unreviewed_volume_ml"] is None
    assert summary["evidence_use"] == "none"


def test_rejects_snapshot_or_permission_escalation(tmp_path: Path) -> None:
    archive, source_root, record, _ = _build_review_bundle(tmp_path)
    record["source_snapshot"]["volume_ml"] = 99
    record["permitted_uses"]["percent_change"] = True
    changed = _replace_review_member(
        archive, tmp_path / "escalated-review.zip", record=record
    )
    summary = lesion_volume_review_summary(changed, source_root)
    assert not summary["valid"]
    assert "source_snapshot does not match the exact nested evidence" in summary["errors"]
    assert "permitted_uses do not match the review decision or safety locks" in summary["errors"]


def test_rejects_accepted_review_with_incomplete_boundary_checklist(tmp_path: Path) -> None:
    archive, source_root, record, _ = _build_review_bundle(tmp_path)
    record["review"]["checklist"]["full_boundary_reviewed"] = False
    changed = _replace_review_member(
        archive, tmp_path / "incomplete-review.zip", record=record
    )
    summary = lesion_volume_review_summary(changed, source_root)
    assert not summary["valid"]
    assert "acceptance for discussion requires every checklist item" in summary["errors"]


def test_rejects_accepted_review_without_opaque_patient_context(tmp_path: Path) -> None:
    archive, source_root, record, _ = _build_review_bundle(tmp_path)
    record["source_snapshot"]["patient_context_id"] = None
    changed = _replace_review_member(
        archive, tmp_path / "missing-patient-context-review.zip", record=record
    )
    summary = lesion_volume_review_summary(changed, source_root)
    assert not summary["valid"]
    assert (
        "acceptance for future pairing review requires an opaque patient context"
        in summary["errors"]
    )


def test_rejects_external_review_page_even_when_hash_is_updated(tmp_path: Path) -> None:
    archive, source_root, record, _ = _build_review_bundle(tmp_path)
    page = b'<!doctype html><html><body><a href="https://example.test">external</a></body></html>'
    record["files"]["review_page"] = {
        "filename": "review.html",
        "bytes": len(page),
        "sha256": _sha256(page),
    }
    changed = _replace_review_member(
        archive,
        tmp_path / "external-page-review.zip",
        record=record,
        replacements={"review.html": page},
    )
    summary = lesion_volume_review_summary(changed, source_root)
    assert not summary["valid"]
    assert "review.html must be a script-free self-contained local page" in summary["errors"]


def test_malformed_reviewer_fails_closed_without_an_exception(tmp_path: Path) -> None:
    archive, source_root, record, _ = _build_review_bundle(tmp_path)
    record["reviewer"] = []
    changed = _replace_review_member(
        archive, tmp_path / "malformed-reviewer.zip", record=record
    )

    summary = lesion_volume_review_summary(changed, source_root)

    assert not summary["valid"]
    assert "reviewer is invalid" in summary["errors"]
    assert "review.html does not present the exact review record" in summary["errors"]
    assert summary["evidence_use"] == "none"


def test_malformed_nested_evidence_fails_closed_without_an_exception(
    tmp_path: Path,
) -> None:
    archive, source_root, record, _ = _build_review_bundle(tmp_path)
    with zipfile.ZipFile(archive) as outer:
        original_evidence = outer.read("evidence.zip")
    malformed_stream = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(original_evidence)) as original, zipfile.ZipFile(
        malformed_stream, "w", compression=zipfile.ZIP_DEFLATED
    ) as malformed:
        malformed.writestr("evidence.json", "{}\n")
        malformed.writestr("segmentation.dcm", original.read("segmentation.dcm"))
        malformed.writestr("README.txt", original.read("README.txt"))
    malformed_evidence = malformed_stream.getvalue()
    record["files"]["evidence_archive"] = {
        "filename": "evidence.zip",
        "bytes": len(malformed_evidence),
        "sha256": _sha256(malformed_evidence),
    }
    changed = _replace_review_member(
        archive,
        tmp_path / "malformed-evidence.zip",
        record=record,
        replacements={"evidence.zip": malformed_evidence},
    )

    summary = lesion_volume_review_summary(changed, source_root)

    assert not summary["valid"]
    assert "nested lesion-volume evidence is invalid against the exact source" in summary["errors"]
    assert summary["computed_unreviewed_volume_ml"] is None
    assert summary["evidence_use"] == "none"


def test_rejects_duplicate_review_fields_and_extra_archive_member(tmp_path: Path) -> None:
    archive, source_root, _, _ = _build_review_bundle(tmp_path)
    with zipfile.ZipFile(archive) as original:
        duplicate_json = b'{"schema_version":"1.0.0",' + original.read("review.json")[1:]
    duplicate = _replace_review_member(
        archive,
        tmp_path / "duplicate-review.zip",
        replacements={"review.json": duplicate_json},
    )
    summary = lesion_volume_review_summary(duplicate, source_root)
    assert not summary["valid"]
    assert "review.json is not strict valid UTF-8 JSON" in summary["errors"]

    with zipfile.ZipFile(archive, "a") as changed:
        changed.writestr("unexpected.txt", "no")
    summary = lesion_volume_review_summary(archive, source_root)
    assert not summary["valid"]
    assert summary["errors"] == [
        "review archive must contain exactly review.json, evidence.zip, review.html, and README.txt"
    ]
