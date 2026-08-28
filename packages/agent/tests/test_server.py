from __future__ import annotations

import json
import threading
from http import HTTPStatus
from http.client import HTTPConnection
from pathlib import Path

import scanview_agent.server as server_module
from scanview_agent.server import create_server
from test_registration_reviews import registration_bundle, review_request


def request(
    port: int, path: str, *, headers: dict[str, str] | None = None
) -> tuple[int, dict[str, str], bytes]:
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    connection.request("GET", path, headers=headers or {})
    response = connection.getresponse()
    result = response.status, dict(response.getheaders()), response.read()
    connection.close()
    return result


def post(
    port: int,
    path: str,
    body: bytes,
    *,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    connection.request("POST", path, body=body, headers=headers or {})
    response = connection.getresponse()
    result = response.status, dict(response.getheaders()), response.read()
    connection.close()
    return result


def test_unified_server_establishes_private_browser_session_and_serves_dicom(
    tmp_path: Path,
) -> None:
    ui_dist = tmp_path / "ui"
    assets = ui_dist / "assets"
    assets.mkdir(parents=True)
    (ui_dist / "index.html").write_text("<!doctype html><title>ScanView test</title>")
    (assets / "app.js").write_text("export {}")
    dicom = tmp_path / "source-image"
    dicom.write_bytes(b"DICM-local-test")
    instance_id = "instance_0123456789abcdef0123"
    catalog = {
        "schema_version": "1.0.0",
        "source": {"dicom_instances": 1},
        "studies": [],
    }
    server = create_server(
        catalog,
        {instance_id: dicom},
        port=0,
        token="test-session-token",
        ui_dist=ui_dist,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_port
    try:
        assert server.browser_bootstrap_token != server.token
        assert server.browser_session_token != server.token
        assert server.browser_session_token != server.browser_bootstrap_token
        status, headers, body = request(port, "/")
        assert status == HTTPStatus.OK
        assert body.startswith(b"<!doctype html>")
        assert "default-src 'self'" in headers["Content-Security-Policy"]

        status, _, body = request(port, "/v1/manifest")
        assert status == HTTPStatus.UNAUTHORIZED
        assert json.loads(body) == {"error": "unauthorized"}

        status, forged_headers, _ = request(
            port, "/?session=test-session-token"
        )
        assert status == HTTPStatus.OK
        assert "Set-Cookie" not in forged_headers

        status, headers, _ = request(
            port, f"/?session={server.browser_bootstrap_token}"
        )
        assert status == HTTPStatus.SEE_OTHER
        assert headers["Location"] == "/"
        assert "HttpOnly" in headers["Set-Cookie"]
        assert "SameSite=Strict" in headers["Set-Cookie"]
        cookie = headers["Set-Cookie"].split(";", 1)[0]

        status, _, body = request(port, "/v1/manifest", headers={"Cookie": cookie})
        assert status == HTTPStatus.OK
        assert json.loads(body)["schema_version"] == "1.0.0"

        status, headers, body = request(
            port,
            f"/v1/instances/{instance_id}",
            headers={"Cookie": cookie},
        )
        assert status == HTTPStatus.OK
        assert headers["Content-Type"] == "application/dicom"
        assert headers["Cache-Control"] == "no-store"
        assert body == b"DICM-local-test"

        status, _, _ = request(
            port,
            "/v1/comparison-candidates",
            headers={"Authorization": "Bearer test-session-token"},
        )
        assert status == HTTPStatus.OK
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_static_server_refuses_asset_path_traversal(tmp_path: Path) -> None:
    ui_dist = tmp_path / "ui"
    (ui_dist / "assets").mkdir(parents=True)
    (ui_dist / "index.html").write_text("ScanView")
    secret = tmp_path / "secret.txt"
    secret.write_text("must not be served")
    server = create_server(
        {"schema_version": "1.0.0", "studies": []},
        {},
        port=0,
        token="test-session-token",
        ui_dist=ui_dist,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, _, body = request(
            server.server_port,
            "/assets/../../secret.txt",
            headers={"Authorization": "Bearer test-session-token"},
        )
        assert status == HTTPStatus.NOT_FOUND
        assert b"must not be served" not in body
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_registration_qa_preview_is_browser_only_and_review_is_idempotent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    bundle = registration_bundle(tmp_path)
    ui_dist = tmp_path / "ui"
    ui_dist.mkdir()
    (ui_dist / "index.html").write_text("ScanView QA")
    original_context = server_module.registration_qa_context
    original_review_builder = server_module.registration_review_bytes
    context_calls = 0

    def counted_context(directory: Path) -> dict:
        nonlocal context_calls
        context_calls += 1
        return original_context(directory)

    review_build_calls = 0

    def build_review_once(
        directory: Path,
        request_bytes: bytes,
        *,
        created_at: str,
    ) -> bytes:
        nonlocal review_build_calls
        review_build_calls += 1
        assert directory == bundle.resolve()
        assert created_at.endswith("Z")
        return original_review_builder(
            directory,
            request_bytes,
            created_at=created_at,
        )

    monkeypatch.setattr(server_module, "registration_qa_context", counted_context)
    monkeypatch.setattr(server_module, "registration_review_bytes", build_review_once)
    server = create_server(
        {
            "schema_version": "1.0.0",
            "source": {"dicom_instances": 0},
            "studies": [],
        },
        {},
        port=0,
        token="qa-session-token",
        ui_dist=ui_dist,
        registration_bundle=bundle,
    )
    assert context_calls == 1
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_port
    bearer = {"Authorization": "Bearer qa-session-token"}
    try:
        status, _, body = request(port, "/v1/registration-qa", headers=bearer)
        assert status == HTTPStatus.OK
        agent_summary = json.loads(body)
        assert agent_summary["available"] is True
        assert agent_summary["display_unlocked"] is False
        assert str(bundle) not in body.decode()

        status, _, body = request(port, "/v1/registration-qa/preview", headers=bearer)
        assert status == HTTPStatus.FORBIDDEN
        assert json.loads(body) == {"error": "browser_session_required"}

        forged_browser = {"Cookie": "scanview_session=qa-session-token"}
        status, _, body = request(
            port,
            "/v1/registration-qa/preview",
            headers=forged_browser,
        )
        assert status == HTTPStatus.UNAUTHORIZED
        assert json.loads(body) == {"error": "unauthorized"}

        status, headers, _ = request(
            port, f"/?session={server.browser_bootstrap_token}"
        )
        assert status == HTTPStatus.SEE_OTHER
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        assert server.browser_session_token in cookie
        assert "qa-session-token" not in cookie
        browser = {"Cookie": cookie}

        status, _, body = request(
            port,
            "/v1/registration-qa/preview",
            headers=browser,
        )
        assert status == HTTPStatus.OK
        preview = json.loads(body)
        assert preview["qa_preview_only"] is True
        assert preview["watermark"] == "UNAPPROVED REGISTRATION — QA ONLY"
        assert str(bundle) not in body.decode()

        status, _, _ = request(
            port,
            "/v1/registration-qa/files/fixed.nrrd",
            headers=bearer,
        )
        assert status == HTTPStatus.FORBIDDEN
        status, volume_headers, volume = request(
            port,
            "/v1/registration-qa/files/fixed.nrrd",
            headers=browser,
        )
        assert status == HTTPStatus.OK
        assert volume_headers["Content-Type"] == "application/vnd.nrrd"
        assert volume_headers["Cache-Control"] == "no-store"
        assert volume == (bundle / "fixed.nrrd").read_bytes()
        assert context_calls == 1

        payload = json.dumps(review_request(decision="rejected")).encode()
        status, _, _ = post(
            port,
            "/v1/registration-reviews",
            payload,
            headers={
                "Cookie": cookie,
                "Origin": "http://example.invalid",
                "Host": f"127.0.0.1:{port}",
                "Content-Type": "application/vnd.scanview.registration-review-input+json",
            },
        )
        assert status == HTTPStatus.FORBIDDEN

        review_headers = {
            "Cookie": cookie,
            "Origin": f"http://127.0.0.1:{port}",
            "Host": f"127.0.0.1:{port}",
            "Content-Type": "application/vnd.scanview.registration-review-input+json",
        }
        status, response_headers, body = post(
            port,
            "/v1/registration-reviews",
            payload,
            headers=review_headers,
        )
        assert status == HTTPStatus.OK
        assert response_headers["Cache-Control"] == "no-store"
        assert response_headers["Content-Type"] == (
            "application/vnd.scanview.registration-review+json"
        )
        record = json.loads(body)
        assert record["review_status"] == "rejected"
        assert record["display_unlocks"]["overlay"] is False
        assert record["display_unlocks"]["subtraction"] is False
        assert str(bundle) not in body.decode()
        assert review_build_calls == 1
        first_body = body
        first_filename = response_headers["Content-Disposition"]

        status, retry_headers, body = post(
            port,
            "/v1/registration-reviews",
            payload,
            headers=review_headers,
        )
        assert status == HTTPStatus.OK
        assert body == first_body
        assert retry_headers["Content-Disposition"] == first_filename
        assert review_build_calls == 1

        different_payload = review_request(decision="rejected")
        different_payload["note"] = "A different rejected QA request."
        status, _, body = post(
            port,
            "/v1/registration-reviews",
            json.dumps(different_payload).encode(),
            headers=review_headers,
        )
        assert status == HTTPStatus.CONFLICT
        assert json.loads(body) == {"error": "registration_review_already_created"}
        assert review_build_calls == 1

        fixed = bundle / "fixed.nrrd"
        fixed_payload = fixed.read_bytes()
        fixed.write_bytes(fixed_payload[:-1] + bytes([fixed_payload[-1] ^ 0x01]))
        status, _, body = request(
            port,
            "/v1/registration-qa/files/fixed.nrrd",
            headers=browser,
        )
        assert status == HTTPStatus.CONFLICT
        assert json.loads(body) == {"error": "registration_bundle_invalid"}
        fixed.write_bytes(fixed_payload)

        original_fixed = tmp_path / "fixed-original.nrrd"
        fixed.rename(original_fixed)
        fixed.symlink_to(original_fixed)
        status, _, body = request(
            port,
            "/v1/registration-qa/files/fixed.nrrd",
            headers=browser,
        )
        assert status == HTTPStatus.CONFLICT
        assert json.loads(body) == {"error": "registration_bundle_invalid"}
        assert context_calls == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
