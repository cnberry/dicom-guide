from __future__ import annotations

import io
from pathlib import Path
from typing import Any, BinaryIO

from .lesion_volume_comparisons import (
    _read_archive as comparison_archive_members,
    _strict_object,
    lesion_volume_comparison_summary,
)
from .lesion_volume_reviews import _read_archive as review_archive_members
from .lesion_volumes import lesion_volume_archive_display_data


ArchiveSource = Path | BinaryIO
DISPLAY_ARTIFACT_TYPE = "lesion_volume_native_boundary_display_context"
DISPLAY_STATUS = "authorized_reviewed_native_boundaries_unregistered"
MASK_URLS = {
    "baseline": "/v1/lesion-volume-comparison-display/masks/baseline",
    "followup": "/v1/lesion-volume-comparison-display/masks/followup",
}
ALWAYS_LOCKED = [
    "spatial_overlay",
    "voxelwise_change_localization",
    "subtraction",
    "mask_propagation",
    "response_classification",
    "causal_treatment_attribution",
    "diagnosis",
    "clinical_conclusion",
    "medical_record_signoff",
]
LIMITATIONS = [
    "Each accepted boundary is displayed only on its own exact native DICOM grid.",
    "The two native coordinate systems are not registered and must never be overlaid, subtracted, or treated as spatially corresponding.",
    "Optional normalized navigation mirrors fractional grid location only; it is approximate navigation, not anatomical alignment.",
    "Reviewer identity, role, and credentials are self asserted and unauthenticated.",
    "The displayed regions are manually painted boundaries whose uncertainty is not quantified.",
    "The pairing reviewer attested same-lesion and represented-tissue judgments for discussion only.",
    "Volume arithmetic can be affected by acquisition, enhancement, edema, necrosis, treatment effect, motion, and partial-volume differences.",
    "No voxelwise change, biological tumor burden, progression, treatment response, treatment causality, diagnosis, or clinical conclusion is established.",
    "Original DICOM images, radiology reports, pathology, treatment history, and the clinical medical record remain authoritative.",
]


def _nested_evidence(review_bytes: bytes, label: str) -> tuple[dict[str, Any], bytes]:
    members, errors = review_archive_members(io.BytesIO(review_bytes))
    if errors or set(members) != {"review.json", "evidence.zip", "review.html", "README.txt"}:
        raise ValueError(f"validated {label} boundary review could not be reopened safely")
    record = _strict_object(members["review.json"], f"nested {label} review.json")
    return record, members["evidence.zip"]


def _timepoint(
    role: str,
    comparison_timepoint: dict[str, Any],
    review_record: dict[str, Any],
    display_data: dict[str, Any],
) -> dict[str, Any]:
    evidence = display_data["evidence"]
    source = evidence["source"]
    measurement = evidence["measurement"]
    review = review_record["review"]
    expected = {
        "review_id": review_record["review_id"],
        "evidence_artifact_id": evidence["artifact_id"],
        "patient_context_id": source["patient_context_id"],
        "study_id": source["study_id"],
        "series_id": source["series_id"],
        "frame_of_reference_id": source["frame_of_reference_id"],
        "modality": source["modality"],
        "source_set_sha256": source["source_set_sha256"],
        "mask_pixel_sha256": measurement["mask_pixel_sha256"],
        "foreground_voxel_count": measurement["foreground_voxel_count"],
        "reviewed_volume_ml": measurement["volume_ml"],
        "represented_tissue": review["represented_tissue"],
        "inclusion_criteria": review["inclusion_criteria"],
        "exclusion_criteria": review["exclusion_criteria"],
    }
    for key, expected_value in expected.items():
        if comparison_timepoint.get(key) != expected_value:
            raise ValueError(f"{role} display evidence disagrees with the validated comparison")
    dimensions = display_data["dimensions"]
    if dimensions != evidence["geometry"]["dimensions"]:
        raise ValueError(f"{role} native mask dimensions are inconsistent")
    if display_data["mask_sha256"] != measurement["mask_pixel_sha256"]:
        raise ValueError(f"{role} native mask hash is inconsistent")
    if len(display_data["mask"]) != dimensions[0] * dimensions[1] * dimensions[2]:
        raise ValueError(f"{role} native mask byte count is inconsistent")
    return {
        "role": role,
        "review_id": review_record["review_id"],
        "evidence_artifact_id": evidence["artifact_id"],
        "patient_context_id": source["patient_context_id"],
        "study_id": source["study_id"],
        "series_id": source["series_id"],
        "frame_of_reference_id": source["frame_of_reference_id"],
        "modality": source["modality"],
        "acquisition_date": comparison_timepoint["acquisition_date"],
        "series_description": comparison_timepoint["series_description"],
        "protocol_name": comparison_timepoint["protocol_name"],
        "source_set_sha256": source["source_set_sha256"],
        "ordered_instance_ids": display_data["ordered_instance_ids"],
        "dimensions": dimensions,
        "reviewed_volume_ml": measurement["volume_ml"],
        "foreground_voxel_count": measurement["foreground_voxel_count"],
        "mask": {
            "url": MASK_URLS[role],
            "bytes": len(display_data["mask"]),
            "sha256": display_data["mask_sha256"],
            "scalar_type": "uint8",
            "binary_values": [0, 1],
            "grid_order": "source_volume_frame_row_column",
        },
        "boundary_review": {
            "status": "accepted_for_discussion",
            "self_attested": True,
            "represented_tissue": review["represented_tissue"],
            "inclusion_criteria": review["inclusion_criteria"],
            "exclusion_criteria": review["exclusion_criteria"],
            "boundary_uncertainty": "not_quantified",
        },
    }


