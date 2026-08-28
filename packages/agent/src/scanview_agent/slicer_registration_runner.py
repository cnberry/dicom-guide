"""Headless 3D Slicer entry point for one ScanView rigid registration job.

This file is launched by the required, version-gated Slicer application, not by the
ordinary ScanView Python runtime. The host process supplies a private request path
through the environment so source or output paths never appear in process arguments.
"""

from __future__ import annotations

import json
import math
import os
import platform
import sys
from pathlib import Path

import slicer
import vtk
from DICOMLib import DICOMUtils


REQUEST_ENVIRONMENT_VARIABLE = "SCANVIEW_REGISTRATION_REQUEST"
SUPPORTED_SLICER_VERSION = "5.12.3"
SUPPORTED_SLICER_REVISION = "34627"
OUTPUTS = {
    "fixed_volume": "fixed.nrrd",
    "moving_volume": "moving.nrrd",
    "registered_moving_volume": "registered-moving.nrrd",
    "moving_to_fixed_transform": "moving-to-fixed.tfm",
}


def _load_one_scalar_series(directory: Path, label: str):
    before = {
        node.GetID()
        for node in slicer.util.getNodesByClass("vtkMRMLScalarVolumeNode")
    }
    database_directory = directory.parent / f"{directory.name}-database"
    with DICOMUtils.TemporaryDICOMDatabase(str(database_directory)) as database:
        if not DICOMUtils.importDicom(str(directory), database):
            raise RuntimeError(f"{label} DICOM import failed")
        series_uids = [
            series_uid
            for patient_uid in database.patients()
            for study_uid in database.studiesForPatient(patient_uid)
            for series_uid in database.seriesForStudy(study_uid)
        ]
        if len(series_uids) != 1:
            raise RuntimeError(f"{label} staging must contain exactly one DICOM series")
        loaded_ids = DICOMUtils.loadSeriesByUID(series_uids)
    loaded = [
        slicer.mrmlScene.GetNodeByID(node_id)
        for node_id in loaded_ids
        if node_id not in before
    ]
    scalar_volumes = [
        node
        for node in loaded
        if node and node.IsA("vtkMRMLScalarVolumeNode")
    ]
    if len(scalar_volumes) != 1:
        raise RuntimeError(f"{label} must load as exactly one scalar volume")
    scalar_volumes[0].SetName(label)
    return scalar_volumes[0]


def _save(node, path: Path, label: str) -> None:
    if not slicer.util.saveNode(node, str(path)):
        raise RuntimeError(f"failed to save {label}")


def _write_lps_affine_transform(node, path: Path) -> None:
    matrix = vtk.vtkMatrix4x4()
    if not node.GetMatrixTransformToParent(matrix):
        raise RuntimeError("rigid transform matrix is unavailable")
    signs = (-1.0, -1.0, 1.0)
    parameters = []
    for row in range(3):
        for column in range(3):
            parameters.append(signs[row] * matrix.GetElement(row, column) * signs[column])
    for row in range(3):
        parameters.append(signs[row] * matrix.GetElement(row, 3))
    if not all(math.isfinite(value) for value in parameters):
        raise RuntimeError("rigid transform contains a non-finite value")
    content = (
        "#Insight Transform File V1.0\n"
        "#Transform 0\n"
        "Transform: AffineTransform_double_3_3\n"
        f"Parameters: {' '.join(format(value, '.17g') for value in parameters)}\n"
        "FixedParameters: 0 0 0\n"
    )
    path.write_text(content)
    path.chmod(0o600)


def _write_report(
    path: Path, status: str, application_version: str, revision: str, parameters
) -> None:
    report = {
        "schema_version": "1.0.0",
        "status": status,
        "engine": "3D Slicer",
        "application_version": application_version,
        "repository_revision": revision,
        "module": "BRAINSFit",
        "platform": f"{platform.system()}-{platform.machine()}",
        "parameters": parameters,
        "outputs": OUTPUTS,
    }
    path.write_text(json.dumps(report, separators=(",", ":")) + "\n")
    path.chmod(0o600)


def run() -> None:
    request_path = os.environ.get(REQUEST_ENVIRONMENT_VARIABLE)
    if not request_path:
        raise RuntimeError("private registration request is unavailable")
    request = json.loads(Path(request_path).read_text())
    if request.get("schema_version") != "1.0.0":
        raise RuntimeError("registration request version is unsupported")
    application_version = str(slicer.app.applicationVersion)
    repository_revision = str(slicer.app.repositoryRevision)
    if (
        application_version != SUPPORTED_SLICER_VERSION
        or repository_revision != SUPPORTED_SLICER_REVISION
    ):
        raise RuntimeError("the installed Slicer build does not match the required version")
    if not getattr(slicer.modules, "brainsfit", None):
        raise RuntimeError("the required BRAINSFit module is unavailable")
    if request.get("mode") == "preflight":
        _write_report(
            Path(request["report_path"]),
            "preflight_completed",
            application_version,
            repository_revision,
            request["parameters"],
        )
        return
    if request.get("mode") != "registration":
        raise RuntimeError("registration request mode is unsupported")

    fixed = _load_one_scalar_series(Path(request["fixed_input_dir"]), "ScanView fixed")
    moving = _load_one_scalar_series(Path(request["moving_input_dir"]), "ScanView moving")
    work = Path(request["work_dir"])
    work.mkdir(parents=True, exist_ok=True)
    _save(fixed, work / OUTPUTS["fixed_volume"], "fixed volume")
    _save(moving, work / OUTPUTS["moving_volume"], "moving volume")

    registered = slicer.mrmlScene.AddNewNodeByClass(
        "vtkMRMLScalarVolumeNode", "ScanView registered moving"
    )
    transform = slicer.mrmlScene.AddNewNodeByClass(
        "vtkMRMLLinearTransformNode", "ScanView moving to fixed"
    )
    parameters = request["parameters"]
    cli_parameters = {
        "fixedVolume": fixed.GetID(),
        "movingVolume": moving.GetID(),
        "outputVolume": registered.GetID(),
        "linearTransform": transform.GetID(),
        "useRigid": True,
        "useScaleVersor3D": False,
        "useScaleSkewVersor3D": False,
        "useAffine": False,
        "useBSpline": False,
        "initializeTransformMode": parameters["initialize_transform_mode"],
        "maskProcessingMode": parameters["mask_processing_mode"],
        "ROIAutoDilateSize": parameters["roi_auto_dilate_mm"],
        "samplingPercentage": parameters["sampling_percentage"],
        "interpolationMode": parameters["interpolation_mode"],
        "histogramMatch": parameters["histogram_match"],
        "failureExitCode": 1,
        "writeTransformOnFailure": False,
    }
    cli_node = slicer.cli.run(
        slicer.modules.brainsfit,
        None,
        cli_parameters,
        wait_for_completion=True,
    )
    if not cli_node or cli_node.GetStatusString() != "Completed":
        raise RuntimeError("BRAINSFit did not complete successfully")
    _save(registered, work / OUTPUTS["registered_moving_volume"], "registered volume")
    _write_lps_affine_transform(
        transform, work / OUTPUTS["moving_to_fixed_transform"]
    )

    _write_report(
        Path(request["report_path"]),
        "completed",
        application_version,
        repository_revision,
        parameters,
    )


if __name__ == "__main__":
    try:
        run()
    except Exception:
        # The host captures diagnostics in owner-only temporary streams, deletes them
        # with the private job directory, and emits only a generic error.
        import traceback

        traceback.print_exc()
        sys.exit(1)
    sys.exit(0)
