from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from typing import Any

from .comparison import suggest_pairs


SCHEMA_VERSION = "1.0.0"
ARTIFACT_TYPE = "scanview.longitudinal-readiness"
MAX_REPORTED_CANDIDATE_PAIRS = 256
OPAQUE_IDS = {
    kind: re.compile(rf"^{kind}_[0-9a-f]{{20}}$")
    for kind in ("study", "series", "patient")
}
MODALITIES = ("MR", "CT")
MODALITY_STATES = {
    "not_present",
    "no_eligible_series",
    "needs_distinct_study",
    "needs_complete_dates",
    "needs_same_patient_context",
    "needs_distinct_dates",
    "candidate_pairs_require_human_review",
}
REQUIRED_HUMAN_DECISIONS = [
    "confirm_patient_identity_in_the_clinical_imaging_system",
    "assign_clinical_baseline_and_followup_roles",
    "confirm_matching_sequence_contrast_coverage_and_artifact",
    "confirm_same_lesion_and_represented_tissue",
    "select_response_criteria_with_the_treating_clinician",
]
REQUIRED_TECHNICAL_GATES = [
    "verify_exact_source_bytes",
    "review_registration_need_for_different_frames",
    "complete_qualified_registration_qa_before_spatial_comparison",
    "review_each_manual_boundary_independently",
]
LIMITATIONS = [
    "This is a metadata-only readiness report, not an accepted clinical pairing.",
    "A candidate score cannot establish lesion identity, response, or treatment effect.",
    "Current MRI and CT studies must remain neutral reference views when no same-modality pair exists.",
]


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _valid_dicom_date(value: Any) -> bool:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{8}", value):
        return False
    try:
        datetime.strptime(value, "%Y%m%d")
    except ValueError:
        return False
    return True


def _validate_catalog(catalog: Any) -> list[dict[str, Any]]:
    if (
        not isinstance(catalog, dict)
        or catalog.get("schema_version") != "1.0.0"
        or not isinstance(catalog.get("studies"), list)
        or not isinstance(catalog.get("source"), dict)
    ):
        raise ValueError("ScanView catalog shape is invalid")
    dicom_instances = catalog["source"].get("dicom_instances")
    if type(dicom_instances) is not int or dicom_instances < 0:
        raise ValueError("ScanView catalog source count is invalid")

    studies: list[dict[str, Any]] = []
    study_ids: set[str] = set()
    series_ids: set[str] = set()
    for study in catalog["studies"]:
        if not isinstance(study, dict) or not OPAQUE_IDS["study"].fullmatch(
            str(study.get("id", ""))
        ):
            raise ValueError("ScanView catalog contains an invalid study")
        if study["id"] in study_ids or not isinstance(study.get("series"), list):
            raise ValueError("ScanView catalog study membership is invalid")
        study_ids.add(study["id"])
        date = study.get("acquisition_date")
        if date is not None and not _valid_dicom_date(date):
            raise ValueError("ScanView catalog contains an invalid acquisition date")
        for series in study["series"]:
            if (
                not isinstance(series, dict)
                or not OPAQUE_IDS["series"].fullmatch(str(series.get("id", "")))
                or series["id"] in series_ids
                or not isinstance(series.get("modality"), str)
                or not isinstance(series.get("series_description"), str)
                or type(series.get("instance_count")) is not int
                or series["instance_count"] < 1
            ):
                raise ValueError("ScanView catalog contains an invalid series")
            patient_context = series.get("patient_context_id")
            if patient_context is not None and not OPAQUE_IDS["patient"].fullmatch(
                str(patient_context)
            ):
                raise ValueError("ScanView catalog contains an invalid patient context")
            series_ids.add(series["id"])
        studies.append(study)
    try:
        _canonical(catalog)
    except (TypeError, ValueError) as error:
        raise ValueError("ScanView catalog contains unsupported values") from error
    return studies


