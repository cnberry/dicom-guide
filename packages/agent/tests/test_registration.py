from __future__ import annotations

import errno
import gzip
import hashlib
import json
import os
import socket
import stat
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

import scanview_agent.registration as registration_module
from scanview_agent.registration import (
    BUNDLE_FILES,
    ENGINE_OUTPUTS,
    REGISTRATION_PARAMETERS,
    _publish_directory_no_replace,
    _run_local_engine,
    registration_bundle_summary,
    registration_doctor,
    run_rigid_registration,
    select_registration_sources,
)


PATIENT = "patient_0123456789abcdef0123"
FIXED_STUDY = "study_0123456789abcdef0123"
MOVING_STUDY = "study_1123456789abcdef0123"
FIXED_SERIES = "series_0123456789abcdef0123"
MOVING_SERIES = "series_1123456789abcdef0123"


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def registration_catalog(source_root: Path) -> tuple[dict, dict[str, Path], dict[str, bytes]]:
    source_root.mkdir()
    registry: dict[str, Path] = {}
    originals: dict[str, bytes] = {}

    def make_series(
        *,
        seed: str,
        series_id: str,
        date: str,
        description: str = "Synthetic T1 post",
        modality: str = "MR",
    ) -> dict:
        instances = []
        sop_class_uid = {
            "MR": "1.2.840.10008.5.1.4.1.1.4",
            "CT": "1.2.840.10008.5.1.4.1.1.2",
        }[modality]
        for index in range(5):
            instance_id = f"instance_{seed * 19}{index}"
            payload = b"synthetic-dicom\x00" + bytes([index]) + seed.encode()
            path = source_root / f"{seed}-{index}.dcm"
            path.write_bytes(payload)
            registry[instance_id] = path
            originals[str(path)] = payload
            instances.append(
                {
                    "id": instance_id,
                    "bytes": len(payload),
                    "sha256": _sha256(payload),
                    "instance_number": index + 1,
                    "image_position_patient": [0.0, 0.0, float(index * 3)],
                    "sop_class_uid": sop_class_uid,
                    "rows": 64,
                    "columns": 64,
                    "pixel_spacing": [1.0, 1.0],
                    "image_orientation_patient": [1.0, 0.0, 0.0, 0.0, 1.0, 0.0],
                    "number_of_frames": 1,
                }
            )
        return {
            "id": series_id,
            "patient_context_id": PATIENT,
            "acquisition_date": date,
            "modality": modality,
            "series_description": description,
            "protocol_name": "Brain",
            "body_part": "BRAIN",
            "image_type": ["ORIGINAL", "PRIMARY"],
            "frame_of_reference_id": f"frame_{seed * 20}",
            "rows": 64,
            "columns": 64,
            "pixel_spacing": [1.0, 1.0],
            "slice_thickness": 1.0,
            "image_orientation_patient": [1.0, 0.0, 0.0, 0.0, 1.0, 0.0],
            "contrast_present": True,
            "repetition_time": 500.0,
            "echo_time": 10.0,
            "inversion_time": None,
            "flip_angle": 90.0,
            "instance_count": len(instances),
            "instances": instances,
            "review_status": "unreviewed",
        }

    fixed = make_series(
        seed="1", series_id=FIXED_SERIES, date="20260101"
    )
    moving = make_series(
        seed="2", series_id=MOVING_SERIES, date="20260315"
    )
    catalog = {
        "schema_version": "1.0.0",
        "studies": [
            {"id": FIXED_STUDY, "acquisition_date": "20260101", "series": [fixed]},
            {"id": MOVING_STUDY, "acquisition_date": "20260315", "series": [moving]},
        ],
    }
    return catalog, registry, originals


