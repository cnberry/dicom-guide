from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlencode, urlparse


NAVIGATION_FRAGMENT_PREFIX = "#dicom-guide-v1?"
OPAQUE_SERIES_ID = re.compile(r"^series_[0-9a-f]{20}$")
OPAQUE_INSTANCE_ID = re.compile(r"^instance_[0-9a-f]{20}$")
LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


def _catalog_series(catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if (
        not isinstance(catalog, dict)
        or catalog.get("schema_version") != "1.0.0"
        or not isinstance(catalog.get("studies"), list)
    ):
        raise ValueError("navigation requires a DICOM Guide manifest v1 catalog")
    result: dict[str, dict[str, Any]] = {}
    for study in catalog["studies"]:
        if not isinstance(study, dict) or not isinstance(study.get("series"), list):
            continue
        for series in study["series"]:
            if (
                isinstance(series, dict)
                and isinstance(series.get("id"), str)
                and series.get("modality") in {"MR", "CT"}
                and isinstance(series.get("instances"), list)
            ):
                result[series["id"]] = series
    return result


def _target(
    series_by_id: dict[str, dict[str, Any]],
    *,
    role: str,
    series_id: str,
    instance_id: str,
) -> dict[str, str]:
    if not OPAQUE_SERIES_ID.fullmatch(series_id):
        raise ValueError(f"{role} series ID is not a supported opaque ID")
    if not OPAQUE_INSTANCE_ID.fullmatch(instance_id):
        raise ValueError(f"{role} instance ID is not a supported opaque ID")
    series = series_by_id.get(series_id)
    if series is None:
        raise ValueError(f"{role} series is not a renderable catalog series")
    instances = series["instances"]
    if not any(
        isinstance(instance, dict) and instance.get("id") == instance_id
        for instance in instances
    ):
        raise ValueError(f"{role} instance does not belong to the selected series")
    return {"series_id": series_id, "instance_id": instance_id}


def _local_base_url(value: str) -> str:
    try:
        parsed = urlparse(value)
        port = parsed.port
    except ValueError as error:
        raise ValueError("viewer base URL is invalid") from error
    if (
        parsed.scheme != "http"
        or parsed.hostname not in LOOPBACK_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or parsed.params
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
        or port is None
        or not (1 <= port <= 65535)
    ):
        raise ValueError("viewer base URL must be a plain loopback HTTP origin with a port")
    canonical_host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
    return f"{parsed.scheme}://{canonical_host}:{port}/"


def build_navigation_intent(
    catalog: dict[str, Any],
    *,
    baseline_series_id: str,
    baseline_instance_id: str,
    followup_series_id: str | None = None,
    followup_instance_id: str | None = None,
    base_url: str | None = None,
) -> dict[str, Any]:
    if (followup_series_id is None) != (followup_instance_id is None):
        raise ValueError("follow-up navigation requires both a series and instance ID")
    series_by_id = _catalog_series(catalog)
    baseline = _target(
        series_by_id,
        role="baseline",
        series_id=baseline_series_id,
        instance_id=baseline_instance_id,
    )
    followup = None
    if followup_series_id is not None and followup_instance_id is not None:
        if followup_series_id == baseline_series_id:
            raise ValueError("baseline and follow-up navigation require distinct series")
        followup = _target(
            series_by_id,
            role="follow-up",
            series_id=followup_series_id,
            instance_id=followup_instance_id,
        )

    parameters = [
        ("baseline_series", baseline["series_id"]),
        ("baseline_instance", baseline["instance_id"]),
    ]
    if followup is not None:
        parameters.extend(
            [
                ("followup_series", followup["series_id"]),
                ("followup_instance", followup["instance_id"]),
            ]
        )
    fragment = NAVIGATION_FRAGMENT_PREFIX + urlencode(parameters)
    result: dict[str, Any] = {
        "schema_version": "1.0.0",
        "local_only": True,
        "sensitive": True,
        "pairing_status": "not_assessed",
        "baseline": baseline,
        "fragment": fragment,
    }
    if followup is not None:
        result["followup"] = followup
    if base_url is not None:
        result["url"] = _local_base_url(base_url) + fragment
    return result
