from __future__ import annotations

import re
from itertools import combinations
from typing import Any


def _terms(value: str) -> set[str]:
    return {term for term in re.split(r"[^a-z0-9]+", value.lower()) if len(term) >= 2}


def _different_number(left: Any, right: Any, tolerance: float) -> bool:
    if left is None or right is None:
        return False
    left_number = float(left)
    right_number = float(right)
    scale = max(abs(left_number), abs(right_number), 1.0)
    return abs(left_number - right_number) / scale > tolerance


def _eligibility_reasons(series: dict[str, Any]) -> list[str]:
    reasons = []
    if series.get("modality") not in {"MR", "CT"}:
        reasons.append("unsupported_non_pixel_modality")
    if series.get("instance_count", 0) < 2:
        reasons.append("insufficient_stack_depth")
    image_terms = {term.upper() for term in series.get("image_type", [])}
    description_terms = _terms(series.get("series_description", ""))
    if image_terms & {"LOCALIZER", "SCOUT"} or description_terms & {"localizer", "scout", "survey"}:
        reasons.append("localizer_or_scout")
    return reasons


def score_pair(baseline: dict[str, Any], followup: dict[str, Any]) -> dict[str, Any]:
    score = 100
    warnings: list[str] = []
    reasons: list[str] = []

    modality_mismatch = baseline["modality"] != followup["modality"]
    if modality_mismatch:
        score -= 60
        warnings.append("different_modality")
        reasons.append("CT and MRI intensity values are not directly comparable.")
    else:
        reasons.append(f"Both series use {baseline['modality']}.")

    shared = sorted(_terms(baseline["series_description"]) & _terms(followup["series_description"]))
    if shared:
        reasons.append(f"Shared sequence terms: {', '.join(shared[:4])}.")
    else:
        score -= 25
        warnings.append("sequence_description_mismatch")
        reasons.append("Sequence descriptions do not share a meaningful term.")

    if baseline.get("contrast_present") != followup.get("contrast_present"):
        score -= 30
        warnings.append("contrast_mismatch")
        reasons.append("Only one series reports contrast agent metadata.")

    if baseline.get("body_part") and followup.get("body_part") and baseline["body_part"] != followup["body_part"]:
        score -= 20
        warnings.append("body_part_mismatch")
        reasons.append("Body-part metadata differs.")

    if (baseline.get("rows"), baseline.get("columns")) != (
        followup.get("rows"),
        followup.get("columns"),
    ):
        score -= 10
        warnings.append("matrix_mismatch")
        reasons.append("Image matrix dimensions differ.")

    left_orientation = baseline.get("image_orientation_patient")
    right_orientation = followup.get("image_orientation_patient")
    if left_orientation and right_orientation and len(left_orientation) == len(right_orientation):
        if max(abs(float(left) - float(right)) for left, right in zip(left_orientation, right_orientation)) > 0.02:
            score -= 10
            warnings.append("orientation_mismatch")
            reasons.append("Acquisition orientations differ.")

    for field, tolerance, label in (
        ("repetition_time", 0.15, "repetition time"),
        ("echo_time", 0.15, "echo time"),
        ("inversion_time", 0.15, "inversion time"),
        ("flip_angle", 0.10, "flip angle"),
    ):
        if _different_number(baseline.get(field), followup.get(field), tolerance):
            score -= 8
            warnings.append(f"{field}_mismatch")
            reasons.append(f"Reported {label} differs materially.")

    if (
        baseline.get("frame_of_reference_id")
        and baseline.get("frame_of_reference_id") == followup.get("frame_of_reference_id")
    ):
        reasons.append("Both series share a DICOM Frame of Reference.")
    else:
        score -= 5
        warnings.append("registration_required")
        reasons.append("Overlay requires a generated transform and registration QA.")

    score = max(0, score)
    return {
        "baseline_series_id": baseline["id"],
        "followup_series_id": followup["id"],
        "score": score,
        "compatibility": (
            "incompatible"
            if modality_mismatch
            else "compatible"
            if score >= 80
            else "review"
            if score >= 40
            else "incompatible"
        ),
        "warnings": warnings,
        "reasons": reasons,
        "auto_approved": False,
        "review_status": "unreviewed",
        "derived_operations": {
            "overlay": "locked_pending_registration_qc",
            "subtraction": "locked_pending_sequence_match_registration_and_normalization",
        },
    }


def suggest_pairs(catalog: dict[str, Any]) -> dict[str, Any]:
    dated_series: list[tuple[str, dict[str, Any]]] = []
    excluded_series = []
    for study in catalog.get("studies", []):
        for series in study.get("series", []):
            eligibility_reasons = _eligibility_reasons(series)
            if eligibility_reasons:
                excluded_series.append({"series_id": series["id"], "reasons": eligibility_reasons})
                continue
            dated_series.append((study.get("acquisition_date") or "", series))

    candidates = []
    for (left_date, left), (right_date, right) in combinations(dated_series, 2):
        if left_date == right_date:
            continue
        if left.get("modality") != right.get("modality"):
            continue
        baseline, followup = (left, right) if left_date <= right_date else (right, left)
        candidates.append(score_pair(baseline, followup))
    candidates.sort(key=lambda item: item["score"], reverse=True)
    return {
        "schema_version": catalog.get("schema_version", "1.0.0"),
        "review_status": "unreviewed",
        "candidates": candidates,
        "excluded_series": excluded_series,
        "limitations": [
            "These are metadata-based suggestions, not accepted clinical pairings.",
            "A person must confirm sequence, contrast, coverage, artifact, and acquisition compatibility.",
        ],
    }
