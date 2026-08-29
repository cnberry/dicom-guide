from __future__ import annotations

import copy
import hashlib
import json
import sys
import threading
from http import HTTPStatus
from http.client import HTTPConnection
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from pydicom.dataset import Dataset, FileDataset, FileMetaDataset
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, generate_uid

from scanview_agent.catalog import build_catalog, opaque_id
from scanview_agent.cli import main
from scanview_agent.presentation_states import (
    ARTIFACT_TYPE,
    GSPS_SOP_CLASS_UID,
    build_presentation_state_catalog,
    presentation_state_summary,
    registry_source_loader,
    validate_presentation_state_catalog,
)
from scanview_agent.server import create_server


def _file_dataset(path: Path, sop_class_uid: str, sop_instance_uid: str) -> FileDataset:
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = sop_class_uid
    meta.MediaStorageSOPInstanceUID = sop_instance_uid
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    meta.ImplementationClassUID = generate_uid()
    dataset = FileDataset(str(path), {}, file_meta=meta, preamble=b"\0" * 128)
    dataset.is_little_endian = True
    dataset.is_implicit_VR = False
    dataset.SOPClassUID = sop_class_uid
    dataset.SOPInstanceUID = sop_instance_uid
    dataset.SpecificCharacterSet = "ISO_IR 192"
    return dataset


