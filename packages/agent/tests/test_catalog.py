from __future__ import annotations

import hashlib
import json
import math
import stat
import sys
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, MRImageStorage, generate_uid

from scanview_agent.catalog import build_catalog
from scanview_agent.cli import main
from scanview_agent.comparison import suggest_pairs
from scanview_agent.measurements import build_measurement_comparison, measurement_packet_summary
from scanview_agent.server import serve


def write_dicom(
    path: Path,
    *,
    study_uid: str,
    series_uid: str,
    date: str,
    instance: int,
    description: str = "T1 POST",
) -> None:
    sop_uid = generate_uid()
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = MRImageStorage
    meta.MediaStorageSOPInstanceUID = sop_uid
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    dataset = FileDataset(path, {}, file_meta=meta, preamble=b"\0" * 128)
    dataset.SOPClassUID = MRImageStorage
    dataset.SOPInstanceUID = sop_uid
    dataset.StudyInstanceUID = study_uid
    dataset.SeriesInstanceUID = series_uid
    dataset.FrameOfReferenceUID = generate_uid()
    dataset.PatientName = "TEST^PRIVATE"
    dataset.PatientID = "SECRET-123"
    dataset.StudyDate = date
    dataset.SeriesDate = date
    dataset.Modality = "MR"
    dataset.SeriesDescription = description
    dataset.ProtocolName = "Synthetic fixture"
    dataset.BodyPartExamined = "BRAIN"
    dataset.ImageType = ["ORIGINAL", "PRIMARY"]
    dataset.InstanceNumber = instance
    dataset.Rows = 2
    dataset.Columns = 2
    dataset.PixelSpacing = [1.0, 1.0]
    dataset.SliceThickness = 1.0
    dataset.ImagePositionPatient = [0.0, 0.0, float(instance)]
    dataset.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
    dataset.SamplesPerPixel = 1
    dataset.PhotometricInterpretation = "MONOCHROME2"
    dataset.BitsAllocated = 16
    dataset.BitsStored = 12
    dataset.HighBit = 11
    dataset.PixelRepresentation = 0
    dataset.PixelData = b"\0" * 8
    dataset.save_as(path, enforce_file_format=True)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_catalog_is_read_only_and_excludes_direct_identifiers(tmp_path: Path) -> None:
    study_uid = generate_uid()
    source = tmp_path / "extensionless-image"
    write_dicom(source, study_uid=study_uid, series_uid=generate_uid(), date="20260101", instance=1)
    before = digest(source)

    catalog, registry = build_catalog(tmp_path)

    assert digest(source) == before
    assert catalog["source"]["dicom_instances"] == 1
    assert catalog["privacy"]["deidentified"] is False
    serialized = str(catalog)
    assert "TEST^PRIVATE" not in serialized
    assert "SECRET-123" not in serialized
    assert str(tmp_path) not in serialized
    assert len(registry) == 1
    assert all(path == source for path in registry.values())


def test_pair_suggestions_are_unreviewed_and_registration_gated(tmp_path: Path) -> None:
    study_one = generate_uid()
    study_two = generate_uid()
    series_one = generate_uid()
    series_two = generate_uid()
    write_dicom(
        tmp_path / "baseline-1",
        study_uid=study_one,
        series_uid=series_one,
        date="20260101",
        instance=1,
    )
    write_dicom(
        tmp_path / "baseline-2",
        study_uid=study_one,
        series_uid=series_one,
        date="20260101",
        instance=2,
    )
    write_dicom(
        tmp_path / "followup-1",
        study_uid=study_two,
        series_uid=series_two,
        date="20260201",
        instance=1,
    )
    write_dicom(
        tmp_path / "followup-2",
        study_uid=study_two,
        series_uid=series_two,
        date="20260201",
        instance=2,
    )
    catalog, _ = build_catalog(tmp_path, include_hashes=False)

    suggestions = suggest_pairs(catalog)

    assert len(suggestions["candidates"]) == 1
    candidate = suggestions["candidates"][0]
    assert candidate["auto_approved"] is False
    assert candidate["review_status"] == "unreviewed"
    assert candidate["derived_operations"]["overlay"] == "locked_pending_registration_qc"


def test_server_refuses_non_loopback_binding() -> None:
    try:
        serve({"schema_version": "1.0.0"}, {}, host="0.0.0.0", port=0)
    except ValueError as error:
        assert "loopback" in str(error)
    else:
        raise AssertionError("A non-loopback bind must never be accepted")


