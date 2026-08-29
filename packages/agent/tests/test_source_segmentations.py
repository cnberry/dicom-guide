from __future__ import annotations

import hashlib
import http.client
import json
import sys
import threading
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydicom import dcmread
from pydicom.dataset import Dataset, FileDataset, FileMetaDataset
from pydicom.sequence import Sequence
from pydicom.tag import Tag
from pydicom.uid import (
    ExplicitVRLittleEndian,
    ImplicitVRLittleEndian,
    MRImageStorage,
    PYDICOM_IMPLEMENTATION_UID,
    SegmentationStorage,
    generate_uid,
)

from scanview_agent.catalog import build_catalog
from scanview_agent import source_segmentations
from scanview_agent.cli import main
from scanview_agent.source_segmentations import (
    build_source_segmentation_catalog,
    registry_segmentation_source_loader,
    source_segmentation_summary,
)
from scanview_agent.server import create_server


def _code(value: str, meaning: str, scheme: str = "DCM") -> Dataset:
    result = Dataset()
    result.CodeValue = value
    result.CodingSchemeDesignator = scheme
    result.CodeMeaning = meaning
    return result


def _part10(path: Path, sop_class_uid: str, sop_instance_uid: str) -> FileDataset:
    meta = FileMetaDataset()
    meta.FileMetaInformationVersion = b"\x00\x01"
    meta.MediaStorageSOPClassUID = sop_class_uid
    meta.MediaStorageSOPInstanceUID = sop_instance_uid
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    meta.ImplementationClassUID = PYDICOM_IMPLEMENTATION_UID
    return FileDataset(str(path), {}, file_meta=meta, preamble=b"\0" * 128)


def _source_image(
    path: Path,
    *,
    patient_id: str,
    study_uid: str,
    series_uid: str,
    frame_uid: str,
    sop_uid: str,
    index: int,
) -> None:
    dataset = _part10(path, str(MRImageStorage), sop_uid)
    dataset.SOPClassUID = MRImageStorage
    dataset.SOPInstanceUID = sop_uid
    dataset.PatientID = patient_id
    dataset.PatientName = "Synthetic^SourceSeg"
    dataset.StudyInstanceUID = study_uid
    dataset.SeriesInstanceUID = series_uid
    dataset.FrameOfReferenceUID = frame_uid
    dataset.Modality = "MR"
    dataset.StudyDate = "20260101"
    dataset.SeriesDate = "20260101"
    dataset.AcquisitionDate = "20260101"
    dataset.SeriesDescription = "Synthetic source segmentation MR"
    dataset.InstanceNumber = index + 1
    dataset.Rows = 2
    dataset.Columns = 3
    dataset.PixelSpacing = [1.0, 2.0]
    dataset.SliceThickness = 4.0
    dataset.SpacingBetweenSlices = 4.0
    dataset.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
    dataset.ImagePositionPatient = [0, 0, index * 4.0]
    dataset.SamplesPerPixel = 1
    dataset.PhotometricInterpretation = "MONOCHROME2"
    dataset.BitsAllocated = 16
    dataset.BitsStored = 12
    dataset.HighBit = 11
    dataset.PixelRepresentation = 0
    dataset.PixelData = bytes(12)
    dataset.save_as(path, enforce_file_format=True)


