from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any


VIEWER_STATE_MEDIA_TYPE = "application/vnd.dicom-guide.viewer-state+json"
SCHEMA_VERSION = "2.0.0"
MAX_VIEWER_STATE_BYTES = 16 * 1024
VIEWER_STATE_TTL_SECONDS = 30.0
PUBLISHER_ID = re.compile(r"^publisher_[0-9a-f]{32}$")
SERIES_ID = re.compile(r"^series_[0-9a-f]{20}$")
INSTANCE_ID = re.compile(r"^instance_[0-9a-f]{20}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
ACTIVE_TOOLS = {"window", "pan", "zoom", "length", "bidirectional", "roi"}
SLICE_LINKS = {"unpaired", "independent", "patient_position", "approximate_index"}
WORKSPACE_MODES = {"consult_prep", "longitudinal_review"}

VIEWER_STATE_PERMISSIONS = {
    "agent_navigation_from_state_authorized": False,
    "source_mutation_authorized": False,
    "source_segmentation_mask_read_authorized": False,
    "source_segmentation_interpretation_authorized": False,
    "diagnosis_authorized": False,
    "response_classification_authorized": False,
    "clinical_conclusion_authorized": False,
}


def _exact_keys(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"{label} has unsupported or missing fields")
    return value


def _catalog_index(catalog: dict[str, Any]) -> dict[str, list[str]]:
    if (
        not isinstance(catalog, dict)
        or catalog.get("schema_version") != "1.0.0"
        or not isinstance(catalog.get("studies"), list)
    ):
        raise ValueError("viewer state requires a DICOM Guide manifest v1 catalog")
    result: dict[str, list[str]] = {}
    for study in catalog["studies"]:
        if not isinstance(study, dict) or not isinstance(study.get("series"), list):
            continue
        for series in study["series"]:
            if (
                not isinstance(series, dict)
                or not SERIES_ID.fullmatch(str(series.get("id", "")))
                or series.get("modality") not in {"MR", "CT"}
                or not isinstance(series.get("instances"), list)
            ):
                continue
            instance_ids = [
                instance["id"]
                for instance in series["instances"]
                if isinstance(instance, dict)
                and INSTANCE_ID.fullmatch(str(instance.get("id", "")))
            ]
            if instance_ids:
                result[series["id"]] = instance_ids
    return result


def _target(
    value: Any,
    *,
    role: str,
    catalog_index: dict[str, list[str]],
) -> dict[str, Any] | None:
    if value is None:
        return None
    target = _exact_keys(
        value,
        {"series_id", "instance_id", "stack_position", "stack_count"},
        f"{role} target",
    )
    series_id = target["series_id"]
    instance_id = target["instance_id"]
    stack_position = target["stack_position"]
    stack_count = target["stack_count"]
    if not isinstance(series_id, str) or not SERIES_ID.fullmatch(series_id):
        raise ValueError(f"{role} target has an invalid opaque series ID")
    if not isinstance(instance_id, str) or not INSTANCE_ID.fullmatch(instance_id):
        raise ValueError(f"{role} target has an invalid opaque instance ID")
    instances = catalog_index.get(series_id)
    if instances is None:
        raise ValueError(f"{role} target series is not in the renderable local catalog")
    if (
        not isinstance(stack_count, int)
        or isinstance(stack_count, bool)
        or stack_count != len(instances)
    ):
        raise ValueError(f"{role} target stack count disagrees with the local catalog")
    if (
        not isinstance(stack_position, int)
        or isinstance(stack_position, bool)
        or not 1 <= stack_position <= stack_count
        or instances[stack_position - 1] != instance_id
    ):
        raise ValueError(f"{role} target position does not match its exact local instance")
    return dict(target)


def _source_segmentation_display(
    value: Any,
    *,
    source_segmentation_catalog: dict[str, Any] | None,
    mpr_series_id: str | None,
) -> dict[str, Any] | None:
    if value is None:
        return None
    display = _exact_keys(
        value,
        {
            "segmentation_id",
            "segment_number",
            "referenced_series_id",
            "catalog_content_sha256",
            "display_status",
            "mask_pixels_shared",
            "creator_identity_authenticated",
            "segment_accuracy_verified",
            "source_segment_clinical_meaning",
            "dicom_guide_interpretation_added",
        },
        "source segmentation display",
    )
    segmentation_id = display["segmentation_id"]
    segment_number = display["segment_number"]
    referenced_series_id = display["referenced_series_id"]
    catalog_hash = display["catalog_content_sha256"]
    if not isinstance(segmentation_id, str) or not INSTANCE_ID.fullmatch(segmentation_id):
        raise ValueError("source segmentation display has an invalid opaque object ID")
    if (
        not isinstance(segment_number, int)
        or isinstance(segment_number, bool)
        or not 1 <= segment_number <= 65535
    ):
        raise ValueError("source segmentation display has an invalid segment number")
    if (
        not isinstance(referenced_series_id, str)
        or not SERIES_ID.fullmatch(referenced_series_id)
    ):
        raise ValueError("source segmentation display has an invalid referenced series")
    if not isinstance(catalog_hash, str) or not SHA256.fullmatch(catalog_hash):
        raise ValueError("source segmentation display has an invalid catalog binding")
    if display["display_status"] != "read_only_native_grid":
        raise ValueError("source segmentation display status is unsupported")
    expected_locks = {
        "mask_pixels_shared": False,
        "creator_identity_authenticated": False,
        "segment_accuracy_verified": False,
        "source_segment_clinical_meaning": "not_assessed",
        "dicom_guide_interpretation_added": False,
    }
    if any(display[key] != expected for key, expected in expected_locks.items()):
        raise ValueError("source segmentation display safety declarations are invalid")
    if mpr_series_id != referenced_series_id:
        raise ValueError("source segmentation display does not match the active MPR series")
    if (
        not isinstance(source_segmentation_catalog, dict)
        or source_segmentation_catalog.get("schema_version") != "2.0.0"
        or source_segmentation_catalog.get("catalog_content_sha256") != catalog_hash
        or not isinstance(source_segmentation_catalog.get("segmentations"), list)
    ):
        raise ValueError("source segmentation display catalog is unavailable or changed")
    candidates = [
        item
        for item in source_segmentation_catalog["segmentations"]
        if isinstance(item, dict) and item.get("segmentation_id") == segmentation_id
    ]
    if len(candidates) != 1:
        raise ValueError("source segmentation display object is unavailable")
    candidate = candidates[0]
    referenced = candidate.get("referenced_series")
    segments = candidate.get("segments")
    if (
        candidate.get("display_status") != "supported_read_only"
        or not isinstance(referenced, dict)
        or referenced.get("series_id") != referenced_series_id
        or not isinstance(segments, list)
        or sum(
            isinstance(segment, dict)
            and segment.get("segment_number") == segment_number
            for segment in segments
        )
        != 1
    ):
        raise ValueError("source segmentation display does not match the guarded catalog")
    return dict(display)


def validate_viewer_state(
    value: Any,
    catalog: dict[str, Any],
    source_segmentation_catalog: dict[str, Any] | None = None,
) -> dict[str, Any]:
    state = _exact_keys(
        value,
        {
            "schema_version",
            "sharing",
            "publisher_id",
            "workspace_mode",
            "view_roles",
            "review_status",
            "active_tool",
            "slice_link",
            "view_a",
            "view_b",
            "mpr_series_id",
            "source_segmentation_display",
            "measurement_count",
            "comparison_draft_present",
            "permissions",
            "privacy",
        },
        "viewer state",
    )
    if state["schema_version"] != SCHEMA_VERSION or state["sharing"] is not True:
        raise ValueError("viewer state version or sharing flag is unsupported")
    publisher_id = state["publisher_id"]
    if not isinstance(publisher_id, str) or not PUBLISHER_ID.fullmatch(publisher_id):
        raise ValueError("viewer state publisher ID is invalid")
    if state["review_status"] != "unreviewed":
        raise ValueError("viewer state must remain unreviewed")
    workspace_mode = state["workspace_mode"]
    if not isinstance(workspace_mode, str) or workspace_mode not in WORKSPACE_MODES:
        raise ValueError("viewer state workspace mode is unsupported")
    view_roles = _exact_keys(
        state["view_roles"], {"view_a", "view_b"}, "viewer state view roles"
    )
    expected_roles = (
        {"view_a": "reference", "view_b": "reference"}
        if workspace_mode == "consult_prep"
        else {"view_a": "baseline", "view_b": "followup"}
    )
    if view_roles != expected_roles:
        raise ValueError("viewer state view roles disagree with its workspace mode")
    if (
        not isinstance(state["active_tool"], str)
        or state["active_tool"] not in ACTIVE_TOOLS
    ):
        raise ValueError("viewer state active tool is unsupported")
    if (
        not isinstance(state["slice_link"], str)
        or state["slice_link"] not in SLICE_LINKS
    ):
        raise ValueError("viewer state slice-link state is unsupported")

    catalog_index = _catalog_index(catalog)
    view_a = _target(state["view_a"], role="view A", catalog_index=catalog_index)
    view_b = _target(state["view_b"], role="view B", catalog_index=catalog_index)
    if view_a is None:
        raise ValueError("viewer state requires one exact local view A target")
    expected_links = (
        {"unpaired"}
        if view_a is None or view_b is None
        else {"independent", "patient_position", "approximate_index"}
    )
    if state["slice_link"] not in expected_links:
        raise ValueError("viewer state slice-link state disagrees with the selected panes")

    mpr_series_id = state["mpr_series_id"]
    if mpr_series_id is not None and (
        not isinstance(mpr_series_id, str) or mpr_series_id not in catalog_index
    ):
        raise ValueError("viewer state MPR series is not in the renderable local catalog")
    source_segmentation_display = _source_segmentation_display(
        state["source_segmentation_display"],
        source_segmentation_catalog=source_segmentation_catalog,
        mpr_series_id=mpr_series_id,
    )
    measurement_count = state["measurement_count"]
    if (
        not isinstance(measurement_count, int)
        or isinstance(measurement_count, bool)
        or not 0 <= measurement_count <= 10_000
    ):
        raise ValueError("viewer state measurement count is invalid")
    if not isinstance(state["comparison_draft_present"], bool):
        raise ValueError("viewer state comparison flag is invalid")
    if workspace_mode == "consult_prep" and state["comparison_draft_present"]:
        raise ValueError("Consult Prep viewer state cannot publish a comparison draft")
    permissions = _exact_keys(
        state["permissions"],
        set(VIEWER_STATE_PERMISSIONS),
        "viewer state permissions",
    )
    if permissions != VIEWER_STATE_PERMISSIONS:
        raise ValueError("viewer state permissions are invalid")
    privacy = _exact_keys(
        state["privacy"],
        {
            "local_only",
            "contains_pixels",
            "contains_direct_identifiers",
            "contains_source_text",
            "contains_measurement_values",
            "contains_segmentation_mask",
            "contains_opaque_source_references",
            "contains_sensitive_segmentation_reference",
            "contains_hashes",
            "deidentified",
            "persisted",
        },
        "viewer state privacy",
    )
    if privacy != {
        "local_only": True,
        "contains_pixels": False,
        "contains_direct_identifiers": False,
        "contains_source_text": False,
        "contains_measurement_values": False,
        "contains_segmentation_mask": False,
        "contains_opaque_source_references": True,
        "contains_sensitive_segmentation_reference": (
            source_segmentation_display is not None
        ),
        "contains_hashes": source_segmentation_display is not None,
        "deidentified": False,
        "persisted": False,
    }:
        raise ValueError("viewer state privacy declaration is invalid")
    return {
        **state,
        "view_roles": dict(view_roles),
        "view_a": view_a,
        "view_b": view_b,
        "source_segmentation_display": source_segmentation_display,
        "permissions": dict(permissions),
        "privacy": dict(privacy),
    }


def is_clear_viewer_state(value: Any) -> tuple[bool, str | None]:
    if not isinstance(value, dict) or set(value) != {
        "schema_version",
        "sharing",
        "publisher_id",
    }:
        return False, None
    publisher_id = value.get("publisher_id")
    valid = (
        value.get("schema_version") == SCHEMA_VERSION
        and value.get("sharing") is False
        and isinstance(publisher_id, str)
        and PUBLISHER_ID.fullmatch(publisher_id) is not None
    )
    return valid, publisher_id if valid else None


def available_viewer_state_response(
    state: dict[str, Any],
    *,
    received_at: str,
    age_seconds: float,
) -> dict[str, Any]:
    age = max(0.0, age_seconds)
    remaining = max(0.0, VIEWER_STATE_TTL_SECONDS - age)
    return {
        "schema_version": SCHEMA_VERSION,
        "available": True,
        "received_at": received_at,
        "age_seconds": round(age, 3),
        "expires_in_seconds": round(remaining, 3),
        "state": state,
    }


def unavailable_viewer_state_response(reason: str) -> dict[str, Any]:
    if reason not in {"not_shared", "stale", "source_changed"}:
        raise ValueError("viewer state unavailability reason is unsupported")
    return {
        "schema_version": SCHEMA_VERSION,
        "available": False,
        "reason": reason,
        "expires_after_seconds": int(VIEWER_STATE_TTL_SECONDS),
    }


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
