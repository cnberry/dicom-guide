from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

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
    'moving_to_fixed_transform': 'moving-to-fixed.tfm',
}
report = {
    'schema_version': '1.0.0',
    'status': 'preflight_completed' if request.get('mode') == 'preflight' else 'completed',
    'engine': '3D Slicer',
    'application_version': '5.12.3',
    'repository_revision': '34627',
    'module': 'BRAINSFit',
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
    assert manifest["algorithm"]["external_api_requested_by_scanview"] is False
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
        "schema_version": "1.0.0",
        "artifact_type": "rigid_registration",
        "artifact_state": "generated_pending_qa",
        "review_status": "unreviewed",
        "qa_status": "pending",
        "display_unlocked": False,
        "external_api_requested_by_scanview": False,
        "errors": [],
        "modality": "MR",
        "file_count": 6,
        "source_instance_count": 10,
    }
    repository_root = Path(__file__).parents[3]
    schema = json.loads(
        (repository_root / "schemas" / "scanview-rigid-registration-v1.schema.json").read_text()
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
    assert doctor["executable_found"] is True


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
