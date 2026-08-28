from __future__ import annotations

import json
import threading
import time
from http import HTTPStatus
from http.client import HTTPConnection
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from scanview_agent.server import create_server
from scanview_agent.viewer_state import (
    MAX_VIEWER_STATE_BYTES,
    VIEWER_STATE_MEDIA_TYPE,
    VIEWER_STATE_TTL_SECONDS,
    validate_viewer_state,
)


SERIES_A = "series_0123456789abcdef0123"
INSTANCE_A1 = "instance_0123456789abcdef0123"
INSTANCE_A2 = "instance_1123456789abcdef0123"
SERIES_B = "series_2123456789abcdef0123"
INSTANCE_B = "instance_2123456789abcdef0123"
PUBLISHER = "publisher_0123456789abcdef0123456789abcdef"


def catalog() -> dict:
    return {
        "schema_version": "1.0.0",
        "source": {"dicom_instances": 3},
        "studies": [
            {
                "id": "study_0123456789abcdef0123",
                "series": [
                    {
                        "id": SERIES_A,
                        "modality": "MR",
                        "instances": [{"id": INSTANCE_A1}, {"id": INSTANCE_A2}],
                    }
                ],
            },
            {
                "id": "study_1123456789abcdef0123",
                "series": [
                    {
                        "id": SERIES_B,
                        "modality": "MR",
                        "instances": [{"id": INSTANCE_B}],
                    }
                ],
            },
        ],
    }


def state() -> dict:
    return {
        "schema_version": "1.0.0",
        "sharing": True,
        "publisher_id": PUBLISHER,
        "review_status": "unreviewed",
        "active_tool": "length",
        "slice_link": "patient_position",
        "baseline": {
            "series_id": SERIES_A,
            "instance_id": INSTANCE_A2,
            "stack_position": 2,
            "stack_count": 2,
        },
        "followup": {
            "series_id": SERIES_B,
            "instance_id": INSTANCE_B,
            "stack_position": 1,
            "stack_count": 1,
        },
        "mpr_series_id": None,
        "measurement_count": 2,
        "comparison_draft_present": False,
        "privacy": {
            "local_only": True,
            "contains_pixels": False,
            "contains_direct_identifiers": False,
            "persisted": False,
        },
    }