def lesion_volume_comparison_display_context(
    archive: ArchiveSource,
    source_root: Path,
    *,
    catalog: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Unlock exact native boundary pixels only after recursive local validation."""

    summary = lesion_volume_comparison_summary(
        archive, source_root, catalog=catalog
    )
    if not summary["valid"]:
        raise ValueError("lesion-volume comparison is invalid against the exact local source")
    if summary.get("decision") != "accepted_for_volume_change_discussion":
        raise ValueError("lesion-volume comparison is not accepted for volume-change discussion")
    members, errors = comparison_archive_members(archive)
    if errors or set(members) != {
        "comparison.json",
        "baseline-review.zip",
        "followup-review.zip",
        "review.html",
        "README.txt",
    }:
        raise ValueError("validated lesion-volume comparison could not be reopened safely")
    record = _strict_object(members["comparison.json"], "comparison.json")
    baseline_review, baseline_evidence = _nested_evidence(
        members["baseline-review.zip"], "baseline"
    )
    followup_review, followup_evidence = _nested_evidence(
        members["followup-review.zip"], "follow-up"
    )
    baseline_data = lesion_volume_archive_display_data(
        io.BytesIO(baseline_evidence), source_root
    )
    followup_data = lesion_volume_archive_display_data(
        io.BytesIO(followup_evidence), source_root
    )
    timepoints = record["timepoints"]
    baseline = _timepoint(
        "baseline", timepoints["baseline"], baseline_review, baseline_data
    )
    followup = _timepoint(
        "followup", timepoints["followup"], followup_review, followup_data
    )
    comparison = record["comparison"]
    pairing = record["pairing_review"]
    context = {
        "schema_version": "1.0.0",
        "artifact_type": DISPLAY_ARTIFACT_TYPE,
        "local_only": True,
        "sensitive": True,
        "deidentified": False,
        "display_status": DISPLAY_STATUS,
        "display_label": "REVIEWED NATIVE BOUNDARIES — UNREGISTERED",
        "comparison_id": record["comparison_id"],
        "review": {
            "decision": pairing["decision"],
            "reviewer_role": pairing["reviewer"]["role"],
            "identity_status": "self_attested_unverified",
            "same_lesion_identity": pairing["same_lesion_identity"],
            "same_represented_tissue": pairing["same_represented_tissue"],
            "acquisition_comparability": pairing["acquisition_comparability"],
            "boundary_comparability": pairing["boundary_comparability"],
            "registration_consideration": pairing["registration_consideration"],
            "limitation_note": pairing["limitation_note"],
            "treatment_context_note": pairing["treatment_context_note"],
        },
        "comparison": comparison,
        "timepoints": {"baseline": baseline, "followup": followup},
        "navigation_policy": {
            "default_linked": False,
            "link_mode": "normalized_native_grid_fraction",
            "approximate_navigation_only": True,
            "anatomical_correspondence": False,
            "registered": False,
            "independent_navigation_available": True,
        },
        "display_policy": {
            "allowed_modes": ["native_side_by_side", "normalized_navigation_link"],
            "always_locked": ALWAYS_LOCKED.copy(),
            "masks_read_only": True,
            "native_dicom_required": True,
        },
        "limitations": LIMITATIONS.copy(),
    }
    return context, {
        "baseline": baseline_data["mask"],
        "followup": followup_data["mask"],
    }


def lesion_volume_comparison_display_agent_summary(
    context: dict[str, Any] | None,
    *,
    configured: bool,
    error: str | None = None,
) -> dict[str, Any]:
    if context is None:
        return {
            "schema_version": "1.0.0",
            "artifact_type": "lesion_volume_native_boundary_display_summary",
            "available": False,
            "configured": configured,
            "display_status": "invalid" if configured else "unavailable",
            "source_validated": False,
            "browser_session_required_for_pixels": False,
            "external_api_required": False,
            "spatial_overlay": False,
            "voxelwise_change_localization": False,
            "response_classification": False,
            "errors": [error] if error else [],
        }
    comparison = context["comparison"]
    return {
        "schema_version": "1.0.0",
        "artifact_type": "lesion_volume_native_boundary_display_summary",
        "available": True,
        "configured": True,
        "display_status": context["display_status"],
        "source_validated": True,
        "comparison_id": context["comparison_id"],
        "modality": context["timepoints"]["baseline"]["modality"],
        "baseline_reviewed_volume_ml": comparison["baseline_volume_ml"],
        "followup_reviewed_volume_ml": comparison["followup_volume_ml"],
        "absolute_volume_change_ml": comparison["absolute_change_ml"],
        "percent_volume_change": comparison["percent_change"],
        "numeric_direction": comparison["numeric_direction"],
        "elapsed_days": comparison["elapsed_days"],
        "native_spaces": 2,
        "registered": False,
        "normalized_navigation_available": True,
        "browser_session_required_for_pixels": False,
        "external_api_required": False,
        "spatial_overlay": False,
        "voxelwise_change_localization": False,
        "causal_treatment_attribution": False,
        "response_classification": False,
        "diagnosis": False,
        "clinical_conclusion": False,
        "errors": [],
    }
