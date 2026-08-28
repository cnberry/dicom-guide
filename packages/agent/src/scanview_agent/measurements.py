from __future__ import annotations

import math
import re
from datetime import datetime
from typing import Any


OPAQUE_ID = re.compile(r"^[0-9a-f]{16}$")


def _has_only_keys(value: dict[str, Any], allowed: set[str]) -> bool:
    return not (set(value) - allowed)


def validate_measurement_packet(packet: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(packet, dict):
        return ["packet must be a JSON object"]
    if not _has_only_keys(
        packet,
        {"schema_version", "created_at", "review_status", "measurements", "limitations"},
    ):
        errors.append("packet contains unsupported fields")
    if packet.get("schema_version") != "1.0.0":
        errors.append("schema_version must be 1.0.0")
    if packet.get("review_status") != "unreviewed":
        errors.append("review_status must be unreviewed")
    if not isinstance(packet.get("created_at"), str) or not packet["created_at"]:
        errors.append("created_at must be a non-empty string")
    else:
        try:
            datetime.fromisoformat(packet["created_at"].replace("Z", "+00:00"))
        except ValueError:
            errors.append("created_at must be an ISO 8601 date-time")
    limitations = packet.get("limitations")
    if not isinstance(limitations, list) or not limitations or not all(
        isinstance(item, str) and item for item in limitations
    ):
        errors.append("limitations must be a non-empty string array")

    measurements = packet.get("measurements")
    if not isinstance(measurements, list):
        errors.append("measurements must be an array")
        return errors
    tracking_ids: set[str] = set()
    for index, measurement in enumerate(measurements):
        prefix = f"measurements[{index}]"
        if not isinstance(measurement, dict):
            errors.append(f"{prefix} must be an object")
            continue
        if not _has_only_keys(
            measurement,
            {
                "tracking_id",
                "type",
                "review_status",
                "source",
                "geometry",
                "result",
                "method",
                "limitations",
            },
        ):
            errors.append(f"{prefix} contains unsupported fields")
        if measurement.get("type") != "length":
            errors.append(f"{prefix}.type must be length")
        if measurement.get("review_status") != "unreviewed":
            errors.append(f"{prefix}.review_status must be unreviewed")
        if not isinstance(measurement.get("tracking_id"), str) or not measurement["tracking_id"]:
            errors.append(f"{prefix}.tracking_id must be a non-empty string")
        elif measurement["tracking_id"] in tracking_ids:
            errors.append(f"{prefix}.tracking_id must be unique")
        else:
            tracking_ids.add(measurement["tracking_id"])
        source = measurement.get("source")
        if not isinstance(source, dict):
            errors.append(f"{prefix}.source must be an object")
        else:
            if not _has_only_keys(
                source, {"series_id", "instance_id", "frame_of_reference_id"}
            ):
                errors.append(f"{prefix}.source contains unsupported fields")
            for key in ("series_id", "instance_id"):
                if not isinstance(source.get(key), str) or not OPAQUE_ID.fullmatch(source[key]):
                    errors.append(f"{prefix}.source.{key} must be a 16-character opaque ID")
            frame = source.get("frame_of_reference_id")
            if frame is not None and (not isinstance(frame, str) or not OPAQUE_ID.fullmatch(frame)):
                errors.append(
                    f"{prefix}.source.frame_of_reference_id must be a 16-character opaque ID"
                )
        geometry = measurement.get("geometry")
        if not isinstance(geometry, dict) or geometry.get("coordinate_system") != "DICOM patient LPS":
            errors.append(f"{prefix}.geometry must use DICOM patient LPS")
        else:
            if not _has_only_keys(geometry, {"coordinate_system", "world_points"}):
                errors.append(f"{prefix}.geometry contains unsupported fields")
            points = geometry.get("world_points")
            if not (
                isinstance(points, list)
                and len(points) == 2
                and all(
                    isinstance(point, list)
                    and len(point) == 3
                    and all(
                        isinstance(value, (int, float))
                        and not isinstance(value, bool)
                        and math.isfinite(value)
                        for value in point
                    )
                    for point in points
                )
            ):
                errors.append(f"{prefix}.geometry.world_points must contain two finite 3D points")
        result = measurement.get("result")
        if not isinstance(result, dict) or result.get("unit") not in {"mm", "unknown"}:
            errors.append(f"{prefix}.result.unit must be mm or unknown")
        else:
            if not _has_only_keys(result, {"value", "unit"}):
                errors.append(f"{prefix}.result contains unsupported fields")
            if result.get("unit") == "mm" and (
                not isinstance(result.get("value"), (int, float))
                or isinstance(result.get("value"), bool)
                or not math.isfinite(result["value"])
                or result["value"] < 0
            ):
                errors.append(f"{prefix}.result.value must be a non-negative finite number for mm")
        method = measurement.get("method")
        if not isinstance(method, dict) or method.get("name") != "manual_two_point_length":
            errors.append(f"{prefix}.method.name must be manual_two_point_length")
        else:
            if not _has_only_keys(method, {"name", "implementation"}):
                errors.append(f"{prefix}.method contains unsupported fields")
            if method.get("implementation") != "Cornerstone3D LengthTool":
                errors.append(f"{prefix}.method.implementation is unsupported")
        measurement_limitations = measurement.get("limitations")
        if not isinstance(measurement_limitations, list) or not measurement_limitations or not all(
            isinstance(item, str) and item for item in measurement_limitations
        ):
            errors.append(f"{prefix}.limitations must be a non-empty string array")
    return errors


def measurement_packet_summary(packet: Any) -> dict[str, Any]:
    errors = validate_measurement_packet(packet)
    measurements = packet.get("measurements", []) if isinstance(packet, dict) else []
    return {
        "valid": not errors,
        "schema_version": packet.get("schema_version") if isinstance(packet, dict) else None,
        "review_status": packet.get("review_status") if isinstance(packet, dict) else None,
        "measurement_count": len(measurements) if isinstance(measurements, list) else 0,
        "errors": errors,
    }
