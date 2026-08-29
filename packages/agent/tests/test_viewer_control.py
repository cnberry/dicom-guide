from __future__ import annotations

import json
import threading
from http import HTTPStatus
from http.client import HTTPConnection
from pathlib import Path

import pytest

from scanview_agent.server import create_server
from scanview_agent.viewer_control import (
    MEDIA_TYPE,
    PERMISSIONS,
    PRIVACY,
    response,
    validate_command,
    validate_observation,
)


SERIES_ID = "series_0123456789abcdef0123"
INSTANCE_IDS = [
    "instance_0123456789abcdef0123",
    "instance_abcdef0123456789abcd",
]
COMMAND_ID = "control_0123456789abcdef0123456789abcdef"


def catalog() -> dict:
    return {
        "schema_version": "1.0.0",
        "source": {"dicom_instances": 2},
        "studies": [
            {
                "id": "study_0123456789abcdef0123",
                "series": [
                    {
                        "id": SERIES_ID,
                        "modality": "MR",
                        "instances": [{"id": value} for value in INSTANCE_IDS],
                    }
                ],
            }
        ],
    }


def command() -> dict:
    return {
        "schema_version": "1.0.0",
        "command_id": COMMAND_ID,
        "view_mode": "mpr",
        "series_id": SERIES_ID,
        "instance_id": INSTANCE_IDS[1],
        "tool": "crosshairs",
        "patient_point_lps_mm": [1.25, -2.5, 3.75],
        "reset_view": True,
    }


def observation(*, agent: bool = True) -> dict:
    return {
        "schema_version": "1.0.0",
        "applied_command_id": COMMAND_ID if agent else None,
        "applied_revision": 4 if agent else 0,
        "interaction_source": "agent" if agent else "person",
        "render_status": "ready",
        "view_mode": "mpr",
        "series_id": SERIES_ID,
        "instance_id": INSTANCE_IDS[1],
        "stack_position": 2,
        "stack_count": 2,
        "tool": "crosshairs",
        "patient_point_lps_mm": [1.25, -2.5, 3.75],
        "point_pinned": True,
        "permissions": PERMISSIONS,
        "privacy": PRIVACY,
    }


def post(
    port: int, path: str, body: dict, headers: dict[str, str]
) -> tuple[int, dict]:
    payload = json.dumps(body, separators=(",", ":")).encode()
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    connection.request("POST", path, body=payload, headers=headers)
    response_value = connection.getresponse()
    status = response_value.status
    decoded = json.loads(response_value.read())
    connection.close()
    return status, decoded


def get(port: int, path: str, headers: dict[str, str]) -> tuple[int, dict]:
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    connection.request("GET", path, headers=headers)
    response_value = connection.getresponse()
    status = response_value.status
    decoded = json.loads(response_value.read())
    connection.close()
    return status, decoded


def test_validates_exact_local_command_and_observation() -> None:
    validated = validate_command(command(), catalog())
    assert validated["instance_id"] == INSTANCE_IDS[1]
    assert validated["patient_point_lps_mm"] == [1.25, -2.5, 3.75]

    current = {**validated, "revision": 4, "issued_at": "2026-08-29T12:00:00Z"}
    observed = validate_observation(observation(), catalog(), current_command=current)
    assert observed["stack_position"] == 2
    assert observed["permissions"]["agent_view_navigation_authorized"] is True
    assert observed["permissions"]["diagnosis_authorized"] is False
    assert observed["privacy"]["contains_pixels"] is False

    # An MPR point is exact in patient space. The nearest native source slice can
    # differ from the command's anchor after volume reconstruction.
    nearest_source = {
        **observation(),
        "instance_id": INSTANCE_IDS[0],
        "stack_position": 1,
    }
    observed = validate_observation(nearest_source, catalog(), current_command=current)
    assert observed["instance_id"] == INSTANCE_IDS[0]