def fake_slicer(path: Path, *, fail: bool = False) -> Path:
    if fail:
        source = """#!/usr/bin/env python3
import sys
print('SECRET PATIENT DIAGNOSTIC', file=sys.stderr)
raise SystemExit(7)
"""
    else:
        source = """#!/usr/bin/env python3
import json
import os
import struct
import sys
from pathlib import Path

request = json.loads(Path(os.environ['SCANVIEW_REGISTRATION_REQUEST']).read_text())
required = {'--disable-settings', '--ignore-slicerrc', '--no-splash', '--no-main-window'}
private_temp = Path(os.environ['SCANVIEW_REGISTRATION_REQUEST']).parent
private_environment = all(
    Path(os.environ[name]) == private_temp for name in ('TMPDIR', 'TMP', 'TEMP')
)
forbidden_environment = any(
    name in os.environ
    for name in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'PYTHONPATH', 'AWS_SECRET_ACCESS_KEY')
)
if (
    not required.issubset(sys.argv)
    or os.environ.get('PYTHONNOUSERSITE') != '1'
    or Path(os.environ.get('PYTHONPYCACHEPREFIX', '')).parent != private_temp
    or not private_environment
    or forbidden_environment
):
    raise SystemExit(8)
outputs = {
    'fixed_volume': 'fixed.nrrd',
    'moving_volume': 'moving.nrrd',
    'registered_moving_volume': 'registered-moving.nrrd',
    'registered_moving_coverage': 'registered-moving-coverage.nrrd',
    'moving_to_fixed_transform': 'moving-to-fixed.tfm',
}
report = {
    'schema_version': '2.0.0',
    'status': 'preflight_completed' if request.get('mode') == 'preflight' else 'completed',
    'engine': '3D Slicer',
    'application_version': '5.12.3',
    'repository_revision': '9034c71',
    'module': 'BRAINSFit',
    'coverage_module': 'BRAINSResample',
    'platform': 'Synthetic-test',
    'parameters': request['parameters'],
    'outputs': outputs,
}
if request.get('mode') == 'preflight':
    Path(request['report_path']).write_text(json.dumps(report) + '\\n')
    raise SystemExit(0)
work = Path(request['work_dir'])
values = {
    'fixed.nrrd': (0, 100, 200, 300, 400, 500, 600, 700),
    'moving.nrrd': (700, 600, 500, 400, 300, 200, 100, 0),
    'registered-moving.nrrd': (0, 110, 190, 310, 390, 510, 590, 700),
}
for name in ('fixed.nrrd', 'moving.nrrd', 'registered-moving.nrrd'):
    header = (
        b'NRRD0005\\n'
        b'type: short\\n'
        b'dimension: 3\\n'
        b'sizes: 2 2 2\\n'
        b'space: left-posterior-superior\\n'
        b'space directions: (1,0,0) (0,1,0) (0,0,1)\\n'
        b'space origin: (0,0,0)\\n'
        b'endian: little\\n'
        b'encoding: raw\\n\\n'
    )
    (work / name).write_bytes(header + struct.pack('<8h', *values[name]))
coverage_header = (
    b'NRRD0005\\n'
    b'type: unsigned char\\n'
    b'dimension: 3\\n'
    b'sizes: 2 2 2\\n'
    b'space: left-posterior-superior\\n'
    b'space directions: (1,0,0) (0,1,0) (0,0,1)\\n'
    b'space origin: (0,0,0)\\n'
    b'encoding: raw\\n\\n'
)
(work / 'registered-moving-coverage.nrrd').write_bytes(coverage_header + bytes([1] * 8))
(work / 'moving-to-fixed.tfm').write_text(
    '#Insight Transform File V1.0\\n'
    '#Transform 0\\n'
    'Transform: AffineTransform_double_3_3\\n'
    'Parameters: 1 0 0 0 1 0 0 0 1 0 0 0\\n'
    'FixedParameters: 0 0 0\\n'
)
Path(request['report_path']).write_text(json.dumps(report) + '\\n')
"""
    path.write_text(source)
    path.chmod(0o700)
    return path


def _coverage_nrrd(
    values: bytes,
    *,
    sizes: tuple[int, int, int] = (2, 2, 2),
    scalar_type: str = "unsigned char",
    encoding: str = "raw",
) -> bytes:
    header = (
        "NRRD0005\n"
        f"type: {scalar_type}\n"
        "dimension: 3\n"
        f"sizes: {' '.join(str(value) for value in sizes)}\n"
        "space: left-posterior-superior\n"
        "space directions: (1,0,0) (0,1,0) (0,0,1)\n"
        "space origin: (0,0,0)\n"
        f"encoding: {encoding}\n\n"
    ).encode()
    return header + (gzip.compress(values) if encoding == "gzip" else values)


def _replace_manifest_payload(bundle: Path, filename: str, payload: bytes) -> None:
    path = bundle / filename
    path.write_bytes(payload)
    path.chmod(0o600)
    manifest_path = bundle / "registration.json"
    manifest = json.loads(manifest_path.read_text())
    entry = next(item for item in manifest["files"] if item["name"] == filename)
    entry["bytes"] = len(payload)
    entry["sha256"] = _sha256(payload)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    manifest_path.chmod(0o600)


