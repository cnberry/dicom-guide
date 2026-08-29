from __future__ import annotations

import hashlib
import json
import math
import os
import re
import secrets
import stat
import tempfile
import unicodedata
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .catalog import hash_file
from .registration import (
    _read_nrrd,
    registration_bundle_summary,
)


SCHEMA_VERSION = "2.0.0"
REVIEW_ID = re.compile(r"^registration_review_[0-9a-f]{20}$")
JOB_ID = re.compile(r"^registration_[0-9a-f]{20}$")
STUDY_ID = re.compile(r"^study_[0-9a-f]{20}$")
SERIES_ID = re.compile(r"^series_[0-9a-f]{20}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
MAX_REQUEST_BYTES = 2 * 1024 * 1024
MAX_RECORD_BYTES = 4 * 1024 * 1024
MAX_LANDMARK_PAIRS = 32
MAX_LANDMARK_OBSERVATIONS = 32
COVERAGE_MASK_FILENAME = "registered-moving-coverage.nrrd"
COVERAGE_MASK_ROLE = "registered_moving_sampling_support_in_fixed_geometry"
COVERAGE_MASK_SEMANTICS = "technical_sampling_support_not_anatomy_or_segmentation"
ACCEPTED_DECISION = "accepted_for_shared_coverage_overlay_swipe"
INTENDED_USE = "shared_coverage_exploratory_overlay_swipe"
ACCEPTED_SCOPE = "shared_coverage"
DECISIONS = {ACCEPTED_DECISION, "rejected"}
REVIEWER_ROLES = {
    "clinician",
    "medical_physicist",
    "patient_or_family",
    "researcher_or_engineer",
    "other",
}
TRAINING_STATUSES = {"self_attested_trained", "self_attested_not_trained"}
LANDMARK_STATUSES = {"aligned", "uncertain", "misaligned", "not_visible"}
INSPECTION_PLANES = ("axial", "coronal", "sagittal")
INSPECTION_MODES = ("checkerboard", "edges", "opacity", "swipe")
TOLERANCE_BASIS = (
    "Maximum fixed-volume voxel spacing from validated registration bundle geometry."
)
LANDMARK_LABELS = {
    "orbits",
    "optic_nerves",
    "brainstem",
    "ventricles",
    "sella_turcica",
    "nose",
    "external_auditory_canals",
    "clivus",
    "sagittal_suture",
    "outer_brain_or_skull_boundary",
    "region_of_importance",
    "other_stable_landmark",
}
QUALITATIVE_CHECKS = {
    "correct_series_roles_and_intended_use_confirmed": (
        "Correct series, chronological roles, and shared-coverage exploratory use confirmed."
    ),
    "full_shared_volume_axial_reviewed": "Full shared volume reviewed axially.",
    "full_shared_volume_coronal_reviewed": "Full shared volume reviewed coronally.",
    "full_shared_volume_sagittal_reviewed": "Full shared volume reviewed sagittally.",
    "native_and_registered_side_by_side_reviewed": (
        "Native and registered-moving views reviewed side by side."
    ),
    "opacity_overlay_reviewed": "Adjustable opacity overlay reviewed.",
    "swipe_or_flicker_reviewed": "Swipe or flicker comparison reviewed.",
    "checkerboard_reviewed": "Checkerboard comparison reviewed.",
    "edge_alignment_reviewed": "Fixed and registered-moving edge agreement reviewed.",
    "coverage_mask_boundary_and_excluded_region_reviewed": (
        "Moving-image sampling-support mask boundary and excluded regions reviewed; "
        "the mask was not interpreted as anatomy, tumor, segmentation, or registration quality."
    ),
    "region_of_importance_reviewed": "Region of greatest importance reviewed.",
    "distant_anatomy_reviewed": "Distant stable anatomy reviewed for global error.",
    "artifacts_coverage_and_anatomical_change_reviewed": (
        "Artifacts, shared coverage, surgery, edema, mass effect, and anatomical change reviewed."
    ),
    "laterality_and_orientation_reviewed": (
        "Laterality, orientation, and gross translation or rotation reviewed."
    ),
    "no_reject_condition_identified": (
        "No global mismatch, material regional mismatch, laterality error, unusable coverage, "
        "or rigid-model failure was identified."
    ),
}
SELF_ATTESTATION = (
    "I attest that this registration QA record is my self-asserted observation for "
    "exploratory display only and is not a diagnosis, treatment-response conclusion, "
    "or authenticated clinical approval."
)
LIMITATIONS = [
    "Acceptance means only spatially acceptable for exploratory overlay and swipe where the required sampling-support mask is one and shared anatomy was visually reviewed.",
    "The coverage mask identifies transformed moving-image sampling support only; it is not anatomy, tumor, segmentation, registration quality, or clinical comparability.",
    "The sampling-support mask excludes default-filled registered-moving pixels but does not establish shared anatomy.",
    "Reviewer identity, role, training, and organization are self asserted and unauthenticated.",
    "Registration QA does not establish patient identity, clinical baseline, lesion identity, tumor boundary, or response.",
    "Registered-moving pixels are resampled and must remain distinguishable from native DICOM.",
    "Tumor, edema, surgery, artifacts, distortion, mass effect, and coverage changes can make rigid alignment misleading.",
    "Subtraction, segmentation, mask propagation, resampled-image measurements, and response conclusions remain locked.",
    "Landmark residuals depend on point-selection uncertainty and do not replace full-volume qualitative inspection.",
    "This investigational workflow is not validated or cleared for primary diagnosis or treatment planning.",
    "The event SHA-256 and any previous-review reference are tamper evidence only, not a digital signature or reviewer authentication.",
]


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _reject_duplicate_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"registration QA JSON repeats object key {key!r}")
        result[key] = value
    return result


def _reject_nonfinite_constant(value: str) -> None:
    raise ValueError(f"registration QA JSON contains non-finite number {value}")


def _contains_forbidden_control(value: Any) -> bool:
    if isinstance(value, str):
        return any(unicodedata.category(character) in {"Cc", "Cf", "Cs"} for character in value)
    if isinstance(value, list):
        return any(_contains_forbidden_control(item) for item in value)
    if isinstance(value, dict):
        return any(
            _contains_forbidden_control(key) or _contains_forbidden_control(item)
            for key, item in value.items()
        )
    return False


