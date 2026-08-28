from __future__ import annotations

import json
import threading
from http import HTTPStatus
from http.client import HTTPConnection
from pathlib import Path

from scanview_agent.server import create_server


def request(
    port: int, path: str, *, headers: dict[str, str] | None = None
) -> tuple[int, dict[str, str], bytes]:
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    connection.request("GET", path, headers=headers or {})
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
        status, headers, body = request(port, "/")
        assert status == HTTPStatus.OK
        assert body.startswith(b"<!doctype html>")
        assert "default-src 'self'" in headers["Content-Security-Policy"]

        status, _, body = request(port, "/v1/manifest")
        assert status == HTTPStatus.UNAUTHORIZED
        assert json.loads(body) == {"error": "unauthorized"}

        status, headers, _ = request(port, "/?session=test-session-token")
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
