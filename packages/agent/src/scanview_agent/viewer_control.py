from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Any


SCHEMA_VERSION = "1.0.0"
MEDIA_TYPE = "application/vnd.scanview.viewer-control+json"
MAX_REQUEST_BYTES = 8 * 1024
OBSERVATION_TTL_SECONDS = 5.0

COMMAND_ID = re.compile(r"^control_[0-9a-f]{32}$")
SERIES_ID = re.compile(r"^series_[0-9a-f]{20}$")
INSTANCE_ID = re.compile(r"^instance_[0-9a-f]{20}$")
VIEW_TOOLS = {
    "native": {"window", "pan", "zoom"},
    "mpr": {"crosshairs", "window", "pan", "zoom", "crop"},
}

PERMISSIONS = {
    "agent_view_navigation_authorized": True,
    "agent_display_tool_control_authorized": True,
    "agent_patient_point_control_authorized": True,
    "source_mutation_authorized": False,
    "measurement_creation_authorized": False,
    "diagnosis_authorized": False,
    "response_classification_authorized": False,
    "clinical_conclusion_authorized": False,
}

PRIVACY = {
    "local_only": True,
    "sensitive": True,
    "contains_pixels": False,
    "contains_direct_identifiers": False,
    "contains_source_text": False,
    "contains_opaque_source_references": True,
    "contains_patient_coordinates": True,
    "deidentified": False,
    "persisted": False,
}


def _exact(value: Any, fields: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(f"{label} has unsupported or missing fields")
    return value


def _catalog_index(catalog: dict[str, Any]) -> dict[str, list[str]]:
    if (
        not isinstance(catalog, dict)
        or catalog.get("schema_version") != "1.0.0"
        or not isinstance(catalog.get("studies"), list)
    ):
        raise ValueError("viewer control requires a ScanView manifest v1 catalog")
    result: dict[str, list[str]] = {}
    for study in catalog["studies"]:
        if not isinstance(study, dict) or not isinstance(study.get("series"), list):
            continue
        for series in study["series"]:
            if (
                not isinstance(series, dict)
                or series.get("modality") not in {"MR", "CT"}
                or not isinstance(series.get("id"), str)
                or not SERIES_ID.fullmatch(series["id"])
                or not isinstance(series.get("instances"), list)
            ):
                continue
            instances = [
                item["id"]
                for item in series["instances"]
                if isinstance(item, dict)
                and isinstance(item.get("id"), str)
                and INSTANCE_ID.fullmatch(item["id"])
            ]
            if instances:
                result[series["id"]] = instances
    return result


def _patient_point(value: Any) -> list[float] | None:
    if value is None:
        return None
    if (
        not isinstance(value, list)
        or len(value) != 3
        or any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in value)
    ):
        raise ValueError("patient point must contain exactly three finite LPS coordinates")
    point = [float(item) for item in value]
    if not all(math.isfinite(item) and abs(item) <= 1_000_000 for item in point):
        raise ValueError("patient point must contain exactly three finite LPS coordinates")
    return point


def _target(
    series_id: Any,
    instance_id: Any,
    stack_position: Any,
    stack_count: Any,
    catalog_index: dict[str, list[str]],
) -> tuple[str, str, int, int]:
    if not isinstance(series_id, str) or not SERIES_ID.fullmatch(series_id):
        raise ValueError("viewer control series ID is invalid")
    if not isinstance(instance_id, str) or not INSTANCE_ID.fullmatch(instance_id):
        raise ValueError("viewer control instance ID is invalid")
    instances = catalog_index.get(series_id)
    if instances is None or instance_id not in instances:
        raise ValueError("viewer control instance does not belong to its series")
    expected_position = instances.index(instance_id) + 1
    if stack_position is not None and (
        type(stack_position) is not int or stack_position != expected_position
    ):
        raise ValueError("viewer control stack position is not exact")
    if stack_count is not None and (
        type(stack_count) is not int or stack_count != len(instances)
    ):
        raise ValueError("viewer control stack count is not exact")
    return series_id, instance_id, expected_position, len(instances)


