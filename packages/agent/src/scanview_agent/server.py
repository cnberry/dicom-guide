from __future__ import annotations

import json
import secrets
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .comparison import suggest_pairs


class ScanViewServer(ThreadingHTTPServer):
    catalog: dict[str, Any]
    registry: dict[str, Path]
    token: str


class Handler(BaseHTTPRequestHandler):
    server: ScanViewServer

    def log_message(self, format: str, *args: object) -> None:
        # Never log filesystem paths, DICOM headers, query strings, or response bodies.
        print(f"scanview-api {self.command} {urlparse(self.path).path} {args[1] if len(args) > 1 else ''}")

    def _authorized(self) -> bool:
        return self.headers.get("Authorization") == f"Bearer {self.server.token}"

    def _send_json(self, value: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        payload = json.dumps(value, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/v1/health":
            self._send_json({"status": "ok", "schema_version": self.server.catalog["schema_version"]})
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
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                with source.open("rb") as stream:
                    while chunk := stream.read(1024 * 1024):
                        self.wfile.write(chunk)
            except (BrokenPipeError, OSError):
                return
            return
        self._send_json({"error": "not_found"}, HTTPStatus.NOT_FOUND)


def serve(
    catalog: dict[str, Any],
    registry: dict[str, Path],
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    token: str | None = None,
) -> None:
    if host not in {"127.0.0.1", "::1", "localhost"}:
        raise ValueError("ScanView only supports loopback binding in this release")
    server = ScanViewServer((host, port), Handler)
    server.catalog = catalog
    server.registry = registry
    server.token = token or secrets.token_urlsafe(24)
    print(f"ScanView read-only API: http://{host}:{server.server_port}")
    print(f"Bearer token: {server.token}")
    print("No write or delete endpoints are enabled. Press Ctrl-C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
