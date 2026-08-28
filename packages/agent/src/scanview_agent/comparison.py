from __future__ import annotations

import re
from itertools import combinations
from typing import Any


def _terms(value: str) -> set[str]:
    return {term for term in re.split(r"[^a-z0-9]+", value.lower()) if len(term) >= 2}


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

    if (baseline.get("rows"), baseline.get("columns")) != (
        followup.get("rows"),
        followup.get("columns"),
    ):
        score -= 10
        warnings.append("matrix_mismatch")
        reasons.append("Image matrix dimensions differ.")

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
    for study in catalog.get("studies", []):
        for series in study.get("series", []):
            dated_series.append((study.get("acquisition_date") or "", series))

    candidates = []
    for (left_date, left), (right_date, right) in combinations(dated_series, 2):
        if left_date == right_date:
            continue
        baseline, followup = (left, right) if left_date <= right_date else (right, left)
        candidates.append(score_pair(baseline, followup))
    candidates.sort(key=lambda item: item["score"], reverse=True)
    return {
        "schema_version": catalog.get("schema_version", "1.0.0"),
        "review_status": "unreviewed",
        "candidates": candidates,
        "limitations": [
            "These are metadata-based suggestions, not accepted clinical pairings.",
            "A person must confirm sequence, contrast, coverage, artifact, and acquisition compatibility.",
        ],
    }