def validate_command(value: Any, catalog: dict[str, Any]) -> dict[str, Any]:
    command = _exact(
        value,
        {
            "schema_version",
            "command_id",
            "view_mode",
            "series_id",
            "instance_id",
            "tool",
            "patient_point_lps_mm",
            "reset_view",
        },
        "viewer control command",
    )
    if command["schema_version"] != SCHEMA_VERSION:
        raise ValueError("viewer control schema version is unsupported")
    if not isinstance(command["command_id"], str) or not COMMAND_ID.fullmatch(
        command["command_id"]
    ):
        raise ValueError("viewer control command ID is invalid")
    view_mode = command["view_mode"]
    if view_mode not in VIEW_TOOLS or command["tool"] not in VIEW_TOOLS[view_mode]:
        raise ValueError("viewer control view mode or tool is unsupported")
    series_id, instance_id, _, _ = _target(
        command["series_id"],
        command["instance_id"],
        None,
        None,
        _catalog_index(catalog),
    )
    if type(command["reset_view"]) is not bool:
        raise ValueError("viewer control reset flag is invalid")
    return {
        **command,
        "series_id": series_id,
        "instance_id": instance_id,
        "patient_point_lps_mm": _patient_point(command["patient_point_lps_mm"]),
    }


def validate_observation(
    value: Any,
    catalog: dict[str, Any],
    *,
    current_command: dict[str, Any] | None,
) -> dict[str, Any]:
    observation = _exact(
        value,
        {
            "schema_version",
            "applied_command_id",
            "applied_revision",
            "interaction_source",
            "render_status",
            "view_mode",
            "series_id",
            "instance_id",
            "stack_position",
            "stack_count",
            "tool",
            "patient_point_lps_mm",
            "point_pinned",
            "permissions",
            "privacy",
        },
        "viewer control observation",
    )
    if observation["schema_version"] != SCHEMA_VERSION:
        raise ValueError("viewer control observation version is unsupported")
    if observation["interaction_source"] not in {"person", "agent"}:
        raise ValueError("viewer control interaction source is unsupported")
    if observation["render_status"] not in {"loading", "ready", "error"}:
        raise ValueError("viewer control render status is unsupported")
    view_mode = observation["view_mode"]
    if view_mode not in VIEW_TOOLS or observation["tool"] not in VIEW_TOOLS[view_mode]:
        raise ValueError("viewer control observation tool is unsupported")
    series_id, instance_id, stack_position, stack_count = _target(
        observation["series_id"],
        observation["instance_id"],
        observation["stack_position"],
        observation["stack_count"],
        _catalog_index(catalog),
    )
    command_id = observation["applied_command_id"]
    revision = observation["applied_revision"]
    if command_id is None:
        if revision != 0 or observation["interaction_source"] != "person":
            raise ValueError("manual viewer observation has invalid command provenance")
    else:
        if (
            not isinstance(command_id, str)
            or not COMMAND_ID.fullmatch(command_id)
            or type(revision) is not int
            or revision < 1
            or observation["interaction_source"] != "agent"
            or current_command is None
            or current_command.get("command_id") != command_id
            or current_command.get("revision") != revision
        ):
            raise ValueError("viewer observation does not match the current agent command")
        if (
            observation["view_mode"] != current_command["view_mode"]
            or series_id != current_command["series_id"]
            or observation["tool"] != current_command["tool"]
        ):
            raise ValueError("viewer observation did not apply the current agent target")
        if (
            observation["view_mode"] == "native"
            and instance_id != current_command["instance_id"]
        ):
            raise ValueError("native viewer observation did not apply the requested instance")
    point = _patient_point(observation["patient_point_lps_mm"])
    if command_id is not None and current_command is not None:
        requested_point = current_command["patient_point_lps_mm"]
        if requested_point is not None and (
            point is None
            or any(abs(point[axis] - requested_point[axis]) > 0.001 for axis in range(3))
        ):
            raise ValueError("viewer observation did not apply the requested patient point")
    if type(observation["point_pinned"]) is not bool or observation["point_pinned"] != (
        point is not None
    ):
        raise ValueError("viewer control point-pinned flag is invalid")
    if observation["permissions"] != PERMISSIONS or observation["privacy"] != PRIVACY:
        raise ValueError("viewer control safety declarations are invalid")
    return {
        **observation,
        "series_id": series_id,
        "instance_id": instance_id,
        "stack_position": stack_position,
        "stack_count": stack_count,
        "patient_point_lps_mm": point,
        "permissions": dict(PERMISSIONS),
        "privacy": dict(PRIVACY),
    }


def response(
    *,
    command: dict[str, Any] | None,
    observation: dict[str, Any] | None,
    observation_age_seconds: float | None,
) -> dict[str, Any]:
    connected = bool(
        observation is not None
        and observation_age_seconds is not None
        and 0 <= observation_age_seconds <= OBSERVATION_TTL_SECONDS
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "viewer_connected": connected,
        "observation_age_seconds": (
            round(max(0.0, observation_age_seconds), 3)
            if observation_age_seconds is not None
            else None
        ),
        "command": command,
        "observation": observation if connected else None,
        "permissions": dict(PERMISSIONS),
        "privacy": dict(PRIVACY),
    }


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