def _write_fixture(
    root: Path,
    *,
    rotation: int = 0,
    voi_function: str | None = None,
    presentation_study_mismatch: bool = False,
    source_rescale: bool = False,
    presentation_aspect: tuple[int, int] = (1, 1),
    extended_bottom_right: bool = False,
    frame_scoped: bool = False,
    presentation_modality_transform: bool = False,
    presentation_lut_sequence: bool = False,
    mask_subtraction: bool = False,
    overlay_activation: bool = False,
    anchor_visibility: str = "Y",
    text: str = "12.3 mm",
    point: tuple[float, float] = (10.5, 20.5),
) -> tuple[Path, list[str]]:
    root.mkdir(parents=True, exist_ok=True)
    study_uid = generate_uid()
    image_series_uid = generate_uid()
    pr_series_uid = generate_uid()
    image_uids = [generate_uid(), generate_uid()]
    for index, instance_uid in enumerate(image_uids, 1):
        path = root / f"image-{index}.dcm"
        dataset = _file_dataset(path, str(CTImageStorage), instance_uid)
        dataset.PatientID = "SYNTHETIC-PRESENTATION-STATE"
        dataset.StudyInstanceUID = study_uid
        dataset.SeriesInstanceUID = image_series_uid
        dataset.StudyDate = "20260829"
        dataset.SeriesDate = "20260829"
        dataset.AcquisitionDate = "20260829"
        dataset.Modality = "CT"
        dataset.SeriesDescription = "SYNTHETIC CT"
        dataset.InstanceNumber = index
        dataset.Rows = 512
        dataset.Columns = 512
        dataset.PixelSpacing = [0.5, 0.5]
        dataset.SamplesPerPixel = 1
        dataset.PhotometricInterpretation = "MONOCHROME2"
        if source_rescale:
            dataset.RescaleSlope = 2
            dataset.RescaleIntercept = 0
        dataset.ImagePositionPatient = [0, 0, index]
        dataset.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
        dataset.save_as(path, enforce_file_format=True)

    pr_uid = generate_uid()
    pr_path = root / "presentation-state.dcm"
    pr = _file_dataset(pr_path, GSPS_SOP_CLASS_UID, pr_uid)
    pr.PatientID = "SYNTHETIC-PRESENTATION-STATE"
    pr.StudyInstanceUID = generate_uid() if presentation_study_mismatch else study_uid
    pr.SeriesInstanceUID = pr_series_uid
    pr.StudyDate = "20260829"
    pr.SeriesDate = "20260829"
    pr.ContentDate = "20260829"
    pr.ContentTime = "120000"
    pr.Modality = "PR"
    pr.SeriesDescription = "SYNTHETIC GSPS"
    pr.InstanceNumber = 1
    pr.ImageRotation = rotation
    pr.ImageHorizontalFlip = "N"
    pr.PresentationLUTShape = "IDENTITY"
    if presentation_modality_transform:
        pr.RescaleSlope = 2
        pr.RescaleIntercept = 0
    if presentation_lut_sequence:
        pr.PresentationLUTSequence = [Dataset()]
    if mask_subtraction:
        pr.MaskSubtractionSequence = [Dataset()]
    if overlay_activation:
        pr.add_new((0x6000, 0x1001), "CS", "LAYER 0")

    referenced_series = Dataset()
    referenced_series.SeriesInstanceUID = image_series_uid
    referenced_series.ReferencedImageSequence = []
    for instance_uid in image_uids:
        reference = Dataset()
        reference.ReferencedSOPClassUID = str(CTImageStorage)
        reference.ReferencedSOPInstanceUID = instance_uid
        if frame_scoped:
            reference.ReferencedFrameNumber = 1
        referenced_series.ReferencedImageSequence.append(reference)
    pr.ReferencedSeriesSequence = [referenced_series]

    voi = Dataset()
    voi.WindowCenter = "40"
    voi.WindowWidth = "400"
    if voi_function is not None:
        voi.VOILUTFunction = voi_function
    pr.SoftcopyVOILUTSequence = [voi]

    area = Dataset()
    area.DisplayedAreaTopLeftHandCorner = [1, 1]
    area.DisplayedAreaBottomRightHandCorner = (
        [513, 513] if extended_bottom_right else [512, 512]
    )
    area.PresentationSizeMode = "SCALE TO FIT"
    area.PresentationPixelAspectRatio = list(presentation_aspect)
    pr.DisplayedAreaSelectionSequence = [area]

    layer = Dataset()
    layer.GraphicLayer = "LAYER 0"
    layer.GraphicLayerOrder = 1
    pr.GraphicLayerSequence = [layer]

    annotation = Dataset()
    annotation.GraphicLayer = "LAYER 0"
    annotation_reference = Dataset()
    annotation_reference.ReferencedSOPClassUID = str(CTImageStorage)
    annotation_reference.ReferencedSOPInstanceUID = image_uids[0]
    annotation.ReferencedImageSequence = [annotation_reference]
    graphic = Dataset()
    graphic.GraphicAnnotationUnits = "PIXEL"
    graphic.GraphicDimensions = 2
    graphic.NumberOfGraphicPoints = 2
    graphic.GraphicData = [point[0], point[1], 30.5, 40.5]
    graphic.GraphicType = "POLYLINE"
    graphic.GraphicFilled = "N"
    annotation.GraphicObjectSequence = [graphic]
    text_object = Dataset()
    text_object.UnformattedTextValue = text
    text_object.AnchorPointAnnotationUnits = "PIXEL"
    text_object.AnchorPoint = [31.0, 41.0]
    text_object.AnchorPointVisibility = anchor_visibility
    annotation.TextObjectSequence = [text_object]
    pr.GraphicAnnotationSequence = [annotation]
    pr.save_as(pr_path, enforce_file_format=True)
    return pr_path, image_uids


def _artifact(root: Path) -> tuple[dict, dict, dict[str, Path]]:
    catalog, registry = build_catalog(root, include_hashes=True)
    artifact = build_presentation_state_catalog(
        catalog,
        registry_source_loader(catalog, registry),
        generated_at="2026-08-29T12:00:00Z",
    )
    return artifact, catalog, registry


def _schema() -> dict:
    return json.loads(
        (
            Path(__file__).parents[3]
            / "schemas"
            / "scanview-presentation-state-catalog-v1.schema.json"
        ).read_text()
    )


