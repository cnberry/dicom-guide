from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Any


SCHEMA_VERSION = "1.0.0"
MEDIA_TYPE = "application/vnd.dicom-guide.viewer-control+json"
MAX_REQUEST_BYTES = 128 * 1024
OBSERVATION_TTL_SECONDS = 5.0

COMMAND_ID = re.compile(r"^control_[0-9a-f]{32}$")
SERIES_ID = re.compile(r"^series_[0-9a-f]{20}$")
INSTANCE_ID = re.compile(r"^instance_[0-9a-f]{20}$")
MARK_ID = re.compile(r"^mark_[0-9a-f]{20}$")
VIEWER_ID = re.compile(r"^viewer_[0-9a-f]{20}$")
DISCUSSION_MARK_COLORS = {"yellow", "cyan", "violet", "green"}
MAX_DISCUSSION_MARKS = 256
MAX_DISCUSSION_MARK_POINTS = 64
VIEW_TOOLS = {
    "native": {"window", "pan", "zoom", "highlight"},
    "mpr": {"crosshairs", "window", "pan", "zoom", "highlight"},
}

PERMISSIONS = {
    "agent_view_navigation_authorized": True,
    "agent_display_tool_control_authorized": True,
    "agent_patient_point_control_authorized": True,
    "agent_discussion_overlay_control_authorized": True,
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
        raise ValueError("viewer control requires a DICOM Guide manifest v1 catalog")
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


def _catalog_geometry(
    catalog: dict[str, Any], series_id: str, instance_id: str
) -> dict[str, Any]:
    for study in catalog.get("studies", []):
        for series in study.get("series", []) if isinstance(study, dict) else []:
            if not isinstance(series, dict) or series.get("id") != series_id:
                continue
            for instance in series.get("instances", []):
                if isinstance(instance, dict) and instance.get("id") == instance_id:
                    geometry = dict(series)
                    geometry.update(
                        {key: value for key, value in instance.items() if value is not None}
                    )
                    return geometry
    raise ValueError("viewer control image geometry is unavailable")


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


def _discussion_marks(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) > MAX_DISCUSSION_MARKS:
        raise ValueError("discussion marks exceed the local overlay limit")
    result = []
    for mark in value:
        mark = _exact(
            mark,
            {"id", "orientation", "color", "author", "points_lps_mm"},
            "discussion mark",
        )
        if not isinstance(mark["id"], str) or not MARK_ID.fullmatch(mark["id"]):
            raise ValueError("discussion mark ID is invalid")
        if mark["orientation"] not in {"axial", "coronal", "sagittal"}:
            raise ValueError("discussion mark orientation is invalid")
        if mark["color"] not in DISCUSSION_MARK_COLORS:
            raise ValueError("discussion mark color is invalid")
        if mark["author"] not in {"person", "agent"}:
            raise ValueError("discussion mark author is invalid")
        points = mark["points_lps_mm"]
        if (
            not isinstance(points, list)
            or not 1 <= len(points) <= MAX_DISCUSSION_MARK_POINTS
        ):
            raise ValueError("discussion mark points are invalid")
        parsed_points = [_patient_point(point) for point in points]
        if any(point is None for point in parsed_points):
            raise ValueError("discussion mark points are invalid")
        result.append({**mark, "points_lps_mm": parsed_points})
    if len({mark["id"] for mark in result}) != len(result):
        raise ValueError("discussion mark IDs must be unique")
    return result


def _finite_numbers(value: Any, length: int, label: str) -> list[float]:
    if (
        not isinstance(value, list)
        or len(value) != length
        or any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in value)
    ):
        raise ValueError(f"{label} is invalid")
    result = [float(item) for item in value]
    if not all(math.isfinite(item) for item in result):
        raise ValueError(f"{label} is invalid")
    return result


def _orientation_from_iop(value: list[float]) -> str:
    row = value[:3]
    column = value[3:]
    normal = [
        row[1] * column[2] - row[2] * column[1],
        row[2] * column[0] - row[0] * column[2],
        row[0] * column[1] - row[1] * column[0],
    ]
    axis = max(range(3), key=lambda index: abs(normal[index]))
    return ("sagittal", "coronal", "axial")[axis]