def _strict_json_loads(payload: bytes | str) -> Any:
    try:
        value = json.loads(
            payload,
            object_pairs_hook=_reject_duplicate_object,
            parse_constant=_reject_nonfinite_constant,
            strict=True,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError("registration QA JSON is invalid") from error
    if _contains_forbidden_control(value):
        raise ValueError("registration QA JSON contains forbidden control characters")
    return value


def _created_at(value: str | None) -> str:
    if value is None:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("registration QA created_at must be an ISO 8601 UTC date-time")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("registration QA created_at must be an ISO 8601 UTC date-time") from error
    if parsed.tzinfo is None:
        raise ValueError("registration QA created_at must include a timezone")
    return value


def _safe_text(
    value: Any,
    label: str,
    maximum: int,
    *,
    required: bool = True,
    multiline: bool = False,
) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text")
    if _contains_forbidden_control(value):
        raise ValueError(f"{label} contains forbidden control characters")
    text = value.strip()
    if required and not text:
        raise ValueError(f"{label} is required")
    if len(text) > maximum or (not multiline and any(character in text for character in "\r\n")):
        raise ValueError(f"{label} is invalid or too long")
    return text or None


def _finite_point(value: Any, label: str) -> list[float]:
    if (
        not isinstance(value, list)
        or len(value) != 3
        or not all(
            isinstance(item, (int, float))
            and not isinstance(item, bool)
            and math.isfinite(float(item))
            and abs(float(item)) <= 1_000_000
            for item in value
        )
    ):
        raise ValueError(f"{label} must be three finite patient-space millimeter values")
    return [float(item) for item in value]


def _volume_geometry(path: Path) -> dict[str, Any]:
    geometry = _read_nrrd(path)
    spacing = [
        math.sqrt(sum(value * value for value in direction))
        for direction in geometry["space_directions"]
    ]
    return {
        "sizes": list(geometry["sizes"]),
        "voxel_spacing_mm": spacing,
        "coordinate_system": geometry["space"],
        "space_directions": [list(direction) for direction in geometry["space_directions"]],
        "space_origin": list(geometry["space_origin"]),
    }


def _validated_bundle(directory: Path) -> tuple[Path, dict[str, Any]]:
    expanded = directory.expanduser()
    summary = registration_bundle_summary(expanded)
    if not summary["valid"]:
        raise ValueError("registration QA requires one valid pending-QA registration bundle")
    directory = expanded.resolve(strict=True)
    manifest = _strict_json_loads((directory / "registration.json").read_bytes())
    if not isinstance(manifest, dict):
        raise ValueError("registration QA bundle manifest is invalid")
    return directory, manifest


def registration_qa_context(directory: Path) -> dict[str, Any]:
    directory, manifest = _validated_bundle(directory)
    file_entries = {item["name"]: item for item in manifest["files"]}

    def volume(role: str, filename: str, *, resampled: bool) -> dict[str, Any]:
        entry = file_entries[filename]
        return {
            "role": role,
            "filename": filename,
            "url": f"/v1/registration-qa/files/{filename}",
            "bytes": entry["bytes"],
            "sha256": entry["sha256"],
            "resampled": resampled,
            "geometry": _volume_geometry(directory / filename),
        }

    coverage = manifest["coverage_mask"]
    coverage_filename = coverage["filename"]
    coverage_entry = file_entries[coverage_filename]
    coverage_mask = {
        "role": COVERAGE_MASK_ROLE,
        "filename": coverage_filename,
        "url": f"/v1/registration-qa/files/{coverage_filename}",
        "bytes": coverage_entry["bytes"],
        "sha256": coverage_entry["sha256"],
        "derived": True,
        "scalar_type": coverage["scalar_type"],
        "binary_values": coverage["binary_values"],
        "semantics": coverage["semantics"],
        "geometry": _volume_geometry(directory / coverage_filename),
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "registration_qa_context",
        "mode": "human_qa_preview",
        "qa_preview_only": True,
        "watermark": "UNAPPROVED REGISTRATION — QA ONLY",
        "job_id": manifest["job_id"],
        "artifact_state": manifest["artifact_state"],
        "review_status": manifest["review_status"],
        "source": {
            "manifest_sha256": hash_file(directory / "registration.json"),
            "transform_direction": manifest["source"]["transform_direction"],
            "modality": manifest["source"]["fixed"]["modality"],
            "fixed": {
                "role": manifest["source"]["fixed"]["role"],
                "study_id": manifest["source"]["fixed"]["study_id"],
                "series_id": manifest["source"]["fixed"]["series_id"],
                "acquisition_date": manifest["source"]["fixed"]["acquisition_date"],
            },
            "moving": {
                "role": manifest["source"]["moving"]["role"],
                "study_id": manifest["source"]["moving"]["study_id"],
                "series_id": manifest["source"]["moving"]["series_id"],
                "acquisition_date": manifest["source"]["moving"]["acquisition_date"],
            },
        },
        "volumes": {
            "fixed": volume("fixed_earlier_reference", "fixed.nrrd", resampled=False),
            "moving": volume("moving_later_reference", "moving.nrrd", resampled=False),
            "registered_moving": volume(
                "moving_later_registered_to_fixed",
                "registered-moving.nrrd",
                resampled=True,
            ),
        },
        "coverage_mask": coverage_mask,
        "transform": {
            "filename": "moving-to-fixed.tfm",
            "sha256": file_entries["moving-to-fixed.tfm"]["sha256"],
            "coordinate_system": manifest["algorithm"]["transform_coordinate_system"],
        },
        "intended_use": INTENDED_USE,
        "qualitative_checks": [
            {"id": identifier, "label": label}
            for identifier, label in QUALITATIVE_CHECKS.items()
        ],
        "landmark_options": sorted(LANDMARK_LABELS),
        "landmark_statuses": sorted(LANDMARK_STATUSES),
        "allowed_decisions": sorted(DECISIONS),
        "display_policy": {
            "qa_preview_allowed_while_pending": [
                "reference_volume_side_by_side",
                "registered_side_by_side",
                "opacity_overlay",
                "swipe_or_flicker",
                "checkerboard",
                "edge_overlay",
                "coverage_mask_boundary",
                "landmark_residuals",
            ],
            "accepted_unlocks": ["overlay", "swipe"],
            "always_locked": [
                "subtraction",
                "mask_propagation",
                "segmentation",
                "resampled_image_measurements",
                "response_conclusions",
            ],
            "sampling_support_enforcement": "required_pixel_mask",
            "shared_anatomy_scope": "reviewer_attested_visual_only",
            "mask_failure_behavior": "lock_display",
            "mask_sampling": "nearest_neighbor",
        },
        "limitations": LIMITATIONS,
    }


def registration_qa_agent_summary(directory: Path | None) -> dict[str, Any]:
    if directory is None:
        return {
            "schema_version": SCHEMA_VERSION,
            "available": False,
            "artifact_type": "registration_qa_summary",
            "qa_status": "unavailable",
            "display_unlocked": False,
            "human_preview_required": True,
            "external_api_required": False,
        }
    try:
        directory, manifest = _validated_bundle(directory)
    except (OSError, ValueError):
        return {
            "schema_version": SCHEMA_VERSION,
            "available": False,
            "artifact_type": "registration_qa_summary",
            "qa_status": "invalid",
            "display_unlocked": False,
            "human_preview_required": True,
            "external_api_required": False,
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "available": True,
        "artifact_type": "registration_qa_summary",
        "job_id": manifest["job_id"],
        "modality": manifest["source"]["fixed"]["modality"],
        "qa_status": "pending_human_review",
        "display_unlocked": False,
        "human_preview_required": True,
        "external_api_required": False,
        "source_manifest_sha256": hash_file(directory / "registration.json"),
        "next_action": "Open the separate browser-capability QA preview; bearer API access cannot approve registration.",
    }


def _source_registration(directory: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    files = {item["name"]: item for item in manifest["files"]}
    bundle_files = [
        {
            "name": path.name,
            "bytes": path.stat().st_size,
            "sha256": hash_file(path),
        }
        for path in sorted(directory.iterdir(), key=lambda item: item.name)
    ]
    fixed_geometry = _volume_geometry(directory / "fixed.nrrd")
    registered_geometry = _volume_geometry(directory / "registered-moving.nrrd")
    coverage_geometry = _volume_geometry(directory / COVERAGE_MASK_FILENAME)
    coverage_mask = deepcopy(manifest["coverage_mask"])
    return {
        "job_id": manifest["job_id"],
        "manifest_sha256": hash_file(directory / "registration.json"),
        "transform_sha256": files["moving-to-fixed.tfm"]["sha256"],
        "fixed_volume_sha256": files["fixed.nrrd"]["sha256"],
        "moving_volume_sha256": files["moving.nrrd"]["sha256"],
        "registered_moving_volume_sha256": files["registered-moving.nrrd"]["sha256"],
        "coverage_mask_sha256": files[COVERAGE_MASK_FILENAME]["sha256"],
        "bundle_files": bundle_files,
        "bundle_sha256": _sha256(_canonical(bundle_files)),
        "transform_direction": manifest["source"]["transform_direction"],
        "modality": manifest["source"]["fixed"]["modality"],
        "fixed": {
            "study_id": manifest["source"]["fixed"]["study_id"],
            "series_id": manifest["source"]["fixed"]["series_id"],
            "acquisition_date": manifest["source"]["fixed"]["acquisition_date"],
        },
        "moving": {
            "study_id": manifest["source"]["moving"]["study_id"],
            "series_id": manifest["source"]["moving"]["series_id"],
            "acquisition_date": manifest["source"]["moving"]["acquisition_date"],
        },
        "fixed_geometry": fixed_geometry,
        "registered_geometry": registered_geometry,
        "coverage_mask_geometry": coverage_geometry,
        "coverage_mask": coverage_mask,
    }


def _reviewer(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "name",
        "role",
        "organization",
        "training_status",
    }:
        raise ValueError("registration QA reviewer fields are incomplete or unsupported")
    role = value.get("role")
    training = value.get("training_status")
    if role not in REVIEWER_ROLES:
        raise ValueError("registration QA reviewer role is unsupported")
    if training not in TRAINING_STATUSES:
        raise ValueError("registration QA training status is unsupported")
    return {
        "name": _safe_text(value.get("name"), "reviewer name", 120),
        "role": role,
        "organization": _safe_text(
            value.get("organization"), "reviewer organization", 160, required=False
        ),
        "training_status": training,
        "identity_status": "self_attested_unverified",
    }


def _qualitative_checks(value: Any) -> dict[str, bool]:
    if not isinstance(value, dict) or set(value) != set(QUALITATIVE_CHECKS):
        raise ValueError("registration QA qualitative checks are incomplete or unsupported")
    if not all(isinstance(item, bool) for item in value.values()):
        raise ValueError("registration QA qualitative checks must be true or false")
    return {identifier: value[identifier] for identifier in QUALITATIVE_CHECKS}


def _landmark_observations(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list) or len(value) > MAX_LANDMARK_OBSERVATIONS:
        raise ValueError("registration QA landmark observations are invalid")
    observations: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict) or set(item) != {"landmark", "status", "note"}:
            raise ValueError("registration QA landmark observation is malformed")
        if item.get("landmark") not in LANDMARK_LABELS:
            raise ValueError("registration QA landmark is unsupported")
        if item.get("status") not in LANDMARK_STATUSES:
            raise ValueError("registration QA landmark status is unsupported")
        observations.append(
            {
                "landmark": item["landmark"],
                "status": item["status"],
                "note": _safe_text(item.get("note"), "landmark note", 500, required=False)
                or "",
            }
        )
    if len({item["landmark"] for item in observations}) != len(observations):
        raise ValueError("registration QA landmark observations must be unique")
    return observations


def _inspection_evidence(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"planes", "modes"}:
        raise ValueError("registration QA inspection evidence is incomplete or unsupported")
    planes = value.get("planes")
    if (
        not isinstance(planes, dict)
        or not set(planes).issubset(INSPECTION_PLANES)
    ):
        raise ValueError("registration QA inspection planes are invalid")
    normalized_planes: dict[str, dict[str, float]] = {}
    for plane in INSPECTION_PLANES:
        if plane not in planes:
            continue
        coverage = planes[plane]
        if not isinstance(coverage, dict) or set(coverage) != {
            "normalized_min",
            "normalized_max",
        }:
            raise ValueError("registration QA plane coverage is malformed")
        minimum = coverage.get("normalized_min")
        maximum = coverage.get("normalized_max")
        if (
            not isinstance(minimum, (int, float))
            or isinstance(minimum, bool)
            or not isinstance(maximum, (int, float))
            or isinstance(maximum, bool)
            or not math.isfinite(float(minimum))
            or not math.isfinite(float(maximum))
            or not 0 <= float(minimum) <= float(maximum) <= 1
        ):
            raise ValueError("registration QA normalized plane coverage is invalid")
        normalized_planes[plane] = {
            "normalized_min": float(minimum),
            "normalized_max": float(maximum),
        }
    modes = value.get("modes")
    if (
        not isinstance(modes, list)
        or len(modes) > len(INSPECTION_MODES)
        or any(not isinstance(mode, str) or mode not in INSPECTION_MODES for mode in modes)
        or len(modes) != len(set(modes))
    ):
        raise ValueError("registration QA inspection modes are invalid")
    return {"planes": normalized_planes, "modes": sorted(modes)}


def _inspection_complete(value: dict[str, Any]) -> bool:
    planes = value.get("planes")
    modes = value.get("modes")
    return bool(
        isinstance(planes, dict)
        and set(planes) == set(INSPECTION_PLANES)
        and all(
            planes[plane]["normalized_min"] <= 0.05
            and planes[plane]["normalized_max"] >= 0.95
            for plane in INSPECTION_PLANES
        )
        and modes == sorted(INSPECTION_MODES)
    )


def _fixed_tolerance_mm(source_registration: Any) -> float:
    if not _source_registration_shape_valid(source_registration):
        raise ValueError("registration QA cannot establish its fixed geometry tolerance")
    return max(float(item) for item in source_registration["fixed_geometry"]["voxel_spacing_mm"])


def _quantitative_assessment(
    value: Any,
    *,
    expected_tolerance_mm: float | None,
) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "status",
        "tolerance_mm",
        "tolerance_basis",
        "pairs",
        "unavailable_reason",
    }:
        raise ValueError("registration QA quantitative assessment is incomplete")
    status = value.get("status")
    if status not in {"recorded", "unavailable"}:
        raise ValueError("registration QA quantitative status is unsupported")
    pairs = value.get("pairs")
    if not isinstance(pairs, list) or len(pairs) > MAX_LANDMARK_PAIRS:
        raise ValueError("registration QA landmark pairs are invalid")
    normalized_pairs = []
    labels: set[str] = set()
    for item in pairs:
        if not isinstance(item, dict) or set(item) != {
            "label",
            "fixed_physical_mm",
            "registered_moving_physical_mm",
        }:
            raise ValueError("registration QA landmark pair is malformed")
        label = _safe_text(item.get("label"), "landmark pair label", 80)
        assert label is not None
        if label in labels:
            raise ValueError("registration QA landmark pair labels must be unique")
        labels.add(label)
        fixed = _finite_point(item.get("fixed_physical_mm"), "fixed landmark")
        moving = _finite_point(
            item.get("registered_moving_physical_mm"), "registered-moving landmark"
        )
        residual = math.sqrt(sum((left - right) ** 2 for left, right in zip(fixed, moving)))
        normalized_pairs.append(
            {
                "label": label,
                "fixed_physical_mm": fixed,
                "registered_moving_physical_mm": moving,
                "residual_mm": round(residual, 6),
            }
        )
    if status == "recorded":
        if len(normalized_pairs) < 3:
            raise ValueError("recorded registration QA requires at least three landmark pairs")
        tolerance = value.get("tolerance_mm")
        if expected_tolerance_mm is None or not math.isfinite(expected_tolerance_mm):
            raise ValueError("recorded registration QA requires validated fixed-volume geometry")
        if (
            not isinstance(tolerance, (int, float))
            or isinstance(tolerance, bool)
            or not math.isfinite(float(tolerance))
            or not math.isclose(
                float(tolerance),
                expected_tolerance_mm,
                rel_tol=0,
                abs_tol=1e-9,
            )
        ):
            raise ValueError(
                "recorded registration QA tolerance must equal the maximum fixed-volume voxel spacing"
            )
        basis = _safe_text(value.get("tolerance_basis"), "landmark tolerance basis", 500)
        if basis != TOLERANCE_BASIS:
            raise ValueError("recorded registration QA tolerance basis is fixed by bundle geometry")
        if value.get("unavailable_reason") is not None:
            raise ValueError("recorded registration QA cannot include an unavailable reason")
        residuals = [item["residual_mm"] for item in normalized_pairs]
        return {
            "status": status,
            "tolerance_mm": expected_tolerance_mm,
            "tolerance_basis": TOLERANCE_BASIS,
            "pairs": normalized_pairs,
            "pair_count": len(normalized_pairs),
            "mean_residual_mm": round(sum(residuals) / len(residuals), 6),
            "maximum_residual_mm": max(residuals),
            "unavailable_reason": None,
        }
    if normalized_pairs or value.get("tolerance_mm") is not None or value.get("tolerance_basis") is not None:
        raise ValueError("unavailable quantitative QA cannot include pairs or a tolerance")
    reason = _safe_text(
        value.get("unavailable_reason"),
        "quantitative QA unavailable reason",
        1000,
        multiline=True,
    )
    return {
        "status": status,
        "tolerance_mm": None,
        "tolerance_basis": None,
        "pairs": [],
        "pair_count": 0,
        "mean_residual_mm": None,
        "maximum_residual_mm": None,
        "unavailable_reason": reason,
    }


