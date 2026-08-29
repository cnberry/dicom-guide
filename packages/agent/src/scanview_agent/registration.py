from __future__ import annotations

import ctypes
import errno
import gzip
import hashlib
import json
import math
import os
import platform
import re
import secrets
import shutil
import signal
import stat
import struct
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .catalog import hash_file
from .comparison import score_pair


SCHEMA_VERSION = "1.0.0"
SUPPORTED_SLICER_VERSION = "5.12.3"
# The public release table calls 34627 the computed revision. The running app
# exposes the Git revision through slicer.app.repositoryRevision instead.
SUPPORTED_SLICER_COMPUTED_REVISION = "34627"
SUPPORTED_SLICER_RUNTIME_REPOSITORY_REVISION = "9034c71"
REQUEST_ENVIRONMENT_VARIABLE = "SCANVIEW_REGISTRATION_REQUEST"
MACOS_NETWORK_DENY_PROFILE = "(version 1) (allow default) (deny network*)"
REGISTRATION_PARAMETERS = {
    "transform_type": "Rigid",
    "degrees_of_freedom": 6,
    "initialize_transform_mode": "useCenterOfHeadAlign",
    "mask_processing_mode": "ROIAUTO",
    "roi_auto_dilate_mm": 3.0,
    "sampling_percentage": 0.02,
    "interpolation_mode": "Linear",
    "histogram_match": False,
}
ENGINE_OUTPUTS = {
    "fixed_volume": "fixed.nrrd",
    "moving_volume": "moving.nrrd",
    "registered_moving_volume": "registered-moving.nrrd",
    "moving_to_fixed_transform": "moving-to-fixed.tfm",
}
BUNDLE_FILES = {
    *ENGINE_OUTPUTS.values(),
    "engine-report.json",
    "registration.json",
}
SERIES_ID = re.compile(r"^series_[0-9a-f]{20}$")
STUDY_ID = re.compile(r"^study_[0-9a-f]{20}$")
PATIENT_ID = re.compile(r"^patient_[0-9a-f]{20}$")
INSTANCE_ID = re.compile(r"^instance_[0-9a-f]{20}$")
JOB_ID = re.compile(r"^registration_[0-9a-f]{20}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
MAX_REPORT_BYTES = 64 * 1024
MAX_MANIFEST_BYTES = 4 * 1024 * 1024
MAX_DERIVATIVE_FILE_BYTES = 16 * 1024 * 1024 * 1024
MIN_REGISTRATION_INSTANCES = 5
MIN_REGISTRATION_COVERAGE_MM = 10.0
SUPPORTED_SOP_CLASS = {
    "CT": "1.2.840.10008.5.1.4.1.1.2",
    "MR": "1.2.840.10008.5.1.4.1.1.4",
}
REQUIRED_QA_CHECKS = [
    (
        "Confirm the intended earlier and later sequences, acquisition suitability, "
        "and clinical baseline or nadir role."
    ),
    "Inspect opacity overlay throughout the full shared anatomy.",
    "Inspect checkerboard alignment at brain boundary, ventricles, and stable landmarks.",
    "Inspect fixed-versus-registered edge agreement and local distortion near tumor or surgery.",
    "Record landmark residuals or explain why quantitative landmarks are unavailable.",
    "Accept or reject this transform explicitly before any derived display is unlocked.",
]
LIMITATIONS = [
    "This rigid transform is generated research evidence and remains unreviewed.",
    "Registration does not prove same-lesion identity, tumor boundaries, or treatment response.",
    (
        "Tumor, edema, surgery, ventricles, artifacts, and coverage changes can cause "
        "plausible but wrong alignment."
    ),
    (
        "The resampled moving volume is interpolated and is never a replacement for "
        "either native DICOM series."
    ),
    (
        "Histogram matching is disabled so the registration step does not intentionally "
        "remap lesion intensity profiles."
    ),
    (
        "No overlay, swipe, subtraction, mask propagation, segmentation, or response "
        "conclusion is unlocked."
    ),
    (
        "Earlier and later are chronological registration roles; neither establishes a "
        "clinical treatment-response baseline or nadir."
    ),
    (
        "The executable version and revision are self-reported; an expected binary hash "
        "must match, but ScanView does not authenticate the distributor or code signature."
    ),
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _aggregate_instances(instances: list[dict[str, Any]]) -> str:
    return hashlib.sha256(_canonical(instances)).hexdigest()


def _exact_keys(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"{label} has unsupported or missing fields")
    return value


def _valid_date(value: Any) -> bool:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{8}", value):
        return False
    try:
        datetime.strptime(value, "%Y%m%d")
    except ValueError:
        return False
    return True


def _finite_numbers(value: Any, length: int) -> bool:
    return (
        isinstance(value, list)
        and len(value) == length
        and all(
            isinstance(item, (int, float))
            and not isinstance(item, bool)
            and math.isfinite(float(item))
            for item in value
        )
    )


def _orientation_is_orthonormal(value: Any) -> bool:
    if not _finite_numbers(value, 6):
        return False
    row = [float(item) for item in value[:3]]
    column = [float(item) for item in value[3:]]
    row_norm = math.sqrt(sum(item * item for item in row))
    column_norm = math.sqrt(sum(item * item for item in column))
    dot = sum(left * right for left, right in zip(row, column))
    return (
        abs(row_norm - 1.0) <= 0.02
        and abs(column_norm - 1.0) <= 0.02
        and abs(dot) <= 0.02
    )


def _normal_from_orientation(value: list[float]) -> list[float]:
    row = [float(item) for item in value[:3]]
    column = [float(item) for item in value[3:]]
    normal = [
        row[1] * column[2] - row[2] * column[1],
        row[2] * column[0] - row[0] * column[2],
        row[0] * column[1] - row[1] * column[0],
    ]
    magnitude = math.sqrt(sum(item * item for item in normal))
    return [item / magnitude for item in normal]


def _descriptor_terms(series: dict[str, Any]) -> set[str]:
    text = " ".join(
        value
        for value in (series.get("series_description"), series.get("protocol_name"))
        if isinstance(value, str)
    ).lower()
    return {term for term in re.split(r"[^a-z0-9]+", text) if term}


def _sequence_family(series: dict[str, Any]) -> str | None:
    if series.get("modality") == "CT":
        return "ct"
    terms = _descriptor_terms(series)
    if "flair" in terms:
        return "flair"
    if terms & {"dwi", "diffusion", "trace"}:
        return "dwi"
    if "adc" in terms:
        return "adc"
    if terms & {"swi", "susceptibility", "t2star"}:
        return "swi"
    if terms & {"t1", "t1w", "mprage", "spgr", "bravo", "vibe"}:
        return "t1"
    if terms & {"t2", "t2w", "space", "cube"}:
        return "t2"
    return None


def _contrast_category(series: dict[str, Any]) -> str | None:
    descriptor = " ".join(
        value
        for value in (series.get("series_description"), series.get("protocol_name"))
        if isinstance(value, str)
    ).lower()
    terms = _descriptor_terms(series)
    described_contrast = bool(
        terms & {"post", "postcontrast", "postgad", "contrast", "gad", "gado", "ce"}
        or re.search(r"(?:\+c|c\+)", descriptor)
    )
    described_noncontrast = bool(
        terms & {"pre", "precontrast", "noncontrast", "without"}
        or re.search(r"\bw\s*[/\-]\s*o\b", descriptor)
    )
    agent_reported = series.get("contrast_present") is True
    if described_noncontrast and (described_contrast or agent_reported):
        return None
    if described_contrast or agent_reported:
        return "contrast"
    if described_noncontrast:
        return "noncontrast"
    return None


def _registration_source_profile(series: dict[str, Any], role: str) -> dict[str, str]:
    terms = _descriptor_terms(series)
    image_type = {
        str(value).upper()
        for value in series.get("image_type", [])
        if isinstance(value, str)
    }
    if (
        "ORIGINAL" not in image_type
        or "PRIMARY" not in image_type
        or image_type & {"DERIVED", "LOCALIZER", "SCOUT"}
        or terms & {"localizer", "scout", "survey"}
    ):
        raise ValueError(f"{role} must be one original primary diagnostic series")
    body_part = re.sub(r"[^A-Z0-9]", "", str(series.get("body_part") or "").upper())
    if body_part not in {"BRAIN", "HEAD"}:
        raise ValueError(f"{role} must have explicit brain or head anatomy metadata")
    sequence_family = _sequence_family(series)
    if sequence_family is None:
        raise ValueError(f"{role} sequence family cannot be established conservatively")
    contrast_category = _contrast_category(series)
    if contrast_category is None:
        raise ValueError(f"{role} contrast category is unknown or contradictory")
    return {
        "sequence_family": sequence_family,
        "contrast_category": contrast_category,
    }


def _find_series(catalog: dict[str, Any], series_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    if not SERIES_ID.fullmatch(series_id):
        raise ValueError("registration requires a valid opaque series ID")
    matches = []
    for study in catalog.get("studies", []):
        if not isinstance(study, dict):
            continue
        for series in study.get("series", []):
            if isinstance(series, dict) and series.get("id") == series_id:
                matches.append((study, series))
    if len(matches) != 1:
        raise ValueError("registration series must resolve exactly once in the catalog")
    return matches[0]


def _source_reference(
    study: dict[str, Any],
    series: dict[str, Any],
    *,
    role: str,
) -> dict[str, Any]:
    study_id = study.get("id")
    series_id = series.get("id")
    patient_context_id = series.get("patient_context_id")
    acquisition_date = series.get("acquisition_date") or study.get("acquisition_date")
    modality = series.get("modality")
    instances = series.get("instances")
    if not isinstance(study_id, str) or not STUDY_ID.fullmatch(study_id):
        raise ValueError(f"{role} study has an invalid opaque ID")
    if not isinstance(series_id, str) or not SERIES_ID.fullmatch(series_id):
        raise ValueError(f"{role} series has an invalid opaque ID")
    if not isinstance(patient_context_id, str) or not PATIENT_ID.fullmatch(patient_context_id):
        raise ValueError(f"{role} series lacks one valid opaque patient context")
    if modality not in {"MR", "CT"}:
        raise ValueError(f"{role} registration source must be MR or CT")
    if not _valid_date(acquisition_date):
        raise ValueError(f"{role} registration source needs a valid acquisition date")
    if (
        not isinstance(instances, list)
        or len(instances) < MIN_REGISTRATION_INSTANCES
        or series.get("instance_count") != len(instances)
    ):
        raise ValueError(f"{role} registration source needs a complete volumetric stack")
    if (
        not isinstance(series.get("rows"), int)
        or isinstance(series.get("rows"), bool)
        or series["rows"] < 2
        or not isinstance(series.get("columns"), int)
        or isinstance(series.get("columns"), bool)
        or series["columns"] < 2
        or not _finite_numbers(series.get("pixel_spacing"), 2)
        or any(float(item) <= 0 for item in series["pixel_spacing"])
        or not _orientation_is_orthonormal(series.get("image_orientation_patient"))
    ):
        raise ValueError(f"{role} registration source has incomplete or invalid geometry")

    source_instances = []
    seen_ids: set[str] = set()
    positions: list[list[float]] = []
    expected_orientation = [float(item) for item in series["image_orientation_patient"]]
    expected_spacing = [float(item) for item in series["pixel_spacing"]]
    expected_sop_class = SUPPORTED_SOP_CLASS[modality]
    for instance in instances:
        if not isinstance(instance, dict):
            raise ValueError(f"{role} registration source has a malformed instance")
        instance_id = instance.get("id")
        digest = instance.get("sha256")
        byte_count = instance.get("bytes")
        if (
            not isinstance(instance_id, str)
            or not INSTANCE_ID.fullmatch(instance_id)
            or instance_id in seen_ids
        ):
            raise ValueError(f"{role} registration source has an invalid opaque instance ID")
        if not isinstance(digest, str) or not SHA256.fullmatch(digest):
            raise ValueError(f"{role} registration requires a SHA-256 for every source instance")
        if (
            not isinstance(byte_count, int)
            or isinstance(byte_count, bool)
            or byte_count <= 0
        ):
            raise ValueError(f"{role} registration source has an invalid byte count")
        if not _finite_numbers(instance.get("image_position_patient"), 3):
            raise ValueError(f"{role} registration source needs every patient-space slice position")
        if (
            instance.get("sop_class_uid") != expected_sop_class
            or instance.get("number_of_frames") != 1
            or instance.get("rows") != series["rows"]
            or instance.get("columns") != series["columns"]
            or not _finite_numbers(instance.get("pixel_spacing"), 2)
            or any(
                abs(float(left) - right) > 1e-6
                for left, right in zip(instance["pixel_spacing"], expected_spacing)
            )
            or not _orientation_is_orthonormal(instance.get("image_orientation_patient"))
            or any(
                abs(float(left) - right) > 0.002
                for left, right in zip(
                    instance["image_orientation_patient"], expected_orientation
                )
            )
        ):
            raise ValueError(f"{role} registration source has mixed or unsupported image geometry")
        seen_ids.add(instance_id)
        positions.append([float(item) for item in instance["image_position_patient"]])
        source_instances.append(
            {"instance_id": instance_id, "bytes": byte_count, "sha256": digest}
        )
    normal = _normal_from_orientation(expected_orientation)
    projected_unsorted = [
        sum(value * axis for value, axis in zip(point, normal)) for point in positions
    ]
    origin = positions[0]
    origin_projection = projected_unsorted[0]
    for point, coordinate in zip(positions, projected_unsorted):
        expected = [
            value + axis * (coordinate - origin_projection)
            for value, axis in zip(origin, normal)
        ]
        lateral_error = math.sqrt(
            sum((value - target) ** 2 for value, target in zip(point, expected))
        )
        if lateral_error > 0.5:
            raise ValueError(f"{role} registration source is not one coplanar stack")
    projected = sorted(projected_unsorted)
    spacings = [right - left for left, right in zip(projected, projected[1:])]
    if not spacings or any(spacing < 0.01 for spacing in spacings):
        raise ValueError(f"{role} registration source has duplicate or invalid slice positions")
    sorted_spacings = sorted(spacings)
    middle = len(sorted_spacings) // 2
    median_spacing = (
        sorted_spacings[middle]
        if len(sorted_spacings) % 2
        else (sorted_spacings[middle - 1] + sorted_spacings[middle]) / 2
    )
    tolerance = max(0.1, median_spacing * 0.1)
    if (
        projected[-1] - projected[0] < MIN_REGISTRATION_COVERAGE_MM
        or any(abs(spacing - median_spacing) > tolerance for spacing in spacings)
    ):
        raise ValueError(f"{role} registration source has insufficient or irregular coverage")
    return {
        "role": role,
        "patient_context_id": patient_context_id,
        "study_id": study_id,
        "series_id": series_id,
        "acquisition_date": acquisition_date,
        "modality": modality,
        "instance_count": len(source_instances),
        "instances_sha256": _aggregate_instances(source_instances),
        "instances": source_instances,
    }


def select_registration_sources(
    catalog: dict[str, Any],
    *,
    fixed_series_id: str,
    moving_series_id: str,
    attest_series_selection: bool,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if not isinstance(catalog, dict) or catalog.get("schema_version") != "1.0.0":
        raise ValueError("registration requires a ScanView manifest v1 catalog")
    if not attest_series_selection:
        raise ValueError("registration requires explicit attestation of the selected series")
    if fixed_series_id == moving_series_id:
        raise ValueError("registration requires two distinct source series")
    fixed_study, fixed_series = _find_series(catalog, fixed_series_id)
    moving_study, moving_series = _find_series(catalog, moving_series_id)
    fixed_profile = _registration_source_profile(fixed_series, "fixed earlier source")
    moving_profile = _registration_source_profile(moving_series, "moving later source")
    fixed = _source_reference(fixed_study, fixed_series, role="fixed_earlier")
    moving = _source_reference(moving_study, moving_series, role="moving_later")
    if fixed["patient_context_id"] != moving["patient_context_id"]:
        raise ValueError("registration requires one matching opaque patient context")
    if fixed["study_id"] == moving["study_id"]:
        raise ValueError("registration requires source series from distinct studies")
    if fixed["modality"] != moving["modality"]:
        raise ValueError("registration requires the same MR or CT modality")
    if fixed["acquisition_date"] >= moving["acquisition_date"]:
        raise ValueError("registration requires a strictly earlier fixed source")
    if fixed_profile["sequence_family"] != moving_profile["sequence_family"]:
        raise ValueError("registration requires one conservatively matched sequence family")
    if fixed_profile["contrast_category"] != moving_profile["contrast_category"]:
        raise ValueError("registration requires one matching explicit contrast category")
    compatibility = score_pair(fixed_series, moving_series)
    if compatibility["compatibility"] != "compatible":
        raise ValueError("the selected series require review beyond the registration metadata gate")
    compatibility_snapshot = {
        "score": compatibility["score"],
        "compatibility": compatibility["compatibility"],
        "warnings": compatibility["warnings"],
        "auto_approved": False,
        "review_status": "unreviewed",
        "sequence_family": fixed_profile["sequence_family"],
        "contrast_category": fixed_profile["contrast_category"],
    }
    return fixed, moving, compatibility_snapshot


def _discover_slicer(explicit: Path | None = None) -> Path | None:
    candidates: list[Path] = []
    if explicit:
        candidates.append(explicit)
        if explicit.suffix == ".app":
            candidates.append(explicit / "Contents" / "MacOS" / "Slicer")
    located = shutil.which("Slicer")
    if located:
        candidates.append(Path(located))
    if platform.system() == "Darwin":
        candidates.extend(
            [
                Path("/Applications/Slicer.app/Contents/MacOS/Slicer"),
                Path.home() / "Applications" / "Slicer.app" / "Contents" / "MacOS" / "Slicer",
            ]
        )
    elif platform.system() == "Linux":
        candidates.extend(sorted(Path("/opt").glob("Slicer*/Slicer"), reverse=True))
        candidates.extend(
            sorted((Path.home() / "Applications").glob("Slicer*/Slicer"), reverse=True)
        )
    for candidate in candidates:
        try:
            resolved = candidate.expanduser().resolve(strict=True)
        except OSError:
            continue
        if resolved.is_file() and os.access(resolved, os.X_OK):
            return resolved
    return None


def registration_doctor(slicer_executable: Path | None = None) -> dict[str, Any]:
    supported_platform = platform.system() in {"Darwin", "Linux"}
    executable = _discover_slicer(slicer_executable)
    network_isolation = _network_isolation_status()
    if not supported_platform:
        note = "Registration execution is supported only on macOS and Linux."
    elif executable is None:
        note = (
            "Install the required local Slicer build; ScanView does not download an "
            "engine or use an external processing API."
        )
    elif not network_isolation["available"]:
        note = (
            "Install a supported OS network-isolation mechanism; ScanView has no "
            "unsandboxed fallback."
        )
    else:
        note = (
            "The exact Slicer version and BRAINSFit completion are checked during "
            "OS-enforced no-network execution."
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "local_only": True,
        "external_api_required": False,
        "platform": f"{platform.system()}-{platform.machine()}",
        "supported_platform": supported_platform,
        "required_engine": {
            "name": "3D Slicer",
            "version": SUPPORTED_SLICER_VERSION,
            "computed_revision": SUPPORTED_SLICER_COMPUTED_REVISION,
            "runtime_repository_revision": (
                SUPPORTED_SLICER_RUNTIME_REPOSITORY_REVISION
            ),
            "module": "BRAINSFit",
        },
        "executable_found": executable is not None,
        "executable_sha256": hash_file(executable) if executable else None,
        "engine_identity_status": (
            "observed_binary_hash_not_distributor_authenticated"
            if executable
            else "unavailable"
        ),
        "network_isolation": network_isolation,
        "ready_for_execution_check": bool(
            supported_platform and executable and network_isolation["available"]
        ),
        "note": note,
    }


def _network_isolation_status() -> dict[str, Any]:
    system = platform.system()
    mechanism: str | None = None
    if system == "Darwin":
        sandbox = Path("/usr/bin/sandbox-exec")
        if sandbox.is_file() and os.access(sandbox, os.X_OK):
            mechanism = "macos_sandbox_exec_deny_all_network"
    elif system == "Linux":
        if shutil.which("bwrap") and _linux_seccomp_architecture() is not None:
            mechanism = "linux_bwrap_network_namespace_seccomp_no_sockets"
    return {
        "required": True,
        "available": mechanism is not None,
        "mechanism": mechanism,
        "external_network_denied": mechanism is not None,
        "host_network_isolated": mechanism is not None,
        "unsandboxed_fallback": False,
    }


def _linux_seccomp_architecture() -> tuple[int, int, int] | None:
    machine = platform.machine().lower()
    if machine in {"x86_64", "amd64"}:
        return 0xC000003E, 41, 53
    if machine in {"aarch64", "arm64"}:
        return 0xC00000B7, 198, 199
    return None


def _linux_no_socket_seccomp_filter() -> bytes:
    architecture = _linux_seccomp_architecture()
    if architecture is None:
        raise ValueError("Linux registration network isolation is unsupported on this CPU")
    audit_arch, socket_syscall, socketpair_syscall = architecture
    load_word_absolute = 0x20
    jump_equal_constant = 0x15
    jump_greater_or_equal_constant = 0x35
    return_constant = 0x06
    seccomp_allow = 0x7FFF0000
    seccomp_kill_process = 0x80000000
    seccomp_errno = 0x00050000 | errno.EPERM
    instructions = [
        (load_word_absolute, 0, 0, 4),
        (jump_equal_constant, 1, 0, audit_arch),
        (return_constant, 0, 0, seccomp_kill_process),
        (load_word_absolute, 0, 0, 0),
        # Reject the x32 syscall range on x86-64 and any unexpected high syscall
        # namespace on the supported 64-bit architectures.
        (jump_greater_or_equal_constant, 0, 1, 0x40000000),
        (return_constant, 0, 0, seccomp_kill_process),
        (jump_equal_constant, 5, 0, socket_syscall),
        (jump_equal_constant, 4, 0, socketpair_syscall),
        (jump_equal_constant, 3, 0, 425),
        (jump_equal_constant, 2, 0, 426),
        (jump_equal_constant, 1, 0, 427),
        (return_constant, 0, 0, seccomp_allow),
        (return_constant, 0, 0, seccomp_errno),
    ]
    return b"".join(struct.pack("=HBBI", *instruction) for instruction in instructions)


def _open_linux_seccomp_filter(temporary: Path) -> int:
    descriptor, name = tempfile.mkstemp(
        prefix="network-deny.",
        suffix=".seccomp.private",
        dir=temporary,
    )
    path = Path(name)
    try:
        payload = _linux_no_socket_seccomp_filter()
        written = os.write(descriptor, payload)
        if written != len(payload):
            raise OSError("short seccomp filter write")
        os.fsync(descriptor)
        os.lseek(descriptor, 0, os.SEEK_SET)
        path.unlink()
        return descriptor
    except Exception:
        os.close(descriptor)
        path.unlink(missing_ok=True)
        raise


def _sandboxed_engine_command(
    command: list[str], temporary: Path, *, seccomp_descriptor: int | None = None
) -> tuple[list[str], str]:
    status = _network_isolation_status()
    mechanism = status["mechanism"]
    if not status["available"] or not isinstance(mechanism, str):
        raise ValueError(
            "local Slicer registration requires supported OS-enforced network isolation"
        )
    if mechanism == "macos_sandbox_exec_deny_all_network":
        return [
            "/usr/bin/sandbox-exec",
            "-p",
            MACOS_NETWORK_DENY_PROFILE,
            *command,
        ], mechanism
    if mechanism == "linux_bwrap_network_namespace_seccomp_no_sockets":
        executable = shutil.which("bwrap")
        if executable is None or seccomp_descriptor is None or seccomp_descriptor < 0:
            raise ValueError("local registration network isolation became unavailable")
        private = str(temporary.resolve(strict=True))
        return [
            executable,
            "--die-with-parent",
            "--new-session",
            "--unshare-all",
            "--seccomp",
            str(seccomp_descriptor),
            "--ro-bind",
            "/",
            "/",
            "--dev",
            "/dev",
            "--proc",
            "/proc",
            "--bind",
            private,
            private,
            "--chdir",
            private,
            "--",
            *command,
        ], mechanism
    raise ValueError("local registration network isolation mechanism is unsupported")


def _verify_and_stage_series(
    source: dict[str, Any],
    registry: dict[str, Path],
    destination: Path,
    source_root: Path,
) -> None:
    destination.mkdir(mode=0o700)
    for index, instance in enumerate(source["instances"], start=1):
        path = registry.get(instance["instance_id"])
        if path is None:
            raise ValueError("registration source instance is missing from the local registry")
        try:
            resolved = path.resolve(strict=True)
            file_stat = resolved.stat()
        except OSError as error:
            raise ValueError("registration source instance is unreadable") from error
        if (
            not resolved.is_file()
            or path.is_symlink()
            or not resolved.is_relative_to(source_root)
        ):
            raise ValueError("registration source instance must be one regular local file")
        if file_stat.st_size != instance["bytes"] or hash_file(resolved) != instance["sha256"]:
            raise ValueError("registration source instance changed after cataloging")
        staged = destination / f"{index:06d}.dcm"
        shutil.copyfile(resolved, staged)
        staged.chmod(0o600)
        if staged.stat().st_size != instance["bytes"] or hash_file(staged) != instance["sha256"]:
            raise ValueError("registration source changed while being staged")


def _engine_environment(temporary: Path, request_path: Path) -> dict[str, str]:
    allowed = {
        "DISPLAY",
        "HOME",
        "LANG",
        "LC_ALL",
        "LOGNAME",
        "PATH",
        "USER",
        "WAYLAND_DISPLAY",
        "XAUTHORITY",
    }
    environment = {
        key: value for key, value in os.environ.items() if key in allowed
    }
    environment[REQUEST_ENVIRONMENT_VARIABLE] = str(request_path)
    environment["PYTHONNOUSERSITE"] = "1"
    environment["PYTHONPYCACHEPREFIX"] = str(temporary / "python-cache")
    for variable in ("TMPDIR", "TMP", "TEMP"):
        environment[variable] = str(temporary)
    return environment


def _run_local_engine(
    command: list[str],
    *,
    temporary: Path,
    environment: dict[str, str],
    timeout_seconds: int,
) -> str:
    stdout_path = temporary / "engine-stdout.private"
    stderr_path = temporary / "engine-stderr.private"
    with stdout_path.open("wb") as stdout_stream, stderr_path.open("wb") as stderr_stream:
        stdout_path.chmod(0o600)
        stderr_path.chmod(0o600)
        isolation = _network_isolation_status()
        seccomp_descriptor = -1
        if isolation.get("mechanism") == (
            "linux_bwrap_network_namespace_seccomp_no_sockets"
        ):
            seccomp_descriptor = _open_linux_seccomp_filter(temporary)
        try:
            sandboxed_command, network_isolation_mechanism = _sandboxed_engine_command(
                command,
                temporary,
                seccomp_descriptor=(
                    seccomp_descriptor if seccomp_descriptor >= 0 else None
                ),
            )
            try:
                process = subprocess.Popen(
                    sandboxed_command,
                    cwd=temporary,
                    env=environment,
                    stdout=stdout_stream,
                    stderr=stderr_stream,
                    start_new_session=True,
                    pass_fds=(
                        (seccomp_descriptor,) if seccomp_descriptor >= 0 else ()
                    ),
                )
            except OSError as error:
                raise ValueError(
                    "the required local Slicer process could not be started"
                ) from error
        finally:
            if seccomp_descriptor >= 0:
                os.close(seccomp_descriptor)
        try:
            return_code = process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=5)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                pass
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
            raise ValueError("local Slicer registration exceeded its bounded timeout") from None
    if return_code != 0:
        raise ValueError("local Slicer registration failed; private diagnostics were deleted")
    return network_isolation_mechanism


def _fsync_directory_tree(directory: Path) -> None:
    for path in directory.iterdir():
        if path.is_file() and not path.is_symlink():
            with path.open("rb") as stream:
                os.fsync(stream.fileno())
    directory_descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(directory_descriptor)
    finally:
        os.close(directory_descriptor)


def _publish_directory_no_replace(staging: Path, output: Path) -> None:
    library = ctypes.CDLL(None, use_errno=True)
    source = os.fsencode(staging)
    destination = os.fsencode(output)
    system = platform.system()
    if system == "Darwin":
        try:
            rename = library.renamex_np
        except AttributeError as error:
            raise ValueError("atomic no-replace publication is unavailable") from error
        rename.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        result = rename(source, destination, 0x00000004)  # RENAME_EXCL
    elif system == "Linux":
        try:
            rename = library.renameat2
        except AttributeError as error:
            raise ValueError("atomic no-replace publication is unavailable") from error
        rename.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        rename.restype = ctypes.c_int
        result = rename(-100, source, -100, destination, 0x00000001)  # RENAME_NOREPLACE
    else:
        raise ValueError("atomic registration publication supports only macOS and Linux")
    if result == 0:
        parent_descriptor = os.open(output.parent, os.O_RDONLY)
        try:
            os.fsync(parent_descriptor)
        finally:
            os.close(parent_descriptor)
        return
    error_number = ctypes.get_errno()
    if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
        raise ValueError("registration output already exists; outputs are never overwritten")
    raise ValueError("registration output could not be published atomically")


def _read_engine_report(
    path: Path, *, expected_status: str = "completed"
) -> dict[str, Any]:
    try:
        if not path.is_file() or path.stat().st_size > MAX_REPORT_BYTES:
            raise ValueError("registration engine report is missing or too large")
        report = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("registration engine report is invalid") from error
    report = _exact_keys(
        report,
        {
            "schema_version",
            "status",
            "engine",
            "application_version",
            "repository_revision",
            "module",
            "platform",
            "parameters",
            "outputs",
        },
        "registration engine report",
    )
    if (
        report["schema_version"] != SCHEMA_VERSION
        or report["status"] != expected_status
        or report["engine"] != "3D Slicer"
        or report["application_version"] != SUPPORTED_SLICER_VERSION
        or str(report["repository_revision"])
        != SUPPORTED_SLICER_RUNTIME_REPOSITORY_REVISION
        or report["module"] != "BRAINSFit"
        or not isinstance(report["platform"], str)
        or not 1 <= len(report["platform"]) <= 80
        or report["parameters"] != REGISTRATION_PARAMETERS
        or report["outputs"] != ENGINE_OUTPUTS
    ):
        raise ValueError("registration engine report disagrees with the required contract")
    return report


def _parse_vector(value: str, length: int, label: str) -> tuple[float, ...]:
    parts = [item.strip() for item in value.strip().strip("()").split(",")]
    if len(parts) != length:
        raise ValueError(f"registration NRRD {label} is invalid")
    try:
        numbers = tuple(float(item) for item in parts)
    except ValueError as error:
        raise ValueError(f"registration NRRD {label} is invalid") from error
    if not all(math.isfinite(item) for item in numbers):
        raise ValueError(f"registration NRRD {label} is invalid")
    return numbers


def _read_nrrd(path: Path) -> dict[str, Any]:
    type_bytes = {
        "signed char": 1,
        "int8": 1,
        "int8_t": 1,
        "uchar": 1,
        "unsigned char": 1,
        "uint8": 1,
        "uint8_t": 1,
        "short": 2,
        "short int": 2,
        "signed short": 2,
        "signed short int": 2,
        "int16": 2,
        "int16_t": 2,
        "ushort": 2,
        "unsigned short": 2,
        "unsigned short int": 2,
        "uint16": 2,
        "uint16_t": 2,
        "int": 4,
        "signed int": 4,
        "int32": 4,
        "int32_t": 4,
        "uint": 4,
        "unsigned int": 4,
        "uint32": 4,
        "uint32_t": 4,
        "float": 4,
        "double": 8,
    }
    with path.open("rb") as stream:
        prefix = stream.read(1024 * 1024)
    separator = b"\r\n\r\n" if b"\r\n\r\n" in prefix else b"\n\n"
    offset = prefix.find(separator)
    if offset < 0:
        raise ValueError("registration engine volume has no bounded NRRD header")
    payload_offset = offset + len(separator)
    try:
        lines = prefix[:offset].decode("ascii").splitlines()
    except UnicodeDecodeError as error:
        raise ValueError("registration engine volume has a non-ASCII NRRD header") from error
    if not lines or not re.fullmatch(r"NRRD000[1-5]", lines[0]):
        raise ValueError("registration engine volume is not a supported NRRD file")
    fields: dict[str, str] = {}
    for line in lines[1:]:
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            raise ValueError("registration engine volume has a malformed NRRD header")
        key, value = line.split(":", 1)
        key = key.strip().lower()
        if key in fields:
            raise ValueError("registration engine volume repeats a NRRD field")
        fields[key] = value.strip()
    if fields.get("data file") or fields.get("datafile"):
        raise ValueError("registration engine volume must use one embedded NRRD payload")
    if fields.get("dimension") != "3":
        raise ValueError("registration engine volume must be one 3-D scalar NRRD")
    space = fields.get("space", "").lower()
    if space not in {"left-posterior-superior", "right-anterior-superior"}:
        raise ValueError("registration engine volume has an unsupported patient space")
    try:
        sizes = tuple(int(item) for item in fields.get("sizes", "").split())
    except ValueError as error:
        raise ValueError("registration engine volume has invalid NRRD sizes") from error
    if len(sizes) != 3 or any(item <= 0 for item in sizes):
        raise ValueError("registration engine volume has invalid NRRD sizes")
    scalar_type = fields.get("type", "").lower()
    if scalar_type not in type_bytes:
        raise ValueError("registration engine volume has an unsupported NRRD scalar type")
    encoding = fields.get("encoding", "").lower()
    if encoding not in {"raw", "gzip", "gz"}:
        raise ValueError("registration engine volume has an unsupported NRRD encoding")
    direction_text = fields.get("space directions", "")
    direction_parts = re.findall(r"\([^)]*\)", direction_text)
    if len(direction_parts) != 3:
        raise ValueError("registration engine volume lacks three NRRD space directions")
    directions = tuple(_parse_vector(item, 3, "space direction") for item in direction_parts)
    if any(math.sqrt(sum(value * value for value in item)) <= 0 for item in directions):
        raise ValueError("registration engine volume has a zero NRRD space direction")
    origin = _parse_vector(fields.get("space origin", ""), 3, "space origin")
    expected_bytes = math.prod(sizes) * type_bytes[scalar_type]
    if not 1 <= expected_bytes <= MAX_DERIVATIVE_FILE_BYTES:
        raise ValueError("registration engine volume has an invalid NRRD payload size")
    if encoding == "raw":
        if path.stat().st_size - payload_offset != expected_bytes:
            raise ValueError("registration engine volume has a truncated NRRD payload")
    else:
        decompressed_bytes = 0
        try:
            with path.open("rb") as raw_stream:
                raw_stream.seek(payload_offset)
                with gzip.GzipFile(fileobj=raw_stream) as payload_stream:
                    while chunk := payload_stream.read(1024 * 1024):
                        decompressed_bytes += len(chunk)
                        if decompressed_bytes > expected_bytes:
                            break
        except (OSError, EOFError) as error:
            raise ValueError("registration engine volume has an invalid NRRD payload") from error
        if decompressed_bytes != expected_bytes:
            raise ValueError("registration engine volume has a truncated NRRD payload")
    return {
        "sizes": sizes,
        "space_directions": directions,
        "space_origin": origin,
        "space": space,
        "scalar_type": scalar_type,
        "encoding": encoding,
    }


def _read_rigid_transform(path: Path) -> tuple[float, ...]:
    try:
        content = path.read_text("ascii")
    except (OSError, UnicodeDecodeError) as error:
        raise ValueError("registration engine transform is not a text ITK transform") from error
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if (
        not lines
        or lines[0] != "#Insight Transform File V1.0"
        or sum(line.startswith("Transform:") for line in lines) != 1
        or "Transform: AffineTransform_double_3_3" not in lines
    ):
        raise ValueError("registration engine transform is not one 3-D affine ITK transform")
    parameter_lines = [line for line in lines if line.startswith("Parameters:")]
    fixed_lines = [line for line in lines if line.startswith("FixedParameters:")]
    try:
        parameters = tuple(float(item) for item in parameter_lines[0].split()[1:])
        fixed = tuple(float(item) for item in fixed_lines[0].split()[1:])
    except (IndexError, ValueError) as error:
        raise ValueError("registration engine transform parameters are invalid") from error
    if (
        len(parameter_lines) != 1
        or len(fixed_lines) != 1
        or len(parameters) != 12
        or len(fixed) != 3
        or not all(math.isfinite(item) for item in (*parameters, *fixed))
    ):
        raise ValueError("registration engine transform parameters are invalid")
    rotation = [parameters[0:3], parameters[3:6], parameters[6:9]]
    for row in rotation:
        if abs(sum(value * value for value in row) - 1.0) > 1e-4:
            raise ValueError("registration engine transform is not rigid")
    if any(
        abs(sum(rotation[left][axis] * rotation[right][axis] for axis in range(3)))
        > 1e-4
        for left, right in ((0, 1), (0, 2), (1, 2))
    ):
        raise ValueError("registration engine transform is not rigid")
    determinant = (
        rotation[0][0]
        * (rotation[1][1] * rotation[2][2] - rotation[1][2] * rotation[2][1])
        - rotation[0][1]
        * (rotation[1][0] * rotation[2][2] - rotation[1][2] * rotation[2][0])
        + rotation[0][2]
        * (rotation[1][0] * rotation[2][1] - rotation[1][1] * rotation[2][0])
    )
    if abs(determinant - 1.0) > 1e-4:
        raise ValueError("registration engine transform is not a proper rigid transform")
    return parameters


def _check_engine_outputs(work: Path) -> None:
    for name in ENGINE_OUTPUTS.values():
        path = work / name
        if not path.is_file() or path.is_symlink():
            raise ValueError("registration engine did not create every required output")
        size = path.stat().st_size
        if not 8 <= size <= MAX_DERIVATIVE_FILE_BYTES:
            raise ValueError("registration engine output has an invalid size")
    fixed_geometry = _read_nrrd(work / "fixed.nrrd")
    _read_nrrd(work / "moving.nrrd")
    registered_geometry = _read_nrrd(work / "registered-moving.nrrd")
    if (
        fixed_geometry["sizes"] != registered_geometry["sizes"]
        or fixed_geometry["space"] != registered_geometry["space"]
        or any(
            abs(left - right) > 1e-5
            for left_row, right_row in zip(
                fixed_geometry["space_directions"],
                registered_geometry["space_directions"],
            )
            for left, right in zip(left_row, right_row)
        )
        or any(
            abs(left - right) > 1e-5
            for left, right in zip(
                fixed_geometry["space_origin"], registered_geometry["space_origin"]
            )
        )
    ):
        raise ValueError("registered moving volume does not use the fixed volume geometry")
    _read_rigid_transform(work / "moving-to-fixed.tfm")


def _manifest(
    *,
    fixed: dict[str, Any],
    moving: dict[str, Any],
    compatibility: dict[str, Any],
    executable_sha256: str,
    runner: Path,
    engine_report: dict[str, Any],
    network_isolation_mechanism: str,
    staged_output: Path,
    created_at: str,
) -> dict[str, Any]:
    files = []
    for name in sorted({*ENGINE_OUTPUTS.values(), "engine-report.json"}):
        path = staged_output / name
        files.append({"name": name, "bytes": path.stat().st_size, "sha256": hash_file(path)})
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "rigid_registration",
        "artifact_state": "generated_pending_qa",
        "review_status": "unreviewed",
        "sensitive": True,
        "deidentified": False,
        "created_at": created_at,
        "job_id": f"registration_{secrets.token_hex(10)}",
        "source": {
            "immutable": True,
            "fixed": fixed,
            "moving": moving,
            "transform_direction": "moving_later_to_fixed_earlier",
        },
        "pairing": {
            "selection": "human_attested_unverified",
            "same_patient_context": True,
            "patient_identity_status": "opaque_context_match_unverified",
            "same_modality": True,
            "distinct_studies": True,
            "strictly_chronological": True,
            "brain_or_head_anatomy": True,
            "diagnostic_original_primary": True,
            "regular_volume_geometry": True,
            "sequence_family": compatibility["sequence_family"],
            "contrast_category": compatibility["contrast_category"],
            "clinical_baseline_status": "not_assessed",
            "metadata_compatibility": compatibility,
            "same_lesion_identity": "not_assessed",
        },
        "algorithm": {
            "engine": engine_report["engine"],
            "application_version": engine_report["application_version"],
            "repository_revision": str(engine_report["repository_revision"]),
            "module": engine_report["module"],
            "platform": engine_report["platform"],
            "parameters": REGISTRATION_PARAMETERS,
            "transform_coordinate_system": "DICOM patient LPS",
            "executable_sha256": executable_sha256,
            "runner_sha256": hash_file(runner),
            "engine_identity": (
                "self_reported_version_revision_expected_binary_hash_matched_"
                "distributor_not_authenticated"
            ),
            "external_api_requested_by_scanview": False,
            "network_isolation": {
                "status": "os_enforced",
                "mechanism": network_isolation_mechanism,
                "external_network": "denied",
                "host_network": "isolated",
                "unsandboxed_fallback": False,
            },
        },
        "files": files,
        "qa": {
            "status": "pending",
            "reviewed_at": None,
            "review_record": None,
            "required_checks": REQUIRED_QA_CHECKS,
            "display_unlocks": {
                "overlay": False,
                "swipe": False,
                "subtraction": False,
                "mask_propagation": False,
            },
        },
        "computed_results": [],
        "candidate_interpretations": [],
        "limitations": LIMITATIONS,
    }


def run_rigid_registration(
    catalog: dict[str, Any],
    registry: dict[str, Path],
    *,
    source_root: Path,
    fixed_series_id: str,
    moving_series_id: str,
    output: Path,
    slicer_executable: Path | None = None,
    expected_slicer_sha256: str,
    attest_series_selection: bool,
    timeout_seconds: int = 7200,
    runner_script: Path | None = None,
) -> dict[str, Any]:
    fixed, moving, compatibility = select_registration_sources(
        catalog,
        fixed_series_id=fixed_series_id,
        moving_series_id=moving_series_id,
        attest_series_selection=attest_series_selection,
    )
    source_root = source_root.expanduser().resolve(strict=True)
    if not source_root.is_dir():
        raise ValueError("registration source root must be one local directory")
    output = output.expanduser().resolve(strict=False)
    if output.exists():
        raise ValueError("registration output already exists; outputs are never overwritten")
    if output == source_root or output.is_relative_to(source_root):
        raise ValueError("registration output must be outside the immutable DICOM source")
    if not isinstance(timeout_seconds, int) or not 60 <= timeout_seconds <= 24 * 60 * 60:
        raise ValueError("registration timeout must be between 60 seconds and 24 hours")
    executable = _discover_slicer(slicer_executable)
    if executable is None:
        raise ValueError("the required local Slicer executable is unavailable")
    if not isinstance(expected_slicer_sha256, str) or not SHA256.fullmatch(
        expected_slicer_sha256
    ):
        raise ValueError("registration requires one expected local Slicer SHA-256")
    executable_sha256 = hash_file(executable)
    if executable_sha256 != expected_slicer_sha256:
        raise ValueError("the local Slicer executable does not match the expected SHA-256")
    runner = (
        runner_script.expanduser().resolve(strict=True)
        if runner_script
        else Path(__file__).with_name("slicer_registration_runner.py").resolve(strict=True)
    )
    if not runner.is_file():
        raise ValueError("the local ScanView Slicer runner is unavailable")

    output.parent.mkdir(parents=True, exist_ok=True)
    created_at = _utc_now()
    with tempfile.TemporaryDirectory(prefix="scanview-registration-") as temporary_name:
        temporary = Path(temporary_name)
        temporary.chmod(0o700)
        fixed_input = temporary / "fixed-input"
        moving_input = temporary / "moving-input"
        work = temporary / "work"
        work.mkdir(mode=0o700)
        request_path = temporary / "request.json"
        preflight_report_path = work / "preflight-report.private.json"
        preflight_request = {
            "schema_version": SCHEMA_VERSION,
            "mode": "preflight",
            "report_path": str(preflight_report_path),
            "parameters": REGISTRATION_PARAMETERS,
        }
        request_path.write_text(
            json.dumps(preflight_request, separators=(",", ":")) + "\n"
        )
        request_path.chmod(0o600)
        environment = _engine_environment(temporary, request_path)
        command = [
            str(executable),
            "--disable-settings",
            "--ignore-slicerrc",
            "--no-splash",
            "--no-main-window",
            "--python-script",
            str(runner),
        ]
        preflight_network_isolation = _run_local_engine(
            command,
            temporary=temporary,
            environment=environment,
            timeout_seconds=min(timeout_seconds, 300),
        )
        _read_engine_report(
            preflight_report_path, expected_status="preflight_completed"
        )
        if hash_file(executable) != executable_sha256:
            raise ValueError("the local Slicer executable changed during preflight")
        preflight_report_path.unlink()

        _verify_and_stage_series(fixed, registry, fixed_input, source_root)
        _verify_and_stage_series(moving, registry, moving_input, source_root)
        report_path = work / "engine-report.json"
        request = {
            "schema_version": SCHEMA_VERSION,
            "mode": "registration",
            "fixed_input_dir": str(fixed_input),
            "moving_input_dir": str(moving_input),
            "work_dir": str(work),
            "report_path": str(report_path),
            "parameters": REGISTRATION_PARAMETERS,
        }
        request_path.write_text(json.dumps(request, separators=(",", ":")) + "\n")
        execution_network_isolation = _run_local_engine(
            command,
            temporary=temporary,
            environment=environment,
            timeout_seconds=timeout_seconds,
        )
        if execution_network_isolation != preflight_network_isolation:
            raise ValueError("local registration network isolation changed during execution")
        if hash_file(executable) != executable_sha256:
            raise ValueError("the local Slicer executable changed during registration")
        engine_report = _read_engine_report(report_path)
        _check_engine_outputs(work)

        staging = Path(
            tempfile.mkdtemp(prefix=f".{output.name}.pending-", dir=output.parent)
        )
        staging.chmod(0o700)
        try:
            for name in ENGINE_OUTPUTS.values():
                destination = staging / name
                shutil.copyfile(work / name, destination)
                destination.chmod(0o600)
            report_destination = staging / "engine-report.json"
            shutil.copyfile(report_path, report_destination)
            report_destination.chmod(0o600)
            manifest = _manifest(
                fixed=fixed,
                moving=moving,
                compatibility=compatibility,
                executable_sha256=executable_sha256,
                runner=runner,
                engine_report=engine_report,
                network_isolation_mechanism=execution_network_isolation,
                staged_output=staging,
                created_at=created_at,
            )
            manifest_path = staging / "registration.json"
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
            manifest_path.chmod(0o600)
            summary = registration_bundle_summary(staging)
            if not summary["valid"]:
                raise ValueError("assembled registration bundle failed local validation")
            _fsync_directory_tree(staging)
            _publish_directory_no_replace(staging, output)
            return manifest
        finally:
            if staging.exists():
                shutil.rmtree(staging)


def _source_errors(value: Any, role: str) -> list[str]:
    errors: list[str] = []
    expected = {
        "role",
        "patient_context_id",
        "study_id",
        "series_id",
        "acquisition_date",
        "modality",
        "instance_count",
        "instances_sha256",
        "instances",
    }
    if not isinstance(value, dict) or set(value) != expected:
        return [f"source.{role} has unsupported or missing fields"]
    if value["role"] != role:
        errors.append(f"source.{role}.role is invalid")
    for field, pattern in (
        ("patient_context_id", PATIENT_ID),
        ("study_id", STUDY_ID),
        ("series_id", SERIES_ID),
    ):
        if not isinstance(value[field], str) or not pattern.fullmatch(value[field]):
            errors.append(f"source.{role}.{field} is invalid")
    if not _valid_date(value["acquisition_date"]):
        errors.append(f"source.{role}.acquisition_date is invalid")
    if value["modality"] not in {"MR", "CT"}:
        errors.append(f"source.{role}.modality is invalid")
    instances = value["instances"]
    if (
        not isinstance(instances, list)
        or len(instances) < MIN_REGISTRATION_INSTANCES
        or value["instance_count"] != len(instances)
    ):
        errors.append(f"source.{role}.instances are invalid")
        return errors
    instance_ids: set[str] = set()
    for instance in instances:
        if (
            not isinstance(instance, dict)
            or set(instance) != {"instance_id", "bytes", "sha256"}
            or not isinstance(instance.get("instance_id"), str)
            or not INSTANCE_ID.fullmatch(instance["instance_id"])
            or not isinstance(instance.get("bytes"), int)
            or isinstance(instance.get("bytes"), bool)
            or instance["bytes"] <= 0
            or not isinstance(instance.get("sha256"), str)
            or not SHA256.fullmatch(instance["sha256"])
        ):
            errors.append(f"source.{role} contains an invalid instance reference")
            break
        if instance["instance_id"] in instance_ids:
            errors.append(f"source.{role} repeats an instance reference")
            break
        instance_ids.add(instance["instance_id"])
    if value["instances_sha256"] != _aggregate_instances(instances):
        errors.append(f"source.{role}.instances_sha256 is invalid")
    return errors


def registration_bundle_errors(directory: Path) -> list[str]:
    errors: list[str] = []
    expanded = directory.expanduser()
    try:
        if expanded.is_symlink():
            return ["registration bundle must not be a symbolic link"]
        directory = expanded.resolve(strict=True)
    except OSError:
        return ["registration bundle is unavailable"]
    if not directory.is_dir():
        return ["registration bundle must be one regular directory"]
    directory_stat = directory.stat()
    if (
        stat.S_IMODE(directory_stat.st_mode) != 0o700
        or directory_stat.st_uid != os.getuid()
    ):
        return ["registration bundle directory is not owner-only"]
    paths = list(directory.iterdir())
    members = {path.name for path in paths}
    if members != BUNDLE_FILES:
        return ["registration bundle has missing, extra, or linked files"]
    for path in paths:
        file_stat = path.lstat()
        if (
            not stat.S_ISREG(file_stat.st_mode)
            or stat.S_IMODE(file_stat.st_mode) != 0o600
            or file_stat.st_uid != os.getuid()
            or file_stat.st_nlink != 1
        ):
            return ["registration bundle contains a linked or non-owner-only file"]
    manifest_path = directory / "registration.json"
    try:
        if manifest_path.stat().st_size > MAX_MANIFEST_BYTES:
            return ["registration manifest is too large"]
        manifest = json.loads(manifest_path.read_text())
    except (OSError, json.JSONDecodeError):
        return ["registration manifest is invalid JSON"]
    expected_top = {
        "schema_version",
        "artifact_type",
        "artifact_state",
        "review_status",
        "sensitive",
        "deidentified",
        "created_at",
        "job_id",
        "source",
        "pairing",
        "algorithm",
        "files",
        "qa",
        "computed_results",
        "candidate_interpretations",
        "limitations",
    }
    if not isinstance(manifest, dict) or set(manifest) != expected_top:
        return ["registration manifest has unsupported or missing fields"]
    if (
        manifest["schema_version"] != SCHEMA_VERSION
        or manifest["artifact_type"] != "rigid_registration"
        or manifest["artifact_state"] != "generated_pending_qa"
        or manifest["review_status"] != "unreviewed"
        or manifest["sensitive"] is not True
        or manifest["deidentified"] is not False
        or not isinstance(manifest["job_id"], str)
        or not JOB_ID.fullmatch(manifest["job_id"])
    ):
        errors.append("registration manifest identity or state is invalid")
    try:
        created_at = str(manifest["created_at"])
        datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        if not created_at.endswith("Z"):
            raise ValueError
    except (TypeError, ValueError):
        errors.append("registration created_at is invalid")
    source = manifest.get("source")
    if not isinstance(source, dict) or set(source) != {
        "immutable",
        "fixed",
        "moving",
        "transform_direction",
    }:
        errors.append("registration source contract is invalid")
    else:
        if source["immutable"] is not True or source["transform_direction"] != (
            "moving_later_to_fixed_earlier"
        ):
            errors.append("registration source direction is invalid")
        source_errors = _source_errors(source["fixed"], "fixed_earlier")
        source_errors.extend(_source_errors(source["moving"], "moving_later"))
        errors.extend(source_errors)
        if not source_errors:
            if source["fixed"]["patient_context_id"] != source["moving"]["patient_context_id"]:
                errors.append("registration sources do not share patient context")
            if source["fixed"]["study_id"] == source["moving"]["study_id"]:
                errors.append("registration sources repeat one study")
            if source["fixed"]["series_id"] == source["moving"]["series_id"]:
                errors.append("registration sources repeat one series")
            if source["fixed"]["modality"] != source["moving"]["modality"]:
                errors.append("registration sources use different modalities")
            if source["fixed"]["acquisition_date"] >= source["moving"]["acquisition_date"]:
                errors.append("registration sources are not strictly chronological")

    pairing = manifest.get("pairing")
    if (
        not isinstance(pairing, dict)
        or set(pairing)
        != {
            "selection",
            "same_patient_context",
            "patient_identity_status",
            "same_modality",
            "distinct_studies",
            "strictly_chronological",
            "brain_or_head_anatomy",
            "diagnostic_original_primary",
            "regular_volume_geometry",
            "sequence_family",
            "contrast_category",
            "clinical_baseline_status",
            "metadata_compatibility",
            "same_lesion_identity",
        }
        or pairing.get("selection") != "human_attested_unverified"
        or pairing.get("same_patient_context") is not True
        or pairing.get("patient_identity_status") != "opaque_context_match_unverified"
        or pairing.get("same_modality") is not True
        or pairing.get("distinct_studies") is not True
        or pairing.get("strictly_chronological") is not True
        or pairing.get("brain_or_head_anatomy") is not True
        or pairing.get("diagnostic_original_primary") is not True
        or pairing.get("regular_volume_geometry") is not True
        or pairing.get("sequence_family") not in {"ct", "t1", "t2", "flair", "dwi", "adc", "swi"}
        or pairing.get("contrast_category") not in {"contrast", "noncontrast"}
        or pairing.get("clinical_baseline_status") != "not_assessed"
        or pairing.get("same_lesion_identity") != "not_assessed"
    ):
        errors.append("registration pairing contract is invalid")
    compatibility = pairing.get("metadata_compatibility") if isinstance(pairing, dict) else None
    if (
        not isinstance(compatibility, dict)
        or set(compatibility)
        != {
            "score",
            "compatibility",
            "warnings",
            "auto_approved",
            "review_status",
            "sequence_family",
            "contrast_category",
        }
        or compatibility.get("compatibility") != "compatible"
        or compatibility.get("auto_approved") is not False
        or compatibility.get("review_status") != "unreviewed"
        or not isinstance(compatibility.get("score"), int)
        or isinstance(compatibility.get("score"), bool)
        or not 80 <= compatibility["score"] <= 100
        or compatibility.get("sequence_family") != (
            pairing.get("sequence_family") if isinstance(pairing, dict) else None
        )
        or compatibility.get("contrast_category") != (
            pairing.get("contrast_category") if isinstance(pairing, dict) else None
        )
        or not isinstance(compatibility.get("warnings"), list)
        or not all(
            isinstance(item, str) and 1 <= len(item) <= 80
            for item in compatibility["warnings"]
        )
        or len(compatibility["warnings"]) != len(set(compatibility["warnings"]))
    ):
        errors.append("registration compatibility snapshot is invalid")

    algorithm = manifest.get("algorithm")
    if (
        not isinstance(algorithm, dict)
        or set(algorithm)
        != {
            "engine",
            "application_version",
            "repository_revision",
            "module",
            "platform",
            "parameters",
            "transform_coordinate_system",
            "executable_sha256",
            "runner_sha256",
            "engine_identity",
            "external_api_requested_by_scanview",
            "network_isolation",
        }
        or algorithm.get("engine") != "3D Slicer"
        or algorithm.get("application_version") != SUPPORTED_SLICER_VERSION
        or algorithm.get("repository_revision")
        != SUPPORTED_SLICER_RUNTIME_REPOSITORY_REVISION
        or algorithm.get("module") != "BRAINSFit"
        or not isinstance(algorithm.get("platform"), str)
        or not 1 <= len(algorithm["platform"]) <= 80
        or algorithm.get("parameters") != REGISTRATION_PARAMETERS
        or algorithm.get("transform_coordinate_system") != "DICOM patient LPS"
        or algorithm.get("engine_identity") != (
            "self_reported_version_revision_expected_binary_hash_matched_"
            "distributor_not_authenticated"
        )
        or algorithm.get("external_api_requested_by_scanview") is not False
        or algorithm.get("network_isolation")
        not in (
            {
                "status": "os_enforced",
                "mechanism": "macos_sandbox_exec_deny_all_network",
                "external_network": "denied",
                "host_network": "isolated",
                "unsandboxed_fallback": False,
            },
            {
                "status": "os_enforced",
                "mechanism": "linux_bwrap_network_namespace_seccomp_no_sockets",
                "external_network": "denied",
                "host_network": "isolated",
                "unsandboxed_fallback": False,
            },
        )
        or not isinstance(algorithm.get("executable_sha256"), str)
        or not SHA256.fullmatch(algorithm["executable_sha256"])
        or not isinstance(algorithm.get("runner_sha256"), str)
        or not SHA256.fullmatch(algorithm["runner_sha256"])
    ):
        errors.append("registration algorithm contract is invalid")

    file_entries = manifest.get("files")
    expected_payloads = {*ENGINE_OUTPUTS.values(), "engine-report.json"}
    if (
        not isinstance(file_entries, list)
        or len(file_entries) != len(expected_payloads)
        or {item.get("name") for item in file_entries if isinstance(item, dict)}
        != expected_payloads
    ):
        errors.append("registration file manifest is invalid")
    else:
        for item in file_entries:
            if (
                set(item) != {"name", "bytes", "sha256"}
                or not isinstance(item["bytes"], int)
                or isinstance(item["bytes"], bool)
                or item["bytes"] <= 0
                or not isinstance(item["sha256"], str)
                or not SHA256.fullmatch(item["sha256"])
            ):
                errors.append("registration file entry is invalid")
                continue
            path = directory / item["name"]
            if path.stat().st_size != item["bytes"] or hash_file(path) != item["sha256"]:
                errors.append("registration file integrity check failed")
    try:
        _check_engine_outputs(directory)
        engine_report = _read_engine_report(directory / "engine-report.json")
        if isinstance(algorithm, dict) and algorithm.get("platform") != engine_report["platform"]:
            errors.append("registration engine platform provenance is inconsistent")
    except ValueError as error:
        errors.append(str(error))

    qa = manifest.get("qa")
    expected_unlocks = {
        "overlay": False,
        "swipe": False,
        "subtraction": False,
        "mask_propagation": False,
    }
    if (
        not isinstance(qa, dict)
        or set(qa)
        != {"status", "reviewed_at", "review_record", "required_checks", "display_unlocks"}
        or qa.get("status") != "pending"
        or qa.get("reviewed_at") is not None
        or qa.get("review_record") is not None
        or qa.get("required_checks") != REQUIRED_QA_CHECKS
        or qa.get("display_unlocks") != expected_unlocks
    ):
        errors.append("registration QA gate is invalid")
    if manifest.get("computed_results") != [] or manifest.get("candidate_interpretations") != []:
        errors.append("registration must not contain measurements or interpretations")
    if manifest.get("limitations") != LIMITATIONS:
        errors.append("registration limitations are invalid")
    return errors


def registration_bundle_summary(directory: Path) -> dict[str, Any]:
    errors = registration_bundle_errors(directory)
    summary: dict[str, Any] = {
        "valid": not errors,
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "rigid_registration",
        "artifact_state": "generated_pending_qa" if not errors else "invalid",
        "review_status": "unreviewed" if not errors else "invalid",
        "qa_status": "pending" if not errors else "invalid",
        "display_unlocked": False,
        "external_api_requested_by_scanview": False,
        "errors": errors,
    }
    if not errors:
        manifest = json.loads((directory / "registration.json").read_text())
        summary["modality"] = manifest["source"]["fixed"]["modality"]
        summary["file_count"] = len(BUNDLE_FILES)
        summary["source_instance_count"] = (
            manifest["source"]["fixed"]["instance_count"]
            + manifest["source"]["moving"]["instance_count"]
        )
    return summary