def _http(
    port: int,
    path: str,
    *,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    connection.request("GET", path, headers=headers or {})
    response = connection.getresponse()
    result = response.status, dict(response.getheaders()), response.read()
    connection.close()
    return result


def test_supported_gsps_is_schema_valid_exact_and_not_reinterpreted(tmp_path: Path) -> None:
    _, image_uids = _write_fixture(tmp_path)
    artifact, catalog, registry = _artifact(tmp_path)

    Draft202012Validator.check_schema(_schema())
    Draft202012Validator(_schema(), format_checker=FormatChecker()).validate(artifact)
    assert artifact["artifact_type"] == ARTIFACT_TYPE
    assert artifact["state_count"] == 1
    assert artifact["supported_state_count"] == 1
    assert artifact["unsupported_state_count"] == 0
    assert artifact["privacy"]["annotation_text_may_contain_identifiers"] is True
    state = artifact["states"][0]
    assert state["display_status"] == "supported_read_only"
    assert state["referenced_instance_count"] == 2
    assert state["presentation"]["voi_range"] == {"lower": -160.0, "upper": 239.0}
    assert state["annotations"][0]["referenced_instance_ids"] == [
        opaque_id("instance", image_uids[0])
    ]
    assert state["annotations"][0]["graphics"][0]["points"] == [
        [10.5, 20.5],
        [30.5, 40.5],
    ]
    assert state["annotations"][0]["texts"][0]["unformatted_text"] == "12.3 mm"
    assert state["author_identity_authenticated"] is False
    assert state["scanview_interpretation_added"] is False
    assert state["source_text_clinical_meaning"] == "not_assessed"
    assert artifact["permissions"]["interpret_annotation_text_as_measurement_authorized"] is False
    assert validate_presentation_state_catalog(
        catalog, registry_source_loader(catalog, registry), artifact
    ) == artifact


@pytest.mark.parametrize(
    "fixture_options",
    [
        {"rotation": 90},
        {"voi_function": "SIGMOID"},
        {"presentation_study_mismatch": True},
        {"source_rescale": True},
        {"presentation_aspect": (2, 1)},
        {"extended_bottom_right": True},
        {"frame_scoped": True},
        {"presentation_modality_transform": True},
        {"presentation_lut_sequence": True},
        {"mask_subtraction": True},
        {"overlay_activation": True},
        {"anchor_visibility": "X"},
        {"text": "bad\ttext"},
        {"point": (700.0, 20.5)},
    ],
)
def test_unsupported_features_fail_closed_without_display_data(
    tmp_path: Path,
    fixture_options: dict,
) -> None:
    _write_fixture(tmp_path, **fixture_options)
    artifact, _, _ = _artifact(tmp_path)

    assert artifact["state_count"] == 1
    assert artifact["supported_state_count"] == 0
    assert artifact["unsupported_state_count"] == 1
    assert artifact["states"] == []
    assert artifact["unsupported_states"][0]["display_status"] == "unsupported"


def test_explicit_linear_voi_function_is_supported(tmp_path: Path) -> None:
    _write_fixture(tmp_path, voi_function="LINEAR")
    artifact, _, _ = _artifact(tmp_path)

    assert artifact["supported_state_count"] == 1
    assert artifact["unsupported_state_count"] == 0


def test_source_equivalent_linear_modality_transform_is_supported(tmp_path: Path) -> None:
    _write_fixture(
        tmp_path,
        source_rescale=True,
        presentation_modality_transform=True,
    )
    artifact, _, _ = _artifact(tmp_path)

    assert artifact["supported_state_count"] == 1
    assert artifact["states"][0]["presentation"]["modality_transform"] == (
        "SOURCE_EQUIVALENT_LINEAR"
    )


def test_malformed_presentation_state_fails_closed_with_sanitized_reason(
    tmp_path: Path,
) -> None:
    pr_path, _ = _write_fixture(tmp_path)
    catalog, _ = build_catalog(tmp_path, include_hashes=True)
    source_size = pr_path.stat().st_size
    malformed = b"not a dicom presentation state".ljust(source_size, b"\0")
    for study in catalog["studies"]:
        for series in study["series"]:
            if series["modality"] == "PR":
                series["instances"][0]["sha256"] = hashlib.sha256(malformed).hexdigest()
    artifact = build_presentation_state_catalog(
        catalog,
        lambda _instance_id: malformed,
        generated_at="2026-08-29T12:00:00Z",
    )

    assert artifact["states"] == []
    assert artifact["unsupported_state_count"] == 1
    assert artifact["unsupported_states"][0]["reason"] == (
        "presentation-state DICOM structure is invalid"
    )


def test_summary_withholds_text_ids_geometry_and_values_and_detects_source_change(
    tmp_path: Path,
) -> None:
    pr_path, _ = _write_fixture(tmp_path)
    artifact, catalog, registry = _artifact(tmp_path)
    loader = registry_source_loader(catalog, registry)
    summary = presentation_state_summary(catalog, loader, artifact)

    assert summary["valid"] is True
    assert summary["state_count"] == 1
    assert summary["annotation_count"] == 1
    assert summary["graphic_count"] == 1
    assert summary["text_count"] == 1
    assert summary["contains_annotation_text"] is False
    assert summary["contains_source_ids"] is False
    assert summary["contains_annotation_geometry"] is False
    serialized = json.dumps(summary)
    assert "12.3 mm" not in serialized
    assert "instance_" not in serialized
    assert "-160" not in serialized

    pr_path.write_bytes(pr_path.read_bytes() + b"changed")
    invalid = presentation_state_summary(catalog, loader, artifact)
    assert invalid["valid"] is False
    assert invalid["exact_source_navigation_authorized"] is False


def test_cli_writes_owner_only_artifact_and_privacy_minimized_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_fixture(tmp_path / "source")
    artifact_path = tmp_path / "presentation-states.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "scanview-agent",
            "presentation-states",
            str(tmp_path / "source"),
            "--output",
            str(artifact_path),
        ],
    )
    main()
    assert artifact_path.stat().st_mode & 0o777 == 0o600
    assert json.loads(artifact_path.read_text())["supported_state_count"] == 1

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "scanview-agent",
            "validate-presentation-states",
            str(tmp_path / "source"),
            str(artifact_path),
        ],
    )
    main()
    summary = json.loads(capsys.readouterr().out)
    assert summary["valid"] is True
    assert summary["contains_annotation_text"] is False
    assert summary["contains_source_ids"] is False


