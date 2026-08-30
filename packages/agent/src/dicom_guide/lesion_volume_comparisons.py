from __future__ import annotations

import hashlib
import html
import io
import json
import math
import os
import re
import stat
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO

from .catalog import build_catalog
from .lesion_volume_reviews import lesion_volume_review_summary
from .lesion_volumes import _strict_json


ArchiveSource = Path | BinaryIO
ARTIFACT_TYPE = "dicom-guide.lesion-volume-comparison-review"
REQUEST_ARTIFACT_TYPE = "dicom-guide.lesion-volume-comparison-request"
EXPECTED_FILES = {
    "comparison.json",
    "baseline-review.zip",
    "followup-review.zip",
    "review.html",
    "README.txt",
}
TRANSPORT_FILES = {
    "baseline-review.zip",
    "followup-review.zip",
    "pairing-request.json",
}
MAX_ARCHIVE_BYTES = 340 * 1024 * 1024
MAX_REVIEW_BYTES = 160 * 1024 * 1024
MAX_TEXT_BYTES = 2 * 1024 * 1024
MAX_TRANSPORT_BYTES = 322 * 1024 * 1024
SHA256 = re.compile(r"^[0-9a-f]{64}$")
COMPARISON_ID = re.compile(r"^volume_pair_[0-9a-f-]{36}$")
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
DECISIONS = {
    "accepted_for_volume_change_discussion",
    "revision_requested",
    "rejected",
}
IDENTITY_VALUES = {"confirmed", "uncertain", "not_confirmed"}
COMPARABILITY_VALUES = {
    "suitable",
    "suitable_with_limitations",
    "not_suitable",
}
REGISTRATION_VALUES = {"required", "not_required", "uncertain"}
CHECKLIST_KEYS = {
    "both_original_sources_reviewed",
    "both_complete_boundaries_reviewed",
    "boundary_definitions_compared",
    "same_lesion_identity_reviewed",
    "same_represented_tissue_reviewed",
    "acquisition_differences_reviewed",
    "chronology_confirmed",
    "registration_need_reviewed",
}
ATTESTATION = (
    "I attest that I personally reviewed both accepted boundary records and their "
    "original local source images, and recorded my judgments about chronology, same-"
    "lesion identity, represented tissue, acquisition comparability, boundary "
    "comparability, and registration need. DICOM Guide has not verified my identity or "
    "credentials."
)
LIMITATIONS = [
    "Reviewer identity, role, and credentials are self-asserted and are not authenticated by DICOM Guide.",
    "Both inputs are separately reviewed manual native-grid boundaries; their boundary uncertainty remains unquantified.",
    "Same-lesion and same-represented-tissue judgments are person-attested and are not established by software.",
    "Absolute and percentage volume change are geometry arithmetic for discussion, not biological tumor burden or a response category.",
    "Acquisition, motion, partial-volume effects, enhancement, edema, necrosis, treatment effect, and boundary choices can change the values.",
    "A treatment-context note does not establish that treatment caused any observed numeric difference.",
    "This artifact does not perform or authorize spatial registration, overlay, subtraction, or voxelwise change localization.",
    "Original DICOM images and the clinical medical record remain authoritative.",
]


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode()


def _valid_datetime(value: Any) -> bool:
    if not isinstance(value, str) or "T" not in value:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _created_at(value: str | None) -> str:
    result = value or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    if not _valid_datetime(result):
        raise ValueError("created_at must be an ISO 8601 date-time with a timezone")
    return result


def _read_source(source: ArchiveSource, maximum: int, label: str) -> bytes:
    if isinstance(source, Path):
        try:
            if source.is_symlink() or not source.is_file():
                raise ValueError(f"{label} must be a regular non-symlink file")
            if source.stat().st_size > maximum:
                raise ValueError(f"{label} exceeds the local safety limit")
            return source.read_bytes()
        except OSError as error:
            raise ValueError(f"{label} is not readable") from error
    source.seek(0, 2)
    size = source.tell()
    source.seek(0)
    if size > maximum:
        raise ValueError(f"{label} exceeds the local safety limit")
    content = source.read(maximum + 1)
    source.seek(0)
    if len(content) > maximum:
        raise ValueError(f"{label} exceeds the local safety limit")
    return content


def _strict_object(content: bytes, label: str) -> dict[str, Any]:
    try:
        parsed = _strict_json(content)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"{label} is not strict valid UTF-8 JSON") from error
    if not isinstance(parsed, dict):
        raise ValueError(f"{label} must contain one JSON object")
    return parsed


def _safe_text(
    value: Any,
    label: str,
    maximum: int,
    *,
    optional: bool = False,
    multiline: bool = False,
) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text")
    normalized = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized and not optional:
        raise ValueError(f"{label} must not be empty")
    if len(normalized) > maximum:
        raise ValueError(f"{label} exceeds {maximum} characters")
    if any(
        (ord(character) < 32 and not (multiline and character in "\n\t"))
        or ord(character) == 127
        for character in normalized
    ):
        raise ValueError(f"{label} contains unsupported control characters")
    if not multiline and any(character in "\n\t" for character in normalized):
        raise ValueError(f"{label} must be one line")
    return normalized