def request(
    port: int,
    method: str,
    path: str,
    *,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    connection.request(method, path, body=body, headers=headers or {})
    response = connection.getresponse()
    result = response.status, dict(response.getheaders()), response.read()
    connection.close()
    return result


def test_viewer_state_validator_requires_exact_catalog_position_and_privacy() -> None:
    assert validate_viewer_state(state(), catalog())["baseline"]["stack_position"] == 2

    wrong_position = state()
    wrong_position["baseline"] = {**wrong_position["baseline"], "stack_position": 1}
    with pytest.raises(ValueError, match="exact local instance"):
        validate_viewer_state(wrong_position, catalog())

    unsafe = state()
    unsafe["privacy"] = {**unsafe["privacy"], "contains_pixels": True}
    with pytest.raises(ValueError, match="privacy declaration"):
        validate_viewer_state(unsafe, catalog())

    extra = state()
    extra["patient_name"] = "must not be accepted"
    with pytest.raises(ValueError, match="unsupported or missing"):
        validate_viewer_state(extra, catalog())


def test_opt_in_viewer_state_http_lifecycle_is_local_authenticated_and_atomic() -> None:
    server = create_server(catalog(), {}, port=0, token="viewer-state-test-token")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_port
    try:
        status, _, _ = request(port, "GET", "/v1/viewer-state")
        assert status == HTTPStatus.UNAUTHORIZED

        bearer = {"Authorization": "Bearer viewer-state-test-token"}
        status, headers, body = request(
            port, "GET", "/v1/viewer-state", headers=bearer
        )
        assert status == HTTPStatus.OK
        assert headers["Cache-Control"] == "no-store"
        assert json.loads(body) == {
            "schema_version": "1.0.0",
            "available": False,
            "reason": "not_shared",
            "expires_after_seconds": 30,
        }

        payload = json.dumps(state(), separators=(",", ":")).encode()
        publication_headers = {
            **bearer,
            "Content-Type": VIEWER_STATE_MEDIA_TYPE,
            "Origin": f"http://127.0.0.1:{port}",
        }
        status, _, _ = request(
            port,
            "POST",
            "/v1/viewer-state",
            body=payload,
            headers={**publication_headers, "Content-Type": "application/json"},
        )
        assert status == HTTPStatus.UNSUPPORTED_MEDIA_TYPE

        status, _, _ = request(
            port,
            "POST",
            "/v1/viewer-state",
            body=b"x" * (MAX_VIEWER_STATE_BYTES + 1),
            headers=publication_headers,
        )
        assert status == HTTPStatus.REQUEST_ENTITY_TOO_LARGE

        status, _, _ = request(
            port,
            "POST",
            "/v1/viewer-state",
            body=payload,
            headers={**publication_headers, "Origin": "http://example.invalid"},
        )
        assert status == HTTPStatus.FORBIDDEN

        status, headers, body = request(
            port,
            "POST",
            "/v1/viewer-state",
            body=payload,
            headers=publication_headers,
        )
        assert status == HTTPStatus.OK
        assert headers["Cache-Control"] == "no-store"
        assert json.loads(body)["expires_after_seconds"] == 30

        status, _, body = request(port, "GET", "/v1/viewer-state", headers=bearer)
        response = json.loads(body)
        assert status == HTTPStatus.OK
        assert response["available"] is True
        assert response["state"] == state()
        assert "patient_name" not in body.decode()
        repository_root = Path(__file__).parents[3]
        schema = json.loads(
            (repository_root / "schemas" / "scanview-viewer-state-v1.schema.json").read_text()
        )
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(response)

        invalid = state()
        invalid["baseline"] = {**invalid["baseline"], "instance_id": INSTANCE_B}
        status, _, _ = request(
            port,
            "POST",
            "/v1/viewer-state",
            body=json.dumps(invalid).encode(),
            headers=publication_headers,
        )
        assert status == HTTPStatus.UNPROCESSABLE_ENTITY
        assert server.viewer_state == state()

        wrong_clear = {
            "schema_version": "1.0.0",
            "sharing": False,
            "publisher_id": "publisher_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        }
        status, _, body = request(
            port,
            "POST",
            "/v1/viewer-state",
            body=json.dumps(wrong_clear).encode(),
            headers=publication_headers,
        )
        assert status == HTTPStatus.OK
        assert json.loads(body)["removed"] is False
        assert server.viewer_state is not None

        clear = {**wrong_clear, "publisher_id": PUBLISHER}
        status, _, body = request(
            port,
            "POST",
            "/v1/viewer-state",
            body=json.dumps(clear).encode(),
            headers=publication_headers,
        )
        assert status == HTTPStatus.OK
        assert json.loads(body)["removed"] is True
        status, _, body = request(port, "GET", "/v1/viewer-state", headers=bearer)
        unavailable = json.loads(body)
        assert unavailable["available"] is False
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(unavailable)

        status, _, body = request(
            port,
            "POST",
            "/v1/viewer-state",
            body=payload,
            headers=publication_headers,
        )
        assert status == HTTPStatus.CONFLICT
        assert json.loads(body) == {"error": "publisher_revoked"}
        assert server.viewer_state is None
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_viewer_state_expires_without_browser_heartbeat() -> None:
    server = create_server(catalog(), {}, port=0, token="viewer-state-test-token")
    server.publish_viewer_state(validate_viewer_state(state(), catalog()))
    assert server.viewer_state_received_monotonic is not None
    server.viewer_state_received_monotonic = (
        time.monotonic() - VIEWER_STATE_TTL_SECONDS - 1
    )

    response = server.viewer_state_response()

    assert response == {
        "schema_version": "1.0.0",
        "available": False,
        "reason": "stale",
        "expires_after_seconds": 30,
    }
    assert server.viewer_state is None
    server.server_close()