def test_registration_source_selection_enforces_hard_longitudinal_gates(
    tmp_path: Path,
) -> None:
    catalog, _, _ = registration_catalog(tmp_path / "dicom")

    with pytest.raises(ValueError, match="attestation"):
        select_registration_sources(
            catalog,
            fixed_series_id=FIXED_SERIES,
            moving_series_id=MOVING_SERIES,
            attest_series_selection=False,
        )

    cross_patient = json.loads(json.dumps(catalog))
    cross_patient["studies"][1]["series"][0]["patient_context_id"] = (
        "patient_aaaaaaaaaaaaaaaaaaaa"
    )
    with pytest.raises(ValueError, match="patient context"):
        select_registration_sources(
            cross_patient,
            fixed_series_id=FIXED_SERIES,
            moving_series_id=MOVING_SERIES,
            attest_series_selection=True,
        )

    cross_modality = json.loads(json.dumps(catalog))
    cross_modality["studies"][1]["series"][0]["modality"] = "CT"
    for instance in cross_modality["studies"][1]["series"][0]["instances"]:
        instance["sop_class_uid"] = "1.2.840.10008.5.1.4.1.1.2"
    with pytest.raises(ValueError, match="same MR or CT"):
        select_registration_sources(
            cross_modality,
            fixed_series_id=FIXED_SERIES,
            moving_series_id=MOVING_SERIES,
            attest_series_selection=True,
        )

    with pytest.raises(ValueError, match="earlier fixed source"):
        select_registration_sources(
            catalog,
            fixed_series_id=MOVING_SERIES,
            moving_series_id=FIXED_SERIES,
            attest_series_selection=True,
        )

    missing_hash = json.loads(json.dumps(catalog))
    missing_hash["studies"][0]["series"][0]["instances"][0]["sha256"] = None
    with pytest.raises(ValueError, match="SHA-256"):
        select_registration_sources(
            missing_hash,
            fixed_series_id=FIXED_SERIES,
            moving_series_id=MOVING_SERIES,
            attest_series_selection=True,
        )

    localizer = json.loads(json.dumps(catalog))
    localizer["studies"][1]["series"][0]["image_type"] = [
        "ORIGINAL",
        "PRIMARY",
        "LOCALIZER",
    ]
    with pytest.raises(ValueError, match="original primary diagnostic"):
        select_registration_sources(
            localizer,
            fixed_series_id=FIXED_SERIES,
            moving_series_id=MOVING_SERIES,
            attest_series_selection=True,
        )

    wrong_anatomy = json.loads(json.dumps(catalog))
    wrong_anatomy["studies"][1]["series"][0]["body_part"] = "CHEST"
    with pytest.raises(ValueError, match="brain or head"):
        select_registration_sources(
            wrong_anatomy,
            fixed_series_id=FIXED_SERIES,
            moving_series_id=MOVING_SERIES,
            attest_series_selection=True,
        )

    unknown_contrast = json.loads(json.dumps(catalog))
    unknown_contrast["studies"][1]["series"][0]["series_description"] = "Synthetic T1"
    unknown_contrast["studies"][1]["series"][0]["contrast_present"] = False
    with pytest.raises(ValueError, match="contrast category is unknown"):
        select_registration_sources(
            unknown_contrast,
            fixed_series_id=FIXED_SERIES,
            moving_series_id=MOVING_SERIES,
            attest_series_selection=True,
        )

    contrast_mismatch = json.loads(json.dumps(catalog))
    contrast_mismatch["studies"][1]["series"][0]["series_description"] = "Synthetic T1 pre"
    contrast_mismatch["studies"][1]["series"][0]["contrast_present"] = False
    with pytest.raises(ValueError, match="matching explicit contrast"):
        select_registration_sources(
            contrast_mismatch,
            fixed_series_id=FIXED_SERIES,
            moving_series_id=MOVING_SERIES,
            attest_series_selection=True,
        )

    sequence_mismatch = json.loads(json.dumps(catalog))
    sequence_mismatch["studies"][1]["series"][0]["series_description"] = "Synthetic T2 post"
    with pytest.raises(ValueError, match="matched sequence family"):
        select_registration_sources(
            sequence_mismatch,
            fixed_series_id=FIXED_SERIES,
            moving_series_id=MOVING_SERIES,
            attest_series_selection=True,
        )

    duplicate_position = json.loads(json.dumps(catalog))
    duplicate_position["studies"][1]["series"][0]["instances"][1][
        "image_position_patient"
    ] = [0.0, 0.0, 0.0]
    with pytest.raises(ValueError, match="duplicate or invalid"):
        select_registration_sources(
            duplicate_position,
            fixed_series_id=FIXED_SERIES,
            moving_series_id=MOVING_SERIES,
            attest_series_selection=True,
        )

    review_only = json.loads(json.dumps(catalog))
    review_series = review_only["studies"][1]["series"][0]
    review_series.update(
        {
            "repetition_time": 2000.0,
            "echo_time": 80.0,
            "flip_angle": 20.0,
            "frame_of_reference_id": "frame_aaaaaaaaaaaaaaaaaaaa",
        }
    )
    with pytest.raises(ValueError, match="review beyond"):
        select_registration_sources(
            review_only,
            fixed_series_id=FIXED_SERIES,
            moving_series_id=MOVING_SERIES,
            attest_series_selection=True,
        )