def _landmark_pairs_span_three_dimensions(quantitative: dict[str, Any]) -> bool:
    pairs = quantitative.get("pairs")
    if not isinstance(pairs, list) or len(pairs) < 3:
        return False
    for field in ("fixed_physical_mm", "registered_moving_physical_mm"):
        for axis in range(3):
            values = [float(pair[field][axis]) for pair in pairs]
            if max(values) - min(values) <= 1e-6:
                return False
    return True


def _integrity_hash(record: dict[str, Any]) -> str:
    value = deepcopy(record)
    value["integrity"]["event_sha256"] = None
    return _sha256(_canonical(value))


def build_registration_review(
    registration_directory: Path,
    request: Any,
    *,
    created_at: str | None = None,
    previous_review_sha256: str | None = None,
) -> dict[str, Any]:
    directory, manifest = _validated_bundle(registration_directory)
    if not isinstance(request, dict) or set(request) != {
        "schema_version",
        "reviewer",
        "attest",
        "decision",
        "region_of_importance",
        "qualitative_checks",
        "inspection_evidence",
        "landmark_observations",
        "quantitative_assessment",
        "regional_defects",
        "note",
    }:
        raise ValueError("registration QA request fields are incomplete or unsupported")
    if request.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("registration QA request schema version is unsupported")
    if request.get("attest") is not True:
        raise ValueError("registration QA requires explicit self-attestation")
    decision = request.get("decision")
    if decision not in DECISIONS:
        raise ValueError("registration QA decision is unsupported")
    reviewer = _reviewer(request.get("reviewer"))
    checks = _qualitative_checks(request.get("qualitative_checks"))
    inspection = _inspection_evidence(request.get("inspection_evidence"))
    observations = _landmark_observations(request.get("landmark_observations"))
    source_registration = _source_registration(directory, manifest)
    fixed_tolerance = _fixed_tolerance_mm(source_registration)
    quantitative = _quantitative_assessment(
        request.get("quantitative_assessment"),
        expected_tolerance_mm=fixed_tolerance,
    )
    region = _safe_text(
        request.get("region_of_importance"), "registration QA region of importance", 500
    )
    defects_value = request.get("regional_defects")
    if not isinstance(defects_value, list) or len(defects_value) > 20:
        raise ValueError("registration QA regional defects are invalid")
    defects = [
        _safe_text(item, "registration QA regional defect", 500) for item in defects_value
    ]
    if len(defects) != len(set(defects)):
        raise ValueError("registration QA regional defects must be unique")
    note = _safe_text(request.get("note"), "registration QA note", 4000, multiline=True)
    if previous_review_sha256 is not None and not SHA256.fullmatch(previous_review_sha256):
        raise ValueError("previous registration QA record SHA-256 is invalid")

    if decision == ACCEPTED_DECISION:
        if (
            reviewer["training_status"] != "self_attested_trained"
            or reviewer["role"] not in {"clinician", "medical_physicist"}
        ):
            raise ValueError(
                "registration QA acceptance requires a self-attested trained clinician or medical physicist"
            )
        if not all(checks.values()):
            raise ValueError("registration QA acceptance requires every qualitative check")
        if not _inspection_complete(inspection):
            raise ValueError(
                "registration QA acceptance requires full normalized coverage in every plane and all comparison modes"
            )
        if defects:
            raise ValueError("registration QA acceptance cannot include regional defects")
        if len(observations) < 3 or not all(
            item["status"] == "aligned" for item in observations
        ):
            raise ValueError(
                "registration QA acceptance requires at least three observations and every observation aligned"
            )
        if quantitative["status"] != "recorded" or quantitative["pair_count"] < 3:
            raise ValueError(
                "registration QA acceptance requires at least three recorded 3-D landmark pairs"
            )
        if not _landmark_pairs_span_three_dimensions(quantitative):
            raise ValueError(
                "registration QA acceptance requires landmark pairs distributed across all three patient-space dimensions"
            )
        if quantitative["maximum_residual_mm"] > fixed_tolerance:
            raise ValueError("registration QA acceptance exceeds its predeclared tolerance")
        unlocks = {
            "overlay": True,
            "swipe": True,
            "subtraction": False,
            "mask_propagation": False,
            "segmentation": False,
            "resampled_image_measurements": False,
            "response_conclusions": False,
        }
    else:
        unlocks = {
            "overlay": False,
            "swipe": False,
            "subtraction": False,
            "mask_propagation": False,
            "segmentation": False,
            "resampled_image_measurements": False,
            "response_conclusions": False,
        }

    record = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "registration_qa_review",
        "review_id": f"registration_review_{secrets.token_hex(10)}",
        "created_at": _created_at(created_at),
        "sensitive": True,
        "deidentified": False,
        "review_status": decision,
        "intended_use": INTENDED_USE,
        "scope": ACCEPTED_SCOPE if decision == ACCEPTED_DECISION else "none",
        "region_of_importance": region,
        "source_registration": source_registration,
        "reviewer": reviewer,
        "attestation": SELF_ATTESTATION,
        "qualitative_checks": checks,
        "inspection_evidence": inspection,
        "landmark_observations": observations,
        "quantitative_assessment": quantitative,
        "regional_defects": defects,
        "note": note,
        "display_unlocks": unlocks,
        "display_label": (
            "EXPLORATORY — SELF-ATTESTED REGISTRATION QA — SPATIAL ERROR NOT QUANTIFIED"
            if quantitative["status"] == "unavailable"
            else "EXPLORATORY — SELF-ATTESTED REGISTRATION QA"
        ),
        "integrity": {
            "unverified_previous_review_sha256": previous_review_sha256,
            "event_sha256": None,
        },
        "limitations": LIMITATIONS,
    }
    record["integrity"]["event_sha256"] = _integrity_hash(record)
    errors = registration_review_errors(record, registration_directory=directory)
    if errors:
        raise ValueError(f"assembled registration QA record is invalid: {'; '.join(errors)}")
    return record


