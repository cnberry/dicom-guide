from __future__ import annotations

import math
import re
from datetime import datetime
from datetime import timezone
from typing import Any


OPAQUE_ID = re.compile(r"^[0-9a-f]{16}$")


def _has_only_keys(value: dict[str, Any], allowed: set[str]) -> bool:
    return not (set(value) - allowed)


def _finite_nonnegative(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0
    )


def _distance(left: list[float], right: list[float]) -> float:
    return math.sqrt(sum((left[index] - right[index]) ** 2 for index in range(3)))


def _approximately_equal(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=0.001, abs_tol=0.001)


def _valid_world_points(points: Any, expected_count: int) -> bool:
    return (
        isinstance(points, list)
        and len(points) == expected_count
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
    )


def validate_measurement_packet(packet: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(packet, dict):
        return ["packet must be a JSON object"]
    if not _has_only_keys(
        packet,
        {"schema_version", "created_at", "review_status", "measurements", "limitations"},
    ):
        errors.append("packet contains unsupported fields")
    schema_version = packet.get("schema_version")
    if schema_version not in {"1.0.0", "2.0.0"}:
        errors.append("schema_version must be 1.0.0 or 2.0.0")
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
        measurement_type = measurement.get("type")
        if measurement_type not in {"length", "bidirectional"} or (
            schema_version == "1.0.0" and measurement_type != "length"
        ):
            errors.append(f"{prefix}.type is unsupported for this schema version")
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
            expected_points = 4 if measurement_type == "bidirectional" else 2
            if not _valid_world_points(points, expected_points):
                errors.append(
                    f"{prefix}.geometry.world_points must contain {expected_points} finite 3D points"
                )
        result = measurement.get("result")
        if not isinstance(result, dict) or result.get("unit") not in {"mm", "unknown"}:
            errors.append(f"{prefix}.result.unit must be mm or unknown")
        elif measurement_type == "bidirectional":
            if not _has_only_keys(
                result,
                {"long_axis", "short_axis", "product", "unit", "product_unit"},
            ):
                errors.append(f"{prefix}.result contains unsupported fields")
            physical_result = (
                result.get("unit") == "mm"
                and result.get("product_unit") == "mm2"
                and _finite_nonnegative(result.get("long_axis"))
                and _finite_nonnegative(result.get("short_axis"))
                and _finite_nonnegative(result.get("product"))
            )
            unknown_result = (
                result.get("unit") == "unknown" and result.get("product_unit") == "unknown"
            )
            if not physical_result and not unknown_result:
                errors.append(f"{prefix}.result bidirectional values are invalid")
            if unknown_result and any(
                result.get(key) is not None for key in ("long_axis", "short_axis", "product")
            ):
                errors.append(f"{prefix}.result reports values with unknown units")
            points = geometry.get("world_points") if isinstance(geometry, dict) else None
            if physical_result and _valid_world_points(points, 4):
                axes = sorted(
                    (_distance(points[0], points[1]), _distance(points[2], points[3])),
                    reverse=True,
                )
                if not (
                    _approximately_equal(result["long_axis"], axes[0])
                    and _approximately_equal(result["short_axis"], axes[1])
                    and _approximately_equal(result["product"], axes[0] * axes[1])
                ):
                    errors.append(f"{prefix}.result disagrees with its geometry")
        else:
            if not _has_only_keys(result, {"value", "unit"}):
                errors.append(f"{prefix}.result contains unsupported fields")
            if result.get("unit") == "mm" and not _finite_nonnegative(result.get("value")):
                errors.append(f"{prefix}.result.value must be a non-negative finite number for mm")
            if result.get("unit") == "unknown" and result.get("value") is not None:
                errors.append(f"{prefix}.result reports a value with unknown units")
            points = geometry.get("world_points") if isinstance(geometry, dict) else None
            if (
                result.get("unit") == "mm"
                and _finite_nonnegative(result.get("value"))
                and _valid_world_points(points, 2)
                and not _approximately_equal(result["value"], _distance(points[0], points[1]))
            ):
                errors.append(f"{prefix}.result disagrees with its geometry")
        method = measurement.get("method")
        expected_method = (
            ("manual_perpendicular_bidirectional", "Cornerstone3D BidirectionalTool")
            if measurement_type == "bidirectional"
            else ("manual_two_point_length", "Cornerstone3D LengthTool")
        )
        if not isinstance(method, dict) or method.get("name") != expected_method[0]:
            errors.append(f"{prefix}.method.name is unsupported")
        else:
            if not _has_only_keys(method, {"name", "implementation"}):
                errors.append(f"{prefix}.method contains unsupported fields")
            if method.get("implementation") != expected_method[1]:
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
    measurement_types = {"length": 0, "bidirectional": 0}
    if isinstance(measurements, list):
        for measurement in measurements:
            if isinstance(measurement, dict) and measurement.get("type") in measurement_types:
                measurement_types[measurement["type"]] += 1
    return {
        "valid": not errors,
        "schema_version": packet.get("schema_version") if isinstance(packet, dict) else None,
        "review_status": packet.get("review_status") if isinstance(packet, dict) else None,
        "measurement_count": len(measurements) if isinstance(measurements, list) else 0,
        "counts_by_type": measurement_types,
        "errors": errors,
    }


def _measurement_by_tracking_id(packet: dict[str, Any], tracking_id: str) -> dict[str, Any]:
    matches = [
        measurement
        for measurement in packet["measurements"]
        if measurement["tracking_id"] == tracking_id
    ]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one measurement with tracking ID {tracking_id!r}")
    return matches[0]


def _percent_change(baseline: float, followup: float) -> float | None:
    return None if baseline == 0 else ((followup - baseline) / baseline) * 100


def build_measurement_comparison(
    baseline_packet: dict[str, Any],
    followup_packet: dict[str, Any],
    *,
    baseline_tracking_id: str,
    followup_tracking_id: str,
) -> dict[str, Any]:
    baseline_errors = validate_measurement_packet(baseline_packet)
    followup_errors = validate_measurement_packet(followup_packet)
    if baseline_errors or followup_errors:
        raise ValueError("both measurement packets must validate before comparison")
    baseline = _measurement_by_tracking_id(baseline_packet, baseline_tracking_id)
    followup = _measurement_by_tracking_id(followup_packet, followup_tracking_id)
    if baseline["type"] != followup["type"]:
        raise ValueError("baseline and follow-up measurement types must match")
    if baseline["source"]["series_id"] == followup["source"]["series_id"]:
        raise ValueError("baseline and follow-up measurements must come from distinct source series")
    if baseline["result"]["unit"] != "mm" or followup["result"]["unit"] != "mm":
        raise ValueError("both measurements require trusted physical millimeter units")

    metrics = (
        [("length", "value", "mm")]
        if baseline["type"] == "length"
        else [
            ("long_axis", "long_axis", "mm"),
            ("short_axis", "short_axis", "mm"),
            ("bidimensional_product", "product", "mm2"),
        ]
    )
    computed_results = []
    limitations = [
        "The two measurements were paired only because the caller explicitly selected both tracking IDs.",
        "Scan compatibility, lesion identity, measurement endpoints, and tumor component remain unreviewed.",
        "Numeric change alone is not a treatment-response category.",
    ]
    for metric, key, unit in metrics:
        baseline_value = float(baseline["result"][key])
        followup_value = float(followup["result"][key])
        percent = _percent_change(baseline_value, followup_value)
        computed = {
            "metric": metric,
            "baseline": baseline_value,
            "followup": followup_value,
            "absolute_change": followup_value - baseline_value,
            "unit": unit,
            "source_measurement_ids": [baseline_tracking_id, followup_tracking_id],
            "review_status": "unreviewed",
        }
        if percent is not None:
            computed["percent_change"] = percent
        else:
            limitations.append(f"Percent change for {metric} is undefined because baseline is zero.")
        computed_results.append(computed)

    return {
        "schema_version": "1.0.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "review_status": "unreviewed",
        "pairing": {
            "method": "explicit_tracking_id_selection",
            "baseline_measurement_id": baseline_tracking_id,
            "followup_measurement_id": followup_tracking_id,
        },
        "observations": [
            {
                "timepoint": "baseline",
                "measurement_type": baseline["type"],
                "source": baseline["source"],
                "review_status": "unreviewed",
            },
            {
                "timepoint": "followup",
                "measurement_type": followup["type"],
                "source": followup["source"],
                "review_status": "unreviewed",
            },
        ],
        "computed_results": computed_results,
        "candidate_interpretations": [],
        "limitations": limitations,
        "missing_context": [
            "clinician-confirmed same-lesion identity",
            "compatible acquisition and contrast protocol",
            "diagnosis-specific response criteria",
            "clinical status, steroid context, and treatment timing",
        ],
        "questions_for_clinician": [
            "Do these measurements represent the same lesion and tumor component?",
            "Are these source series suitable for longitudinal response measurement?",
            "Which response criteria and baseline or nadir convention should apply?",
        ],
    }