def _pack_frames(frames: list[list[int]]) -> bytes:
    bits = [value for frame in frames for value in frame]
    payload = bytearray((len(bits) + 7) // 8)
    for index, value in enumerate(bits):
        payload[index // 8] |= value << (index % 8)
    if len(payload) % 2:
        payload.append(0)
    return bytes(payload)


def _segmentation(
    path: Path,
    *,
    patient_id: str,
    study_uid: str,
    series_uid: str,
    frame_uid: str,
    source_series_uid: str,
    source_uids: list[str],
    wrong_orientation: bool = False,
) -> None:
    sop_uid = generate_uid()
    dataset = _part10(path, str(SegmentationStorage), sop_uid)
    dataset.SOPClassUID = SegmentationStorage
    dataset.SOPInstanceUID = sop_uid
    dataset.PatientID = patient_id
    dataset.PatientName = "Synthetic^SourceSeg"
    dataset.StudyInstanceUID = study_uid
    dataset.SeriesInstanceUID = series_uid
    dataset.FrameOfReferenceUID = frame_uid
    dataset.Modality = "SEG"
    dataset.SeriesNumber = 90
    dataset.InstanceNumber = 1
    dataset.ImageType = ["DERIVED", "PRIMARY"]
    dataset.ContentLabel = "SYNTHETIC"
    dataset.Rows = 2
    dataset.Columns = 3
    dataset.NumberOfFrames = 3
    dataset.SamplesPerPixel = 1
    dataset.PhotometricInterpretation = "MONOCHROME2"
    dataset.BitsAllocated = 1
    dataset.BitsStored = 1
    dataset.HighBit = 0
    dataset.PixelRepresentation = 0
    dataset.SegmentationType = "BINARY"
    dataset.SegmentsOverlap = "YES"

    segment_one = Dataset()
    segment_one.SegmentNumber = 1
    segment_one.SegmentLabel = "Source label one"
    segment_one.SegmentAlgorithmType = "MANUAL"
    segment_one.SegmentedPropertyCategoryCodeSequence = Sequence(
        [_code("49755003", "Morphologically Abnormal Structure", "SCT")]
    )
    segment_one.SegmentedPropertyTypeCodeSequence = Sequence(
        [_code("52988006", "Lesion", "SCT")]
    )
    segment_one.RecommendedDisplayCIELabValue = [40000, 30000, 50000]
    segment_two = Dataset()
    segment_two.SegmentNumber = 2
    segment_two.SegmentLabel = "Source label two"
    segment_two.SegmentAlgorithmType = "AUTOMATIC"
    segment_two.SegmentAlgorithmName = "Synthetic algorithm"
    segment_two.SegmentedPropertyCategoryCodeSequence = Sequence(
        [_code("49755003", "Morphologically Abnormal Structure", "SCT")]
    )
    segment_two.SegmentedPropertyTypeCodeSequence = Sequence(
        [_code("52988006", "Lesion", "SCT")]
    )
    dataset.SegmentSequence = Sequence([segment_one, segment_two])

    dimension_uid = generate_uid()
    dimension_organization = Dataset()
    dimension_organization.DimensionOrganizationUID = dimension_uid
    dataset.DimensionOrganizationSequence = Sequence([dimension_organization])
    segment_dimension = Dataset()
    segment_dimension.DimensionOrganizationUID = dimension_uid
    segment_dimension.DimensionIndexPointer = Tag(0x0062000B)
    segment_dimension.FunctionalGroupPointer = Tag(0x0062000A)
    position_dimension = Dataset()
    position_dimension.DimensionOrganizationUID = dimension_uid
    position_dimension.DimensionIndexPointer = Tag(0x00200032)
    position_dimension.FunctionalGroupPointer = Tag(0x00209113)
    dataset.DimensionIndexSequence = Sequence([segment_dimension, position_dimension])

    source_series = Dataset()
    source_series.SeriesInstanceUID = source_series_uid
    source_series.ReferencedInstanceSequence = Sequence([])
    for source_uid in source_uids:
        reference = Dataset()
        reference.ReferencedSOPClassUID = MRImageStorage
        reference.ReferencedSOPInstanceUID = source_uid
        source_series.ReferencedInstanceSequence.append(reference)
    dataset.ReferencedSeriesSequence = Sequence([source_series])

    shared = Dataset()
    measures = Dataset()
    measures.PixelSpacing = [1.0, 2.0]
    measures.SliceThickness = 4.0
    measures.SpacingBetweenSlices = 4.0
    shared.PixelMeasuresSequence = Sequence([measures])
    orientation = Dataset()
    orientation.ImageOrientationPatient = (
        [0, 1, 0, 1, 0, 0] if wrong_orientation else [1, 0, 0, 0, 1, 0]
    )
    shared.PlaneOrientationSequence = Sequence([orientation])
    dataset.SharedFunctionalGroupsSequence = Sequence([shared])

    frame_specs = [(1, 0), (1, 2), (2, 1)]
    dataset.PerFrameFunctionalGroupsSequence = Sequence([])
    for frame_index, (segment_number, source_index) in enumerate(frame_specs):
        group = Dataset()
        segment_identification = Dataset()
        segment_identification.ReferencedSegmentNumber = segment_number
        group.SegmentIdentificationSequence = Sequence([segment_identification])
        derivation = Dataset()
        derivation.DerivationCodeSequence = Sequence(
            [_code("113076", "Segmentation")]
        )
        source = Dataset()
        source.ReferencedSOPClassUID = MRImageStorage
        source.ReferencedSOPInstanceUID = source_uids[source_index]
        source.SpatialLocationsPreserved = "YES"
        source.PurposeOfReferenceCodeSequence = Sequence(
            [_code("121322", "Source Image for Image Processing Operation")]
        )
        derivation.SourceImageSequence = Sequence([source])
        group.DerivationImageSequence = Sequence([derivation])
        position = Dataset()
        position.ImagePositionPatient = [0, 0, source_index * 4.0]
        group.PlanePositionSequence = Sequence([position])
        content = Dataset()
        content.DimensionIndexValues = [segment_number, source_index + 1]
        content.InStackPositionNumber = source_index + 1
        content.StackID = "1"
        group.FrameContentSequence = Sequence([content])
        dataset.PerFrameFunctionalGroupsSequence.append(group)
    dataset.PixelData = _pack_frames(
        [
            [1, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 1],
            [0, 1, 1, 0, 0, 0],
        ]
    )
    dataset.save_as(path, enforce_file_format=True)


def _fixture(root: Path, *, wrong_orientation: bool = False):
    root.mkdir()
    patient_id = "SYNTHETIC-SEG"
    study_uid = generate_uid()
    source_series_uid = generate_uid()
    seg_series_uid = generate_uid()
    frame_uid = generate_uid()
    source_uids = [generate_uid() for _ in range(3)]
    for index, source_uid in enumerate(source_uids):
        _source_image(
            root / f"source-{index + 1}.dcm",
            patient_id=patient_id,
            study_uid=study_uid,
            series_uid=source_series_uid,
            frame_uid=frame_uid,
            sop_uid=source_uid,
            index=index,
        )
    seg_path = root / "segmentation.dcm"
    _segmentation(
        seg_path,
        patient_id=patient_id,
        study_uid=study_uid,
        series_uid=seg_series_uid,
        frame_uid=frame_uid,
        source_series_uid=source_series_uid,
        source_uids=source_uids,
        wrong_orientation=wrong_orientation,
    )
    catalog, registry = build_catalog(root, include_hashes=True)
    return catalog, registry, seg_path


def test_builds_multi_segment_read_only_native_masks(tmp_path: Path) -> None:
    catalog, registry, _ = _fixture(tmp_path / "dicom")
    artifact, masks, guarded = build_source_segmentation_catalog(
        catalog,
        registry_segmentation_source_loader(catalog, registry),
    )

    assert artifact["supported_segmentation_count"] == 1
    assert artifact["unsupported_segmentation_count"] == 0
    assert artifact["segment_count"] == 2
    state = artifact["segmentations"][0]
    assert state["grid"]["dimensions"] == [3, 2, 3]
    assert state["grid"]["voxel_volume_mm3"] == 8.0
    assert state["referenced_instance_count"] == 3
    assert state["segments"][0]["marked_voxel_count"] == 2
    assert state["segments"][0]["computed_volume_ml"] == 0.016
    assert state["segments"][1]["marked_voxel_count"] == 2
    assert state["segments"][1]["computed_volume_ml"] == 0.016
    assert state["creator_identity_authenticated"] is False
    assert state["source_segment_clinical_meaning"] == "not_assessed"
    assert state["scanview_interpretation_added"] is False
    assert len(guarded) == 4
    schema = json.loads(
        (
            Path(__file__).resolve().parents[3]
            / "schemas"
            / "scanview-source-segmentation-catalog-v1.schema.json"
        ).read_text()
    )
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(artifact)
    for segment in state["segments"]:
        payload = masks[(state["segmentation_id"], segment["segment_number"])]
        assert len(payload) == 18
        assert sum(payload) == 2
        assert hashlib.sha256(payload).hexdigest() == segment["mask_sha256"]

    summary = source_segmentation_summary(
        json.loads(json.dumps(artifact)),
        catalog=catalog,
        load_source=registry_segmentation_source_loader(catalog, registry),
    )
    assert summary == {
        "schema_version": "1.0.0",
        "artifact_type": "scanview.source-segmentation-summary",
        "valid": True,
        "errors": [],
        "supported_segmentation_count": 1,
        "unsupported_segmentation_count": 0,
        "segment_count": 2,
        "contains_segment_text": False,
        "contains_identifiers": False,
        "contains_paths": False,
        "contains_pixels": False,
        "contains_geometry": False,
        "contains_computed_volumes": False,
        "local_only": True,
        "external_api_required": False,
    }


def test_locks_resampled_or_mismatched_geometry_as_one_object(tmp_path: Path) -> None:
    catalog, registry, _ = _fixture(
        tmp_path / "dicom", wrong_orientation=True
    )
    artifact, masks, _ = build_source_segmentation_catalog(
        catalog,
        registry_segmentation_source_loader(catalog, registry),
    )

    assert artifact["supported_segmentation_count"] == 0
    assert artifact["unsupported_segmentation_count"] == 1
    assert "orientation does not match" in artifact["unsupported_segmentations"][0]["reason"]
    assert masks == {}


def test_accepts_supported_implicit_vr_little_endian_seg(tmp_path: Path) -> None:
    root = tmp_path / "dicom"
    _, _, seg_path = _fixture(root)
    dataset = dcmread(seg_path)
    dataset.file_meta.TransferSyntaxUID = ImplicitVRLittleEndian
    dataset.save_as(
        seg_path,
        implicit_vr=True,
        little_endian=True,
        enforce_file_format=True,
    )
    catalog, registry = build_catalog(root, include_hashes=True)

    artifact, masks, _ = build_source_segmentation_catalog(
        catalog,
        registry_segmentation_source_loader(catalog, registry),
    )

    assert artifact["supported_segmentation_count"] == 1
    assert artifact["unsupported_segmentation_count"] == 0
    assert len(masks) == 2


def test_locks_mismatched_top_level_source_sop_class(tmp_path: Path) -> None:
    root = tmp_path / "dicom"
    _, _, seg_path = _fixture(root)
    dataset = dcmread(seg_path)
    dataset.ReferencedSeriesSequence[0].ReferencedInstanceSequence[
        0
    ].ReferencedSOPClassUID = SegmentationStorage
    dataset.save_as(seg_path, enforce_file_format=True)
    catalog, registry = build_catalog(root, include_hashes=True)

    artifact, masks, _ = build_source_segmentation_catalog(
        catalog,
        registry_segmentation_source_loader(catalog, registry),
    )

    assert artifact["supported_segmentation_count"] == 0
    assert artifact["unsupported_segmentation_count"] == 1
    assert "unavailable source reference" in artifact["unsupported_segmentations"][0]["reason"]
    assert masks == {}


def test_accepts_complete_series_reference_when_empty_planes_are_omitted(
    tmp_path: Path,
) -> None:
    root = tmp_path / "dicom"
    _, _, seg_path = _fixture(root)
    dataset = dcmread(seg_path)
    first_frame = dataset.PerFrameFunctionalGroupsSequence[0]
    third_frame = dataset.PerFrameFunctionalGroupsSequence[2]
    third_frame.FrameContentSequence[0].DimensionIndexValues = [2, 2]
    dataset.PerFrameFunctionalGroupsSequence = Sequence([first_frame, third_frame])
    dataset.NumberOfFrames = 2
    dataset.PixelData = _pack_frames(
        [
            [1, 0, 0, 1, 0, 0],
            [1, 1, 0, 0, 0, 0],
        ]
    )
    dataset.save_as(seg_path, enforce_file_format=True)
    catalog, registry = build_catalog(root, include_hashes=True)

    artifact, masks, _ = build_source_segmentation_catalog(
        catalog,
        registry_segmentation_source_loader(catalog, registry),
    )

    assert artifact["supported_segmentation_count"] == 1
    assert artifact["unsupported_segmentation_count"] == 0
    state = artifact["segmentations"][0]
    assert state["frame_count"] == 2
    assert state["referenced_instance_count"] == 3
    assert len(state["referenced_series"]["referenced_instance_ids"]) == 3
    assert [segment["marked_voxel_count"] for segment in state["segments"]] == [2, 2]
    assert len(masks) == 2


def test_requires_explicit_preserved_spatial_locations(tmp_path: Path) -> None:
    root = tmp_path / "dicom"
    _, _, seg_path = _fixture(root)
    dataset = dcmread(seg_path)
    dataset.PerFrameFunctionalGroupsSequence[0].DerivationImageSequence[
        0
    ].SourceImageSequence[0].SpatialLocationsPreserved = "NO"
    dataset.save_as(seg_path, enforce_file_format=True)
    catalog, registry = build_catalog(root, include_hashes=True)

    artifact, masks, _ = build_source_segmentation_catalog(
        catalog,
        registry_segmentation_source_loader(catalog, registry),
    )

    assert artifact["supported_segmentation_count"] == 0
    assert "explicitly preserve" in artifact["unsupported_segmentations"][0]["reason"]
    assert masks == {}


def test_requires_consistent_multiframe_dimensions(tmp_path: Path) -> None:
    root = tmp_path / "dicom"
    _, _, seg_path = _fixture(root)
    dataset = dcmread(seg_path)
    dataset.PerFrameFunctionalGroupsSequence[0].FrameContentSequence[
        0
    ].DimensionIndexValues = [2, 1]
    dataset.save_as(seg_path, enforce_file_format=True)
    catalog, registry = build_catalog(root, include_hashes=True)

    artifact, masks, _ = build_source_segmentation_catalog(
        catalog,
        registry_segmentation_source_loader(catalog, registry),
    )

    assert artifact["supported_segmentation_count"] == 0
    assert "dimension indexes contradict" in artifact["unsupported_segmentations"][0]["reason"]
    assert masks == {}


def test_rejects_nonadjacent_duplicate_source_planes(tmp_path: Path) -> None:
    root = tmp_path / "dicom"
    _fixture(root)
    third = dcmread(root / "source-3.dcm")
    third.ImagePositionPatient = [0, 0, 0]
    third.save_as(root / "source-3.dcm", enforce_file_format=True)
    catalog, registry = build_catalog(root, include_hashes=True)

    artifact, masks, _ = build_source_segmentation_catalog(
        catalog,
        registry_segmentation_source_loader(catalog, registry),
    )

    assert artifact["supported_segmentation_count"] == 0
    assert "overlap or are duplicated" in artifact["unsupported_segmentations"][0]["reason"]
    assert masks == {}


def test_preflights_one_catalog_wide_dense_mask_budget(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "dicom"
    _, _, seg_path = _fixture(root)
    duplicate = dcmread(seg_path)
    duplicate_uid = generate_uid()
    duplicate.SOPInstanceUID = duplicate_uid
    duplicate.file_meta.MediaStorageSOPInstanceUID = duplicate_uid
    duplicate.save_as(root / "segmentation-2.dcm", enforce_file_format=True)
    catalog, registry = build_catalog(root, include_hashes=True)
    monkeypatch.setattr(source_segmentations, "MAX_TOTAL_MASK_BYTES", 50)

    artifact, masks, _ = build_source_segmentation_catalog(
        catalog,
        registry_segmentation_source_loader(catalog, registry),
    )

    assert artifact["segmentation_count"] == 2
    assert artifact["supported_segmentation_count"] == 1
    assert artifact["unsupported_segmentation_count"] == 1
    assert "aggregate local safety bound" in artifact["unsupported_segmentations"][0]["reason"]
    assert sum(len(payload) for payload in masks.values()) == 36


def test_preflights_catalog_wide_decoded_frame_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "dicom"
    catalog, registry, _ = _fixture(root)
    monkeypatch.setattr(source_segmentations, "MAX_TOTAL_DECODED_FRAME_VOXELS", 17)

    artifact, masks, _ = build_source_segmentation_catalog(
        catalog,
        registry_segmentation_source_loader(catalog, registry),
    )

    assert artifact["supported_segmentation_count"] == 0
    assert "catalog-wide local processing bound" in artifact["unsupported_segmentations"][0]["reason"]
    assert masks == {}


def test_validation_fails_after_exact_source_change_without_echoing_content(
    tmp_path: Path,
) -> None:
    catalog, registry, _ = _fixture(tmp_path / "dicom")
    loader = registry_segmentation_source_loader(catalog, registry)
    artifact, _, _ = build_source_segmentation_catalog(catalog, loader)
    source_path = next(
        path
        for instance_id, path in registry.items()
        if instance_id != artifact["segmentations"][0]["segmentation_id"]
    )
    source_path.write_bytes(source_path.read_bytes() + b"changed")

    summary = source_segmentation_summary(
        artifact,
        catalog=catalog,
        load_source=loader,
    )
    assert summary["valid"] is False
    assert summary["supported_segmentation_count"] == 0
    serialized = json.dumps(summary)
    assert "Source label" not in serialized
    assert str(source_path) not in serialized


def test_cli_writes_owner_only_catalog_and_privacy_minimized_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "dicom"
    _, _, _ = _fixture(root)
    artifact_path = tmp_path / "source-segmentations.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "scanview-agent",
            "source-segmentations",
            str(root),
            "--output",
            str(artifact_path),
        ],
    )
    main()
    assert artifact_path.stat().st_mode & 0o777 == 0o600
    assert json.loads(artifact_path.read_text())["supported_segmentation_count"] == 1

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "scanview-agent",
            "validate-source-segmentations",
            str(root),
            str(artifact_path),
        ],
    )
    main()
    valid = json.loads(capsys.readouterr().out)
    assert valid["valid"] is True
    assert valid["contains_segment_text"] is False
    assert valid["contains_paths"] is False
    assert valid["contains_computed_volumes"] is False

    changed = root / "source-1.dcm"
    changed.write_bytes(changed.read_bytes() + b"changed")
    with pytest.raises(SystemExit) as exit_info:
        main()
    assert exit_info.value.code == 1
    invalid_output = capsys.readouterr().out
    assert json.loads(invalid_output)["valid"] is False
    assert "Source label" not in invalid_output
    assert str(changed) not in invalid_output