def _normalized_quantitative_record(
    value: Any,
    *,
    expected_tolerance_mm: float | None,
) -> dict[str, Any]:
    expected = {
        "status",
        "tolerance_mm",
        "tolerance_basis",
        "pairs",
        "pair_count",
        "mean_residual_mm",
        "maximum_residual_mm",
        "unavailable_reason",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError("registration QA quantitative assessment is invalid")
    pairs = value.get("pairs")
    if not isinstance(pairs, list):
        raise ValueError("registration QA quantitative landmark pairs are invalid")
    draft_pairs: list[dict[str, Any]] = []
    for item in pairs:
        if not isinstance(item, dict) or set(item) != {
            "label",
            "fixed_physical_mm",
            "registered_moving_physical_mm",
            "residual_mm",
        }:
            raise ValueError("registration QA quantitative landmark pair is invalid")
        draft_pairs.append(
            {
                "label": item.get("label"),
                "fixed_physical_mm": item.get("fixed_physical_mm"),
                "registered_moving_physical_mm": item.get(
                    "registered_moving_physical_mm"
                ),
            }
        )
    normalized = _quantitative_assessment(
        {
            "status": value.get("status"),
            "tolerance_mm": value.get("tolerance_mm"),
            "tolerance_basis": value.get("tolerance_basis"),
            "pairs": draft_pairs,
            "unavailable_reason": value.get("unavailable_reason"),
        },
        expected_tolerance_mm=expected_tolerance_mm,
    )
    if value != normalized:
        raise ValueError("registration QA quantitative derived values are invalid")
    return normalized


def registration_review_errors(
    value: Any,
    *,
    registration_directory: Path | None = None,
) -> list[str]:
    try:
        return _registration_review_errors(
            value,
            registration_directory=registration_directory,
        )
    except Exception:
        return ["registration QA record contains malformed nested data"]


def _registration_review_errors(
    value: Any,
    *,
    registration_directory: Path | None,
) -> list[str]:
    errors: list[str] = []
    expected = {
        "schema_version",
        "artifact_type",
        "review_id",
        "created_at",
        "sensitive",
        "deidentified",
        "review_status",
        "intended_use",
        "scope",
        "region_of_importance",
        "source_registration",
        "reviewer",
        "attestation",
        "qualitative_checks",
        "inspection_evidence",
        "landmark_observations",
        "quantitative_assessment",
        "regional_defects",
        "note",
        "display_unlocks",
        "display_label",
        "integrity",
        "limitations",
    }
    if not isinstance(value, dict) or set(value) != expected:
        return ["registration QA record fields are incomplete or unsupported"]
    if (
        value.get("schema_version") != SCHEMA_VERSION
        or value.get("artifact_type") != "registration_qa_review"
        or not isinstance(value.get("review_id"), str)
        or not REVIEW_ID.fullmatch(value["review_id"])
        or value.get("sensitive") is not True
        or value.get("deidentified") is not False
        or value.get("review_status") not in DECISIONS
        or value.get("intended_use") != INTENDED_USE
        or value.get("scope")
        != (ACCEPTED_SCOPE if value.get("review_status") == ACCEPTED_DECISION else "none")
        or value.get("attestation") != SELF_ATTESTATION
        or value.get("limitations") != LIMITATIONS
    ):
        errors.append("registration QA record identity or state is invalid")
    try:
        _created_at(value.get("created_at"))
        _safe_text(value.get("region_of_importance"), "registration QA region", 500)
        _safe_text(value.get("note"), "registration QA note", 4000, multiline=True)
    except ValueError as error:
        errors.append(str(error))

    reviewer = value.get("reviewer")
    normalized_reviewer: dict[str, Any] = {}
    if not isinstance(reviewer, dict) or set(reviewer) != {
        "name",
        "role",
        "organization",
        "training_status",
        "identity_status",
    }:
        errors.append("registration QA reviewer is invalid")
    else:
        try:
            normalized_reviewer = _reviewer(
                {
                    key: reviewer[key]
                    for key in ("name", "role", "organization", "training_status")
                }
            )
            if reviewer != normalized_reviewer:
                errors.append("registration QA reviewer derived values are invalid")
        except ValueError as error:
            errors.append(str(error))
        if reviewer.get("identity_status") != "self_attested_unverified":
            errors.append("registration QA reviewer identity status is invalid")

    checks = value.get("qualitative_checks")
    try:
        normalized_checks = _qualitative_checks(checks)
    except ValueError as error:
        errors.append(str(error))
        normalized_checks = {}
    inspection = value.get("inspection_evidence")
    try:
        normalized_inspection = _inspection_evidence(inspection)
        if inspection != normalized_inspection:
            errors.append("registration QA inspection evidence normalization is invalid")
    except ValueError as error:
        errors.append(str(error))
        normalized_inspection = {}
    observations = value.get("landmark_observations")
    try:
        normalized_observations = _landmark_observations(observations)
    except ValueError as error:
        errors.append(str(error))
        normalized_observations = []
    source = value.get("source_registration")
    source_shape_valid = _source_registration_shape_valid(source)
    expected_tolerance: float | None = None
    if not source_shape_valid:
        errors.append("registration QA source registration is invalid")
    else:
        try:
            expected_tolerance = _fixed_tolerance_mm(source)
        except ValueError as error:
            errors.append(str(error))
    if registration_directory is not None:
        try:
            directory, manifest = _validated_bundle(registration_directory)
            if source != _source_registration(directory, manifest):
                errors.append("registration QA source anchor does not match the bundle")
        except (OSError, ValueError):
            errors.append("registration QA source bundle is invalid")

    quantitative = value.get("quantitative_assessment")
    try:
        normalized_quantitative = _normalized_quantitative_record(
            quantitative,
            expected_tolerance_mm=expected_tolerance,
        )
    except ValueError as error:
        errors.append(str(error))
        normalized_quantitative = {}

    defects = value.get("regional_defects")
    if not isinstance(defects, list) or len(defects) > 20:
        errors.append("registration QA regional defects are invalid")
    else:
        try:
            normalized_defects = [
                _safe_text(item, "registration QA regional defect", 500) for item in defects
            ]
            if defects != normalized_defects:
                errors.append("registration QA regional defects normalization is invalid")
            if len(normalized_defects) != len(set(normalized_defects)):
                errors.append("registration QA regional defects must be unique")
        except ValueError as error:
            errors.append(str(error))

    accepted = value.get("review_status") == ACCEPTED_DECISION
    expected_unlocks = {
        "overlay": accepted,
        "swipe": accepted,
        "subtraction": False,
        "mask_propagation": False,
        "segmentation": False,
        "resampled_image_measurements": False,
        "response_conclusions": False,
    }
    if value.get("display_unlocks") != expected_unlocks:
        errors.append("registration QA display unlocks are invalid")
    expected_label = (
        "EXPLORATORY — SELF-ATTESTED REGISTRATION QA — SPATIAL ERROR NOT QUANTIFIED"
        if normalized_quantitative.get("status") == "unavailable"
        else "EXPLORATORY — SELF-ATTESTED REGISTRATION QA"
    )
    if value.get("display_label") != expected_label:
        errors.append("registration QA display label is invalid")
    if accepted:
        if (
            normalized_reviewer.get("training_status") != "self_attested_trained"
            or normalized_reviewer.get("role") not in {"clinician", "medical_physicist"}
        ):
            errors.append(
                "registration QA acceptance requires a self-attested trained clinician or medical physicist"
            )
        if not normalized_checks or not all(normalized_checks.values()):
            errors.append("registration QA acceptance requires every qualitative check")
        if not normalized_inspection or not _inspection_complete(normalized_inspection):
            errors.append(
                "registration QA acceptance requires full normalized coverage in every plane and all comparison modes"
            )
        if defects:
            errors.append("registration QA acceptance cannot include regional defects")
        if len(normalized_observations) < 3 or not all(
            item.get("status") == "aligned" for item in normalized_observations
        ):
            errors.append(
                "registration QA acceptance requires at least three observations and every observation aligned"
            )
        if (
            normalized_quantitative.get("status") != "recorded"
            or normalized_quantitative.get("pair_count", 0) < 3
        ):
            errors.append(
                "registration QA acceptance requires at least three recorded 3-D landmark pairs"
            )
        elif not _landmark_pairs_span_three_dimensions(normalized_quantitative):
            errors.append(
                "registration QA acceptance requires landmark pairs distributed across all three patient-space dimensions"
            )
        elif normalized_quantitative.get("maximum_residual_mm", math.inf) > (
            expected_tolerance if expected_tolerance is not None else -math.inf
        ):
            errors.append("registration QA acceptance exceeds its predeclared tolerance")

    integrity = value.get("integrity")
    if not isinstance(integrity, dict) or set(integrity) != {
        "unverified_previous_review_sha256",
        "event_sha256",
    }:
        errors.append("registration QA integrity fields are invalid")
    else:
        previous = integrity.get("unverified_previous_review_sha256")
        event_hash = integrity.get("event_sha256")
        if previous is not None and (
            not isinstance(previous, str) or not SHA256.fullmatch(previous)
        ):
            errors.append("registration QA previous review hash is invalid")
        if not isinstance(event_hash, str) or not SHA256.fullmatch(event_hash):
            errors.append("registration QA event hash is invalid")
        try:
            if (
                isinstance(event_hash, str)
                and SHA256.fullmatch(event_hash)
                and event_hash != _integrity_hash(value)
            ):
                errors.append("registration QA event hash does not match the record")
        except (TypeError, ValueError, RecursionError):
            errors.append("registration QA event hash input is invalid")
    return errors


def _geometry_shape_valid(value: Any) -> bool:
    def finite_vector(candidate: Any, *, positive_norm: bool = False) -> bool:
        if (
            not isinstance(candidate, list)
            or len(candidate) != 3
            or not all(
                isinstance(item, (int, float))
                and not isinstance(item, bool)
                and math.isfinite(float(item))
                and abs(float(item)) <= 1_000_000
                for item in candidate
            )
        ):
            return False
        return not positive_norm or math.hypot(*(float(item) for item in candidate)) > 0

    basic = (
        isinstance(value, dict)
        and set(value)
        == {
            "sizes",
            "voxel_spacing_mm",
            "coordinate_system",
            "space_directions",
            "space_origin",
        }
        and isinstance(value.get("sizes"), list)
        and len(value["sizes"]) == 3
        and all(isinstance(item, int) and not isinstance(item, bool) and item > 0 for item in value["sizes"])
        and isinstance(value.get("voxel_spacing_mm"), list)
        and len(value["voxel_spacing_mm"]) == 3
        and all(isinstance(item, (int, float)) and not isinstance(item, bool) and math.isfinite(float(item)) and float(item) > 0 for item in value["voxel_spacing_mm"])
        and value.get("coordinate_system") in {"left-posterior-superior", "right-anterior-superior"}
        and isinstance(value.get("space_directions"), list)
        and len(value["space_directions"]) == 3
        and all(finite_vector(item, positive_norm=True) for item in value["space_directions"])
        and finite_vector(value.get("space_origin"))
    )
    if not basic:
        return False
    directions = [
        [float(component) for component in direction]
        for direction in value["space_directions"]
    ]
    norms = [math.hypot(*direction) for direction in directions]
    spacing = [float(item) for item in value["voxel_spacing_mm"]]
    if any(
        not math.isclose(left, right, rel_tol=0, abs_tol=1e-9)
        for left, right in zip(spacing, norms)
    ):
        return False
    if any(
        abs(sum(directions[left][axis] * directions[right][axis] for axis in range(3)))
        > 1e-5 * norms[left] * norms[right]
        for left, right in ((0, 1), (0, 2), (1, 2))
    ):
        return False
    determinant = (
        directions[0][0]
        * (directions[1][1] * directions[2][2] - directions[1][2] * directions[2][1])
        - directions[0][1]
        * (directions[1][0] * directions[2][2] - directions[1][2] * directions[2][0])
        + directions[0][2]
        * (directions[1][0] * directions[2][1] - directions[1][1] * directions[2][0])
    )
    return abs(determinant) > 1e-8 * math.prod(norms)


def _valid_acquisition_date(value: Any) -> datetime | None:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{8}", value):
        return None
    try:
        return datetime.strptime(value, "%Y%m%d")
    except ValueError:
        return None


def _coverage_mask_shape_valid(value: Any, geometry: Any) -> bool:
    expected_keys = {
        "filename",
        "semantics",
        "source_volume",
        "reference_volume",
        "transform",
        "transform_direction",
        "source_basis",
        "resampler",
        "registered_volume_interpolation",
        "mask_interpolation",
        "scalar_type",
        "binary_values",
        "outside_value",
        "total_voxel_count",
        "foreground_voxel_count",
        "foreground_fraction",
    }
    if not isinstance(value, dict) or set(value) != expected_keys:
        return False
    total = value.get("total_voxel_count")
    foreground = value.get("foreground_voxel_count")
    fraction = value.get("foreground_fraction")
    if (
        value.get("filename") != COVERAGE_MASK_FILENAME
        or value.get("semantics") != COVERAGE_MASK_SEMANTICS
        or value.get("source_volume") != "moving.nrrd"
        or value.get("reference_volume") != "fixed.nrrd"
        or value.get("transform") != "moving-to-fixed.tfm"
        or value.get("transform_direction") != "moving_later_to_fixed_earlier"
        or value.get("source_basis") != "constant_one_moving_grid"
        or value.get("resampler") != "BRAINSResample"
        or value.get("registered_volume_interpolation") != "Linear"
        or value.get("mask_interpolation") != "NearestNeighbor"
        or value.get("scalar_type") != "uint8"
        or value.get("binary_values") != [0, 1]
        or value.get("outside_value") != 0
        or not isinstance(total, int)
        or isinstance(total, bool)
        or not isinstance(foreground, int)
        or isinstance(foreground, bool)
        or not isinstance(fraction, (int, float))
        or isinstance(fraction, bool)
        or not math.isfinite(float(fraction))
        or not _geometry_shape_valid(geometry)
    ):
        return False
    expected_total = math.prod(geometry["sizes"])
    return bool(
        total == expected_total
        and 0 < foreground <= total
        and 0 < float(fraction) <= 1
        and math.isclose(
            float(fraction),
            foreground / total,
            rel_tol=0,
            abs_tol=1e-12,
        )
    )


def _source_registration_shape_valid(value: Any) -> bool:
    if not isinstance(value, dict) or set(value) != {
        "job_id",
        "manifest_sha256",
        "transform_sha256",
        "fixed_volume_sha256",
        "moving_volume_sha256",
        "registered_moving_volume_sha256",
        "coverage_mask_sha256",
        "bundle_files",
        "bundle_sha256",
        "transform_direction",
        "modality",
        "fixed",
        "moving",
        "fixed_geometry",
        "registered_geometry",
        "coverage_mask_geometry",
        "coverage_mask",
    }:
        return False
    if (
        not isinstance(value.get("job_id"), str)
        or not JOB_ID.fullmatch(value["job_id"])
        or value.get("transform_direction") != "moving_later_to_fixed_earlier"
        or value.get("modality") not in {"MR", "CT"}
        or any(
            not isinstance(value.get(name), str) or not SHA256.fullmatch(value[name])
            for name in (
                "manifest_sha256",
                "transform_sha256",
                "fixed_volume_sha256",
                "moving_volume_sha256",
                "registered_moving_volume_sha256",
                "coverage_mask_sha256",
                "bundle_sha256",
            )
        )
        or not _geometry_shape_valid(value.get("fixed_geometry"))
        or not _geometry_shape_valid(value.get("registered_geometry"))
        or not _geometry_shape_valid(value.get("coverage_mask_geometry"))
        or not _coverage_mask_shape_valid(
            value.get("coverage_mask"), value.get("coverage_mask_geometry")
        )
    ):
        return False
    bundle_files = value.get("bundle_files")
    expected_names = sorted(
        [
            "engine-report.json",
            "fixed.nrrd",
            "moving-to-fixed.tfm",
            "moving.nrrd",
            COVERAGE_MASK_FILENAME,
            "registered-moving.nrrd",
            "registration.json",
        ]
    )
    if (
        not isinstance(bundle_files, list)
        or len(bundle_files) != 7
        or [item.get("name") for item in bundle_files if isinstance(item, dict)]
        != expected_names
        or any(
            not isinstance(item, dict)
            or set(item) != {"name", "bytes", "sha256"}
            or not isinstance(item.get("bytes"), int)
            or isinstance(item.get("bytes"), bool)
            or not 0 < item["bytes"] <= 2**63 - 1
            or not isinstance(item.get("sha256"), str)
            or not SHA256.fullmatch(item["sha256"])
            for item in bundle_files
        )
        or value.get("bundle_sha256") != _sha256(_canonical(bundle_files))
    ):
        return False
    file_entries = {item["name"]: item for item in bundle_files}
    if (
        value["manifest_sha256"] != file_entries["registration.json"]["sha256"]
        or value["transform_sha256"] != file_entries["moving-to-fixed.tfm"]["sha256"]
        or value["fixed_volume_sha256"] != file_entries["fixed.nrrd"]["sha256"]
        or value["moving_volume_sha256"] != file_entries["moving.nrrd"]["sha256"]
        or value["registered_moving_volume_sha256"]
        != file_entries["registered-moving.nrrd"]["sha256"]
        or value["coverage_mask_sha256"]
        != file_entries[COVERAGE_MASK_FILENAME]["sha256"]
        or value["fixed_geometry"] != value["registered_geometry"]
        or value["fixed_geometry"] != value["coverage_mask_geometry"]
    ):
        return False
    source_dates: dict[str, datetime] = {}
    for role in ("fixed", "moving"):
        source = value.get(role)
        if (
            not isinstance(source, dict)
            or set(source) != {"study_id", "series_id", "acquisition_date"}
            or not isinstance(source.get("study_id"), str)
            or not STUDY_ID.fullmatch(source["study_id"])
            or not isinstance(source.get("series_id"), str)
            or not SERIES_ID.fullmatch(source["series_id"])
            or _valid_acquisition_date(source.get("acquisition_date")) is None
        ):
            return False
        parsed_date = _valid_acquisition_date(source["acquisition_date"])
        assert parsed_date is not None
        source_dates[role] = parsed_date
    return bool(
        source_dates["fixed"] < source_dates["moving"]
        and value["fixed"]["study_id"] != value["moving"]["study_id"]
        and value["fixed"]["series_id"] != value["moving"]["series_id"]
    )


def registration_review_summary(
    source: Path | bytes,
    *,
    registration_directory: Path | None = None,
) -> dict[str, Any]:
    try:
        payload = source if isinstance(source, bytes) else source.read_bytes()
        if not 1 <= len(payload) <= MAX_RECORD_BYTES:
            raise ValueError("registration QA record is empty or too large")
        record = _strict_json_loads(payload)
    except (OSError, ValueError):
        return {
            "valid": False,
            "schema_version": None,
            "artifact_type": None,
            "review_status": "invalid",
            "display_unlocked": False,
            "quantitative_status": None,
            "landmark_pair_count": 0,
            "source_integrity": False,
            "external_api_required": False,
            "errors": ["registration QA record is invalid JSON"],
        }
    errors = registration_review_errors(record, registration_directory=registration_directory)
    quantitative = record.get("quantitative_assessment") if isinstance(record, dict) else None
    source_integrity = not errors if registration_directory is not None else False
    return {
        "valid": not errors,
        "schema_version": record.get("schema_version") if isinstance(record, dict) else None,
        "artifact_type": record.get("artifact_type") if isinstance(record, dict) else None,
        "review_status": record.get("review_status") if not errors else "invalid",
        "display_unlocked": bool(
            not errors
            and registration_directory is not None
            and source_integrity
            and isinstance(record.get("display_unlocks"), dict)
            and record["display_unlocks"].get("overlay") is True
            and record["display_unlocks"].get("swipe") is True
        ),
        "quantitative_status": (
            quantitative.get("status") if isinstance(quantitative, dict) else None
        ),
        "landmark_pair_count": (
            quantitative.get("pair_count", 0) if isinstance(quantitative, dict) else 0
        ),
        "source_integrity": source_integrity,
        "external_api_required": False,
        "errors": errors,
    }


def registration_review_bytes(
    registration_directory: Path,
    request_bytes: bytes,
    *,
    created_at: str | None = None,
    previous_review_sha256: str | None = None,
) -> bytes:
    if not 1 <= len(request_bytes) <= MAX_REQUEST_BYTES:
        raise ValueError("registration QA request is empty or too large")
    try:
        request = _strict_json_loads(request_bytes)
    except ValueError as error:
        raise ValueError("registration QA request is invalid JSON") from error
    record = build_registration_review(
        registration_directory,
        request,
        created_at=created_at,
        previous_review_sha256=previous_review_sha256,
    )
    return json.dumps(record, indent=2, allow_nan=False).encode() + b"\n"


def _write_new_owner_only(output: Path, payload: bytes) -> None:
    requested_output = output.expanduser()
    requested_output.parent.mkdir(parents=True, exist_ok=True)
    parent = requested_output.parent.resolve(strict=True)
    output = parent / requested_output.name
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.",
        suffix=".tmp",
        dir=parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, output, follow_symlinks=False)
        temporary.unlink()
        parent_descriptor = os.open(parent, os.O_RDONLY)
        try:
            os.fsync(parent_descriptor)
        finally:
            os.close(parent_descriptor)
    finally:
        temporary.unlink(missing_ok=True)