def test_loopback_endpoint_requires_local_authority_and_locks_after_change(
    tmp_path: Path,
) -> None:
    pr_path, _ = _write_fixture(tmp_path)
    catalog, registry = build_catalog(tmp_path, include_hashes=True)
    server = create_server(catalog, registry, port=0, token="presentation-state-token")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_port
    try:
        status, _, _ = _http(port, "/v1/presentation-states")
        assert status == HTTPStatus.UNAUTHORIZED

        status, headers, body = _http(
            port,
            "/v1/presentation-states",
            headers={"Authorization": "Bearer presentation-state-token"},
        )
        assert status == HTTPStatus.OK
        assert headers["Cache-Control"] == "no-store"
        assert json.loads(body)["supported_state_count"] == 1

        status, headers, _ = _http(
            port, f"/?session={server.browser_bootstrap_token}"
        )
        assert status == HTTPStatus.SEE_OTHER
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        status, _, body = _http(
            port,
            "/v1/presentation-states",
            headers={"Cookie": cookie},
        )
        assert status == HTTPStatus.OK
        assert json.loads(body)["states"][0]["text_count"] == 1

        pr_path.write_bytes(pr_path.read_bytes() + b"changed")
        status, _, _ = _http(
            port,
            "/v1/presentation-states",
            headers={"Cookie": cookie},
        )
        assert status == HTTPStatus.CONFLICT
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