def test_presentation_states_are_excluded_from_pair_candidates() -> None:
    catalog = {
        "schema_version": "1.0.0",
        "studies": [
            {
                "acquisition_date": "20260101",
                "series": [
                    {
                        "id": "series_pr_baseline",
                        "modality": "PR",
                        "series_description": "Presentation state",
                        "image_type": [],
                        "instance_count": 3,
                    }
                ],
            },
            {
                "acquisition_date": "20260201",
                "series": [
                    {
                        "id": "series_pr_followup",
                        "modality": "PR",
                        "series_description": "Presentation state",
                        "image_type": [],
                        "instance_count": 3,
                    }
                ],
            },
        ],
    }

    suggestions = suggest_pairs(catalog)

    assert suggestions["candidates"] == []
    assert len(suggestions["excluded_series"]) == 2
    assert all(
        "unsupported_non_pixel_modality" in item["reasons"]
        for item in suggestions["excluded_series"]
    )


def test_measurement_packet_validation_preserves_unreviewed_source_provenance() -> None:
    packet = {
        "schema_version": "1.0.0",
        "created_at": "2026-08-28T00:00:00Z",
        "review_status": "unreviewed",
        "measurements": [
            {
                "tracking_id": "length:test",
                "type": "length",
                "review_status": "unreviewed",
                "source": {
                    "series_id": "0123456789abcdef",
                    "instance_id": "fedcba9876543210",
                    "frame_of_reference_id": "0011223344556677",
                },
                "geometry": {
                    "coordinate_system": "DICOM patient LPS",
                    "world_points": [[0, 0, 0], [3, 4, 0]],
                },
                "result": {"value": 5, "unit": "mm"},
                "method": {
                    "name": "manual_two_point_length",
                    "implementation": "Cornerstone3D LengthTool",
                },
                "limitations": ["Manual and unreviewed."],
            }
        ],
        "limitations": ["Not a diagnosis."],
    }

    assert measurement_packet_summary(packet) == {
        "valid": True,
        "schema_version": "1.0.0",
        "review_status": "unreviewed",
        "measurement_count": 1,
        "counts_by_type": {"length": 1, "bidirectional": 0, "elliptical_roi": 0},
        "errors": [],
    }

    packet["unexpected_patient_field"] = "must not be accepted"
    summary = measurement_packet_summary(packet)
    assert summary["valid"] is False
    assert "unsupported fields" in " ".join(summary["errors"])


def test_bidirectional_measurement_packet_validation() -> None:
    packet = {
        "schema_version": "2.0.0",
        "created_at": "2026-08-28T00:00:00Z",
        "review_status": "unreviewed",
        "measurements": [
            {
                "tracking_id": "bidirectional:test",
                "type": "bidirectional",
                "review_status": "unreviewed",
                "source": {
                    "series_id": "series_0123456789abcdef0123",
                    "instance_id": "instance_0123456789abcdef0123",
                },
                "geometry": {
                    "coordinate_system": "DICOM patient LPS",
                    "world_points": [[0, 0, 0], [10, 0, 0], [5, -2, 0], [5, 2, 0]],
                },
                "result": {
                    "long_axis": 10,
                    "short_axis": 4,
                    "product": 40,
                    "unit": "mm",
                    "product_unit": "mm2",
                },
                "method": {
                    "name": "manual_perpendicular_bidirectional",
                    "implementation": "Cornerstone3D BidirectionalTool",
                },
                "limitations": ["Manual and unreviewed."],
            }
        ],
        "limitations": ["Not a response category."],
    }

    summary = measurement_packet_summary(packet)

    assert summary["valid"] is True
    assert summary["counts_by_type"] == {
        "length": 0,
        "bidirectional": 1,
        "elliptical_roi": 0,
    }


