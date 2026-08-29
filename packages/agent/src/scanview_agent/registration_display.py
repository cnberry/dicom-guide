from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path
from typing import Any

from .registration import registration_bundle_summary
from .registration_reviews import (
    ACCEPTED_DECISION,
    ACCEPTED_SCOPE,
    COVERAGE_MASK_FILENAME,
    COVERAGE_MASK_ROLE,
    INTENDED_USE,
    MAX_RECORD_BYTES,
    _strict_json_loads,
    registration_review_summary,
)


SCHEMA_VERSION = "2.0.0"
ARTIFACT_TYPE = "reviewed_registration_display_context"
SUMMARY_ARTIFACT_TYPE = "reviewed_registration_display_summary"
AUTHORIZED_STATUS = "authorized"
ALLOWED_DISPLAY_MODES = ["opacity", "swipe"]
ALWAYS_LOCKED = [
    "subtraction",
    "mask_propagation",
    "segmentation",
    "resampled_image_measurements",
    "response_conclusions",
]
SAMPLING_SUPPORT_ENFORCEMENT = "required_pixel_mask"
SHARED_ANATOMY_SCOPE = "reviewer_attested_visual_only"
MASK_FAILURE_BEHAVIOR = "lock_display"
MASK_SAMPLING = "nearest_neighbor"
MAX_REVIEWED_ENCODED_VOLUME_BYTES = 256 * 1024 * 1024
MAX_REVIEWED_ENCODED_MASK_BYTES = 256 * 1024 * 1024
MAX_REVIEWED_ENCODED_TOTAL_BYTES = 384 * 1024 * 1024
LIMITATIONS = [
    "Registered-moving display is authorized only where the required sampling-support mask is one and shared anatomy was visually reviewed.",
    "The coverage mask identifies transformed moving-image sampling support only; it is not anatomy, tumor, segmentation, registration quality, or clinical comparability.",
    "The sampling-support mask excludes default-filled registered-moving pixels but does not establish shared anatomy.",
    "Reviewer identity, role, training, and organization are self asserted and unauthenticated.",
    "The fixed volume is a derived local scalar-volume representation that preserves fixed geometry; it is not native DICOM.",
    "The registered-moving volume is derived and interpolated into fixed geometry; it is not native DICOM.",
    "Subtraction, mask propagation, segmentation, resampled-image measurements, and response conclusions remain prohibited.",
    "This authorization is bound to the exact saved review and live seven-file registration bundle hashes, geometry, and coverage-mask semantics and counts.",
    "This exploratory display is not a diagnosis, treatment-response conclusion, or authorization for treatment planning.",
    "The review event SHA-256 and saved-review SHA-256 provide tamper evidence, not a digital signature or reviewer authentication.",
]


def _summary(
    *,
    available: bool,
    display_status: str,
    review_status: str,
    errors: list[str],
) -> dict[str, Any]:
    authorized = display_status == AUTHORIZED_STATUS
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": SUMMARY_ARTIFACT_TYPE,
        "available": available,
        "display_status": display_status,
        "display_authorized": authorized,
        "review_status": review_status,
        "intended_use": INTENDED_USE,
        "scope": ACCEPTED_SCOPE if authorized else "none",
        "allowed_display_modes": list(ALLOWED_DISPLAY_MODES) if authorized else [],
        "external_api_required": False,
        "errors": errors,
    }


def _read_owner_only_review(path: Path) -> bytes:
    def identity(metadata: os.stat_result) -> tuple[int, ...]:
        return (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_mode,
            metadata.st_uid,
            metadata.st_nlink,
            metadata.st_size,
            metadata.st_mtime_ns,
            metadata.st_ctime_ns,
        )

    expanded = path.expanduser()
    try:
        path_stat = expanded.lstat()
    except OSError as error:
        raise FileNotFoundError("registration review is unavailable") from error
    if (
        not stat.S_ISREG(path_stat.st_mode)
        or stat.S_IMODE(path_stat.st_mode) != 0o600
        or path_stat.st_uid != os.getuid()
        or path_stat.st_nlink != 1
    ):
        raise ValueError("registration review must be one owner-only unlinked regular file")
    flags = os.O_RDONLY
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(expanded, flags)
    try:
        opened_stat = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened_stat.st_mode)
            or stat.S_IMODE(opened_stat.st_mode) != 0o600
            or opened_stat.st_uid != os.getuid()
            or opened_stat.st_nlink != 1
            or identity(opened_stat) != identity(path_stat)
            or not 1 <= opened_stat.st_size <= MAX_RECORD_BYTES
        ):
            raise ValueError("registration review file metadata is invalid")
        payload = b""
        while len(payload) <= MAX_RECORD_BYTES:
            chunk = os.read(descriptor, min(64 * 1024, MAX_RECORD_BYTES + 1 - len(payload)))
            if not chunk:
                break
            payload += chunk
        if not 1 <= len(payload) <= MAX_RECORD_BYTES or len(payload) != opened_stat.st_size:
            raise ValueError("registration review file size changed or is unsupported")
        completed_stat = os.fstat(descriptor)
        if identity(completed_stat) != identity(opened_stat):
            raise ValueError("registration review file changed while it was read")
    finally:
        os.close(descriptor)
    final_stat = expanded.lstat()
    if identity(final_stat) != identity(opened_stat):
        raise ValueError("registration review file changed while it was read")
    return payload