def _read_bounded_regular_file(path: Path, maximum_bytes: int) -> bytes:
    """Read one stable regular file without following a final-component symlink."""

    requested = Path(os.path.abspath(os.fspath(path.expanduser())))
    descriptor = -1
    try:
        descriptor = os.open(
            requested,
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or not 1 <= before.st_size <= maximum_bytes:
            raise ValueError("registration QA record is empty, too large, or not a regular file")
        payload = bytearray()
        while chunk := os.read(descriptor, min(1024 * 1024, maximum_bytes + 1)):
            payload.extend(chunk)
            if len(payload) > maximum_bytes:
                raise ValueError("registration QA record is too large")
        after = os.fstat(descriptor)
        before_identity = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        after_identity = (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        if before_identity != after_identity or len(payload) != before.st_size:
            raise ValueError("registration QA record changed while it was read")
        return bytes(payload)
    except OSError as error:
        raise ValueError("registration QA record cannot be read safely") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def import_registration_review(
    registration_directory: Path,
    downloaded_review: Path,
    output: Path,
) -> dict[str, Any]:
    """Validate and copy a browser-downloaded record into one owner-only archive."""

    payload = _read_bounded_regular_file(downloaded_review, MAX_RECORD_BYTES)
    summary = registration_review_summary(
        payload,
        registration_directory=registration_directory,
    )
    if not summary["valid"] or not summary["source_integrity"]:
        raise ValueError("registration QA record is invalid or for another live bundle")
    _write_new_owner_only(output, payload)
    return summary


def write_registration_review(
    registration_directory: Path,
    request_path: Path,
    output: Path,
    *,
    previous_review: Path | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    previous_hash = None
    if previous_review is not None:
        previous_summary = registration_review_summary(
            previous_review, registration_directory=registration_directory
        )
        if not previous_summary["valid"]:
            raise ValueError("previous registration QA record is invalid or for another bundle")
        previous_hash = hash_file(previous_review)
    payload = registration_review_bytes(
        registration_directory,
        request_path.read_bytes(),
        created_at=created_at,
        previous_review_sha256=previous_hash,
    )
    _write_new_owner_only(output, payload)
    record = _strict_json_loads(payload)
    assert isinstance(record, dict)
    return record