def bidirectional_packet(
    tracking_id: str,
    long_axis: float,
    short_axis: float,
    *,
    series_id: str,
    unit: str = "mm",
) -> dict:
    result = (
        {
            "long_axis": long_axis,
            "short_axis": short_axis,
            "product": long_axis * short_axis,
            "unit": "mm",
            "product_unit": "mm2",
        }
        if unit == "mm"
        else {"unit": "unknown", "product_unit": "unknown"}
    )
    return {
        "schema_version": "2.0.0",
        "created_at": "2026-08-28T00:00:00Z",
        "review_status": "unreviewed",
        "measurements": [
            {
                "tracking_id": tracking_id,
                "type": "bidirectional",
                "review_status": "unreviewed",
                "source": {
                    "series_id": series_id,
                    "instance_id": "fedcba9876543210",
                },
                "geometry": {
                    "coordinate_system": "DICOM patient LPS",
                    "world_points": [
                        [0, 0, 0],
                        [long_axis, 0, 0],
                        [0, -short_axis / 2, 0],
                        [0, short_axis / 2, 0],
                    ],
                },
                "result": result,
                "method": {
                    "name": "manual_perpendicular_bidirectional",
                    "implementation": "Cornerstone3D BidirectionalTool",
                },
                "limitations": ["Manual and unreviewed."],
            }
        ],
        "limitations": ["Not a response category."],
    }


def elliptical_roi_packet(
    tracking_id: str,
    major_axis: float,
    minor_axis: float,
    *,
    series_id: str,
) -> dict:
    return {
        "schema_version": "3.0.0",
        "created_at": "2026-08-28T00:00:00Z",
        "review_status": "unreviewed",
        "measurements": [
            {
                "tracking_id": tracking_id,
                "type": "elliptical_roi",
                "review_status": "unreviewed",
                "source": {
                    "series_id": series_id,
                    "instance_id": "fedcba9876543210",
                },
                "geometry": {
                    "coordinate_system": "DICOM patient LPS",
                    "world_points": [
                        [0, -minor_axis / 2, 0],
                        [0, minor_axis / 2, 0],
                        [-major_axis / 2, 0, 0],
                        [major_axis / 2, 0, 0],
                    ],
                },
                "result": {
                    "major_axis": major_axis,
                    "minor_axis": minor_axis,
                    "area": math.pi * (major_axis / 2) * (minor_axis / 2),
                    "unit": "mm",
                    "area_unit": "mm2",
                },
                "method": {
                    "name": "manual_elliptical_roi",
                    "implementation": "Cornerstone3D EllipticalROITool",
                },
                "limitations": ["Manual 2D ROI; not a segmentation or response verdict."],
            }
        ],
        "limitations": ["Not a response category."],
    }


def test_elliptical_roi_validation_and_geometry_consistency() -> None:
    packet = elliptical_roi_packet(
        "elliptical_roi:test", 10, 4, series_id="0123456789abcdef"
    )

    summary = measurement_packet_summary(packet)

    assert summary["valid"] is True
    assert summary["counts_by_type"] == {
        "length": 0,
        "bidirectional": 0,
        "elliptical_roi": 1,
    }

    packet["measurements"][0]["result"]["area"] = 999
    summary = measurement_packet_summary(packet)
    assert summary["valid"] is False
    assert "disagrees with its geometry" in " ".join(summary["errors"])


def test_explicit_elliptical_roi_comparison_is_numeric_and_unreviewed() -> None:
    comparison = build_measurement_comparison(
        elliptical_roi_packet(
            "elliptical_roi:baseline", 10, 4, series_id="0123456789abcdef"
        ),
        elliptical_roi_packet(
            "elliptical_roi:followup", 8, 3, series_id="1123456789abcdef"
        ),
        baseline_tracking_id="elliptical_roi:baseline",
        followup_tracking_id="elliptical_roi:followup",
    )

    assert comparison["review_status"] == "unreviewed"
    assert comparison["candidate_interpretations"] == []
    assert [item["metric"] for item in comparison["computed_results"]] == [
        "major_axis",
        "minor_axis",
        "elliptical_area",
    ]
    assert comparison["computed_results"][2]["unit"] == "mm2"
    assert math.isclose(comparison["computed_results"][2]["percent_change"], -40.0)

    repository_root = Path(__file__).parents[3]
    packet_schema = json.loads(
        (repository_root / "schemas" / "scanview-measurements-v3.schema.json").read_text()
    )
    comparison_schema = json.loads(
        (
            repository_root
            / "schemas"
            / "scanview-measurement-comparison-v1.schema.json"
        ).read_text()
    )
    Draft202012Validator.check_schema(packet_schema)
    Draft202012Validator(packet_schema, format_checker=FormatChecker()).validate(
        elliptical_roi_packet(
            "elliptical_roi:schema", 10, 4, series_id="0123456789abcdef"
        )
    )
    Draft202012Validator.check_schema(comparison_schema)
    Draft202012Validator(
        comparison_schema, format_checker=FormatChecker()
    ).validate(comparison)