def _http(
    port: int,
    path: str,
    *,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    connection.request("GET", path, headers=headers or {})
    response = connection.getresponse()
    body = response.read()
    result = response.status, dict(response.getheaders()), body
    connection.close()
    return result


def test_server_separates_agent_catalog_from_browser_only_mask_and_detects_change(
    tmp_path: Path,
) -> None:
    catalog, registry, _ = _fixture(tmp_path / "dicom")
    server = create_server(catalog, registry, port=0, token="local-agent-token")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, _, _ = _http(server.server_port, "/v1/source-segmentations")
        assert status == 401
        status, headers, body = _http(
            server.server_port,
            "/v1/source-segmentations",
            headers={"Authorization": "Bearer local-agent-token"},
        )
        assert status == 200
        assert headers["Cache-Control"] == "no-store"
        artifact = json.loads(body)
        state = artifact["segmentations"][0]
        segment = state["segments"][0]
        mask_path = (
            f"/v1/source-segmentations/{state['segmentation_id']}"
            f"/masks/{segment['segment_number']}"
        )
        status, _, _ = _http(
            server.server_port,
            mask_path,
            headers={"Authorization": "Bearer local-agent-token"},
        )
        assert status == 403

        status, headers, _ = _http(
            server.server_port,
            f"/?session={server.browser_bootstrap_token}",
        )
        assert status == 303
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        status, headers, mask = _http(
            server.server_port,
            mask_path,
            headers={"Cookie": cookie},
        )
        assert status == 200
        assert headers["Content-Type"] == "application/vnd.scanview.source-binary-mask"
        assert headers["X-Content-SHA256"] == segment["mask_sha256"]
        assert len(mask) == 18
        assert sum(mask) == 2

        changed_source = registry[state["referenced_series"]["ordered_instance_ids"][0]]
        changed_source.write_bytes(changed_source.read_bytes() + b"changed")
        status, _, body = _http(
            server.server_port,
            "/v1/source-segmentations",
            headers={"Cookie": cookie},
        )
        assert status == 409
        assert json.loads(body) == {"error": "source_segmentation_inputs_changed"}
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
