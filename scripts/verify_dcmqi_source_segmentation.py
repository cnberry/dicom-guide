#!/usr/bin/env python3
"""Verify DICOM Guide SEG import against independently executed dcmqi tools.

This optional gate creates patient-free data only. The exact dcmqi executables run
inside OS-enforced external-network isolation and never enter the DICOM Guide runtime.
"""

from __future__ import annotations

import gzip
import hashlib
from importlib.metadata import version
import json
import math
import os
from pathlib import Path
import platform
import re
import runpy
import shutil
import struct
import subprocess
import sys
import tempfile
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "packages" / "agent" / "src"))

from pydicom import dcmread  # noqa: E402

from dicom_guide.catalog import build_catalog  # noqa: E402
from dicom_guide.source_segmentations import (  # noqa: E402
    build_source_segmentation_catalog,
    registry_segmentation_source_loader,
    source_segmentation_summary,
)


EXPECTED_VERSIONS = {
    "dcmqi": "1.5.6",
    "pydicom": "3.0.2",
}
EXPECTED_DCMQI_REVISION = "60d63dc"
ROWS = 64
COLUMNS = 64
SLICES = 24
ROW_SPACING = 0.8
COLUMN_SPACING = 0.8
SLICE_SPACING = 2.0
EXPECTED_VOXELS = 3083
EXPECTED_VOLUME_ML = 3.94624
EXPECTED_MASK_SHA256 = (
    "81946112b1311f1ee9ff4fe1d61f86d36ce82d076122b39b9d4e7a8e46cf82bb"
)
VECTOR = re.compile(r"^\(([^,]+),([^,]+),([^,]+)\)$")


def _executable(name: str) -> Path:
    candidate = Path(sys.executable).parent / name
    if not candidate.is_file() or not os.access(candidate, os.X_OK):
        raise RuntimeError(f"exact dcmqi executable is unavailable: {name}")
    return candidate


def _sandboxed(command: list[str], private_root: Path) -> tuple[list[str], str]:
    system = platform.system()
    if system == "Darwin":
        sandbox = Path("/usr/bin/sandbox-exec")
        if not sandbox.is_file() or not os.access(sandbox, os.X_OK):
            raise RuntimeError("macOS deny-all-network sandbox is unavailable")
        return [
            str(sandbox),
            "-p",
            "(version 1) (allow default) (deny network*)",
            *command,
        ], "macos_sandbox_exec_deny_all_network"
    if system == "Linux":
        bwrap = shutil.which("bwrap")
        if bwrap is None:
            raise RuntimeError("Linux private-network bubblewrap is unavailable")
        private = str(private_root.resolve(strict=True))
        return [
            bwrap,
            "--die-with-parent",
            "--new-session",
            "--unshare-all",
            "--ro-bind",
            "/",
            "/",
            "--bind",
            private,
            private,
            "--dev",
            "/dev",
            "--proc",
            "/proc",
            "--chdir",
            private,
            "--",
            *command,
        ], "linux_bwrap_private_network_namespace"
    raise RuntimeError("dcmqi interoperability is supported only on macOS and Linux")


def _run_isolated(command: list[str], private_root: Path) -> tuple[str, str]:
    sandboxed, mechanism = _sandboxed(command, private_root)
    completed = subprocess.run(
        sandboxed,
        cwd=private_root,
        env={
            "LANG": "C",
            "LC_ALL": "C",
            "PATH": os.pathsep.join(
                [str(Path(sys.executable).parent), "/usr/bin", "/bin"]
            ),
            "TMPDIR": str(private_root / "tmp"),
        },
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=60,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"isolated dcmqi command failed ({completed.returncode}): "
            f"{completed.stdout[-2000:]}"
        )
    return completed.stdout, mechanism


def _prove_external_network_denied(private_root: Path) -> str:
    command = [
        sys.executable,
        "-c",
        (
            "import socket,sys; s=socket.socket(); s.settimeout(0.2); "
            "\ntry: s.connect(('1.1.1.1', 53))"
            "\nexcept OSError: sys.exit(0)"
            "\nelse: sys.exit(91)"
        ),
    ]
    _, mechanism = _run_isolated(command, private_root)
    return mechanism