def test_explicit_bidirectional_comparison_is_numeric_and_unreviewed() -> None:
    comparison = build_measurement_comparison(
        bidirectional_packet(
            "bidirectional:baseline", 10, 4, series_id="0123456789abcdef"
        ),
        bidirectional_packet(
            "bidirectional:followup", 8, 3, series_id="1123456789abcdef"
        ),
        baseline_tracking_id="bidirectional:baseline",
        followup_tracking_id="bidirectional:followup",
    )

    assert comparison["review_status"] == "unreviewed"
    assert comparison["pairing"]["method"] == "explicit_tracking_id_selection"
    assert comparison["candidate_interpretations"] == []
    assert comparison["computed_results"] == [
        {
            "metric": "long_axis",
            "baseline": 10.0,
            "followup": 8.0,
            "absolute_change": -2.0,
            "unit": "mm",
            "source_measurement_ids": [
                "bidirectional:baseline",
                "bidirectional:followup",
            ],
            "review_status": "unreviewed",
            "percent_change": -20.0,
        },
        {
            "metric": "short_axis",
            "baseline": 4.0,
            "followup": 3.0,
            "absolute_change": -1.0,
            "unit": "mm",
            "source_measurement_ids": [
                "bidirectional:baseline",
                "bidirectional:followup",
            ],
            "review_status": "unreviewed",
            "percent_change": -25.0,
        },
        {
            "metric": "bidimensional_product",
            "baseline": 40.0,
            "followup": 24.0,
            "absolute_change": -16.0,
            "unit": "mm2",
            "source_measurement_ids": [
                "bidirectional:baseline",
                "bidirectional:followup",
            ],
            "review_status": "unreviewed",
            "percent_change": -40.0,
        },
    ]
    assert "diagnosis-specific response criteria" in comparison["missing_context"]


def test_comparison_refuses_unknown_units_and_inconsistent_results() -> None:
    baseline = bidirectional_packet(
        "bidirectional:baseline", 10, 4, series_id="0123456789abcdef"
    )
    followup = bidirectional_packet(
        "bidirectional:followup",
        8,
        3,
        series_id="1123456789abcdef",
        unit="unknown",
    )

    try:
        build_measurement_comparison(
            baseline,
            followup,
            baseline_tracking_id="bidirectional:baseline",
            followup_tracking_id="bidirectional:followup",
        )
    except ValueError as error:
        assert "millimeter" in str(error)
    else:
        raise AssertionError("Unknown-unit measurements must not be compared")

    baseline["measurements"][0]["result"]["long_axis"] = 999
    summary = measurement_packet_summary(baseline)
    assert summary["valid"] is False
    assert "disagrees with its geometry" in " ".join(summary["errors"])


def test_comparison_refuses_the_same_source_series() -> None:
    baseline = bidirectional_packet(
        "bidirectional:baseline", 10, 4, series_id="0123456789abcdef"
    )
    followup = bidirectional_packet(
        "bidirectional:followup", 8, 3, series_id="0123456789abcdef"
    )

    try:
        build_measurement_comparison(
            baseline,
            followup,
            baseline_tracking_id="bidirectional:baseline",
            followup_tracking_id="bidirectional:followup",
        )
    except ValueError as error:
        assert "distinct source series" in str(error)
    else:
        raise AssertionError("A same-series measurement pair must not be treated as longitudinal")


def test_comparison_cli_writes_owner_only_unreviewed_output(
    tmp_path: Path, monkeypatch
) -> None:
    baseline_path = tmp_path / "baseline.json"
    followup_path = tmp_path / "followup.json"
    output_path = tmp_path / "comparison.json"
    baseline_path.write_text(
        json.dumps(
            bidirectional_packet(
                "bidirectional:baseline", 10, 4, series_id="0123456789abcdef"
            )
        )
    )
    followup_path.write_text(
        json.dumps(
            bidirectional_packet(
                "bidirectional:followup", 8, 3, series_id="1123456789abcdef"
            )
        )
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "scanview-agent",
            "compare-measurements",
            str(baseline_path),
            str(followup_path),
            "--baseline-id",
            "bidirectional:baseline",
            "--followup-id",
            "bidirectional:followup",
            "--output",
            str(output_path),
        ],
    )

    main()

    comparison = json.loads(output_path.read_text())
    assert comparison["candidate_interpretations"] == []
    assert comparison["review_status"] == "unreviewed"
    assert stat.S_IMODE(output_path.stat().st_mode) == 0o600