def test_rigid_registration_is_local_immutable_and_locked_pending_qa(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "dicom"
    catalog, registry, originals = registration_catalog(source_root)
    executable = fake_slicer(tmp_path / "Slicer")
    output = tmp_path / "registration-output"

    manifest = run_rigid_registration(
        catalog,
        registry,
        source_root=source_root,
        fixed_series_id=FIXED_SERIES,
        moving_series_id=MOVING_SERIES,
        output=output,
        slicer_executable=executable,
        expected_slicer_sha256=_sha256(executable.read_bytes()),
        attest_series_selection=True,
        timeout_seconds=60,
    )

    assert {path.name for path in output.iterdir()} == BUNDLE_FILES
    assert stat.S_IMODE(output.stat().st_mode) == 0o700
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in output.iterdir())
    assert manifest["artifact_state"] == "generated_pending_qa"
    assert manifest["qa"]["status"] == "pending"
    assert not any(manifest["qa"]["display_unlocks"].values())
    assert manifest["algorithm"]["parameters"] == REGISTRATION_PARAMETERS
    assert manifest["algorithm"]["module"] == "BRAINSFit"
    assert manifest["algorithm"]["coverage_module"] == "BRAINSResample"
    assert manifest["algorithm"]["external_api_requested_by_scanview"] is False
    network_isolation = manifest["algorithm"]["network_isolation"]
    assert network_isolation["status"] == "os_enforced"
    assert network_isolation["mechanism"] in {
        "macos_sandbox_exec_deny_all_network",
        "linux_bwrap_network_namespace_seccomp_no_sockets",
        "linux_bwrap_network_namespace_seccomp_no_network_sockets",
    }
    assert network_isolation["external_network"] == "denied"
    assert network_isolation["host_network"] == "isolated"
    assert network_isolation["unsandboxed_fallback"] is False
    assert manifest["coverage_mask"] == {
        "filename": "registered-moving-coverage.nrrd",
        "semantics": "technical_sampling_support_not_anatomy_or_segmentation",
        "source_volume": "moving.nrrd",
        "reference_volume": "fixed.nrrd",
        "transform": "moving-to-fixed.tfm",
        "transform_direction": "moving_later_to_fixed_earlier",
        "source_basis": "constant_one_moving_grid",
        "resampler": "BRAINSResample",
        "registered_volume_interpolation": "Linear",
        "mask_interpolation": "NearestNeighbor",
        "scalar_type": "uint8",
        "binary_values": [0, 1],
        "outside_value": 0,
        "total_voxel_count": 8,
        "foreground_voxel_count": 8,
        "foreground_fraction": 1.0,
    }
    assert manifest["pairing"]["patient_identity_status"] == "opaque_context_match_unverified"
    assert manifest["pairing"]["clinical_baseline_status"] == "not_assessed"
    assert manifest["computed_results"] == []
    assert manifest["candidate_interpretations"] == []
    serialized = json.dumps(manifest)
    assert str(source_root) not in serialized
    assert "Synthetic T1 post" not in serialized
    for source, payload in originals.items():
        assert Path(source).read_bytes() == payload

    summary = registration_bundle_summary(output)
    assert summary == {
        "valid": True,
        "schema_version": "2.0.0",
        "artifact_type": "rigid_registration",
        "artifact_state": "generated_pending_qa",
        "review_status": "unreviewed",
        "qa_status": "pending",
        "display_unlocked": False,
        "external_api_requested_by_scanview": False,
        "errors": [],
        "modality": "MR",
        "file_count": 7,
        "source_instance_count": 10,
    }
    repository_root = Path(__file__).parents[3]
    schema = json.loads(
        (repository_root / "schemas" / "scanview-rigid-registration-v2.schema.json").read_text()
    )
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(manifest)

    registered_path = output / ENGINE_OUTPUTS["registered_moving_volume"]
    registered_payload = registered_path.read_bytes()
    registered_path.write_bytes(
        b"NRRD0005\ntampered"
    )
    invalid = registration_bundle_summary(output)
    assert invalid["valid"] is False
    assert invalid["display_unlocked"] is False
    assert not any(FIXED_SERIES in error for error in invalid["errors"])

    registered_path.write_bytes(registered_payload)
    registered_path.chmod(0o644)
    assert "owner-only" in " ".join(registration_bundle_summary(output)["errors"])
    registered_path.chmod(0o600)
    hardlink = tmp_path / "registered-hardlink"
    os.link(registered_path, hardlink)
    assert "linked" in " ".join(registration_bundle_summary(output)["errors"])
    hardlink.unlink()

    transform_path = output / ENGINE_OUTPUTS["moving_to_fixed_transform"]
    transform_payload = transform_path.read_bytes()
    transform_path.write_text(
        "#Insight Transform File V1.0\n#Transform 0\n"
        "Transform: AffineTransform_double_3_3\n"
        "Parameters: 2 0 0 0 1 0 0 0 1 0 0 0\nFixedParameters: 0 0 0\n"
    )
    assert registration_bundle_summary(output)["valid"] is False
    transform_path.write_bytes(transform_payload)
    stored_manifest = json.loads((output / "registration.json").read_text())
    stored_manifest["qa"]["display_unlocks"]["overlay"] = True
    (output / "registration.json").write_text(json.dumps(stored_manifest))
    assert registration_bundle_summary(output)["valid"] is False


