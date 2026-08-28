from __future__ import annotations

import json
import mimetypes
import secrets
import webbrowser
from http.cookies import SimpleCookie
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlparse

from .comparison import suggest_pairs


class ScanViewServer(ThreadingHTTPServer):
    catalog: dict[str, Any]
    registry: dict[str, Path]
    token: str
    ui_dist: Path | None


class Handler(BaseHTTPRequestHandler):
    server: ScanViewServer

    def log_message(self, format: str, *args: object) -> None:
        # Never log filesystem paths, DICOM headers, query strings, or response bodies.
        path = urlparse(self.path).path
        if path.startswith("/v1/instances/"):
            path = "/v1/instances/{opaque_id}"
        print(f"scanview-local {self.command} {path} {args[1] if len(args) > 1 else ''}")

    def _authorized(self) -> bool:
        supplied = self.headers.get("Authorization", "")
        if secrets.compare_digest(supplied, f"Bearer {self.server.token}"):
            return True
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
        except ValueError:
            return False
        session = cookie.get("scanview_session")
        return bool(session and secrets.compare_digest(session.value, self.server.token))

    def _security_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")

    def _send_json(self, value: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        payload = json.dumps(value, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self._security_headers()
        self.end_headers()
        self.wfile.write(payload)

    def _send_static(self, path: str) -> bool:
        root = self.server.ui_dist
        if root is None:
            return False
        if path == "/":
            relative = Path("index.html")
        elif path.startswith("/assets/"):
            relative = Path(path.removeprefix("/"))
        else:
            return False
        if ".." in relative.parts:
            return False
        source = (root / relative).resolve()
        if not source.is_relative_to(root) or not source.is_file():
            return False
        try:
            payload = source.read_bytes()
        except OSError:
            return False
        content_type, _ = mimetypes.guess_type(source.name)
        if source.suffix == ".wasm":
            content_type = "application/wasm"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(payload)))
        self._security_headers()
        if source.name == "index.html":
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; base-uri 'none'; connect-src 'self' blob:; "
                "img-src 'self' data: blob:; media-src 'self' blob:; "
                "script-src 'self' 'wasm-unsafe-eval'; style-src 'self' 'unsafe-inline'; "
                "worker-src 'self' blob:; object-src 'none'; frame-ancestors 'none'; "
                "form-action 'none'",
            )
        self.end_headers()
        self.wfile.write(payload)
        return True

    def _establish_browser_session(self, path: str, query: str) -> bool:
        if path != "/" or not query:
            return False
        supplied_values = parse_qs(query, keep_blank_values=True).get("session", [])
        if len(supplied_values) != 1 or not secrets.compare_digest(
            supplied_values[0], self.server.token
        ):
            return False
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", "/")
        cookie = SimpleCookie()
        cookie["scanview_session"] = self.server.token
        cookie["scanview_session"]["httponly"] = True
        cookie["scanview_session"]["samesite"] = "Strict"
        cookie["scanview_session"]["path"] = "/"
        self.send_header("Set-Cookie", cookie.output(header="").strip())
        self._security_headers()
        self.end_headers()
        return True

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        if self._establish_browser_session(path, parsed.query):
            return
        if self._send_static(path):
            return
        if path == "/v1/health":
            self._send_json(
                {
                    "status": "ok",
                    "schema_version": self.server.catalog["schema_version"],
                    "ui_available": self.server.ui_dist is not None,
                }
            )
            return
        if not self._authorized():
            self._send_json({"error": "unauthorized"}, HTTPStatus.UNAUTHORIZED)
            return
        if path == "/v1/manifest":
            self._send_json(self.server.catalog)
            return
        if path == "/v1/comparison-candidates":
            self._send_json(suggest_pairs(self.server.catalog))
            return
        prefix = "/v1/instances/"
        if path.startswith(prefix):
            instance_id = path[len(prefix) :]
            source = self.server.registry.get(instance_id)
            if not source:
                self._send_json({"error": "not_found"}, HTTPStatus.NOT_FOUND)
                return
            try:
                size = source.stat().st_size
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/dicom")
                self.send_header("Content-Length", str(size))
                self._security_headers()
                self.end_headers()
                with source.open("rb") as stream:
                    while chunk := stream.read(1024 * 1024):
                        self.wfile.write(chunk)
            except (BrokenPipeError, OSError):
                return
            return
        self._send_json({"error": "not_found"}, HTTPStatus.NOT_FOUND)


def create_server(
    catalog: dict[str, Any],
    registry: dict[str, Path],
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    token: str | None = None,
    ui_dist: Path | None = None,
) -> ScanViewServer:
    if host not in {"127.0.0.1", "::1", "localhost"}:
        raise ValueError("ScanView only supports loopback binding in this release")
    resolved_ui = ui_dist.expanduser().resolve(strict=True) if ui_dist else None
    if resolved_ui is not None and not (resolved_ui / "index.html").is_file():
        raise ValueError(f"ScanView UI bundle is missing index.html: {resolved_ui}")
    server = ScanViewServer((host, port), Handler)
    server.catalog = catalog
    server.registry = registry
    server.token = token or secrets.token_urlsafe(24)
    server.ui_dist = resolved_ui
    return server


def serve(
    catalog: dict[str, Any],
    registry: dict[str, Path],
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    token: str | None = None,
    ui_dist: Path | None = None,
    open_browser: bool = False,
) -> None:
    server = create_server(
        catalog,
        registry,
        host=host,
        port=port,
        token=token,
        ui_dist=ui_dist,
    )
    base_url = f"http://{host}:{server.server_port}"
    print(f"ScanView read-only API: {base_url}")
    print(f"Bearer token: {server.token}")
    if server.ui_dist:
        session_url = f"{base_url}/?session={quote(server.token, safe='')}"
        print(f"ScanView local workspace: {session_url}")
        if open_browser:
            webbrowser.open(session_url)
    print("No write or delete endpoints are enabled. Press Ctrl-C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