def test_native_observation_requires_the_exact_command_instance() -> None:
    current = {
        **command(),
        "view_mode": "native",
        "tool": "window",
        "patient_point_lps_mm": None,
        "revision": 4,
        "issued_at": "2026-08-29T12:00:00Z",
    }
    wrong_instance = {
        **observation(),
        "view_mode": "native",
        "tool": "window",
        "patient_point_lps_mm": None,
        "point_pinned": False,
        "instance_id": INSTANCE_IDS[0],
        "stack_position": 1,
    }
    with pytest.raises(ValueError, match="requested instance"):
        validate_observation(wrong_instance, catalog(), current_command=current)


def test_refuses_wrong_membership_tool_provenance_and_point_flag() -> None:
    cases = [
        {**command(), "instance_id": "instance_11111111111111111111"},
        {**command(), "tool": "length"},
        {**command(), "patient_point_lps_mm": [1, 2, float("inf")]},
    ]
    for value in cases:
        with pytest.raises(ValueError):
            validate_command(value, catalog())

    current = {**command(), "revision": 4, "issued_at": "2026-08-29T12:00:00Z"}
    with pytest.raises(ValueError):
        validate_observation(
            {**observation(), "applied_revision": 3},
            catalog(),
            current_command=current,
        )
    with pytest.raises(ValueError):
        validate_observation(
            {**observation(), "point_pinned": False},
            catalog(),
            current_command=current,
        )


def test_allows_display_crop_for_mpr_but_not_native() -> None:
    crop_command = {**command(), "tool": "crop", "patient_point_lps_mm": None}
    assert validate_command(crop_command, catalog())["tool"] == "crop"
    with pytest.raises(ValueError, match="unsupported"):
        validate_command(
            {**crop_command, "view_mode": "native"},
            catalog(),
        )


def test_response_withholds_stale_observation() -> None:
    current = {**command(), "revision": 4, "issued_at": "2026-08-29T12:00:00Z"}
    available = response(command=current, observation=observation(), observation_age_seconds=1.2)
    assert available["viewer_connected"] is True
    assert available["observation"]["instance_id"] == INSTANCE_IDS[1]
    stale = response(command=current, observation=observation(), observation_age_seconds=5.1)
    assert stale["viewer_connected"] is False
    assert stale["observation"] is None


def test_loopback_control_separates_bearer_command_from_browser_observation(
    tmp_path: Path,
) -> None:
    sources = []
    registry = {}
    for index, instance_id in enumerate(INSTANCE_IDS):
        source = tmp_path / f"source-{index}.dcm"
        source.write_bytes(b"DICM-control-test")
        sources.append(source)
        registry[instance_id] = source
    server = create_server(catalog(), registry, port=0, token="control-token")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_port
    bearer = {
        "Authorization": "Bearer control-token",
        "Content-Type": MEDIA_TYPE,
    }
    try:
        status, body = post(port, "/v1/viewer-control", command(), bearer)
        assert status == HTTPStatus.OK
        assert body["accepted"] is True
        assert body["revision"] == 1
        assert body["viewer_connected"] is False

        status, body = get(
            port,
            "/v1/viewer-control",
            {"Authorization": "Bearer control-token"},
        )
        assert status == HTTPStatus.OK
        assert body["command"]["command_id"] == COMMAND_ID
        assert body["observation"] is None

        status, body = post(port, "/v1/viewer-control/observation", observation(), bearer)
        assert status == HTTPStatus.FORBIDDEN
        assert body == {"error": "same_origin_required"}

        browser_observation = {**observation(), "applied_revision": 1}
        status, body = post(
            port,
            "/v1/viewer-control/observation",
            browser_observation,
            {
                "Host": f"127.0.0.1:{port}",
                "Origin": f"http://127.0.0.1:{port}",
                "Content-Type": MEDIA_TYPE,
            },
        )
        assert status == HTTPStatus.OK
        assert body["accepted"] is True

        status, body = get(
            port,
            "/v1/viewer-control",
            {"Authorization": "Bearer control-token"},
        )
        assert status == HTTPStatus.OK
        assert body["viewer_connected"] is True
        assert body["observation"]["applied_revision"] == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