def test_registration_coverage_mask_validation_is_fail_closed(tmp_path: Path) -> None:
    source_root = tmp_path / "dicom"
    catalog, registry, _ = registration_catalog(source_root)
    executable = fake_slicer(tmp_path / "Slicer")
    output = tmp_path / "registration-output"
    run_rigid_registration(
        catalog,
        registry,
        source_root=source_root,
        fixed_series_id=FIXED_SERIES,
        moving_series_id=MOVING_SERIES,
        output=output,
        slicer_executable=executable,
        expected_slicer_sha256=_sha256(executable.read_bytes()),
        attest_series_selection=True,
        timeout_seconds=60,
    )
    mask_path = output / "registered-moving-coverage.nrrd"
    original_mask = mask_path.read_bytes()
    manifest_path = output / "registration.json"
    original_manifest = manifest_path.read_bytes()
    report_path = output / "engine-report.json"
    original_report = report_path.read_bytes()

    def restore() -> None:
        mask_path.write_bytes(original_mask)
        mask_path.chmod(0o600)
        manifest_path.write_bytes(original_manifest)
        manifest_path.chmod(0o600)
        report_path.write_bytes(original_report)
        report_path.chmod(0o600)

    mask_path.unlink()
    assert "missing, extra" in " ".join(registration_bundle_summary(output)["errors"])
    restore()

    extra = output / "unexpected.nrrd"
    extra.write_bytes(original_mask)
    extra.chmod(0o600)
    assert "missing, extra" in " ".join(registration_bundle_summary(output)["errors"])
    extra.unlink()

    mask_path.write_bytes(original_mask[:-1] + b"\x00")
    assert "integrity" in " ".join(registration_bundle_summary(output)["errors"])
    restore()

    _replace_manifest_payload(
        output,
        mask_path.name,
        _coverage_nrrd(bytes([1] * 4), sizes=(1, 2, 2)),
    )
    assert "does not use the fixed volume geometry" in " ".join(
        registration_bundle_summary(output)["errors"]
    )
    restore()

    _replace_manifest_payload(
        output,
        mask_path.name,
        _coverage_nrrd(bytes([1] * 8), scalar_type="signed char"),
    )
    assert "unsigned 8-bit" in " ".join(registration_bundle_summary(output)["errors"])
    restore()

    _replace_manifest_payload(
        output,
        mask_path.name,
        _coverage_nrrd(bytes([1, 1, 1, 2, 1, 1, 1, 1])),
    )
    assert "only 0 and 1" in " ".join(registration_bundle_summary(output)["errors"])
    restore()

    _replace_manifest_payload(
        output,
        mask_path.name,
        _coverage_nrrd(bytes(8)),
    )
    assert "no sampling support" in " ".join(registration_bundle_summary(output)["errors"])
    restore()

    _replace_manifest_payload(
        output,
        mask_path.name,
        _coverage_nrrd(bytes([1] * 8), encoding="gzip"),
    )
    assert registration_bundle_summary(output)["valid"] is True
    restore()

    manifest = json.loads(manifest_path.read_text())
    manifest["coverage_mask"]["foreground_voxel_count"] = 7
    manifest["coverage_mask"]["foreground_fraction"] = 0.875
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    manifest_path.chmod(0o600)
    assert "coverage mask contract" in " ".join(
        registration_bundle_summary(output)["errors"]
    )
    restore()

    manifest = json.loads(manifest_path.read_text())
    manifest["schema_version"] = "1.0.0"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    manifest_path.chmod(0o600)
    assert registration_bundle_summary(output)["valid"] is False
    restore()

    report = json.loads(report_path.read_text())
    report["schema_version"] = "1.0.0"
    _replace_manifest_payload(
        output,
        report_path.name,
        (json.dumps(report, separators=(",", ":")) + "\n").encode(),
    )
    assert "engine report disagrees" in " ".join(
        registration_bundle_summary(output)["errors"]
    )


