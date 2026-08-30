#!/usr/bin/env python3
"""Verify DICOM Guide SEG import against an independently generated highdicom object.

This script is an optional, patient-free interoperability gate. highdicom and NumPy
are test-only dependencies and never become part of the DICOM Guide offline runtime.
"""

from __future__ import annotations

import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import runpy
import socket
import sys
import tempfile


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "packages" / "agent" / "src"))

import highdicom as hd  # noqa: E402
import numpy as np  # noqa: E402
from pydicom import dcmread  # noqa: E402
from pydicom.uid import ExplicitVRLittleEndian  # noqa: E402

from dicom_guide.catalog import build_catalog  # noqa: E402
from dicom_guide.source_segmentations import (  # noqa: E402
    build_source_segmentation_catalog,
    registry_segmentation_source_loader,
    source_segmentation_summary,
)


EXPECTED_VERSIONS = {
    "highdicom": "0.28.1",
    "numpy": "2.5.2",
    "pydicom": "3.0.2",
}


def _deny_network() -> None:
    def blocked(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("highdicom interoperability gate forbids network access")

    socket.create_connection = blocked  # type: ignore[assignment]
    socket.socket.connect = blocked  # type: ignore[method-assign]
    socket.socket.connect_ex = blocked  # type: ignore[method-assign]


def _generate_dicom_guide_sources(output: Path) -> None:
    generator = REPOSITORY_ROOT / "scripts" / "generate_synthetic_source_segmentation.py"
    previous_argv = sys.argv
    try:
        sys.argv = [str(generator), str(output)]
        runpy.run_path(str(generator), run_name="__main__")
    finally:
        sys.argv = previous_argv


def _highdicom_segmentation(output: Path) -> tuple[np.ndarray, list[str]]:
    source_paths = sorted(output.glob("mr-*.dcm"))
    source_images = [dcmread(path) for path in source_paths]
    for image in source_images:
        # Type 2 patient/study attributes required by the independent constructor.
        # Empty values preserve the synthetic source identity used on disk.
        image.PatientBirthDate = ""
        image.PatientSex = ""
        image.StudyID = "1"
        image.AccessionNumber = ""
        image.ReferringPhysicianName = ""
        image.StudyTime = "120000"
        image.SeriesTime = "120100"

    mask = np.zeros((len(source_images), 64, 64), dtype=np.uint8)
    rows, columns = np.ogrid[:64, :64]
    for source_index in range(len(source_images)):
        depth = (source_index - 12) / 5.2
        mask[source_index][
            ((columns - 28) / 13.0) ** 2
            + ((rows - 34) / 11.0) ** 2
            + depth * depth
            <= 1
        ] = 1

    description = hd.seg.SegmentDescription(
        segment_number=1,
        segment_label="Independent synthetic test region",
        segmented_property_category=hd.sr.CodedConcept(
            "49755003", "SCT", "Morphologically Abnormal Structure"
        ),
        segmented_property_type=hd.sr.CodedConcept(
            "52988006", "SCT", "Lesion"
        ),
        algorithm_type=hd.seg.SegmentAlgorithmTypeValues.MANUAL,
    )
    segmentation = hd.seg.Segmentation(
        source_images=source_images,
        pixel_array=mask,
        segmentation_type=hd.seg.SegmentationTypeValues.BINARY,
        segment_descriptions=[description],
        series_instance_uid=hd.UID(),
        series_number=91,
        sop_instance_uid=hd.UID(),
        instance_number=1,
        manufacturer="highdicom interoperability fixture",
        manufacturer_model_name="patient-free generator",
        software_versions=EXPECTED_VERSIONS["highdicom"],
        device_serial_number="SYNTHETIC-ONLY",
        content_description="Independent patient-free DICOM Guide SEG fixture",
        content_creator_name="Interoperability^Fixture",
        series_description="Highdicom independent source SEG",
        transfer_syntax_uid=ExplicitVRLittleEndian,
        omit_empty_frames=True,
    )
    destination = output / "source-segmentation.dcm"
    temporary = output / "highdicom-seg.tmp"
    segmentation.save_as(temporary, enforce_file_format=True)
    temporary.replace(destination)
    destination.chmod(0o600)
    return mask, [str(image.SOPInstanceUID) for image in source_images]


def main() -> None:
    observed_versions = {name: version(name) for name in EXPECTED_VERSIONS}
    if observed_versions != EXPECTED_VERSIONS:
        raise SystemExit(
            "interoperability dependency versions differ: "
            + json.dumps(observed_versions, sort_keys=True)
        )
    _deny_network()
    with tempfile.TemporaryDirectory(prefix="dicom-guide-highdicom-") as temporary:
        root = Path(temporary) / "dicom"
        _generate_dicom_guide_sources(root)
        expected_mask, source_uids = _highdicom_segmentation(root)

        # Independently reconstruct a dense source-ordered mask using highdicom's
        # public source-instance API, including omitted empty frames.
        independent = hd.seg.segread(root / "source-segmentation.dcm")
        highdicom_mask = independent.get_pixels_by_source_instance(
            source_uids,
            segment_numbers=[1],
            assert_missing_frames_are_empty=True,
        )[..., 0]
        if not np.array_equal(highdicom_mask, expected_mask):
            raise RuntimeError("highdicom did not reconstruct its source-ordered mask")

        catalog, registry = build_catalog(root, include_hashes=True)
        loader = registry_segmentation_source_loader(catalog, registry)
        artifact, masks, guarded = build_source_segmentation_catalog(catalog, loader)
        summary = source_segmentation_summary(
            json.loads(json.dumps(artifact)),
            catalog=catalog,
            load_source=loader,
        )
        if not summary["valid"] or artifact["supported_segmentation_count"] != 1:
            raise RuntimeError("DICOM Guide did not accept the independent DICOM SEG")
        state = artifact["segmentations"][0]
        segment = state["segments"][0]
        dicom_guide_mask = masks[(state["segmentation_id"], 1)]
        expected_bytes = expected_mask.tobytes(order="C")
        if dicom_guide_mask != expected_bytes:
            raise RuntimeError("DICOM Guide and highdicom dense masks differ")
        if (
            state["frame_count"] != 11
            or state["referenced_instance_count"] != 24
            or segment["marked_voxel_count"] != 3083
            or abs(segment["computed_volume_ml"] - 3.94624) > 1e-9
            or hashlib.sha256(dicom_guide_mask).hexdigest()
            != segment["mask_sha256"]
            or len(guarded) != 25
        ):
            raise RuntimeError("DICOM Guide interoperability provenance or arithmetic differs")
        print(
            json.dumps(
                {
                    "artifact_type": "dicom-guide.highdicom-source-segmentation-interop",
                    "valid": True,
                    "patient_data_used": False,
                    "network_access_allowed": False,
                    "runtime_dependency_added": False,
                    "versions": observed_versions,
                    "source_images": 24,
                    "segmentation_frames": state["frame_count"],
                    "referenced_instances": state["referenced_instance_count"],
                    "marked_voxels": segment["marked_voxel_count"],
                    "computed_volume_ml": round(segment["computed_volume_ml"], 6),
                    "mask_sha256": segment["mask_sha256"],
                },
                indent=2,
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    main()