def _generate_sources(output: Path) -> None:
    generator = REPOSITORY_ROOT / "scripts" / "generate_synthetic_source_segmentation.py"
    previous_argv = sys.argv
    try:
        sys.argv = [str(generator), str(output)]
        runpy.run_path(str(generator), run_name="__main__")
    finally:
        sys.argv = previous_argv
    generated_segmentation = output / "source-segmentation.dcm"
    generated_segmentation.unlink()


def _expected_mask() -> bytes:
    payload = bytearray()
    for source_index in range(SLICES):
        depth = (source_index - 12) / 5.2
        for row in range(ROWS):
            y = (row - 34) / 11.0
            for column in range(COLUMNS):
                x = (column - 28) / 13.0
                payload.append(int(x * x + y * y + depth * depth <= 1))
    return bytes(payload)


def _write_inputs(private_root: Path, mask: bytes) -> tuple[Path, Path]:
    nrrd = private_root / "mask.nrrd"
    header = (
        "NRRD0005\n"
        "type: uint8\n"
        "dimension: 3\n"
        "space: left-posterior-superior\n"
        f"sizes: {COLUMNS} {ROWS} {SLICES}\n"
        f"space directions: ({COLUMN_SPACING},0,0) "
        f"(0,{ROW_SPACING},0) (0,0,{SLICE_SPACING})\n"
        "kinds: domain domain domain\n"
        "endian: little\n"
        "encoding: raw\n"
        "space origin: (0,0,0)\n\n"
    ).encode("ascii")
    nrrd.write_bytes(header + mask)
    nrrd.chmod(0o600)
    metadata = private_root / "metadata.json"
    metadata.write_text(
        json.dumps(
            {
                "@schema": (
                    "https://raw.githubusercontent.com/qiicr/dcmqi/master/"
                    "doc/schemas/seg-schema.json#"
                ),
                "ContentCreatorName": "DICOM Guide^InteropFixture",
                "ClinicalTrialSeriesID": "SYNTHETIC",
                "ClinicalTrialTimePointID": "1",
                "ClinicalTrialCoordinatingCenterName": (
                    "DICOM Guide patient-free interoperability"
                ),
                "SeriesDescription": "dcmqi independent patient-free SEG",
                "SeriesNumber": "92",
                "InstanceNumber": "1",
                "ContentLabel": "SYNTHETIC_SEG",
                "ContentDescription": (
                    "Independent patient-free interoperability fixture"
                ),
                "segmentAttributes": [
                    [
                        {
                            "labelID": 1,
                            "SegmentDescription": (
                                "Independent patient-free test region"
                            ),
                            "SegmentLabel": "Independent synthetic test region",
                            "SegmentAlgorithmType": "MANUAL",
                            "SegmentAlgorithmName": (
                                "DICOM Guide patient-free fixture"
                            ),
                            "recommendedDisplayRGBValue": [255, 100, 60],
                            "SegmentedPropertyCategoryCodeSequence": {
                                "CodeValue": "49755003",
                                "CodingSchemeDesignator": "SCT",
                                "CodeMeaning": (
                                    "Morphologically Abnormal Structure"
                                ),
                            },
                            "SegmentedPropertyTypeCodeSequence": {
                                "CodeValue": "52988006",
                                "CodingSchemeDesignator": "SCT",
                                "CodeMeaning": "Lesion",
                            },
                        }
                    ]
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    metadata.chmod(0o600)
    return nrrd, metadata


def _parse_vector(value: str) -> tuple[float, float, float]:
    match = VECTOR.fullmatch(value.strip())
    if match is None:
        raise RuntimeError("dcmqi NRRD vector is invalid")
    result = tuple(float(item) for item in match.groups())
    if not all(math.isfinite(item) for item in result):
        raise RuntimeError("dcmqi NRRD vector is non-finite")
    return result[0], result[1], result[2]


def _vector_close(
    observed: tuple[float, float, float],
    expected: tuple[float, float, float],
) -> bool:
    return all(
        abs(left - right) <= 1e-9
        for left, right in zip(observed, expected, strict=True)
    )


def _read_roundtrip_mask(path: Path) -> bytes:
    content = path.read_bytes()
    try:
        header_bytes, encoded = content.split(b"\n\n", 1)
        lines = header_bytes.decode("ascii").splitlines()
    except (UnicodeDecodeError, ValueError) as error:
        raise RuntimeError("dcmqi NRRD header is invalid") from error
    if not lines or lines[0] not in {"NRRD0004", "NRRD0005"}:
        raise RuntimeError("dcmqi NRRD signature is unsupported")
    fields: dict[str, str] = {}
    for line in lines[1:]:
        if not line or line.startswith("#"):
            continue
        if ": " not in line:
            raise RuntimeError("dcmqi NRRD field is malformed")
        key, value = line.split(": ", 1)
        if key in fields:
            raise RuntimeError("dcmqi NRRD field is duplicated")
        fields[key] = value
    if (
        fields.get("type") != "short"
        or fields.get("dimension") != "3"
        or fields.get("space") != "left-posterior-superior"
        or fields.get("endian") != "little"
        or fields.get("encoding") != "gzip"
    ):
        raise RuntimeError("dcmqi NRRD encoding is outside the exact test profile")
    try:
        sizes = tuple(int(item) for item in fields["sizes"].split())
        directions = tuple(
            _parse_vector(item)
            for item in re.findall(r"\([^)]*\)", fields["space directions"])
        )
        origin = _parse_vector(fields["space origin"])
        decoded = gzip.decompress(encoded)
    except (KeyError, OSError, ValueError) as error:
        raise RuntimeError("dcmqi NRRD geometry or payload is invalid") from error
    if (
        len(sizes) != 3
        or sizes[0] != COLUMNS
        or sizes[1] != ROWS
        or not 1 <= sizes[2] <= SLICES
        or len(directions) != 3
        or not all(
            _vector_close(observed, expected)
            for observed, expected in zip(
                directions,
                (
                    (COLUMN_SPACING, 0.0, 0.0),
                    (0.0, ROW_SPACING, 0.0),
                    (0.0, 0.0, SLICE_SPACING),
                ),
                strict=True,
            )
        )
        or abs(origin[0]) > 1e-9
        or abs(origin[1]) > 1e-9
    ):
        raise RuntimeError("dcmqi NRRD does not preserve the synthetic native grid")
    voxel_count = math.prod(sizes)
    if len(decoded) != voxel_count * 2:
        raise RuntimeError("dcmqi NRRD decoded length is invalid")
    values = struct.unpack(f"<{voxel_count}h", decoded)
    if any(value not in {0, 1} for value in values):
        raise RuntimeError("dcmqi NRRD contains a non-binary label")
    first_slice = round(origin[2] / SLICE_SPACING)
    if (
        abs(origin[2] - first_slice * SLICE_SPACING) > 1e-9
        or first_slice < 0
        or first_slice + sizes[2] > SLICES
    ):
        raise RuntimeError("dcmqi NRRD origin is not on the source grid")
    dense = bytearray(ROWS * COLUMNS * SLICES)
    slab = ROWS * COLUMNS
    for output_slice in range(sizes[2]):
        source_start = output_slice * slab
        dense_start = (first_slice + output_slice) * slab
        dense[dense_start : dense_start + slab] = bytes(
            values[source_start : source_start + slab]
        )
    return bytes(dense)


def _converter_revision(executable: Path) -> str:
    completed = subprocess.run(
        [str(executable), "--version"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=10,
        check=True,
    )
    if (
        f"revision: {EXPECTED_DCMQI_REVISION}" not in completed.stdout
        or "tag: v1.5.6" not in completed.stdout
    ):
        raise RuntimeError("dcmqi executable revision differs from the pinned package")
    return EXPECTED_DCMQI_REVISION


def main() -> None:
    observed_versions = {name: version(name) for name in EXPECTED_VERSIONS}
    if observed_versions != EXPECTED_VERSIONS:
        raise SystemExit(
            "interoperability dependency versions differ: "
            + json.dumps(observed_versions, sort_keys=True)
        )
    writer = _executable("itkimage2segimage")
    reader = _executable("segimage2itkimage")
    revision = _converter_revision(writer)
    if _converter_revision(reader) != revision:
        raise RuntimeError("dcmqi writer and reader revisions differ")

    with tempfile.TemporaryDirectory(prefix="dicom-guide-dcmqi-") as temporary:
        private_root = Path(temporary)
        private_root.chmod(0o700)
        (private_root / "tmp").mkdir(mode=0o700)
        network_isolation = _prove_external_network_denied(private_root)
        dicom = private_root / "dicom"
        _generate_sources(dicom)
        expected_mask = _expected_mask()
        if (
            len(expected_mask) != ROWS * COLUMNS * SLICES
            or sum(expected_mask) != EXPECTED_VOXELS
            or hashlib.sha256(expected_mask).hexdigest() != EXPECTED_MASK_SHA256
        ):
            raise RuntimeError("patient-free reference mask differs")
        nrrd, metadata = _write_inputs(private_root, expected_mask)
        segmentation = dicom / "source-segmentation.dcm"
        _, writer_isolation = _run_isolated(
            [
                str(writer),
                "--inputImageList",
                str(nrrd),
                "--inputDICOMDirectory",
                str(dicom),
                "--inputMetadata",
                str(metadata),
                "--outputDICOM",
                str(segmentation),
                "--skip",
                "1",
                "--compress",
                "none",
            ],
            private_root,
        )
        if writer_isolation != network_isolation or not segmentation.is_file():
            raise RuntimeError("isolated dcmqi writer did not publish its SEG")
        segmentation.chmod(0o600)
        dataset = dcmread(segmentation, stop_before_pixels=True)
        frames = list(dataset.PerFrameFunctionalGroupsSequence)
        if (
            str(dataset.Manufacturer) != "QIICR"
            or str(dataset.ManufacturerModelName) != "https://github.com/QIICR/dcmqi"
            or str(dataset.SoftwareVersions) != EXPECTED_DCMQI_REVISION
            or int(dataset.NumberOfFrames) != 11
            or any(
                hasattr(
                    frame.DerivationImageSequence[0].SourceImageSequence[0],
                    "SpatialLocationsPreserved",
                )
                for frame in frames
            )
        ):
            raise RuntimeError("dcmqi SEG provenance or optional-tag fixture differs")

        roundtrip = private_root / "roundtrip"
        roundtrip.mkdir(mode=0o700)
        _, reader_isolation = _run_isolated(
            [
                str(reader),
                "--inputDICOM",
                str(segmentation),
                "--outputDirectory",
                str(roundtrip),
                "--prefix",
                "mask",
                "--outputType",
                "nrrd",
            ],
            private_root,
        )
        if reader_isolation != network_isolation:
            raise RuntimeError("dcmqi reader isolation differs")
        roundtrip_mask = _read_roundtrip_mask(roundtrip / "mask-1.nrrd")
        if roundtrip_mask != expected_mask:
            raise RuntimeError("dcmqi did not reconstruct its dense source-grid mask")

        catalog, registry = build_catalog(dicom, include_hashes=True)
        loader = registry_segmentation_source_loader(catalog, registry)
        artifact, masks, guarded = build_source_segmentation_catalog(catalog, loader)
        summary = source_segmentation_summary(
            json.loads(json.dumps(artifact)),
            catalog=catalog,
            load_source=loader,
        )
        if not summary["valid"] or artifact["supported_segmentation_count"] != 1:
            raise RuntimeError("DICOM Guide did not accept the independent dcmqi SEG")
        state = artifact["segmentations"][0]
        segment = state["segments"][0]
        dicom_guide_mask = masks[(state["segmentation_id"], 1)]
        if (
            dicom_guide_mask != expected_mask
            or state["spatial_location_evidence"]
            != "optional_tag_absent_exact_native_geometry"
            or state["frame_count"] != 11
            or state["referenced_instance_count"] != 11
            or segment["marked_voxel_count"] != EXPECTED_VOXELS
            or abs(segment["computed_volume_ml"] - EXPECTED_VOLUME_ML) > 1e-9
            or segment["mask_sha256"] != EXPECTED_MASK_SHA256
            or len(guarded) != 25
        ):
            raise RuntimeError("DICOM Guide dcmqi provenance or arithmetic differs")
        print(
            json.dumps(
                {
                    "artifact_type": "dicom-guide.dcmqi-source-segmentation-interop",
                    "valid": True,
                    "patient_data_used": False,
                    "external_network_denied": True,
                    "network_isolation": network_isolation,
                    "runtime_dependency_added": False,
                    "versions": observed_versions,
                    "dcmqi_revision": revision,
                    "source_images": SLICES,
                    "segmentation_frames": state["frame_count"],
                    "referenced_instances": state["referenced_instance_count"],
                    "spatial_location_evidence": state[
                        "spatial_location_evidence"
                    ],
                    "marked_voxels": segment["marked_voxel_count"],
                    "computed_volume_ml": round(segment["computed_volume_ml"], 6),
                    "mask_sha256": segment["mask_sha256"],
                    "dcmqi_roundtrip_equal": roundtrip_mask == expected_mask,
                },
                indent=2,
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    main()