def _modality_readiness(
    modality: str,
    studies: list[dict[str, Any]],
    eligible_ids: set[str],
    candidate_pairs: list[dict[str, Any]],
    series_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    records = [
        (study["id"], study.get("acquisition_date"), series)
        for study in studies
        for series in study["series"]
        if series["modality"] == modality
    ]
    eligible = [record for record in records if record[2]["id"] in eligible_ids]
    study_count = len({study_id for study_id, _, _ in records})
    eligible_study_count = len({study_id for study_id, _, _ in eligible})
    dated_study_count = len(
        {study_id for study_id, date, _ in eligible if _valid_dicom_date(date)}
    )
    contexts = {
        series.get("patient_context_id")
        for _, _, series in eligible
        if series.get("patient_context_id")
    }
    modality_candidates = [
        candidate
        for candidate in candidate_pairs
        if series_by_id[candidate["baseline_series_id"]]["modality"] == modality
    ]

    if not records:
        state = "not_present"
    elif not eligible:
        state = "no_eligible_series"
    elif modality_candidates:
        state = "candidate_pairs_require_human_review"
    elif eligible_study_count < 2:
        state = "needs_distinct_study"
    elif dated_study_count < 2:
        state = "needs_complete_dates"
    else:
        by_context: dict[str, list[tuple[str, str]]] = {}
        for study_id, date, series in eligible:
            context = series.get("patient_context_id")
            if context and _valid_dicom_date(date):
                by_context.setdefault(context, []).append((study_id, date))
        same_context_groups = [
            values
            for values in by_context.values()
            if len({study_id for study_id, _ in values}) >= 2
        ]
        if not same_context_groups:
            state = "needs_same_patient_context"
        elif not any(len({date for _, date in values}) >= 2 for values in same_context_groups):
            state = "needs_distinct_dates"
        else:
            raise ValueError("ScanView readiness state is internally inconsistent")

    if state not in MODALITY_STATES:
        raise ValueError("ScanView readiness modality state is unsupported")
    return {
        "modality": modality,
        "state": state,
        "study_count": study_count,
        "eligible_study_count": eligible_study_count,
        "series_count": len(records),
        "eligible_series_count": len(eligible),
        "dated_study_count": dated_study_count,
        "patient_context_count": len(contexts),
        "candidate_pair_count": len(modality_candidates),
    }


def _missing_data(
    *,
    study_count: int,
    eligible_series_count: int,
    modality_readiness: list[dict[str, Any]],
    candidate_count: int,
) -> list[str]:
    if study_count == 0:
        return ["dicom_studies"]
    if eligible_series_count == 0:
        return ["eligible_mr_or_ct_stack"]
    if candidate_count:
        return []
    state_to_requirement = {
        "needs_distinct_study": "future_distinct_study_same_modality_series",
        "needs_complete_dates": "complete_acquisition_dates",
        "needs_same_patient_context": "same_patient_context_across_exams",
        "needs_distinct_dates": "distinct_exam_dates",
    }
    requirements = {
        state_to_requirement[item["state"]]
        for item in modality_readiness
        if item["state"] in state_to_requirement
    }
    return [
        requirement
        for requirement in (
            "future_distinct_study_same_modality_series",
            "complete_acquisition_dates",
            "same_patient_context_across_exams",
            "distinct_exam_dates",
        )
        if requirement in requirements
    ]


def build_longitudinal_readiness(
    catalog: Any,
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    studies = _validate_catalog(catalog)
    if generated_at is None:
        generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    try:
        parsed_generated_at = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as error:
        raise ValueError("readiness generation timestamp is invalid") from error
    if parsed_generated_at.tzinfo is None:
        raise ValueError("readiness generation timestamp must include a timezone")

    try:
        suggestions = suggest_pairs(catalog)
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        raise ValueError("ScanView catalog cannot produce a readiness report") from error
    excluded_ids = {
        item["series_id"]
        for item in suggestions["excluded_series"]
        if (
            isinstance(item, dict)
            and isinstance(item.get("series_id"), str)
            and isinstance(item.get("reasons"), list)
            and any(
                reason != "missing_or_invalid_acquisition_date"
                for reason in item["reasons"]
            )
        )
    }
    series_by_id = {
        series["id"]: series for study in studies for series in study["series"]
    }
    eligible_ids = {
        series_id
        for series_id, series in series_by_id.items()
        if series_id not in excluded_ids and series["modality"] in MODALITIES
    }
    candidates = suggestions["candidates"]
    if not isinstance(candidates, list):
        raise ValueError("ScanView candidate report is invalid")
    compact_candidates = []
    for candidate in candidates[:MAX_REPORTED_CANDIDATE_PAIRS]:
        if (
            not isinstance(candidate, dict)
            or candidate.get("baseline_series_id") not in series_by_id
            or candidate.get("followup_series_id") not in series_by_id
            or type(candidate.get("score")) is not int
            or not math.isfinite(candidate["score"])
            or candidate.get("compatibility")
            not in {"compatible", "review", "incompatible"}
            or not isinstance(candidate.get("warnings"), list)
            or not all(isinstance(value, str) for value in candidate["warnings"])
        ):
            raise ValueError("ScanView candidate report is invalid")
        compact_candidates.append(
            {
                "baseline_series_id": candidate["baseline_series_id"],
                "followup_series_id": candidate["followup_series_id"],
                "score": candidate["score"],
                "compatibility": candidate["compatibility"],
                "warnings": candidate["warnings"],
                "review_status": "unreviewed",
                "auto_approved": False,
            }
        )

    modality_readiness = [
        _modality_readiness(
            modality,
            studies,
            eligible_ids,
            candidates,
            series_by_id,
        )
        for modality in MODALITIES
    ]
    all_series = list(series_by_id.values())
    patient_contexts = {
        series.get("patient_context_id")
        for series in all_series
        if series.get("patient_context_id")
    }
    candidate_count = len(candidates)
    state = (
        "no_dicom_studies"
        if not studies
        else "candidate_pairs_require_human_review"
        if candidate_count
        else "no_same_modality_longitudinal_pair"
    )
    missing_data = _missing_data(
        study_count=len(studies),
        eligible_series_count=len(eligible_ids),
        modality_readiness=modality_readiness,
        candidate_count=candidate_count,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "generated_at": generated_at,
        "catalog_sha256": hashlib.sha256(_canonical(catalog)).hexdigest(),
        "local_only": True,
        "review_status": "unreviewed",
        "state": state,
        "privacy": {
            "classification": "sensitive_local_medical_data",
            "direct_identifier_tags_excluded": True,
            "deidentified": False,
            "contains_pixels": False,
            "contains_paths": False,
        },
        "source_summary": {
            "study_count": len(studies),
            "dated_study_count": len(
                {
                    study["id"]
                    for study in studies
                    if _valid_dicom_date(study.get("acquisition_date"))
                }
            ),
            "series_count": len(all_series),
            "eligible_series_count": len(eligible_ids),
            "dicom_instance_count": catalog["source"]["dicom_instances"],
            "patient_context_count": len(patient_contexts),
            "candidate_pair_count": candidate_count,
            "reported_candidate_pair_count": len(compact_candidates),
            "candidate_pairs_truncated": candidate_count > len(compact_candidates),
        },
        "modality_readiness": modality_readiness,
        "candidate_pairs": compact_candidates,
        "missing_data": missing_data,
        "required_human_decisions": list(REQUIRED_HUMAN_DECISIONS),
        "required_technical_gates": list(REQUIRED_TECHNICAL_GATES),
        "permissions": {
            "candidate_selection_authorized": False,
            "registration_authorized": False,
            "spatial_comparison_authorized": False,
            "lesion_link_authorized": False,
            "response_classification_authorized": False,
            "treatment_effect_conclusion_authorized": False,
            "diagnosis_authorized": False,
            "clinical_conclusion_authorized": False,
        },
        "limitations": list(LIMITATIONS),
    }