def test_registration_failure_or_source_change_creates_no_partial_output(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "dicom"
    catalog, registry, _ = registration_catalog(source_root)
    failed_output = tmp_path / "failed-output"
    failing_executable = fake_slicer(tmp_path / "Slicer-fail", fail=True)

    hash_mismatch_output = tmp_path / "hash-mismatch-output"
    with pytest.raises(ValueError, match="expected SHA-256"):
        run_rigid_registration(
            catalog,
            registry,
            source_root=source_root,
            fixed_series_id=FIXED_SERIES,
            moving_series_id=MOVING_SERIES,
            output=hash_mismatch_output,
            slicer_executable=failing_executable,
            expected_slicer_sha256="0" * 64,
            attest_series_selection=True,
            timeout_seconds=60,
        )
    assert not hash_mismatch_output.exists()

    with pytest.raises(ValueError, match="private diagnostics were deleted") as failure:
        run_rigid_registration(
            catalog,
            registry,
            source_root=source_root,
            fixed_series_id=FIXED_SERIES,
            moving_series_id=MOVING_SERIES,
            output=failed_output,
            slicer_executable=failing_executable,
            expected_slicer_sha256=_sha256(failing_executable.read_bytes()),
            attest_series_selection=True,
            timeout_seconds=60,
        )
    assert "SECRET" not in str(failure.value)
    assert not failed_output.exists()

    outside_executable = fake_slicer(tmp_path / "Slicer-outside-check")
    with pytest.raises(ValueError, match="outside the immutable DICOM source"):
        run_rigid_registration(
            catalog,
            registry,
            source_root=source_root,
            fixed_series_id=FIXED_SERIES,
            moving_series_id=MOVING_SERIES,
            output=source_root / "forbidden-derivative",
            slicer_executable=outside_executable,
            expected_slicer_sha256=_sha256(outside_executable.read_bytes()),
            attest_series_selection=True,
            timeout_seconds=60,
        )

    changed_output = tmp_path / "changed-output"
    registry[next(iter(registry))].write_bytes(b"changed after catalog")
    changed_executable = fake_slicer(tmp_path / "Slicer-ok")
    with pytest.raises(ValueError, match="changed after cataloging"):
        run_rigid_registration(
            catalog,
            registry,
            source_root=source_root,
            fixed_series_id=FIXED_SERIES,
            moving_series_id=MOVING_SERIES,
            output=changed_output,
            slicer_executable=changed_executable,
            expected_slicer_sha256=_sha256(changed_executable.read_bytes()),
            attest_series_selection=True,
            timeout_seconds=60,
        )
    assert not changed_output.exists()

    doctor = registration_doctor(tmp_path / "Slicer-ok")
    assert doctor["local_only"] is True
    assert doctor["external_api_required"] is False
    assert doctor["required_engine"] == {
        "name": "3D Slicer",
        "version": "5.12.3",
        "computed_revision": "34627",
        "runtime_repository_revision": "9034c71",
        "module": "BRAINSFit",
        "coverage_module": "BRAINSResample",
    }
    assert doctor["executable_found"] is True
    assert doctor["network_isolation"]["required"] is True
    assert doctor["network_isolation"]["available"] is True
    assert doctor["network_isolation"]["mechanism"] in {
        "macos_sandbox_exec_deny_all_network",
        "linux_bwrap_network_namespace_seccomp_no_sockets",
        "linux_bwrap_network_namespace_seccomp_no_network_sockets",
    }
    assert doctor["network_isolation"]["external_network_denied"] is True
    assert doctor["network_isolation"]["host_network_isolated"] is True
    assert doctor["network_isolation"]["unsandboxed_fallback"] is False
    assert doctor["display_runtime"] == {
        "required": False,
        "available": True,
        "mechanism": "native_platform_display_runtime",
        "private_local_display": True,
        "external_network_listener": False,
        "inherited_display_allowed": False,
    }
    assert doctor["ready_for_execution_check"] is True


def test_engine_network_sandbox_cannot_reach_host_loopback(tmp_path: Path) -> None:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    marker = tmp_path / "network-denied"
    probe = tmp_path / "network-probe.py"
    probe.write_text(
        "import os, socket, sys\n"
        "from pathlib import Path\n"
        "connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
        "connection.settimeout(2)\n"
        "try:\n"
        "    connection.connect(('127.0.0.1', int(os.environ['PROBE_PORT'])))\n"
        "except OSError:\n"
        "    Path(os.environ['PROBE_MARKER']).write_text('network isolated')\n"
        "    raise SystemExit(0)\n"
        "finally:\n"
        "    connection.close()\n"
        "raise SystemExit(9)\n"
    )
    try:
        _run_local_engine(
            [sys.executable, str(probe)],
            temporary=tmp_path,
            environment={
                "PROBE_PORT": str(listener.getsockname()[1]),
                "PROBE_MARKER": str(marker),
            },
            timeout_seconds=10,
        )
    finally:
        listener.close()
    assert marker.read_text() == "network isolated"


def test_engine_refuses_unsandboxed_execution(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(registration_module.platform, "system", lambda: "Unsupported")
    with pytest.raises(ValueError, match="OS-enforced network isolation"):
        _run_local_engine(
            [sys.executable, "-c", "raise SystemExit(0)"],
            temporary=tmp_path,
            environment={},
            timeout_seconds=10,
        )
    doctor = registration_doctor()
    assert doctor["network_isolation"]["available"] is False
    assert doctor["network_isolation"]["unsandboxed_fallback"] is False
    assert doctor["ready_for_execution_check"] is False


def test_linux_engine_sandbox_command_is_network_isolated(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(registration_module.platform, "system", lambda: "Linux")
    monkeypatch.setattr(registration_module.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(
        registration_module.shutil,
        "which",
        lambda name: "/usr/bin/bwrap" if name == "bwrap" else None,
    )
    command, mechanism = registration_module._sandboxed_engine_command(
        ["/opt/Slicer/Slicer", "--no-main-window"],
        tmp_path,
        seccomp_descriptor=9,
    )
    assert mechanism == (
        "linux_bwrap_network_namespace_seccomp_no_network_sockets"
    )
    assert {
        "--new-session",
        "--unshare-all",
        "--seccomp",
        "--ro-bind",
        "--bind",
        "--chdir",
        "--dev",
    }.issubset(command)
    assert command[command.index("--seccomp") + 1] == "9"
    assert command[-2:] == ["/opt/Slicer/Slicer", "--no-main-window"]

    payload = registration_module._linux_network_socket_seccomp_filter()
    assert len(payload) == 16 * 8
    instructions = [
        registration_module.struct.unpack("=HBBI", payload[index : index + 8])
        for index in range(0, len(payload), 8)
    ]
    assert instructions[6][3] == 41  # socket
    assert instructions[7][3] == 53  # socketpair
    assert [instruction[3] for instruction in instructions[8:11]] == [425, 426, 427]
    assert instructions[12][3] == 16  # seccomp_data.args[0], socket domain
    assert instructions[13][3] == 1  # AF_UNIX
    assert instructions[-1][3] == 0x00050000 | errno.EPERM
    descriptor = registration_module._open_linux_network_seccomp_filter(tmp_path)
    try:
        metadata = os.fstat(descriptor)
        assert stat.S_IMODE(metadata.st_mode) == 0o600
        assert metadata.st_nlink == 0
        assert os.read(descriptor, len(payload)) == payload
    finally:
        os.close(descriptor)
    assert not list(tmp_path.glob("network-deny.*.seccomp.private"))


def test_linux_engine_refuses_unshare_without_bwrap(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(registration_module.platform, "system", lambda: "Linux")
    monkeypatch.setattr(registration_module.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(
        registration_module.shutil,
        "which",
        lambda name: "/usr/bin/unshare" if name == "unshare" else None,
    )
    status = registration_module._network_isolation_status()
    assert status["available"] is False
    with pytest.raises(ValueError, match="OS-enforced network isolation"):
        registration_module._sandboxed_engine_command(
            ["/opt/Slicer/Slicer"],
            tmp_path,
        )


def test_linux_slicer_uses_private_xvfb_without_tcp(monkeypatch) -> None:
    monkeypatch.setattr(registration_module.platform, "system", lambda: "Linux")
    monkeypatch.setattr(
        registration_module.shutil,
        "which",
        lambda name: "/usr/bin/xvfb-run" if name == "xvfb-run" else None,
    )
    status = registration_module._slicer_display_runtime_status()
    assert status == {
        "required": True,
        "available": True,
        "mechanism": "linux_private_xvfb_no_tcp",
        "private_local_display": True,
        "external_network_listener": False,
        "inherited_display_allowed": False,
    }
    command = registration_module._private_display_command(
        ["/usr/bin/bwrap", "--", "/opt/Slicer/Slicer"]
    )
    assert command[:3] == [
        "/usr/bin/xvfb-run",
        "--auto-servernum",
        "--server-args=-screen 0 1280x1024x24 -nolisten tcp",
    ]
    assert command[-3:] == ["/usr/bin/bwrap", "--", "/opt/Slicer/Slicer"]


def test_linux_doctor_refuses_inherited_display_without_xvfb(
    tmp_path: Path, monkeypatch
) -> None:
    slicer = tmp_path / "Slicer"
    slicer.write_text("#!/bin/sh\nexit 0\n")
    slicer.chmod(0o700)
    monkeypatch.setattr(registration_module.platform, "system", lambda: "Linux")
    monkeypatch.setattr(registration_module.platform, "machine", lambda: "x86_64")
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(
        registration_module.shutil,
        "which",
        lambda name: "/usr/bin/bwrap" if name == "bwrap" else None,
    )
    doctor = registration_doctor(slicer)
    assert doctor["network_isolation"]["available"] is True
    assert doctor["display_runtime"] == {
        "required": True,
        "available": False,
        "mechanism": None,
        "private_local_display": False,
        "external_network_listener": None,
        "inherited_display_allowed": False,
    }
    assert doctor["ready_for_execution_check"] is False
    assert "Xvfb" in doctor["note"]


def test_linux_engine_trust_record_keeps_checksum_and_signature_distinct() -> None:
    repository = Path(__file__).parents[3]
    record = json.loads(
        (repository / "packaging/slicer/linux-amd64-5.12.3.json").read_text()
    )
    assert record["record_type"] == "scanview_slicer_engine_trust"
    assert record["official_package"]["bytes"] == 498_683_944
    assert record["official_package"]["sha512"] == (
        "66bd3a1b9a7f636b40b96cb8c49f395ee783cdcaf7b43a4b895d6a40df9e0af"
        "8393f5ab7631ba50f6bbe06aa17dbcd8a46984a53b693bdf203d34337e2e80401"
    )
    assert record["publisher"]["download_sha512_matches_official_metadata"] is True
    assert record["publisher"]["linux_package_signature_provided"] is False
    assert record["publisher"]["publisher_signature_verified"] is False
    assert record["verification"]["source_sha256_manifests_unchanged"] is True
    assert record["verification"]["seccomp_af_inet_socket"] == "denied with EPERM"
    assert record["verification"]["external_api_required"] is False
    assert record["verification"]["patient_data_used"] is False


def test_engine_timeout_terminates_the_private_process_group(tmp_path: Path) -> None:
    group_file = tmp_path / "process-group"
    launcher = tmp_path / "launcher"
    launcher.write_text(
        "#!/usr/bin/env python3\n"
        "import os, subprocess, sys, time\n"
        "from pathlib import Path\n"
        "Path(os.environ['GROUP_FILE']).write_text(str(os.getpgrp()))\n"
        "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        "time.sleep(60)\n"
    )
    launcher.chmod(0o700)
    environment = {"GROUP_FILE": str(group_file)}

    with pytest.raises(ValueError, match="bounded timeout"):
        _run_local_engine(
            [str(launcher)],
            temporary=tmp_path,
            environment=environment,
            timeout_seconds=1,
        )

    process_group = int(group_file.read_text())
    with pytest.raises(ProcessLookupError):
        os.killpg(process_group, 0)

    staging = tmp_path / "staging"
    existing_output = tmp_path / "existing-output"
    staging.mkdir()
    existing_output.mkdir()
    with pytest.raises(ValueError, match="already exists"):
        _publish_directory_no_replace(staging, existing_output)
    assert staging.is_dir()
    assert existing_output.is_dir()
