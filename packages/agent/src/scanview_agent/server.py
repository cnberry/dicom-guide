from __future__ import annotations

import io
import json
import mimetypes
import secrets
import threading
import time
import webbrowser
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlparse

from .comparison import suggest_pairs
from .comparison_reviews import (
    MAX_COMPARISON_REVIEW_TRANSPORT_BYTES,
    comparison_review_from_transport,
    comparison_review_summary,
)
from .navigation import NAVIGATION_FRAGMENT_PREFIX
from .visit_packets import (
    MAX_VISIT_PACKET_TRANSPORT_BYTES,
    visit_packet_from_transport,
    visit_packet_summary,
)
from .viewer_state import (
    MAX_VIEWER_STATE_BYTES,
    VIEWER_STATE_MEDIA_TYPE,
    VIEWER_STATE_TTL_SECONDS,
    available_viewer_state_response,
    is_clear_viewer_state,
    unavailable_viewer_state_response,
    utc_now,
    validate_viewer_state,
)


class ScanViewServer(ThreadingHTTPServer):
    catalog: dict[str, Any]
    registry: dict[str, Path]
    token: str
    ui_dist: Path | None
    viewer_state_lock: threading.Lock
    viewer_state: dict[str, Any] | None
    viewer_state_received_at: str | None
    viewer_state_received_monotonic: float | None
    viewer_state_revoked_publishers: set[str]

    def publish_viewer_state(self, state: dict[str, Any]) -> bool:
        with self.viewer_state_lock:
            if state["publisher_id"] in self.viewer_state_revoked_publishers:
                return False
            self.viewer_state = state
            self.viewer_state_received_at = utc_now()
            self.viewer_state_received_monotonic = time.monotonic()
            return True

    def clear_viewer_state(self, publisher_id: str) -> bool:
        with self.viewer_state_lock:
            self.viewer_state_revoked_publishers.add(publisher_id)
            removed = bool(
                self.viewer_state
                and self.viewer_state.get("publisher_id") == publisher_id
            )
            if removed:
                self.viewer_state = None
                self.viewer_state_received_at = None
                self.viewer_state_received_monotonic = None
            return removed

    def viewer_state_response(self) -> dict[str, Any]:
        with self.viewer_state_lock:
            if (
                self.viewer_state is None
                or self.viewer_state_received_at is None
                or self.viewer_state_received_monotonic is None
            ):
                return unavailable_viewer_state_response("not_shared")
            age = time.monotonic() - self.viewer_state_received_monotonic
            if age > VIEWER_STATE_TTL_SECONDS:
                self.viewer_state = None
                self.viewer_state_received_at = None
                self.viewer_state_received_monotonic = None
                return unavailable_viewer_state_response("stale")
            return available_viewer_state_response(
                self.viewer_state,
                received_at=self.viewer_state_received_at,
                age_seconds=age,
            )


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

    def _same_origin(self) -> bool:
        host = self.headers.get("Host", "")
        allowed_hosts = {
            f"127.0.0.1:{self.server.server_port}",
            f"localhost:{self.server.server_port}",
            f"[::1]:{self.server.server_port}",
        }
        return host in allowed_hosts and self.headers.get("Origin") == f"http://{host}"

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
        if path == "/v1/viewer-state":
            self._send_json(self.server.viewer_state_response())
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

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/v1/viewer-state":
            self._handle_viewer_state_post()
            return
        supported = {
            "/v1/visit-packets": (
                "application/vnd.scanview.visit-input+zip",
                MAX_VISIT_PACKET_TRANSPORT_BYTES,
            ),
            "/v1/comparison-reviews": (
                "application/vnd.scanview.comparison-review-input+zip",
                MAX_COMPARISON_REVIEW_TRANSPORT_BYTES,
            ),
        }
        if path not in supported:
            self._send_json({"error": "not_found"}, HTTPStatus.NOT_FOUND)
            return
        if not self._authorized():
            self._send_json({"error": "unauthorized"}, HTTPStatus.UNAUTHORIZED)
            return
        if not self._same_origin():
            self._send_json({"error": "same_origin_required"}, HTTPStatus.FORBIDDEN)
            return
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        expected_media_type, maximum_bytes = supported[path]
        if content_type != expected_media_type:
            self._send_json(
                {"error": "unsupported_media_type"}, HTTPStatus.UNSUPPORTED_MEDIA_TYPE
            )
            return
        try:
            content_length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            self._send_json({"error": "content_length_required"}, HTTPStatus.LENGTH_REQUIRED)
            return
        if content_length <= 0 or content_length > maximum_bytes:
            self._send_json({"error": "request_too_large"}, HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            return
        body = self.rfile.read(content_length)
        if len(body) != content_length:
            self._send_json({"error": "incomplete_request"}, HTTPStatus.BAD_REQUEST)
            return
        created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        try:
            if path == "/v1/visit-packets":
                payload = visit_packet_from_transport(body, created_at=created_at)
                summary = visit_packet_summary(io.BytesIO(payload))
                if not summary["valid"]:
                    raise ValueError("assembled visit packet failed local integrity validation")
                filename_prefix = "scanview-visit-packet"
            else:
                payload = comparison_review_from_transport(
                    body,
                    visit_created_at=created_at,
                )
                summary = comparison_review_summary(io.BytesIO(payload))
                if not summary["valid"]:
                    raise ValueError(
                        "assembled comparison review failed local integrity validation"
                    )
                filename_prefix = "scanview-comparison-review"
        except ValueError as error:
            self._send_json(
                {
                    "error": (
                        "invalid_visit_packet_input"
                        if path == "/v1/visit-packets"
                        else "invalid_comparison_review_input"
                    ),
                    "detail": str(error),
                },
                HTTPStatus.UNPROCESSABLE_ENTITY,
            )
            return
        timestamp = created_at.replace("-", "").replace(":", "").split(".", 1)[0] + "Z"
        filename = f"{filename_prefix}-{timestamp}.zip"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(payload)))
        self._security_headers()
        self.end_headers()
        self.wfile.write(payload)

    def _handle_viewer_state_post(self) -> None:
        if not self._authorized():
            self._send_json({"error": "unauthorized"}, HTTPStatus.UNAUTHORIZED)
            return
        if not self._same_origin():
            self._send_json({"error": "same_origin_required"}, HTTPStatus.FORBIDDEN)
            return
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type != VIEWER_STATE_MEDIA_TYPE:
            self._send_json(
                {"error": "unsupported_media_type"}, HTTPStatus.UNSUPPORTED_MEDIA_TYPE
            )
            return
        try:
            content_length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            self._send_json({"error": "content_length_required"}, HTTPStatus.LENGTH_REQUIRED)
            return
        if content_length <= 0 or content_length > MAX_VIEWER_STATE_BYTES:
            self._send_json({"error": "request_too_large"}, HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            return
        body = self.rfile.read(content_length)
        if len(body) != content_length:
            self._send_json({"error": "incomplete_request"}, HTTPStatus.BAD_REQUEST)
            return
        try:
            value = json.loads(body.decode("utf-8"))
            clear, publisher_id = is_clear_viewer_state(value)
            if clear and publisher_id is not None:
                removed = self.server.clear_viewer_state(publisher_id)
                self._send_json(
                    {
                        "schema_version": "1.0.0",
                        "accepted": True,
                        "sharing": False,
                        "removed": removed,
                    }
                )
                return
            state = validate_viewer_state(value, self.server.catalog)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
            self._send_json(
                {"error": "invalid_viewer_state", "detail": str(error)},
                HTTPStatus.UNPROCESSABLE_ENTITY,
            )
            return
        if not self.server.publish_viewer_state(state):
            self._send_json(
                {"error": "publisher_revoked"},
                HTTPStatus.CONFLICT,
            )
            return
        self._send_json(
            {
                "schema_version": "1.0.0",
                "accepted": True,
                "sharing": True,
                "expires_after_seconds": int(VIEWER_STATE_TTL_SECONDS),
            }
        )


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
    server.viewer_state_lock = threading.Lock()
    server.viewer_state = None
    server.viewer_state_received_at = None
    server.viewer_state_received_monotonic = None
    server.viewer_state_revoked_publishers = set()
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
    navigation_fragment: str | None = None,
) -> None:
    if navigation_fragment is not None and (
        not navigation_fragment.startswith(NAVIGATION_FRAGMENT_PREFIX)
        or len(navigation_fragment) > 320
    ):
        raise ValueError("viewer navigation fragment is invalid")
    server = create_server(
        catalog,
        registry,
        host=host,
        port=port,
        token=token,
        ui_dist=ui_dist,
    )
    url_host = f"[{host}]" if ":" in host else host
    base_url = f"http://{url_host}:{server.server_port}"
    print(f"ScanView local source-read-only API: {base_url}")
    print(f"Bearer token: {server.token}")
    if server.ui_dist:
        session_url = (
            f"{base_url}/?session={quote(server.token, safe='')}"
            f"{navigation_fragment or ''}"
        )
        print(f"ScanView local workspace: {session_url}")
        if open_browser:
            webbrowser.open(session_url)
    print(
        "Source mutation and deletion are disabled; visit/review derivatives and opt-in "
        "viewer state remain memory-only. Press Ctrl-C to stop."
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
