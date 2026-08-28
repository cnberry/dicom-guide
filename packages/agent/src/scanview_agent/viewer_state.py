from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any


VIEWER_STATE_MEDIA_TYPE = "application/vnd.scanview.viewer-state+json"
MAX_VIEWER_STATE_BYTES = 16 * 1024
VIEWER_STATE_TTL_SECONDS = 30.0
PUBLISHER_ID = re.compile(r"^publisher_[0-9a-f]{32}$")
SERIES_ID = re.compile(r"^series_[0-9a-f]{20}$")
INSTANCE_ID = re.compile(r"^instance_[0-9a-f]{20}$")
ACTIVE_TOOLS = {"window", "pan", "zoom", "length", "bidirectional", "roi"}
SLICE_LINKS = {"unpaired", "independent", "patient_position", "approximate_index"}


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
        raise ValueError("viewer state requires a ScanView manifest v1 catalog")
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


def validate_viewer_state(value: Any, catalog: dict[str, Any]) -> dict[str, Any]:
    state = _exact_keys(
        value,
        {
            "schema_version",
            "sharing",
            "publisher_id",
            "review_status",
            "active_tool",
            "slice_link",
            "baseline",
            "followup",
            "mpr_series_id",
            "measurement_count",
            "comparison_draft_present",
            "privacy",
        },
        "viewer state",
    )
    if state["schema_version"] != "1.0.0" or state["sharing"] is not True:
        raise ValueError("viewer state version or sharing flag is unsupported")
    publisher_id = state["publisher_id"]
    if not isinstance(publisher_id, str) or not PUBLISHER_ID.fullmatch(publisher_id):
        raise ValueError("viewer state publisher ID is invalid")
    if state["review_status"] != "unreviewed":
        raise ValueError("viewer state must remain unreviewed")
    if state["active_tool"] not in ACTIVE_TOOLS:
        raise ValueError("viewer state active tool is unsupported")
    if state["slice_link"] not in SLICE_LINKS:
        raise ValueError("viewer state slice-link state is unsupported")

    catalog_index = _catalog_index(catalog)
    baseline = _target(state["baseline"], role="baseline", catalog_index=catalog_index)
    followup = _target(state["followup"], role="follow-up", catalog_index=catalog_index)
    expected_links = (
        {"unpaired"}
        if baseline is None or followup is None
        else {"independent", "patient_position", "approximate_index"}
    )
    if state["slice_link"] not in expected_links:
        raise ValueError("viewer state slice-link state disagrees with the selected panes")

    mpr_series_id = state["mpr_series_id"]
    if mpr_series_id is not None and (
        not isinstance(mpr_series_id, str) or mpr_series_id not in catalog_index
    ):
        raise ValueError("viewer state MPR series is not in the renderable local catalog")
    measurement_count = state["measurement_count"]
    if (
        not isinstance(measurement_count, int)
        or isinstance(measurement_count, bool)
        or not 0 <= measurement_count <= 10_000
    ):
        raise ValueError("viewer state measurement count is invalid")
    if not isinstance(state["comparison_draft_present"], bool):
        raise ValueError("viewer state comparison flag is invalid")
    privacy = _exact_keys(
        state["privacy"],
        {
            "local_only",
            "contains_pixels",
            "contains_direct_identifiers",
            "persisted",
        },
        "viewer state privacy",
    )
    if privacy != {
        "local_only": True,
        "contains_pixels": False,
        "contains_direct_identifiers": False,
        "persisted": False,
    }:
        raise ValueError("viewer state privacy declaration is invalid")
    return {
        **state,
        "baseline": baseline,
        "followup": followup,
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
        value.get("schema_version") == "1.0.0"
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
        "schema_version": "1.0.0",
        "available": True,
        "received_at": received_at,
        "age_seconds": round(age, 3),
        "expires_in_seconds": round(remaining, 3),
        "state": state,
    }


def unavailable_viewer_state_response(reason: str) -> dict[str, Any]:
    if reason not in {"not_shared", "stale"}:
        raise ValueError("viewer state unavailability reason is unsupported")
    return {
        "schema_version": "1.0.0",
        "available": False,
        "reason": reason,
        "expires_after_seconds": int(VIEWER_STATE_TTL_SECONDS),
    }


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