def _validate_request(value: Any) -> dict[str, Any]:
    expected = {
        "schema_version",
        "artifact_type",
        "reviewer",
        "decision",
        "pairing",
        "checklist",
        "attestation",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError("pairing request fields do not match the v1 contract")
    if value.get("schema_version") != "1.0.0" or value.get("artifact_type") != REQUEST_ARTIFACT_TYPE:
        raise ValueError("pairing request type or version is invalid")
    decision = value.get("decision")
    if decision not in DECISIONS:
        raise ValueError("pairing decision is invalid")
    reviewer = value.get("reviewer")
    if not isinstance(reviewer, dict) or set(reviewer) != {
        "name",
        "role",
        "organization",
        "identity_verification",
    }:
        raise ValueError("pairing reviewer is invalid")
    reviewer_name = _safe_text(reviewer.get("name"), "reviewer.name", 120)
    if reviewer.get("role") not in ROLES:
        raise ValueError("reviewer.role is invalid")
    organization = reviewer.get("organization")
    if organization is not None:
        organization = _safe_text(organization, "reviewer.organization", 160)
    if reviewer.get("identity_verification") != "self_asserted_unverified":
        raise ValueError("reviewer identity must remain self asserted and unverified")

    pairing = value.get("pairing")
    pairing_keys = {
        "same_lesion_identity",
        "same_represented_tissue",
        "chronology",
        "acquisition_comparability",
        "boundary_comparability",
        "registration_consideration",
        "limitation_note",
        "treatment_context_note",
    }
    if not isinstance(pairing, dict) or set(pairing) != pairing_keys:
        raise ValueError("pairing judgments are invalid")
    if pairing.get("same_lesion_identity") not in IDENTITY_VALUES:
        raise ValueError("same-lesion judgment is invalid")
    if pairing.get("same_represented_tissue") not in IDENTITY_VALUES:
        raise ValueError("same-tissue judgment is invalid")
    if pairing.get("chronology") not in {"confirmed", "not_confirmed"}:
        raise ValueError("chronology judgment is invalid")
    for key in ("acquisition_comparability", "boundary_comparability"):
        if pairing.get(key) not in COMPARABILITY_VALUES:
            raise ValueError(f"{key} judgment is invalid")
    if pairing.get("registration_consideration") not in REGISTRATION_VALUES:
        raise ValueError("registration consideration is invalid")
    limitation_note = _safe_text(
        pairing.get("limitation_note"),
        "pairing.limitation_note",
        2000,
        optional=True,
        multiline=True,
    )
    treatment_note = _safe_text(
        pairing.get("treatment_context_note"),
        "pairing.treatment_context_note",
        2000,
        optional=True,
        multiline=True,
    )
    needs_limit = (
        pairing.get("acquisition_comparability") == "suitable_with_limitations"
        or pairing.get("boundary_comparability") == "suitable_with_limitations"
        or pairing.get("registration_consideration") != "not_required"
    )
    if needs_limit and not limitation_note:
        raise ValueError("documented comparability or registration limitations require a note")

    checklist = value.get("checklist")
    if not isinstance(checklist, dict) or set(checklist) != CHECKLIST_KEYS:
        raise ValueError("pairing checklist is invalid")
    if any(not isinstance(item, bool) for item in checklist.values()):
        raise ValueError("pairing checklist values must be boolean")
    if value.get("attestation") != ATTESTATION:
        raise ValueError("pairing attestation is invalid")
    if decision == "accepted_for_volume_change_discussion":
        if pairing.get("same_lesion_identity") != "confirmed":
            raise ValueError("acceptance requires confirmed same-lesion identity")
        if pairing.get("same_represented_tissue") != "confirmed":
            raise ValueError("acceptance requires confirmed represented-tissue match")
        if pairing.get("chronology") != "confirmed":
            raise ValueError("acceptance requires confirmed chronology")
        if pairing.get("acquisition_comparability") not in {
            "suitable",
            "suitable_with_limitations",
        }:
            raise ValueError("acceptance requires suitable acquisition comparability")
        if pairing.get("boundary_comparability") not in {
            "suitable",
            "suitable_with_limitations",
        }:
            raise ValueError("acceptance requires suitable boundary comparability")
        if not all(item is True for item in checklist.values()):
            raise ValueError("acceptance requires every pairing checklist item")
    return {
        **value,
        "reviewer": {
            **reviewer,
            "name": reviewer_name,
            "organization": organization,
        },
        "pairing": {
            **pairing,
            "limitation_note": limitation_note,
            "treatment_context_note": treatment_note,
        },
    }


def _review_components(
    source: ArchiveSource, source_root: Path, label: str
) -> tuple[bytes, dict[str, Any]]:
    content = _read_source(source, MAX_REVIEW_BYTES, f"{label} review")
    summary = lesion_volume_review_summary(io.BytesIO(content), source_root)
    if not summary["valid"]:
        raise ValueError(f"{label} boundary review is invalid against the exact local source")
    if (
        summary.get("review_status") != "accepted_for_discussion"
        or summary.get("eligible_for_future_pairing_review") is not True
    ):
        raise ValueError(f"{label} boundary review is not accepted for future pairing review")
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            record = _strict_object(archive.read("review.json"), f"{label} review.json")
    except (KeyError, zipfile.BadZipFile) as error:
        raise ValueError(f"{label} boundary review cannot be read") from error
    return content, record


def _catalog_series(
    catalog: dict[str, Any], record: dict[str, Any], label: str
) -> dict[str, Any]:
    snapshot = record["source_snapshot"]
    matches: list[dict[str, Any]] = []
    for study in catalog.get("studies", []):
        if not isinstance(study, dict) or study.get("id") != snapshot["study_id"]:
            continue
        for series in study.get("series", []):
            if isinstance(series, dict) and series.get("id") == snapshot["series_id"]:
                matches.append(series)
    if len(matches) != 1:
        raise ValueError(f"{label} reviewed series is not an exact member of the live local catalog")
    series = matches[0]
    if (
        series.get("patient_context_id") != snapshot["patient_context_id"]
        or series.get("modality") != snapshot["modality"]
        or series.get("frame_of_reference_id") != snapshot["frame_of_reference_id"]
    ):
        raise ValueError(f"{label} review disagrees with the live local catalog")
    acquisition_date = series.get("acquisition_date")
    if not isinstance(acquisition_date, str) or not re.fullmatch(r"[0-9]{8}", acquisition_date):
        raise ValueError(f"{label} series requires one exact DICOM acquisition date")
    try:
        date.fromisoformat(
            f"{acquisition_date[:4]}-{acquisition_date[4:6]}-{acquisition_date[6:8]}"
        )
    except ValueError as error:
        raise ValueError(f"{label} DICOM acquisition date is invalid") from error
    instance_dates = {
        item.get("acquisition_date")
        for item in series.get("instances", [])
        if isinstance(item, dict)
    }
    if instance_dates != {acquisition_date}:
        raise ValueError(
            f"{label} reviewed source instances do not share one exact DICOM acquisition date"
        )
    return series


def _timepoint(record: dict[str, Any], series: dict[str, Any]) -> dict[str, Any]:
    source = record["source_snapshot"]
    review = record["review"]
    return {
        "review_id": record["review_id"],
        "evidence_artifact_id": source["evidence_artifact_id"],
        "patient_context_id": source["patient_context_id"],
        "study_id": source["study_id"],
        "series_id": source["series_id"],
        "frame_of_reference_id": source["frame_of_reference_id"],
        "modality": source["modality"],
        "acquisition_date": series["acquisition_date"],
        "series_description": str(series.get("series_description") or "Unnamed series")[:300],
        "protocol_name": (
            str(series["protocol_name"])[:300]
            if series.get("protocol_name") is not None
            else None
        ),
        "source_set_sha256": source["source_set_sha256"],
        "mask_pixel_sha256": source["mask_pixel_sha256"],
        "foreground_voxel_count": source["foreground_voxel_count"],
        "reviewed_volume_ml": source["volume_ml"],
        "boundary_uncertainty": "not_quantified",
        "represented_tissue": review["represented_tissue"],
        "inclusion_criteria": review["inclusion_criteria"],
        "exclusion_criteria": review["exclusion_criteria"],
    }


def _elapsed_days(baseline: str, followup: str) -> int:
    earlier = date.fromisoformat(f"{baseline[:4]}-{baseline[4:6]}-{baseline[6:8]}")
    later = date.fromisoformat(f"{followup[:4]}-{followup[4:6]}-{followup[6:8]}")
    return (later - earlier).days


def _comparison(
    baseline: dict[str, Any], followup: dict[str, Any], accepted: bool
) -> dict[str, Any] | None:
    if not accepted:
        return None
    baseline_volume = float(baseline["reviewed_volume_ml"])
    followup_volume = float(followup["reviewed_volume_ml"])
    absolute_change = followup_volume - baseline_volume
    if absolute_change > 0:
        direction = "increased"
    elif absolute_change < 0:
        direction = "decreased"
    else:
        direction = "unchanged"
    return {
        "status": "qualified_pairing_review_for_discussion_only",
        "method": "followup_reviewed_volume_minus_baseline_reviewed_volume",
        "baseline_volume_ml": baseline_volume,
        "followup_volume_ml": followup_volume,
        "absolute_change_ml": absolute_change,
        "percent_change": absolute_change / baseline_volume * 100.0,
        "numeric_direction": direction,
        "elapsed_days": _elapsed_days(
            baseline["acquisition_date"], followup["acquisition_date"]
        ),
        "boundary_uncertainty": "not_quantified",
        "response_assessment": "not_performed",
        "causal_treatment_attribution": False,
        "interpretations": [],
    }


def _permissions(accepted: bool) -> dict[str, Any]:
    return {
        "reviewed_single_timepoint_volumes_for_discussion": True,
        "same_lesion_pair_for_discussion": accepted,
        "absolute_volume_change_for_discussion": accepted,
        "percent_volume_change_for_discussion": accepted,
        "spatial_overlay": False,
        "voxelwise_change_localization": False,
        "causal_treatment_attribution": False,
        "response_classification": False,
        "diagnosis": False,
        "clinical_conclusion": False,
        "medical_record_signoff": False,
    }


def _format_date(value: str) -> str:
    return f"{value[:4]}-{value[4:6]}-{value[6:8]}"


def _render_page(record_without_files: dict[str, Any]) -> bytes:
    baseline = record_without_files["timepoints"]["baseline"]
    followup = record_without_files["timepoints"]["followup"]
    pairing = record_without_files["pairing_review"]
    comparison = record_without_files["comparison"]
    reviewer = pairing["reviewer"]
    organization = (
        f" · {html.escape(reviewer['organization'])}" if reviewer["organization"] else ""
    )
    if comparison is None:
        numeric = (
            "<p class=\"withheld\">Numeric change is withheld because this pairing was not accepted.</p>"
        )
    else:
        numeric = f"""
<table><thead><tr><th></th><th>Baseline</th><th>Follow-up</th><th>Change</th></tr></thead><tbody>
<tr><th>Reviewed volume</th><td>{comparison['baseline_volume_ml']:.6f} mL</td><td>{comparison['followup_volume_ml']:.6f} mL</td><td>{comparison['absolute_change_ml']:.6f} mL · {comparison['percent_change']:.2f}%</td></tr>
</tbody></table><p>Numeric direction: {comparison['numeric_direction']} · elapsed time: {comparison['elapsed_days']} days · boundary uncertainty: not quantified.</p>"""
    checks = "".join(
        f"<li>{'Yes' if checked else 'No'} · {html.escape(key.replace('_', ' '))}</li>"
        for key, checked in pairing["checklist"].items()
    )
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>DICOM Guide reviewed volume comparison</title><style>
body{{font:16px/1.5 system-ui,sans-serif;margin:0;background:#f5f7f6;color:#17201e}}main{{max-width:980px;margin:auto;padding:32px}}.warning{{border:3px solid #a23d35;background:#fff2f0;padding:16px;font-weight:700}}section{{background:white;border:1px solid #cbd5d1;border-radius:10px;padding:20px;margin:18px 0}}table{{width:100%;border-collapse:collapse}}th,td{{border-bottom:1px solid #ccd6d2;padding:9px;text-align:left}}dt{{font-weight:700}}dd{{margin:0 0 12px}}.withheld{{font-weight:700;color:#87372f}}footer{{font-size:13px;color:#4b5c57}}@media print{{body{{background:white}}main{{padding:0}}section{{break-inside:avoid}}}}
</style></head><body><main><h1>Reviewed manual ROI volume comparison</h1><p class="warning">SELF-ATTESTED PAIRING FOR DISCUSSION ONLY · IDENTITY NOT VERIFIED · NOT A RESPONSE CLASSIFICATION · NO TREATMENT CAUSALITY · NO DIAGNOSIS</p>
<section><h2>Decision</h2><dl><dt>Status</dt><dd>{html.escape(pairing['decision'].replace('_', ' '))}</dd><dt>Reviewer</dt><dd>{html.escape(reviewer['name'])} · {html.escape(reviewer['role'].replace('_', ' '))}{organization}</dd><dt>Source chronology</dt><dd>{_format_date(baseline['acquisition_date'])} to {_format_date(followup['acquisition_date'])}</dd></dl></section>
<section><h2>Reviewed timepoints</h2><dl><dt>Baseline</dt><dd>{html.escape(baseline['series_description'])} · {baseline['modality']} · {baseline['reviewed_volume_ml']:.6f} mL · {html.escape(baseline['represented_tissue'])}</dd><dt>Follow-up</dt><dd>{html.escape(followup['series_description'])} · {followup['modality']} · {followup['reviewed_volume_ml']:.6f} mL · {html.escape(followup['represented_tissue'])}</dd></dl></section>
<section><h2>Source-linked arithmetic</h2>{numeric}<p>These values do not establish biological tumor burden, progression, response, or treatment effect.</p></section>
<section><h2>Pairing judgments</h2><dl><dt>Same lesion identity</dt><dd>{pairing['same_lesion_identity'].replace('_', ' ')}</dd><dt>Same represented tissue</dt><dd>{pairing['same_represented_tissue'].replace('_', ' ')}</dd><dt>Acquisition comparability</dt><dd>{pairing['acquisition_comparability'].replace('_', ' ')}</dd><dt>Boundary comparability</dt><dd>{pairing['boundary_comparability'].replace('_', ' ')}</dd><dt>Registration consideration</dt><dd>{pairing['registration_consideration'].replace('_', ' ')}</dd><dt>Limitations</dt><dd>{html.escape(pairing['limitation_note'] or 'None recorded.')}</dd><dt>Treatment context note</dt><dd>{html.escape(pairing['treatment_context_note'] or 'None recorded.')}</dd></dl><ul>{checks}</ul></section>
<section><h2>Attestation</h2><p>{html.escape(record_without_files['attestation'])}</p></section>
<footer>{''.join(f'<p>{html.escape(item)}</p>' for item in record_without_files['limitations'])}</footer></main></body></html>\n"""
    return page.encode()


def _readme() -> bytes:
    return (
        "DICOM Guide reviewed manual ROI volume comparison\n\n"
        "This sensitive local archive contains two complete accepted boundary-review archives, comparison.json, review.html, and README.txt.\n"
        "Validate it against the original local DICOM root before discussion:\n"
        "  dicom-guide validate-lesion-volume-comparison comparison.zip '/path/to/DICOM-root'\n\n"
        "A valid accepted pairing authorizes only discussion of source-linked manual volume arithmetic. It does not classify response, establish treatment causality, diagnose, spatially register scans, or create a clinical conclusion.\n"
    ).encode()


def _file_contract(filename: str, content: bytes) -> dict[str, Any]:
    return {"filename": filename, "bytes": len(content), "sha256": _sha256(content)}


def _record_without_files(
    baseline_record: dict[str, Any],
    followup_record: dict[str, Any],
    baseline_series: dict[str, Any],
    followup_series: dict[str, Any],
    request: dict[str, Any],
    *,
    comparison_id: str,
    created_at: str,
) -> dict[str, Any]:
    baseline = _timepoint(baseline_record, baseline_series)
    followup = _timepoint(followup_record, followup_series)
    if baseline["patient_context_id"] != followup["patient_context_id"]:
        raise ValueError("boundary reviews do not share one exact patient context")
    if baseline["modality"] != followup["modality"]:
        raise ValueError("boundary reviews must use the same modality")
    if baseline["study_id"] == followup["study_id"]:
        raise ValueError("boundary reviews must come from distinct studies")
    if baseline["series_id"] == followup["series_id"]:
        raise ValueError("boundary reviews must come from distinct series")
    if baseline["review_id"] == followup["review_id"]:
        raise ValueError("boundary reviews must be distinct")
    if baseline["evidence_artifact_id"] == followup["evidence_artifact_id"]:
        raise ValueError("boundary evidence artifacts must be distinct")
    elapsed = _elapsed_days(baseline["acquisition_date"], followup["acquisition_date"])
    if elapsed <= 0:
        raise ValueError("baseline DICOM acquisition date must precede follow-up")
    accepted = request["decision"] == "accepted_for_volume_change_discussion"
    pairing = {
        "reviewer": request["reviewer"],
        "decision": request["decision"],
        **request["pairing"],
        "checklist": request["checklist"],
        "identity_verification": "self_asserted_unverified",
    }
    return {
        "schema_version": "1.0.0",
        "artifact_type": ARTIFACT_TYPE,
        "comparison_id": comparison_id,
        "created_at": created_at,
        "state": (
            "qualified_pairing_review_for_discussion"
            if accepted
            else "pairing_revision_or_rejection_record"
        ),
        "local_only": True,
        "sensitive": True,
        "deidentified": False,
        "timepoints": {"baseline": baseline, "followup": followup},
        "pairing_review": pairing,
        "comparison": _comparison(baseline, followup, accepted),
        "attestation": ATTESTATION,
        "permitted_uses": _permissions(accepted),
        "limitations": LIMITATIONS.copy(),
    }


def lesion_volume_comparison_archive_bytes(
    baseline_review: ArchiveSource,
    followup_review: ArchiveSource,
    request_source: ArchiveSource,
    source_root: Path,
    *,
    catalog: dict[str, Any] | None = None,
    comparison_id: str | None = None,
    created_at: str | None = None,
) -> bytes:
    baseline_bytes, baseline_record = _review_components(
        baseline_review, source_root, "baseline"
    )
    followup_bytes, followup_record = _review_components(
        followup_review, source_root, "follow-up"
    )
    request = _validate_request(
        _strict_object(
            _read_source(request_source, MAX_TEXT_BYTES, "pairing request"),
            "pairing-request.json",
        )
    )
    live_catalog = (
        catalog
        if catalog is not None
        else build_catalog(source_root, include_hashes=False)[0]
    )
    baseline_series = _catalog_series(live_catalog, baseline_record, "baseline")
    followup_series = _catalog_series(live_catalog, followup_record, "follow-up")
    identifier = comparison_id or f"volume_pair_{os.urandom(16).hex()[:8]}-0000-4000-8000-{os.urandom(6).hex()}"
    if not COMPARISON_ID.fullmatch(identifier):
        raise ValueError("comparison_id is invalid")
    record_without_files = _record_without_files(
        baseline_record,
        followup_record,
        baseline_series,
        followup_series,
        request,
        comparison_id=identifier,
        created_at=_created_at(created_at),
    )
    page = _render_page(record_without_files)
    readme = _readme()
    record = {
        **record_without_files,
        "files": {
            "baseline_review": _file_contract("baseline-review.zip", baseline_bytes),
            "followup_review": _file_contract("followup-review.zip", followup_bytes),
            "review_page": _file_contract("review.html", page),
            "readme": _file_contract("README.txt", readme),
        },
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.writestr("comparison.json", _json_bytes(record))
        archive.writestr("baseline-review.zip", baseline_bytes)
        archive.writestr("followup-review.zip", followup_bytes)
        archive.writestr("review.html", page)
        archive.writestr("README.txt", readme)
    return output.getvalue()


def lesion_volume_comparison_from_transport(
    transport: bytes,
    source_root: Path,
    *,
    catalog: dict[str, Any] | None = None,
    created_at: str | None = None,
) -> bytes:
    if not transport or len(transport) > MAX_TRANSPORT_BYTES:
        raise ValueError("volume-comparison request exceeds the local safety limit")
    try:
        with zipfile.ZipFile(io.BytesIO(transport)) as archive:
            infos = archive.infolist()
            names = [item.filename for item in infos]
            if len(infos) != 3 or set(names) != TRANSPORT_FILES:
                raise ValueError(
                    "volume-comparison request must contain exactly baseline-review.zip, followup-review.zip, and pairing-request.json"
                )
            if len(names) != len(set(names)) or any(item.flag_bits & 0x1 for item in infos):
                raise ValueError("ambiguous or encrypted volume-comparison request is unsupported")
            limits = {
                "baseline-review.zip": MAX_REVIEW_BYTES,
                "followup-review.zip": MAX_REVIEW_BYTES,
                "pairing-request.json": MAX_TEXT_BYTES,
            }
            if any(item.file_size > limits[item.filename] for item in infos):
                raise ValueError("volume-comparison request member exceeds its safety limit")
            baseline = archive.read("baseline-review.zip")
            followup = archive.read("followup-review.zip")
            request = archive.read("pairing-request.json")
    except (KeyError, OSError, RuntimeError, zipfile.BadZipFile) as error:
        raise ValueError("volume-comparison request is not a readable ZIP") from error
    return lesion_volume_comparison_archive_bytes(
        io.BytesIO(baseline),
        io.BytesIO(followup),
        io.BytesIO(request),
        source_root,
        catalog=catalog,
        created_at=created_at,
    )


def _read_archive(source: ArchiveSource) -> tuple[dict[str, bytes], list[str]]:
    errors: list[str] = []
    try:
        content = _read_source(source, MAX_ARCHIVE_BYTES, "volume-comparison archive")
    except ValueError as error:
        return {}, [str(error)]
    members: dict[str, bytes] = {}
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            infos = archive.infolist()
            names = [item.filename for item in infos]
            if len(infos) != 5 or set(names) != EXPECTED_FILES:
                return {}, [
                    "volume-comparison archive must contain exactly comparison.json, baseline-review.zip, followup-review.zip, review.html, and README.txt"
                ]
            if len(names) != len(set(names)):
                return {}, ["volume-comparison archive contains duplicate members"]
            expanded = 0
            for item in infos:
                mode = item.external_attr >> 16
                if (
                    item.flag_bits & 0x1
                    or stat.S_ISLNK(mode)
                    or item.filename.startswith(("/", "\\"))
                    or ".." in Path(item.filename).parts
                ):
                    errors.append("volume-comparison archive contains an unsafe member")
                    continue
                maximum = MAX_REVIEW_BYTES if item.filename.endswith("-review.zip") else MAX_TEXT_BYTES
                if item.file_size > maximum:
                    errors.append(f"{item.filename} exceeds its local safety limit")
                    continue
                expanded += item.file_size
                if expanded > MAX_ARCHIVE_BYTES:
                    errors.append("expanded volume-comparison archive exceeds the local safety limit")
                    continue
                members[item.filename] = archive.read(item)
    except (OSError, RuntimeError, zipfile.BadZipFile):
        errors.append("volume-comparison archive is not a readable ZIP")
    return members, errors


def _semantic_errors(record: Any) -> list[str]:
    errors: list[str] = []
    expected = {
        "schema_version",
        "artifact_type",
        "comparison_id",
        "created_at",
        "state",
        "local_only",
        "sensitive",
        "deidentified",
        "timepoints",
        "pairing_review",
        "comparison",
        "attestation",
        "permitted_uses",
        "limitations",
        "files",
    }
    if not isinstance(record, dict) or set(record) != expected:
        return ["comparison.json fields do not match the v1 contract"]
    constants = {
        "schema_version": "1.0.0",
        "artifact_type": ARTIFACT_TYPE,
        "local_only": True,
        "sensitive": True,
        "deidentified": False,
        "attestation": ATTESTATION,
        "limitations": LIMITATIONS,
    }
    for key, value in constants.items():
        if record.get(key) != value:
            errors.append(f"comparison.{key} is invalid")
    if not isinstance(record.get("comparison_id"), str) or not COMPARISON_ID.fullmatch(record["comparison_id"]):
        errors.append("comparison_id is invalid")
    if not _valid_datetime(record.get("created_at")):
        errors.append("comparison created_at must include a timezone")
    pairing = record.get("pairing_review")
    request: dict[str, Any] | None = None
    if isinstance(pairing, dict):
        pairing_keys = {
            "reviewer",
            "decision",
            "same_lesion_identity",
            "same_represented_tissue",
            "chronology",
            "acquisition_comparability",
            "boundary_comparability",
            "registration_consideration",
            "limitation_note",
            "treatment_context_note",
            "checklist",
            "identity_verification",
        }
        if set(pairing) != pairing_keys or pairing.get("identity_verification") != "self_asserted_unverified":
            errors.append("pairing_review fields are invalid")
        else:
            request = {
                "schema_version": "1.0.0",
                "artifact_type": REQUEST_ARTIFACT_TYPE,
                "reviewer": pairing["reviewer"],
                "decision": pairing["decision"],
                "pairing": {
                    key: pairing[key]
                    for key in (
                        "same_lesion_identity",
                        "same_represented_tissue",
                        "chronology",
                        "acquisition_comparability",
                        "boundary_comparability",
                        "registration_consideration",
                        "limitation_note",
                        "treatment_context_note",
                    )
                },
                "checklist": pairing["checklist"],
                "attestation": record.get("attestation"),
            }
            try:
                _validate_request(request)
            except ValueError as error:
                errors.append(str(error))
    else:
        errors.append("pairing_review is invalid")
    accepted = isinstance(pairing, dict) and pairing.get("decision") == "accepted_for_volume_change_discussion"
    expected_state = "qualified_pairing_review_for_discussion" if accepted else "pairing_revision_or_rejection_record"
    if record.get("state") != expected_state:
        errors.append("comparison state does not match the pairing decision")
    if record.get("permitted_uses") != _permissions(accepted):
        errors.append("comparison permissions do not match the pairing decision")
    timepoints = record.get("timepoints")
    if not isinstance(timepoints, dict) or set(timepoints) != {"baseline", "followup"}:
        errors.append("comparison timepoints are invalid")
    elif all(isinstance(timepoints.get(key), dict) for key in ("baseline", "followup")):
        try:
            expected_comparison = _comparison(timepoints["baseline"], timepoints["followup"], accepted)
            observed = record.get("comparison")
            if expected_comparison is None:
                if observed is not None:
                    errors.append("unaccepted pairing must withhold numeric comparison")
            elif not isinstance(observed, dict) or set(observed) != set(expected_comparison):
                errors.append("numeric comparison fields are invalid")
            else:
                for key, value in expected_comparison.items():
                    observed_value = observed.get(key)
                    if isinstance(value, float):
                        if not isinstance(observed_value, (int, float)) or isinstance(observed_value, bool) or not math.isclose(float(observed_value), value, rel_tol=1e-12, abs_tol=1e-12):
                            errors.append(f"numeric comparison {key} is invalid")
                    elif observed_value != value:
                        errors.append(f"numeric comparison {key} is invalid")
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            errors.append("numeric comparison cannot be recomputed")
    files = record.get("files")
    if not isinstance(files, dict) or set(files) != {
        "baseline_review",
        "followup_review",
        "review_page",
        "readme",
    }:
        errors.append("comparison files are invalid")
    return list(dict.fromkeys(errors))


def lesion_volume_comparison_summary(
    archive: ArchiveSource,
    source_root: Path,
    *,
    catalog: dict[str, Any] | None = None,
) -> dict[str, Any]:
    members, errors = _read_archive(archive)
    record: dict[str, Any] = {}
    if "comparison.json" in members:
        try:
            record = _strict_object(members["comparison.json"], "comparison.json")
        except ValueError as error:
            errors.append(str(error))
    if record:
        errors.extend(_semantic_errors(record))
    files = record.get("files") if isinstance(record, dict) else None
    file_map = {
        "baseline_review": "baseline-review.zip",
        "followup_review": "followup-review.zip",
        "review_page": "review.html",
        "readme": "README.txt",
    }
    if isinstance(files, dict):
        for key, filename in file_map.items():
            item = files.get(key)
            payload = members.get(filename)
            if not isinstance(item, dict) or set(item) != {"filename", "bytes", "sha256"}:
                errors.append(f"files.{key} is invalid")
                continue
            if item.get("filename") != filename or not isinstance(payload, bytes):
                errors.append(f"files.{key} does not match the archive")
                continue
            if item.get("bytes") != len(payload) or item.get("sha256") != _sha256(payload):
                errors.append(f"{filename} does not match comparison.json")

    baseline_record: dict[str, Any] = {}
    followup_record: dict[str, Any] = {}
    live_catalog: dict[str, Any] | None = None
    for role, filename in (("baseline", "baseline-review.zip"), ("follow-up", "followup-review.zip")):
        payload = members.get(filename)
        if payload is None:
            continue
        summary = lesion_volume_review_summary(io.BytesIO(payload), source_root)
        if not summary["valid"] or summary.get("review_status") != "accepted_for_discussion" or summary.get("eligible_for_future_pairing_review") is not True:
            errors.append(f"nested {role} boundary review is invalid or not accepted")
            continue
        try:
            with zipfile.ZipFile(io.BytesIO(payload)) as nested:
                parsed = _strict_object(nested.read("review.json"), f"nested {role} review.json")
            if role == "baseline":
                baseline_record = parsed
            else:
                followup_record = parsed
        except (KeyError, ValueError, zipfile.BadZipFile):
            errors.append(f"nested {role} boundary review cannot be read")
    if baseline_record and followup_record and record:
        try:
            live_catalog = (
                catalog
                if catalog is not None
                else build_catalog(source_root, include_hashes=False)[0]
            )
            baseline_series = _catalog_series(live_catalog, baseline_record, "baseline")
            followup_series = _catalog_series(live_catalog, followup_record, "follow-up")
            pairing = record.get("pairing_review")
            if not isinstance(pairing, dict):
                raise ValueError("pairing review is invalid")
            request = {
                "schema_version": "1.0.0",
                "artifact_type": REQUEST_ARTIFACT_TYPE,
                "reviewer": pairing["reviewer"],
                "decision": pairing["decision"],
                "pairing": {
                    key: pairing[key]
                    for key in (
                        "same_lesion_identity",
                        "same_represented_tissue",
                        "chronology",
                        "acquisition_comparability",
                        "boundary_comparability",
                        "registration_consideration",
                        "limitation_note",
                        "treatment_context_note",
                    )
                },
                "checklist": pairing["checklist"],
                "attestation": record["attestation"],
            }
            rebuilt = _record_without_files(
                baseline_record,
                followup_record,
                baseline_series,
                followup_series,
                _validate_request(request),
                comparison_id=record["comparison_id"],
                created_at=record["created_at"],
            )
            observed_without_files = {key: value for key, value in record.items() if key != "files"}
            if observed_without_files != rebuilt:
                errors.append("comparison record does not match the exact nested reviews and live DICOM catalog")
            if members.get("review.html") != _render_page(rebuilt):
                errors.append("review.html does not exactly present the validated comparison record")
            if members.get("README.txt") != _readme():
                errors.append("README.txt does not match the v1 local instructions")
        except (KeyError, TypeError, ValueError, ZeroDivisionError) as error:
            errors.append(str(error))

    errors = list(dict.fromkeys(errors))
    valid = not errors and bool(record) and baseline_record and followup_record
    pairing_value = record.get("pairing_review") if record else None
    safe_pairing = pairing_value if isinstance(pairing_value, dict) else {}
    accepted = bool(
        valid
        and safe_pairing.get("decision")
        == "accepted_for_volume_change_discussion"
    )
    comparison = record.get("comparison") if accepted else None
    return {
        "valid": bool(valid),
        "errors": errors,
        "schema_version": record.get("schema_version") if record else None,
        "artifact_type": record.get("artifact_type") if record else None,
        "decision": safe_pairing.get("decision") if valid else None,
        "identity_verification": "self_asserted_unverified" if valid else None,
        "source_validated": bool(valid),
        "pairing_review_self_attested": bool(valid),
        "reviewed_volume_change_for_discussion": accepted,
        "baseline_reviewed_volume_ml": comparison.get("baseline_volume_ml") if comparison else None,
        "followup_reviewed_volume_ml": comparison.get("followup_volume_ml") if comparison else None,
        "absolute_volume_change_ml": comparison.get("absolute_change_ml") if comparison else None,
        "percent_volume_change": comparison.get("percent_change") if comparison else None,
        "numeric_direction": comparison.get("numeric_direction") if comparison else None,
        "elapsed_days": comparison.get("elapsed_days") if comparison else None,
        "spatial_overlay": False,
        "voxelwise_change_localization": False,
        "causal_treatment_attribution": False,
        "response_classification": False,
        "diagnosis": False,
        "clinical_conclusion": False,
        "evidence_use": (
            "qualified_reviewed_volume_change_for_discussion_only"
            if accepted
            else "pairing_revision_or_rejection_only"
            if valid
            else "none"
        ),
    }


def write_lesion_volume_comparison(
    baseline_review: Path,
    followup_review: Path,
    request: Path,
    source_root: Path,
    output: Path,
    *,
    created_at: str | None = None,
) -> dict[str, Any]:
    if output.exists() or output.is_symlink():
        raise ValueError("volume-comparison output already exists")
    payload = lesion_volume_comparison_archive_bytes(
        baseline_review,
        followup_review,
        request,
        source_root,
        created_at=created_at,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        output.unlink(missing_ok=True)
        raise
    return lesion_volume_comparison_summary(output, source_root)