def _assessment(
    registration_directory: Path | None,
    review_source: Path | bytes | None,
) -> tuple[dict[str, Any], dict[str, Any] | None, bytes | None]:
    if registration_directory is None or review_source is None:
        return (
            _summary(
                available=False,
                display_status="unavailable",
                review_status="unavailable",
                errors=["reviewed registration display inputs are unavailable"],
            ),
            None,
            None,
        )
    if not isinstance(registration_directory, Path):
        return (
            _summary(
                available=False,
                display_status="invalid",
                review_status="invalid",
                errors=["registration bundle input is invalid"],
            ),
            None,
            None,
        )
    try:
        if not registration_directory.exists():
            return (
                _summary(
                    available=False,
                    display_status="unavailable",
                    review_status="unavailable",
                    errors=["registration bundle is unavailable"],
                ),
                None,
                None,
            )
        bundle = registration_bundle_summary(registration_directory)
    except (OSError, ValueError, TypeError):
        bundle = {"valid": False}
    if not bundle.get("valid"):
        return (
            _summary(
                available=False,
                display_status="invalid",
                review_status="invalid",
                errors=["live registration bundle is invalid or unsafe"],
            ),
            None,
            None,
        )
    if isinstance(review_source, bytes):
        return (
            _summary(
                available=False,
                display_status="invalid",
                review_status="invalid",
                errors=["standalone registration review cannot authorize display"],
            ),
            None,
            None,
        )
    if not isinstance(review_source, Path):
        return (
            _summary(
                available=False,
                display_status="invalid",
                review_status="invalid",
                errors=["registration review input is invalid"],
            ),
            None,
            None,
        )
    if not review_source.exists() and not review_source.is_symlink():
        return (
            _summary(
                available=False,
                display_status="unavailable",
                review_status="unavailable",
                errors=["saved registration review is unavailable"],
            ),
            None,
            None,
        )
    try:
        payload = _read_owner_only_review(review_source)
        review = registration_review_summary(
            payload,
            registration_directory=registration_directory,
        )
        record = _strict_json_loads(payload)
    except (OSError, ValueError, TypeError):
        return (
            _summary(
                available=False,
                display_status="invalid",
                review_status="invalid",
                errors=["saved registration review is invalid or unsafe"],
            ),
            None,
            None,
        )
    if not review.get("valid") or not isinstance(record, dict):
        return (
            _summary(
                available=False,
                display_status="invalid",
                review_status="invalid",
                errors=["registration review is malformed, tampered, or for another bundle"],
            ),
            None,
            None,
        )
    if record.get("review_status") != ACCEPTED_DECISION:
        return (
            _summary(
                available=True,
                display_status="locked",
                review_status="rejected",
                errors=["registration review did not authorize display"],
            ),
            record,
            payload,
        )
    if not review.get("display_unlocked") or not review.get("source_integrity"):
        return (
            _summary(
                available=False,
                display_status="invalid",
                review_status="invalid",
                errors=["registration review display authorization is invalid"],
            ),
            None,
            None,
        )
    try:
        file_entries = {
            item["name"]: item for item in record["source_registration"]["bundle_files"]
        }
        fixed_bytes = file_entries["fixed.nrrd"]["bytes"]
        registered_bytes = file_entries["registered-moving.nrrd"]["bytes"]
        coverage_bytes = file_entries[COVERAGE_MASK_FILENAME]["bytes"]
    except (KeyError, TypeError):
        fixed_bytes = registered_bytes = coverage_bytes = 0
    if (
        not isinstance(fixed_bytes, int)
        or isinstance(fixed_bytes, bool)
        or not isinstance(registered_bytes, int)
        or isinstance(registered_bytes, bool)
        or not isinstance(coverage_bytes, int)
        or isinstance(coverage_bytes, bool)
        or fixed_bytes <= 0
        or registered_bytes <= 0
        or coverage_bytes <= 0
        or fixed_bytes > MAX_REVIEWED_ENCODED_VOLUME_BYTES
        or registered_bytes > MAX_REVIEWED_ENCODED_VOLUME_BYTES
        or coverage_bytes > MAX_REVIEWED_ENCODED_MASK_BYTES
        or fixed_bytes + registered_bytes + coverage_bytes
        > MAX_REVIEWED_ENCODED_TOTAL_BYTES
    ):
        return (
            _summary(
                available=False,
                display_status="invalid",
                review_status="invalid",
                errors=["reviewed registration artifacts exceed the display safety limit"],
            ),
            None,
            None,
        )
    return (
        _summary(
            available=True,
            display_status=AUTHORIZED_STATUS,
            review_status=ACCEPTED_DECISION,
            errors=[],
        ),
        record,
        payload,
    )