def _image_points_to_lps(
    points: Any,
    *,
    catalog: dict[str, Any],
    series_id: str,
    instance_id: str,
) -> tuple[str, list[list[float]]]:
    if (
        not isinstance(points, list)
        or not 1 <= len(points) <= MAX_DISCUSSION_MARK_POINTS
    ):
        raise ValueError("discussion mark image points are invalid")
    geometry = _catalog_geometry(catalog, series_id, instance_id)
    position = _finite_numbers(geometry.get("image_position_patient"), 3, "image position")
    iop = _finite_numbers(geometry.get("image_orientation_patient"), 6, "image orientation")
    spacing = _finite_numbers(geometry.get("pixel_spacing"), 2, "pixel spacing")
    rows = geometry.get("rows")
    columns = geometry.get("columns")
    if (
        type(rows) is not int
        or type(columns) is not int
        or rows < 2
        or columns < 2
        or any(value <= 0 for value in spacing)
    ):
        raise ValueError("source image dimensions are invalid")
    resolved = []
    for value in points:
        column_index, row_index = _finite_numbers(
            value, 2, "discussion mark image point"
        )
        if not (0 <= column_index <= columns - 1 and 0 <= row_index <= rows - 1):
            raise ValueError("discussion mark image point is outside the source image")
        resolved.append(
            [
                position[axis]
                + column_index * spacing[1] * iop[axis]
                + row_index * spacing[0] * iop[axis + 3]
                for axis in range(3)
            ]
        )
    return _orientation_from_iop(iop), resolved


def _normalized_image_points_to_lps(
    points: Any,
    *,
    catalog: dict[str, Any],
    series_id: str,
    instance_id: str,
) -> tuple[str, list[list[float]]]:
    geometry = _catalog_geometry(catalog, series_id, instance_id)
    rows = geometry.get("rows")
    columns = geometry.get("columns")
    if type(rows) is not int or type(columns) is not int or rows < 2 or columns < 2:
        raise ValueError("source image dimensions are invalid")
    if not isinstance(points, list):
        raise ValueError("discussion mark normalized image points are invalid")
    image_points = []
    for value in points:
        horizontal, vertical = _finite_numbers(
            value, 2, "discussion mark normalized image point"
        )
        if not (0 <= horizontal <= 1 and 0 <= vertical <= 1):
            raise ValueError("discussion mark normalized image point is outside the image")
        image_points.append(
            [horizontal * (columns - 1), vertical * (rows - 1)]
        )
    return _image_points_to_lps(
        image_points,
        catalog=catalog,
        series_id=series_id,
        instance_id=instance_id,
    )


def _discussion_marks_patch(
    value: Any,
    *,
    catalog: dict[str, Any],
    series_id: str,
    instance_id: str,
) -> dict[str, Any]:
    allowed = {"add", "remove_ids", "clear_agent"}
    if not isinstance(value, dict) or not value or not set(value).issubset(allowed):
        raise ValueError("discussion marks patch has unsupported or missing fields")
    additions = value.get("add", [])
    removals = value.get("remove_ids", [])
    clear_agent = value.get("clear_agent", False)
    if type(clear_agent) is not bool:
        raise ValueError("discussion marks clear flag is invalid")
    if not isinstance(removals, list) or any(
        not isinstance(mark_id, str) or not MARK_ID.fullmatch(mark_id)
        for mark_id in removals
    ):
        raise ValueError("discussion mark removal IDs are invalid")
    if len(set(removals)) != len(removals):
        raise ValueError("discussion mark removal IDs must be unique")
    if not isinstance(additions, list) or len(additions) > MAX_DISCUSSION_MARKS:
        raise ValueError("discussion mark additions exceed the local overlay limit")
    parsed_additions = []
    for addition in additions:
        if not isinstance(addition, dict):
            raise ValueError("discussion mark addition is invalid")
        common = {"id", "color"}
        lps_fields = common | {"orientation", "points_lps_mm"}
        image_fields = common | {"points_image_px"}
        normalized_image_fields = common | {"points_image_normalized"}
        if set(addition) == lps_fields:
            mark = _discussion_marks([{**addition, "author": "agent"}])[0]
        elif set(addition) == image_fields:
            orientation, points_lps = _image_points_to_lps(
                addition["points_image_px"],
                catalog=catalog,
                series_id=series_id,
                instance_id=instance_id,
            )
            mark = _discussion_marks(
                [
                    {
                        "id": addition["id"],
                        "orientation": orientation,
                        "color": addition["color"],
                        "author": "agent",
                        "points_lps_mm": points_lps,
                    }
                ]
            )[0]
        elif set(addition) == normalized_image_fields:
            orientation, points_lps = _normalized_image_points_to_lps(
                addition["points_image_normalized"],
                catalog=catalog,
                series_id=series_id,
                instance_id=instance_id,
            )
            mark = _discussion_marks(
                [
                    {
                        "id": addition["id"],
                        "orientation": orientation,
                        "color": addition["color"],
                        "author": "agent",
                        "points_lps_mm": points_lps,
                    }
                ]
            )[0]
        else:
            raise ValueError("discussion mark addition has unsupported or missing fields")
        parsed_additions.append(mark)
    if len({mark["id"] for mark in parsed_additions}) != len(parsed_additions):
        raise ValueError("discussion mark addition IDs must be unique")
    return {
        "add": parsed_additions,
        "remove_ids": removals,
        "clear_agent": clear_agent,
    }


