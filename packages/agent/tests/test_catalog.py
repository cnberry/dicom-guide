from __future__ import annotations

import hashlib
from pathlib import Path

from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, MRImageStorage, generate_uid

from scanview_agent.catalog import build_catalog
from scanview_agent.comparison import suggest_pairs
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