def reviewed_registration_display_context(
    registration_directory: Path,
    review_source: Path | bytes,
) -> dict[str, Any]:
    """Return a hash-bound display context only for a valid saved accepted review."""

    summary, record, payload = _assessment(registration_directory, review_source)
    if not summary["display_authorized"] or record is None or payload is None:
        raise ValueError("reviewed registration display is not authorized")
    source = record["source_registration"]
    file_entries = {item["name"]: item for item in source["bundle_files"]}

    def volume(
        *,
        role: str,
        filename: str,
        derived: bool,
        resampled: bool,
        geometry: dict[str, Any],
    ) -> dict[str, Any]:
        entry = file_entries[filename]
        return {
            "role": role,
            "filename": filename,
            "url": f"/v1/reviewed-registration/files/{filename}",
            "bytes": entry["bytes"],
            "sha256": entry["sha256"],
            "derived": derived,
            "resampled": resampled,
            "geometry": geometry,
        }

    coverage_entry = file_entries[COVERAGE_MASK_FILENAME]
    coverage = source["coverage_mask"]
    coverage_mask = {
        "role": COVERAGE_MASK_ROLE,
        "filename": COVERAGE_MASK_FILENAME,
        "url": f"/v1/reviewed-registration/files/{COVERAGE_MASK_FILENAME}",
        "bytes": coverage_entry["bytes"],
        "sha256": coverage_entry["sha256"],
        "derived": True,
        "scalar_type": coverage["scalar_type"],
        "binary_values": coverage["binary_values"],
        "semantics": coverage["semantics"],
        "geometry": source["coverage_mask_geometry"],
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "sensitive": True,
        "deidentified": False,
        "display_status": "authorized_for_exploratory_shared_coverage_overlay_swipe",
        "intended_use": INTENDED_USE,
        "scope": ACCEPTED_SCOPE,
        "review": {
            "review_id": record["review_id"],
            "job_id": source["job_id"],
            "decision": record["review_status"],
            "review_sha256": hashlib.sha256(payload).hexdigest(),
            "event_sha256": record["integrity"]["event_sha256"],
            "self_attested": True,
        },
        "source": {
            "manifest_sha256": source["manifest_sha256"],
            "bundle_sha256": source["bundle_sha256"],
            "transform_sha256": source["transform_sha256"],
            "bundle_files": source["bundle_files"],
            "transform_direction": source["transform_direction"],
            "modality": source["modality"],
            "fixed": source["fixed"],
            "moving": source["moving"],
        },
        "reviewer": {
            "role": record["reviewer"]["role"],
            "training_status": record["reviewer"]["training_status"],
            "identity_status": record["reviewer"]["identity_status"],
        },
        "volumes": {
            "fixed": volume(
                role="fixed_earlier_reference",
                filename="fixed.nrrd",
                derived=True,
                resampled=False,
                geometry=source["fixed_geometry"],
            ),
            "registered_moving": volume(
                role="moving_later_registered_to_fixed",
                filename="registered-moving.nrrd",
                derived=True,
                resampled=True,
                geometry=source["registered_geometry"],
            ),
        },
        "coverage_mask": coverage_mask,
        "display_policy": {
            "allowed_modes": list(ALLOWED_DISPLAY_MODES),
            "always_locked": list(ALWAYS_LOCKED),
            "native_moving_available": False,
            "native_moving_withheld": True,
            "sampling_support_enforcement": SAMPLING_SUPPORT_ENFORCEMENT,
            "shared_anatomy_scope": SHARED_ANATOMY_SCOPE,
            "mask_failure_behavior": MASK_FAILURE_BEHAVIOR,
            "mask_sampling": MASK_SAMPLING,
        },
        "display_label": record["display_label"],
        "limitations": list(LIMITATIONS),
    }


def reviewed_registration_display_summary(
    registration_directory: Path | None,
    review_source: Path | bytes | None,
) -> dict[str, Any]:
    """Return a privacy-safe, non-raising display authorization summary."""

    try:
        summary, _, _ = _assessment(registration_directory, review_source)
        return summary
    except Exception:
        return _summary(
            available=False,
            display_status="invalid",
            review_status="invalid",
            errors=["reviewed registration display inputs are invalid"],
        )


def reviewed_registration_display_errors(
    registration_directory: Path | None,
    review_source: Path | bytes | None,
) -> list[str]:
    """Return privacy-safe reasons that the reviewed display remains locked."""

    return reviewed_registration_display_summary(
        registration_directory,
        review_source,
    )["errors"]