def apply_discussion_marks_patch(
    current: list[dict[str, Any]], patch: dict[str, Any]
) -> list[dict[str, Any]]:
    removals = set(patch["remove_ids"])
    result = [
        mark
        for mark in current
        if not (
            mark["author"] == "agent"
            and (patch["clear_agent"] or mark["id"] in removals)
        )
    ]
    person_ids = {mark["id"] for mark in result if mark["author"] == "person"}
    if person_ids.intersection(mark["id"] for mark in patch["add"]):
        raise ValueError("agent highlight ID conflicts with a person highlight")
    addition_ids = {mark["id"] for mark in patch["add"]}
    result = [
        mark
        for mark in result
        if not (mark["author"] == "agent" and mark["id"] in addition_ids)
    ]
    result.extend(patch["add"])
    if len(result) > MAX_DISCUSSION_MARKS:
        raise ValueError("discussion marks exceed the local overlay limit")
    return result


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
    required_fields = {
        "schema_version",
        "command_id",
        "view_mode",
        "series_id",
        "instance_id",
        "tool",
        "patient_point_lps_mm",
        "reset_view",
    }
    if (
        not isinstance(value, dict)
        or not required_fields.issubset(value)
        or not set(value).issubset(
            required_fields | {"discussion_marks_patch", "target_viewer_id"}
        )
    ):
        raise ValueError("viewer control command has unsupported or missing fields")
    command = value
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
    target_viewer_id = command.get("target_viewer_id")
    if target_viewer_id is not None and (
        not isinstance(target_viewer_id, str)
        or not VIEWER_ID.fullmatch(target_viewer_id)
    ):
        raise ValueError("target viewer ID is invalid")
    patch = (
        _discussion_marks_patch(
            command["discussion_marks_patch"],
            catalog=catalog,
            series_id=series_id,
            instance_id=instance_id,
        )
        if "discussion_marks_patch" in command
        else None
    )
    return {
        **command,
        "series_id": series_id,
        "instance_id": instance_id,
        "patient_point_lps_mm": _patient_point(command["patient_point_lps_mm"]),
        **(
            {"target_viewer_id": target_viewer_id}
            if target_viewer_id is not None
            else {}
        ),
        **({"discussion_marks_patch": patch} if patch is not None else {}),
    }


def validate_observation(
    value: Any,
    catalog: dict[str, Any],
    *,
    current_command: dict[str, Any] | None,
) -> dict[str, Any]:
    required_fields = {
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
        "viewer_id",
    }
    if (
        not isinstance(value, dict)
        or not required_fields.issubset(value)
        or not set(value).issubset(required_fields | {"discussion_marks"})
    ):
        raise ValueError("viewer control observation has unsupported or missing fields")
    observation = value
    if observation["schema_version"] != SCHEMA_VERSION:
        raise ValueError("viewer control observation version is unsupported")
    if not isinstance(observation["viewer_id"], str) or not VIEWER_ID.fullmatch(
        observation["viewer_id"]
    ):
        raise ValueError("viewer control observation viewer ID is invalid")
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
            current_command.get("target_viewer_id") is not None
            and observation["viewer_id"] != current_command["target_viewer_id"]
        ):
            raise ValueError("viewer observation came from a non-target viewer")
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
    marks = _discussion_marks(observation.get("discussion_marks", []))
    if command_id is not None and current_command is not None:
        requested_point = current_command["patient_point_lps_mm"]
        if requested_point is not None and (
            point is None
            or any(abs(point[axis] - requested_point[axis]) > 0.001 for axis in range(3))
        ):
            raise ValueError("viewer observation did not apply the requested patient point")
        requested_marks = current_command.get("discussion_marks")
        if requested_marks is not None and marks != requested_marks:
            raise ValueError("viewer observation did not apply the requested discussion marks")
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
        "discussion_marks": marks,
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
