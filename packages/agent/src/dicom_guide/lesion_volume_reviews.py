from __future__ import annotations

import hashlib
import html
import io
import json
import math
import re
import stat
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, BinaryIO

from .lesion_volumes import (
    _archive_members as evidence_archive_members,
    _strict_json,
    lesion_volume_archive_summary,
)


ArchiveSource = Path | BinaryIO
ARTIFACT_TYPE = "dicom-guide.lesion-volume-review"
EXPECTED_FILES = {"review.json", "evidence.zip", "review.html", "README.txt"}
MAX_ARCHIVE_BYTES = 160 * 1024 * 1024
MAX_EVIDENCE_BYTES = 128 * 1024 * 1024
MAX_TEXT_BYTES = 2 * 1024 * 1024
SHA256 = re.compile(r"^[0-9a-f]{64}$")
REVIEW_ID = re.compile(r"^review_[0-9a-f-]{36}$")
OPAQUE_ID = re.compile(
    r"^(?:[0-9a-f]{16}|(?:study|series|instance|frame|patient)_[0-9a-f]{20})$"
)
ROLES = {
    "radiologist",
    "neuro_oncologist",
    "neurosurgeon",
    "medical_physicist",
    "other_qualified_clinician",
}
DECISIONS = {"accepted_for_discussion", "revision_requested", "rejected"}
ACQUISITION_VALUES = {"suitable", "uncertain", "not_suitable"}
CHECKLIST_KEYS = {
    "original_images_reviewed",
    "full_boundary_reviewed",
    "all_three_planes_reviewed",
    "source_overlay_reviewed",
    "motion_considered",
    "partial_volume_considered",
    "treatment_effect_considered",
    "acquisition_protocol_considered",
}
ATTESTATION = (
    "I attest that I personally reviewed the complete manual boundary on the "
    "original local source images within the scope of my stated role. DICOM Guide "
    "has not verified my identity or credentials."
)
LIMITATIONS = [
    "Reviewer identity, role, and credentials are self-asserted and are not authenticated by DICOM Guide.",
    "Acceptance means suitable for discussion only; it is not clinical validation, medical-record sign-off, or regulatory clearance.",
    "The underlying source evidence remains a manually painted native-grid draft and its boundary uncertainty is not quantified.",
    "This review applies to one exact source series and does not establish that another scan contains the same lesion or tissue component.",
    "Differences in acquisition, motion, partial-volume effects, enhancement, edema, necrosis, and treatment effect can alter a boundary or volume.",
    "No longitudinal change, percentage change, treatment-response category, diagnosis, or clinical conclusion is authorized.",
    "Original DICOM images and the clinical medical record remain authoritative.",
]


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _finite(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _valid_datetime(value: Any) -> bool:
    if not isinstance(value, str) or "T" not in value:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _safe_text(
    value: Any,
    label: str,
    maximum: int,
    errors: list[str],
    *,
    optional: bool = False,
    multiline: bool = False,
) -> None:
    if not isinstance(value, str):
        errors.append(f"{label} must be text")
        return
    if not value.strip() and not optional:
        errors.append(f"{label} must not be empty")
    if len(value) > maximum:
        errors.append(f"{label} exceeds {maximum} characters")
    if any(
        ord(character) < 32
        and not (multiline and character in "\n\t")
        or ord(character) == 127
        for character in value
    ):
        errors.append(f"{label} contains unsupported control characters")
    if not multiline and any(character in "\n\t" for character in value):
        errors.append(f"{label} must be one line")


def _read_archive(source: ArchiveSource) -> tuple[dict[str, bytes], list[str]]:
    errors: list[str] = []
    members: dict[str, bytes] = {}
    if isinstance(source, Path):
        try:
            if not source.is_file() or source.is_symlink():
                return {}, ["review archive must be a regular non-symlink file"]
            if source.stat().st_size > MAX_ARCHIVE_BYTES:
                return {}, ["review archive exceeds the local safety limit"]
        except OSError:
            return {}, ["review archive is not readable"]
    else:
        source.seek(0, 2)
        size = source.tell()
        source.seek(0)
        if size > MAX_ARCHIVE_BYTES:
            return {}, ["review archive exceeds the local safety limit"]
    try:
        with zipfile.ZipFile(source) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(names) != len(EXPECTED_FILES) or set(names) != EXPECTED_FILES:
                return {}, [
                    "review archive must contain exactly review.json, evidence.zip, review.html, and README.txt"
                ]
            expanded = 0
            for info in infos:
                mode = info.external_attr >> 16
                if (
                    info.flag_bits & 0x1
                    or stat.S_ISLNK(mode)
                    or info.filename.startswith(("/", "\\"))
                    or ".." in Path(info.filename).parts
                ):
                    errors.append("review archive contains an encrypted or unsafe member")
                    continue
                maximum = (
                    MAX_EVIDENCE_BYTES
                    if info.filename == "evidence.zip"
                    else MAX_TEXT_BYTES
                )
                if info.file_size > maximum:
                    errors.append(f"{info.filename} exceeds its local safety limit")
                    continue
                expanded += info.file_size
                if expanded > MAX_ARCHIVE_BYTES:
                    errors.append("expanded review archive exceeds the local safety limit")
                    continue
                members[info.filename] = archive.read(info)
    except (OSError, RuntimeError, zipfile.BadZipFile):
        errors.append("review archive is not a readable ZIP file")
    return members, errors


def validate_lesion_volume_review(record: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(record, dict):
        return ["review.json must contain one JSON object"]
    expected = {
        "schema_version",
        "artifact_type",
        "review_id",
        "created_at",
        "review_status",
        "local_only",
        "sensitive",
        "deidentified",
        "source_snapshot",
        "reviewer",
        "review",
        "attestation",
        "permitted_uses",
        "files",
        "limitations",
    }
    if set(record) != expected:
        errors.append("review.json fields do not match the v1 contract")
    constants = {
        "schema_version": "1.0.0",
        "artifact_type": ARTIFACT_TYPE,
        "local_only": True,
        "sensitive": True,
        "deidentified": False,
    }
    for key, value in constants.items():
        if record.get(key) != value:
            errors.append(f"{key} must be {value!r}")
    if not isinstance(record.get("review_id"), str) or not REVIEW_ID.fullmatch(
        record["review_id"]
    ):
        errors.append("review_id is invalid")
    if not _valid_datetime(record.get("created_at")):
        errors.append("created_at must be an ISO 8601 date-time with a timezone")
    decision = record.get("review_status")
    if decision not in DECISIONS:
        errors.append("review_status is invalid")

    snapshot = record.get("source_snapshot")
    snapshot_keys = {
        "evidence_artifact_id",
        "patient_context_id",
        "study_id",
        "series_id",
        "frame_of_reference_id",
        "modality",
        "source_set_sha256",
        "mask_pixel_sha256",
        "foreground_voxel_count",
        "volume_mm3",
        "volume_ml",
        "boundary_uncertainty",
    }
    if not isinstance(snapshot, dict) or set(snapshot) != snapshot_keys:
        errors.append("source_snapshot is invalid")
    else:
        if not isinstance(snapshot.get("evidence_artifact_id"), str) or not re.fullmatch(
            r"seg_[0-9a-f-]{36}", snapshot["evidence_artifact_id"]
        ):
            errors.append("source_snapshot.evidence_artifact_id is invalid")
        patient_context = snapshot.get("patient_context_id")
        if patient_context is not None and (
            not isinstance(patient_context, str) or not OPAQUE_ID.fullmatch(patient_context)
        ):
            errors.append("source_snapshot.patient_context_id is invalid")
        for key in ("study_id", "series_id", "frame_of_reference_id"):
            if not isinstance(snapshot.get(key), str) or not OPAQUE_ID.fullmatch(snapshot[key]):
                errors.append(f"source_snapshot.{key} is invalid")
        if snapshot.get("modality") not in {"MR", "CT"}:
            errors.append("source_snapshot.modality is invalid")
        for key in ("source_set_sha256", "mask_pixel_sha256"):
            if not isinstance(snapshot.get(key), str) or not SHA256.fullmatch(snapshot[key]):
                errors.append(f"source_snapshot.{key} is invalid")
        if (
            not isinstance(snapshot.get("foreground_voxel_count"), int)
            or isinstance(snapshot.get("foreground_voxel_count"), bool)
            or snapshot["foreground_voxel_count"] < 1
        ):
            errors.append("source_snapshot.foreground_voxel_count is invalid")
        for key in ("volume_mm3", "volume_ml"):
            if not _finite(snapshot.get(key)) or snapshot[key] <= 0:
                errors.append(f"source_snapshot.{key} is invalid")
        if snapshot.get("boundary_uncertainty") != "not_quantified":
            errors.append("source_snapshot boundary uncertainty must remain not_quantified")

    reviewer = record.get("reviewer")
    reviewer_keys = {"name", "role", "organization", "identity_verification"}
    if not isinstance(reviewer, dict) or set(reviewer) != reviewer_keys:
        errors.append("reviewer is invalid")
    else:
        _safe_text(reviewer.get("name"), "reviewer.name", 120, errors)
        if reviewer.get("role") not in ROLES:
            errors.append("reviewer.role is invalid")
        organization = reviewer.get("organization")
        if organization is not None:
            _safe_text(organization, "reviewer.organization", 160, errors)
        if reviewer.get("identity_verification") != "self_asserted_unverified":
            errors.append("reviewer identity must remain self asserted and unverified")

    review = record.get("review")
    review_keys = {
        "decision",
        "acquisition_suitability",
        "planes_reviewed",
        "represented_tissue",
        "inclusion_criteria",
        "exclusion_criteria",
        "note",
        "checklist",
    }
    checklist: dict[str, Any] = {}
    if not isinstance(review, dict) or set(review) != review_keys:
        errors.append("review is invalid")
    else:
        if review.get("decision") != decision:
            errors.append("review.decision must equal review_status")
        if review.get("acquisition_suitability") not in ACQUISITION_VALUES:
            errors.append("review.acquisition_suitability is invalid")
        if review.get("planes_reviewed") != ["axial", "coronal", "sagittal"]:
            errors.append("review.planes_reviewed must contain all three canonical planes")
        _safe_text(
            review.get("represented_tissue"),
            "review.represented_tissue",
            500,
            errors,
            multiline=True,
        )
        _safe_text(
            review.get("inclusion_criteria"),
            "review.inclusion_criteria",
            1000,
            errors,
            multiline=True,
        )
        _safe_text(
            review.get("exclusion_criteria"),
            "review.exclusion_criteria",
            1000,
            errors,
            multiline=True,
        )
        _safe_text(
            review.get("note"),
            "review.note",
            2000,
            errors,
            optional=True,
            multiline=True,
        )
        candidate = review.get("checklist")
        if not isinstance(candidate, dict) or set(candidate) != CHECKLIST_KEYS:
            errors.append("review.checklist is invalid")
        else:
            checklist = candidate
            if any(not isinstance(value, bool) for value in checklist.values()):
                errors.append("review checklist values must be boolean")

    if record.get("attestation") != ATTESTATION:
        errors.append("review attestation is invalid")
    accepted = decision == "accepted_for_discussion"
    if accepted:
        if not isinstance(review, dict) or review.get("acquisition_suitability") != "suitable":
            errors.append("acceptance for discussion requires suitable acquisition")
        if not checklist or not all(value is True for value in checklist.values()):
            errors.append("acceptance for discussion requires every checklist item")
        if not isinstance(snapshot, dict) or snapshot.get("patient_context_id") is None:
            errors.append(
                "acceptance for future pairing review requires an opaque patient context"
            )

    expected_permissions = {
        "source_boundary_discussion": True,
        "reviewed_volume_for_discussion": accepted,
        "eligible_for_future_pairing_review": accepted,
        "longitudinal_link": False,
        "percent_change": False,
        "response_classification": False,
        "diagnosis": False,
        "clinical_conclusion": False,
    }
    if record.get("permitted_uses") != expected_permissions:
        errors.append("permitted_uses do not match the review decision or safety locks")
    if record.get("limitations") != LIMITATIONS:
        errors.append("limitations must match the fixed v1 safety statements")

    files = record.get("files")
    file_keys = {"evidence_archive", "review_page", "readme"}
    expected_names = {
        "evidence_archive": "evidence.zip",
        "review_page": "review.html",
        "readme": "README.txt",
    }
    if not isinstance(files, dict) or set(files) != file_keys:
        errors.append("files is invalid")
    else:
        for key, filename in expected_names.items():
            item = files.get(key)
            if (
                not isinstance(item, dict)
                or set(item) != {"filename", "bytes", "sha256"}
                or item.get("filename") != filename
                or not isinstance(item.get("bytes"), int)
                or isinstance(item.get("bytes"), bool)
                or item["bytes"] < 1
                or not isinstance(item.get("sha256"), str)
                or not SHA256.fullmatch(item["sha256"])
            ):
                errors.append(f"files.{key} is invalid")
    return list(dict.fromkeys(errors))


def _snapshot_matches_evidence(record: dict[str, Any], evidence: dict[str, Any]) -> bool:
    source = evidence["source"]
    measurement = evidence["measurement"]
    expected = {
        "evidence_artifact_id": evidence["artifact_id"],
        "patient_context_id": source.get("patient_context_id"),
        "study_id": source["study_id"],
        "series_id": source["series_id"],
        "frame_of_reference_id": source["frame_of_reference_id"],
        "modality": source["modality"],
        "source_set_sha256": source["source_set_sha256"],
        "mask_pixel_sha256": measurement["mask_pixel_sha256"],
        "foreground_voxel_count": measurement["foreground_voxel_count"],
        "volume_mm3": measurement["volume_mm3"],
        "volume_ml": measurement["volume_ml"],
        "boundary_uncertainty": measurement["boundary_uncertainty"],
    }
    return record.get("source_snapshot") == expected


def lesion_volume_review_summary(
    archive: ArchiveSource, source_root: Path
) -> dict[str, Any]:
    members, errors = _read_archive(archive)
    record: dict[str, Any] = {}
    if "review.json" in members:
        try:
            parsed = _strict_json(members["review.json"])
            if isinstance(parsed, dict):
                record = parsed
            else:
                errors.append("review.json must contain one JSON object")
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            errors.append("review.json is not strict valid UTF-8 JSON")
    if record:
        errors.extend(validate_lesion_volume_review(record))

    files = record.get("files") if isinstance(record, dict) else None
    file_map = {
        "evidence_archive": "evidence.zip",
        "review_page": "review.html",
        "readme": "README.txt",
    }
    if isinstance(files, dict):
        for key, filename in file_map.items():
            if filename not in members or not isinstance(files.get(key), dict):
                continue
            contract = files[key]
            payload = members[filename]
            if contract.get("bytes") != len(payload):
                errors.append(f"{filename} byte count does not match review.json")
            if contract.get("sha256") != _sha256(payload):
                errors.append(f"{filename} SHA-256 does not match review.json")

    page = members.get("review.html", b"")
    try:
        page_text = page.decode("utf-8")
    except UnicodeDecodeError:
        errors.append("review.html is not valid UTF-8")
        page_text = ""
    lowered_page = page_text.lower()
    unsafe_page_patterns = (
        "<script",
        "<iframe",
        "<object",
        "<embed",
        "<link",
        "<form",
        "<input",
        "<button",
        "<svg",
        "<math",
        "http://",
        "https://",
        "javascript:",
        "data:",
        "src=",
        "href=",
        "url(",
        "@import",
        "http-equiv",
    )
    unsafe_event_attribute = re.search(r"\son[a-z0-9_-]+\s*=", lowered_page)
    required_page_copy = (
        "SELF-ATTESTED REVIEW FOR DISCUSSION ONLY",
        "IDENTITY NOT VERIFIED",
        "NOT A DIAGNOSIS",
        "NO LONGITUDINAL OR RESPONSE CONCLUSION",
    )
    if page_text and (
        not lowered_page.startswith("<!doctype html>")
        or any(pattern in lowered_page for pattern in unsafe_page_patterns)
        or unsafe_event_attribute is not None
        or any(item not in page_text for item in required_page_copy)
    ):
        errors.append("review.html must be a script-free self-contained local page")
    if page_text and record and isinstance(record.get("review"), dict):
        reviewer = record.get("reviewer")
        safe_reviewer = reviewer if isinstance(reviewer, dict) else {}
        review_status = record.get("review_status")
        reviewer_role = safe_reviewer.get("role")
        visible_record_values = [
            review_status.replace("_", " ") if isinstance(review_status, str) else None,
            safe_reviewer.get("name"),
            reviewer_role.replace("_", " ") if isinstance(reviewer_role, str) else None,
            record["review"].get("represented_tissue", ""),
            record["review"].get("inclusion_criteria", ""),
            record["review"].get("exclusion_criteria", ""),
        ]
        if any(
            not isinstance(value, str)
            or html.escape(value, quote=True).replace("&#x27;", "&#39;") not in page_text
            for value in visible_record_values
        ):
            errors.append("review.html does not present the exact review record")

    evidence_summary: dict[str, Any] = {}
    evidence: dict[str, Any] = {}
    if "evidence.zip" in members:
        evidence_bytes = members["evidence.zip"]
        evidence_summary = lesion_volume_archive_summary(
            io.BytesIO(evidence_bytes), source_root
        )
        if not evidence_summary["valid"]:
            errors.append("nested lesion-volume evidence is invalid against the exact source")
        nested_members, nested_errors = evidence_archive_members(io.BytesIO(evidence_bytes))
        if nested_errors:
            errors.append("nested lesion-volume evidence cannot be read")
        elif "evidence.json" in nested_members:
            try:
                parsed = _strict_json(nested_members["evidence.json"])
                if isinstance(parsed, dict):
                    evidence = parsed
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
                errors.append("nested evidence.json is not strict valid JSON")
    if (
        record
        and evidence
        and evidence_summary.get("valid") is True
        and not _snapshot_matches_evidence(record, evidence)
    ):
        errors.append("source_snapshot does not match the exact nested evidence")

    errors = list(dict.fromkeys(errors))
    valid = not errors and bool(record) and evidence_summary.get("valid") is True
    accepted = valid and record.get("review_status") == "accepted_for_discussion"
    return {
        "valid": valid,
        "errors": errors,
        "schema_version": record.get("schema_version") if record else None,
        "artifact_type": record.get("artifact_type") if record else None,
        "review_status": record.get("review_status") if valid else None,
        "identity_verification": (
            record.get("reviewer", {}).get("identity_verification") if valid else None
        ),
        "source_validated": bool(valid and evidence_summary.get("source_validated")),
        "boundary_review_self_attested": valid,
        "reviewed_volume_for_discussion": accepted,
        "eligible_for_future_pairing_review": accepted,
        "computed_unreviewed_volume_ml": (
            evidence_summary.get("computed_unreviewed_volume_ml") if valid else None
        ),
        "longitudinal_link": False,
        "percent_change": False,
        "response_classification": False,
        "diagnosis": False,
        "clinical_conclusion": False,
        "evidence_use": (
            "single_timepoint_reviewed_for_discussion_only"
            if accepted
            else "single_timepoint_revision_or_rejection_only"
            if valid
            else "none"
        ),
    }
