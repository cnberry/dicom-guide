from __future__ import annotations

import hashlib
import io
import json
import mimetypes
import os
import secrets
import stat
import tempfile
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
from .consultation_boards import (
    MAX_BOARD_TRANSPORT_BYTES,
    consultation_board_from_transport,
    consultation_board_summary,
)
from .consultation_packets import (
    MAX_CONSULTATION_PACKET_TRANSPORT_BYTES,
    consultation_packet_from_transport,
    consultation_packet_summary,
)
from .lesion_volume_comparisons import (
    MAX_TRANSPORT_BYTES as MAX_LESION_VOLUME_COMPARISON_TRANSPORT_BYTES,
    lesion_volume_comparison_from_transport,
    lesion_volume_comparison_summary,
)
from .lesion_volume_display import (
    lesion_volume_comparison_display_agent_summary,
    lesion_volume_comparison_display_context,
)
from .navigation import NAVIGATION_FRAGMENT_PREFIX
from .registration_display import (
    reviewed_registration_display_context,
    reviewed_registration_display_summary,
)
from .registration_reviews import (
    MAX_REQUEST_BYTES as MAX_REGISTRATION_REVIEW_REQUEST_BYTES,
    registration_qa_context,
    registration_review_bytes,
)
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


REVIEWED_REGISTRATION_BUNDLE_FILES = (
    "engine-report.json",
    "fixed.nrrd",
    "moving-to-fixed.tfm",
    "moving.nrrd",
    "registered-moving-coverage.nrrd",
    "registered-moving.nrrd",
    "registration.json",
)


def _distinct_token(excluded: set[str]) -> str:
    while True:
        candidate = secrets.token_urlsafe(24)
        if candidate not in excluded:
            return candidate


def _absolute_without_resolving_links(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path.expanduser())))


def _catalog_instances(catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    instances: dict[str, dict[str, Any]] = {}
    for study in catalog.get("studies", []):
        if not isinstance(study, dict):
            continue
        for series in study.get("series", []):
            if not isinstance(series, dict):
                continue
            for instance in series.get("instances", []):
                if isinstance(instance, dict) and isinstance(instance.get("id"), str):
                    instances[instance["id"]] = instance
    return instances


def _guard_instance_sources(
    catalog: dict[str, Any], registry: dict[str, Path]
) -> tuple[dict[str, Path], dict[str, dict[str, Any]]]:
    catalog_instances = _catalog_instances(catalog)
    guarded_registry: dict[str, Path] = {}
    guards: dict[str, dict[str, Any]] = {}
    for instance_id, requested_path in registry.items():
        path = _absolute_without_resolving_links(requested_path)
        descriptor = os.open(
            path,
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            metadata = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("indexed DICOM source must be a regular file")
        catalog_instance = catalog_instances.get(instance_id, {})
        expected_bytes = catalog_instance.get("bytes")
        if expected_bytes is not None and expected_bytes != metadata.st_size:
            raise ValueError("indexed DICOM source changed after cataloging")
        expected_sha256 = catalog_instance.get("sha256")
        if expected_sha256 is not None and (
            not isinstance(expected_sha256, str)
            or len(expected_sha256) != 64
            or any(character not in "0123456789abcdef" for character in expected_sha256)
        ):
            raise ValueError("indexed DICOM source has an invalid catalog hash")
        guarded_registry[instance_id] = path
        guards[instance_id] = {
            "device": metadata.st_dev,
            "inode": metadata.st_ino,
            "bytes": metadata.st_size,
            "mtime_ns": metadata.st_mtime_ns,
            "ctime_ns": metadata.st_ctime_ns,
            "sha256": expected_sha256,
        }
    return guarded_registry, guards


def _path_metadata_guard(path: Path) -> dict[str, Any]:
    metadata = path.lstat()
    return {
        "device": metadata.st_dev,
        "inode": metadata.st_ino,
        "mode": metadata.st_mode,
        "uid": metadata.st_uid,
        "links": metadata.st_nlink,
        "bytes": metadata.st_size,
        "mtime_ns": metadata.st_mtime_ns,
        "ctime_ns": metadata.st_ctime_ns,
    }


def _reviewed_registration_input_guards(
    bundle: Path,
    review: Path,
) -> list[tuple[Path, dict[str, Any]]]:
    paths = [
        bundle,
        review,
        *(bundle / name for name in REVIEWED_REGISTRATION_BUNDLE_FILES),
    ]
    return [(path, _path_metadata_guard(path)) for path in paths]


def _metadata_guards_unchanged(
    guards: list[tuple[Path, dict[str, Any]]],
) -> bool:
    try:
        return all(_path_metadata_guard(path) == expected for path, expected in guards)
    except OSError:
        return False


def _registration_agent_summary(
    context: dict[str, Any] | None,
) -> dict[str, Any]:
    if context is None:
        return {
            "schema_version": "2.0.0",
            "available": False,
            "artifact_type": "registration_qa_summary",
            "qa_status": "unavailable",
            "display_unlocked": False,
            "human_preview_required": True,
            "sampling_support_mask_required": True,
            "external_api_required": False,
        }
    return {
        "schema_version": context["schema_version"],
        "available": True,
        "artifact_type": "registration_qa_summary",
        "job_id": context["job_id"],
        "modality": context["source"]["modality"],
        "qa_status": "pending_human_review",
        "display_unlocked": False,
        "human_preview_required": True,
        "sampling_support_mask_required": True,
        "sampling_support_mask_available": context.get("coverage_mask") is not None,
        "external_api_required": False,
        "source_manifest_sha256": context["source"]["manifest_sha256"],
        "next_action": (
            "Open the separate browser-capability QA preview; bearer API access "
            "cannot approve registration."
        ),
    }


class ScanViewServer(ThreadingHTTPServer):
    catalog: dict[str, Any]
    registry: dict[str, Path]
    source_root: Path | None
    instance_guards: dict[str, dict[str, Any]]
    token: str
    browser_bootstrap_token: str
    browser_session_token: str
    ui_dist: Path | None
    viewer_state_lock: threading.Lock
    viewer_state: dict[str, Any] | None
    viewer_state_received_at: str | None
    viewer_state_received_monotonic: float | None
    viewer_state_revoked_publishers: set[str]
    registration_bundle: Path | None
    registration_context: dict[str, Any] | None
    registration_review: Path | None
    reviewed_registration_context: dict[str, Any] | None
    reviewed_registration_guards: list[tuple[Path, dict[str, Any]]]
    registration_agent_summary: dict[str, Any]
    registration_review_lock: threading.Lock
    registration_review_request_sha256: str | None
    registration_review_payload: bytes | None
    registration_review_filename: str | None
    lesion_volume_comparison: Path | None
    lesion_volume_display_context: dict[str, Any] | None
    lesion_volume_display_masks: dict[str, bytes]
    lesion_volume_display_guard: dict[str, Any] | None
    lesion_volume_display_instance_ids: set[str]
    lesion_volume_display_agent_summary: dict[str, Any]

    def reviewed_registration_inputs_unchanged(self) -> bool:
        if self.registration_review is None:
            return True
        if self.reviewed_registration_context is None or not self.reviewed_registration_guards:
            return False
        return _metadata_guards_unchanged(self.reviewed_registration_guards)

    def lesion_volume_display_inputs_unchanged(self) -> bool:
        if self.lesion_volume_comparison is None:
            return True
        if (
            self.lesion_volume_display_context is None
            or self.lesion_volume_display_guard is None
        ):
            return False
        try:
            if (
                _path_metadata_guard(self.lesion_volume_comparison)
                != self.lesion_volume_display_guard
            ):
                return False
            for instance_id in self.lesion_volume_display_instance_ids:
                path = self.registry.get(instance_id)
                guard = self.instance_guards.get(instance_id)
                if path is None or guard is None:
                    return False
                metadata = path.lstat()
                observed = {
                    "device": metadata.st_dev,
                    "inode": metadata.st_ino,
                    "bytes": metadata.st_size,
                    "mtime_ns": metadata.st_mtime_ns,
                    "ctime_ns": metadata.st_ctime_ns,
                }
                if not stat.S_ISREG(metadata.st_mode) or any(
                    observed[field] != guard[field] for field in observed
                ):
                    return False
        except OSError:
            return False
        return True

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
        return bool(
            session
            and secrets.compare_digest(
                session.value, self.server.browser_session_token
            )
        )

    def _browser_authorized(self) -> bool:
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
        except ValueError:
            return False
        session = cookie.get("scanview_session")
        return bool(
            session
            and secrets.compare_digest(
                session.value, self.server.browser_session_token
            )
        )

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
            supplied_values[0], self.server.browser_bootstrap_token
        ):
            return False
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", "/")
        cookie = SimpleCookie()
        cookie["scanview_session"] = self.server.browser_session_token
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
        if path == "/v1/lesion-volume-comparison-display":
            summary = self.server.lesion_volume_display_agent_summary
            if (
                self.server.lesion_volume_display_context is not None
                and not self.server.lesion_volume_display_inputs_unchanged()
            ):
                summary = lesion_volume_comparison_display_agent_summary(
                    None,
                    configured=True,
                    error="validated comparison or native DICOM inputs changed after startup",
                )
            self._send_json(summary)
            return
        if path == "/v1/lesion-volume-comparison-display/context":
            if not self._browser_authorized():
                self._send_json(
                    {"error": "browser_session_required"}, HTTPStatus.FORBIDDEN
                )
                return
            if self.server.lesion_volume_comparison is None:
                self._send_json({"error": "not_found"}, HTTPStatus.NOT_FOUND)
                return
            if self.server.lesion_volume_display_context is None:
                self._send_json(
                    {"error": "native_boundary_display_locked"}, HTTPStatus.LOCKED
                )
                return
            if not self.server.lesion_volume_display_inputs_unchanged():
                self._send_json(
                    {"error": "native_boundary_display_inputs_changed"},
                    HTTPStatus.LOCKED,
                )
                return
            self._send_json(self.server.lesion_volume_display_context)
            return
        lesion_mask_prefix = "/v1/lesion-volume-comparison-display/masks/"
        if path.startswith(lesion_mask_prefix):
            self._send_lesion_volume_display_mask(
                path.removeprefix(lesion_mask_prefix)
            )
            return
        if path == "/v1/registration-qa":
            summary = self.server.registration_agent_summary
            if (
                self.server.reviewed_registration_context is not None
                and not self.server.reviewed_registration_inputs_unchanged()
            ):
                summary = {
                    **summary,
                    "available": False,
                    "display_status": "invalid",
                    "display_authorized": False,
                    "allowed_display_modes": [],
                    "errors": ["reviewed registration inputs changed after startup"],
                }
            self._send_json(summary)
            return
        if path == "/v1/registration-qa/preview":
            if not self._browser_authorized():
                self._send_json({"error": "browser_session_required"}, HTTPStatus.FORBIDDEN)
                return
            if self.server.registration_context is None:
                self._send_json({"error": "not_found"}, HTTPStatus.NOT_FOUND)
                return
            self._send_json(self.server.registration_context)
            return
        registration_file_prefix = "/v1/registration-qa/files/"
        if path.startswith(registration_file_prefix):
            self._send_registration_qa_file(
                path.removeprefix(registration_file_prefix)
            )
            return
        if path == "/v1/reviewed-registration/display":
            if not self._browser_authorized():
                self._send_json({"error": "browser_session_required"}, HTTPStatus.FORBIDDEN)
                return
            if self.server.reviewed_registration_context is None:
                if self.server.registration_review is not None:
                    self._send_json(
                        {"error": "reviewed_registration_locked"},
                        HTTPStatus.LOCKED,
                    )
                else:
                    self._send_json({"error": "not_found"}, HTTPStatus.NOT_FOUND)
                return
            if not self.server.reviewed_registration_inputs_unchanged():
                self._send_json(
                    {"error": "reviewed_registration_changed"},
                    HTTPStatus.LOCKED,
                )
                return
            self._send_json(self.server.reviewed_registration_context)
            return
        reviewed_registration_file_prefix = "/v1/reviewed-registration/files/"
        if path.startswith(reviewed_registration_file_prefix):
            self._send_reviewed_registration_file(
                path.removeprefix(reviewed_registration_file_prefix)
            )
            return
        prefix = "/v1/instances/"
        if path.startswith(prefix):
            self._send_instance_file(path[len(prefix) :])
            return
        self._send_json({"error": "not_found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/v1/viewer-state":
            self._handle_viewer_state_post()
            return
        if path == "/v1/registration-reviews":
            self._handle_registration_review_post()
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
            "/v1/lesion-volume-comparisons": (
                "application/vnd.scanview.lesion-volume-comparison-input+zip",
                MAX_LESION_VOLUME_COMPARISON_TRANSPORT_BYTES,
            ),
            "/v1/consultation-packets": (
                "application/vnd.scanview.consultation-input+zip",
                MAX_CONSULTATION_PACKET_TRANSPORT_BYTES,
            ),
            "/v1/consultation-boards": (
                "application/vnd.scanview.consultation-board-input+zip",
                MAX_BOARD_TRANSPORT_BYTES,
            ),
        }
        if path not in supported:
            self._send_json({"error": "not_found"}, HTTPStatus.NOT_FOUND)
            return
        if path == "/v1/lesion-volume-comparisons" and self.server.source_root is None:
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
            elif path == "/v1/comparison-reviews":
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
            elif path == "/v1/lesion-volume-comparisons":
                if self.server.source_root is None:
                    raise ValueError("local DICOM source root is unavailable")
                payload = lesion_volume_comparison_from_transport(
                    body,
                    self.server.source_root,
                    catalog=self.server.catalog,
                    created_at=created_at,
                )
                summary = lesion_volume_comparison_summary(
                    io.BytesIO(payload),
                    self.server.source_root,
                    catalog=self.server.catalog,
                )
                if not summary["valid"]:
                    raise ValueError(
                        "assembled lesion-volume comparison failed local integrity validation"
                    )
                filename_prefix = "scanview-lesion-volume-comparison"
            elif path == "/v1/consultation-packets":
                payload = consultation_packet_from_transport(
                    body,
                    self.server.catalog,
                    self.server.registry,
                    created_at=created_at,
                )
                summary = consultation_packet_summary(io.BytesIO(payload))
                if not summary["valid"]:
                    raise ValueError(
                        "assembled consultation packet failed local integrity validation"
                    )
                filename_prefix = "scanview-consultation-packet"
            else:
                payload = consultation_board_from_transport(
                    body,
                    self.server.catalog,
                    self.server.registry,
                    created_at=created_at,
                )
                summary = consultation_board_summary(io.BytesIO(payload))
                if not summary["valid"]:
                    raise ValueError(
                        "assembled consultation board failed local integrity validation"
                    )
                filename_prefix = "scanview-consultation-board"
        except ValueError as error:
            self._send_json(
                {
                    "error": {
                        "/v1/visit-packets": "invalid_visit_packet_input",
                        "/v1/comparison-reviews": "invalid_comparison_review_input",
                        "/v1/lesion-volume-comparisons": "invalid_lesion_volume_comparison_input",
                        "/v1/consultation-packets": "invalid_consultation_packet_input",
                        "/v1/consultation-boards": "invalid_consultation_board_input",
                    }[path],
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

    def _send_registration_qa_file(self, filename: str) -> None:
        self._send_registration_file(
            filename,
            context=self.server.registration_context,
            allowed={
                "fixed.nrrd",
                "moving.nrrd",
                "registered-moving-coverage.nrrd",
                "registered-moving.nrrd",
            },
        )

    def _send_lesion_volume_display_mask(self, role: str) -> None:
        if not self._browser_authorized():
            self._send_json(
                {"error": "browser_session_required"}, HTTPStatus.FORBIDDEN
            )
            return
        if role not in {"baseline", "followup"}:
            self._send_json({"error": "not_found"}, HTTPStatus.NOT_FOUND)
            return
        if self.server.lesion_volume_comparison is None:
            self._send_json({"error": "not_found"}, HTTPStatus.NOT_FOUND)
            return
        if (
            self.server.lesion_volume_display_context is None
            or not self.server.lesion_volume_display_inputs_unchanged()
        ):
            self._send_json(
                {"error": "native_boundary_display_locked"}, HTTPStatus.LOCKED
            )
            return
        payload = self.server.lesion_volume_display_masks.get(role)
        descriptor = self.server.lesion_volume_display_context["timepoints"][role][
            "mask"
        ]
        if (
            payload is None
            or len(payload) != descriptor["bytes"]
            or hashlib.sha256(payload).hexdigest() != descriptor["sha256"]
        ):
            self._send_json(
                {"error": "native_boundary_mask_integrity_failed"},
                HTTPStatus.LOCKED,
            )
            return
        self.send_response(HTTPStatus.OK)
        self.send_header(
            "Content-Type", "application/vnd.scanview.native-binary-mask"
        )
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("X-Content-SHA256", descriptor["sha256"])
        self._security_headers()
        self.end_headers()
        self.wfile.write(payload)

    def _send_instance_file(self, instance_id: str) -> None:
        source = self.server.registry.get(instance_id)
        guard = self.server.instance_guards.get(instance_id)
        if source is None or guard is None:
            self._send_json({"error": "not_found"}, HTTPStatus.NOT_FOUND)
            return
        descriptor = -1
        headers_sent = False
        try:
            descriptor = os.open(
                source,
                os.O_RDONLY
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0),
            )
            metadata = os.fstat(descriptor)
            observed = {
                "device": metadata.st_dev,
                "inode": metadata.st_ino,
                "bytes": metadata.st_size,
                "mtime_ns": metadata.st_mtime_ns,
                "ctime_ns": metadata.st_ctime_ns,
            }
            if not stat.S_ISREG(metadata.st_mode) or any(
                observed[field] != guard[field] for field in observed
            ):
                raise ValueError("indexed DICOM source changed")

            digest = hashlib.sha256()
            copied = 0
            with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode="w+b") as snapshot:
                while chunk := os.read(descriptor, 1024 * 1024):
                    copied += len(chunk)
                    if copied > guard["bytes"]:
                        raise ValueError("indexed DICOM source grew while it was read")
                    digest.update(chunk)
                    snapshot.write(chunk)
                final_metadata = os.fstat(descriptor)
                final_observed = {
                    "device": final_metadata.st_dev,
                    "inode": final_metadata.st_ino,
                    "bytes": final_metadata.st_size,
                    "mtime_ns": final_metadata.st_mtime_ns,
                    "ctime_ns": final_metadata.st_ctime_ns,
                }
                if copied != guard["bytes"] or any(
                    final_observed[field] != guard[field] for field in final_observed
                ):
                    raise ValueError("indexed DICOM source changed while it was read")
                observed_sha256 = digest.hexdigest()
                if guard["sha256"] is not None and observed_sha256 != guard["sha256"]:
                    raise ValueError("indexed DICOM source hash changed")
                snapshot.seek(0)
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/dicom")
                self.send_header("Content-Length", str(copied))
                self.send_header("X-Content-SHA256", observed_sha256)
                self._security_headers()
                self.end_headers()
                headers_sent = True
                while chunk := snapshot.read(1024 * 1024):
                    self.wfile.write(chunk)
        except (ValueError, OSError, BrokenPipeError):
            if not headers_sent:
                self._send_json(
                    {"error": "dicom_source_changed"},
                    HTTPStatus.CONFLICT,
                )
        finally:
            if descriptor >= 0:
                os.close(descriptor)

    def _send_reviewed_registration_file(self, filename: str) -> None:
        if (
            self.server.reviewed_registration_context is not None
            and not self.server.reviewed_registration_inputs_unchanged()
        ):
            self._send_json(
                {"error": "reviewed_registration_changed"},
                HTTPStatus.CONFLICT,
            )
            return
        self._send_registration_file(
            filename,
            context=self.server.reviewed_registration_context,
            allowed={
                "fixed.nrrd",
                "registered-moving-coverage.nrrd",
                "registered-moving.nrrd",
            },
        )

    def _send_registration_file(
        self,
        filename: str,
        *,
        context: dict[str, Any] | None,
        allowed: set[str],
    ) -> None:
        if (
            filename not in allowed
            or self.server.registration_bundle is None
            or context is None
        ):
            self._send_json({"error": "not_found"}, HTTPStatus.NOT_FOUND)
            return
        if not self._browser_authorized():
            self._send_json({"error": "browser_session_required"}, HTTPStatus.FORBIDDEN)
            return
        descriptor = -1
        headers_sent = False
        try:
            candidates = list(context["volumes"].values())
            coverage_mask = context.get("coverage_mask")
            if isinstance(coverage_mask, dict):
                candidates.append(coverage_mask)
            volume = next(item for item in candidates if item["filename"] == filename)
            source = self.server.registration_bundle / filename
            descriptor = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or stat.S_IMODE(metadata.st_mode) != 0o600
                or metadata.st_uid != os.getuid()
                or metadata.st_nlink != 1
                or metadata.st_size != volume["bytes"]
            ):
                raise ValueError("registration volume changed")
            digest = hashlib.sha256()
            while chunk := os.read(descriptor, 1024 * 1024):
                digest.update(chunk)
            if digest.hexdigest() != volume["sha256"]:
                raise ValueError("registration volume changed")
            os.lseek(descriptor, 0, os.SEEK_SET)
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/vnd.nrrd")
            self.send_header("Content-Length", str(volume["bytes"]))
            self.send_header("X-Content-SHA256", volume["sha256"])
            self._security_headers()
            self.end_headers()
            headers_sent = True
            while chunk := os.read(descriptor, 1024 * 1024):
                self.wfile.write(chunk)
        except (KeyError, StopIteration, TypeError, ValueError):
            if not headers_sent:
                self._send_json(
                    {"error": "registration_bundle_invalid"},
                    HTTPStatus.CONFLICT,
                )
        except (BrokenPipeError, OSError):
            if not headers_sent:
                self._send_json(
                    {"error": "registration_bundle_invalid"},
                    HTTPStatus.CONFLICT,
                )
        finally:
            if descriptor >= 0:
                os.close(descriptor)

    def _handle_registration_review_post(self) -> None:
        if not self._browser_authorized():
            self._send_json({"error": "browser_session_required"}, HTTPStatus.FORBIDDEN)
            return
        if not self._same_origin():
            self._send_json({"error": "same_origin_required"}, HTTPStatus.FORBIDDEN)
            return
        if (
            self.server.registration_bundle is None
            or self.server.registration_context is None
        ):
            self._send_json({"error": "not_found"}, HTTPStatus.NOT_FOUND)
            return
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/vnd.scanview.registration-review-input+json":
            self._send_json(
                {"error": "unsupported_media_type"}, HTTPStatus.UNSUPPORTED_MEDIA_TYPE
            )
            return
        try:
            content_length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            self._send_json({"error": "content_length_required"}, HTTPStatus.LENGTH_REQUIRED)
            return
        if content_length <= 0 or content_length > MAX_REGISTRATION_REVIEW_REQUEST_BYTES:
            self._send_json({"error": "request_too_large"}, HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            return
        body = self.rfile.read(content_length)
        if len(body) != content_length:
            self._send_json({"error": "incomplete_request"}, HTTPStatus.BAD_REQUEST)
            return
        request_sha256 = hashlib.sha256(body).hexdigest()
        with self.server.registration_review_lock:
            if self.server.registration_review_request_sha256 is not None:
                if not secrets.compare_digest(
                    request_sha256, self.server.registration_review_request_sha256
                ):
                    self._send_json(
                        {"error": "registration_review_already_created"},
                        HTTPStatus.CONFLICT,
                    )
                    return
                payload = self.server.registration_review_payload
                filename = self.server.registration_review_filename
                if payload is None or filename is None:
                    self._send_json(
                        {"error": "registration_review_unavailable"},
                        HTTPStatus.CONFLICT,
                    )
                    return
            else:
                created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                try:
                    payload = registration_review_bytes(
                        self.server.registration_bundle,
                        body,
                        created_at=created_at,
                    )
                except OSError:
                    self._send_json(
                        {
                            "error": "invalid_registration_review",
                            "detail": "registration bundle is unavailable",
                        },
                        HTTPStatus.UNPROCESSABLE_ENTITY,
                    )
                    return
                except ValueError as error:
                    self._send_json(
                        {"error": "invalid_registration_review", "detail": str(error)},
                        HTTPStatus.UNPROCESSABLE_ENTITY,
                    )
                    return
                timestamp = created_at.replace("-", "").replace(":", "").split(".", 1)[0] + "Z"
                filename = f"scanview-registration-review-{timestamp}.json"
                self.server.registration_review_request_sha256 = request_sha256
                self.server.registration_review_payload = payload
                self.server.registration_review_filename = filename
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/vnd.scanview.registration-review+json")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(payload)))
        self._security_headers()
        self.end_headers()
        try:
            self.wfile.write(payload)
        except OSError:
            return

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
    registration_bundle: Path | None = None,
    registration_review: Path | None = None,
    lesion_volume_comparison: Path | None = None,
    source_root: Path | None = None,
) -> ScanViewServer:
    if host not in {"127.0.0.1", "::1", "localhost"}:
        raise ValueError("ScanView only supports loopback binding in this release")
    guarded_registry, instance_guards = _guard_instance_sources(catalog, registry)
    resolved_source_root = (
        source_root.expanduser().resolve(strict=True) if source_root is not None else None
    )
    if resolved_source_root is not None and not resolved_source_root.is_dir():
        raise ValueError("ScanView DICOM source root must be a directory")
    resolved_ui = ui_dist.expanduser().resolve(strict=True) if ui_dist else None
    if resolved_ui is not None and not (resolved_ui / "index.html").is_file():
        raise ValueError(f"ScanView UI bundle is missing index.html: {resolved_ui}")
    if registration_review is not None and registration_bundle is None:
        raise ValueError("--registration-review requires --registration-bundle")
    if lesion_volume_comparison is not None and registration_bundle is not None:
        raise ValueError(
            "--lesion-volume-comparison cannot be combined with a registration display mode"
        )
    if lesion_volume_comparison is not None and resolved_source_root is None:
        raise ValueError("--lesion-volume-comparison requires the local DICOM source root")
    resolved_registration = None
    resolved_registration_review = None
    cached_registration_context = None
    cached_reviewed_registration_context = None
    reviewed_registration_guards: list[tuple[Path, dict[str, Any]]] = []
    cached_registration_summary = _registration_agent_summary(None)
    if registration_bundle is not None:
        if registration_review is None:
            resolved_registration = _absolute_without_resolving_links(
                registration_bundle
            )
            cached_registration_context = registration_qa_context(resolved_registration)
            cached_registration_summary = _registration_agent_summary(
                cached_registration_context
            )
        else:
            # Reviewed-display mode is deliberately separate from pending QA. Missing,
            # rejected, malformed, or tampered review inputs leave the ordinary DICOM
            # server running but never republish the QA preview or registration pixels.
            resolved_registration = _absolute_without_resolving_links(
                registration_bundle
            )
            resolved_registration_review = _absolute_without_resolving_links(
                registration_review
            )
            cached_registration_summary = reviewed_registration_display_summary(
                resolved_registration,
                resolved_registration_review,
            )
            if cached_registration_summary.get("display_authorized") is True:
                try:
                    candidate_guards = _reviewed_registration_input_guards(
                        resolved_registration,
                        resolved_registration_review,
                    )
                    cached_reviewed_registration_context = (
                        reviewed_registration_display_context(
                            resolved_registration,
                            resolved_registration_review,
                        )
                    )
                    if not _metadata_guards_unchanged(candidate_guards):
                        raise ValueError(
                            "reviewed registration evidence changed during validation"
                        )
                    reviewed_registration_guards = candidate_guards
                except (KeyError, OSError, TypeError, ValueError):
                    cached_reviewed_registration_context = None
                    reviewed_registration_guards = []
                    cached_registration_summary = {
                        **cached_registration_summary,
                        "available": False,
                        "display_status": "invalid",
                        "display_authorized": False,
                        "allowed_display_modes": [],
                        "errors": [
                            "Reviewed registration display validation failed."
                        ],
                    }
    resolved_lesion_volume_comparison = None
    cached_lesion_volume_display_context = None
    cached_lesion_volume_display_masks: dict[str, bytes] = {}
    lesion_volume_display_guard = None
    lesion_volume_display_instance_ids: set[str] = set()
    cached_lesion_volume_display_summary = (
        lesion_volume_comparison_display_agent_summary(None, configured=False)
    )
    if lesion_volume_comparison is not None:
        resolved_lesion_volume_comparison = _absolute_without_resolving_links(
            lesion_volume_comparison
        )
        try:
            candidate_guard = _path_metadata_guard(
                resolved_lesion_volume_comparison
            )
            (
                cached_lesion_volume_display_context,
                cached_lesion_volume_display_masks,
            ) = lesion_volume_comparison_display_context(
                resolved_lesion_volume_comparison,
                resolved_source_root,
                catalog=catalog,
            )
            if (
                _path_metadata_guard(resolved_lesion_volume_comparison)
                != candidate_guard
            ):
                raise ValueError(
                    "lesion-volume comparison changed during startup validation"
                )
            lesion_volume_display_guard = candidate_guard
            lesion_volume_display_instance_ids = {
                instance_id
                for role in ("baseline", "followup")
                for instance_id in cached_lesion_volume_display_context["timepoints"][
                    role
                ]["ordered_instance_ids"]
            }
            if not lesion_volume_display_instance_ids.issubset(guarded_registry):
                raise ValueError(
                    "reviewed native boundary source instances are unavailable"
                )
            cached_lesion_volume_display_summary = (
                lesion_volume_comparison_display_agent_summary(
                    cached_lesion_volume_display_context, configured=True
                )
            )
        except (KeyError, OSError, TypeError, ValueError):
            cached_lesion_volume_display_context = None
            cached_lesion_volume_display_masks = {}
            lesion_volume_display_guard = None
            lesion_volume_display_instance_ids = set()
            cached_lesion_volume_display_summary = (
                lesion_volume_comparison_display_agent_summary(
                    None,
                    configured=True,
                    error="reviewed native-boundary display validation failed",
                )
            )
    server = ScanViewServer((host, port), Handler)
    server.catalog = catalog
    server.registry = guarded_registry
    server.source_root = resolved_source_root
    server.instance_guards = instance_guards
    server.token = token or secrets.token_urlsafe(24)
    server.browser_bootstrap_token = _distinct_token({server.token})
    server.browser_session_token = _distinct_token(
        {server.token, server.browser_bootstrap_token}
    )
    server.ui_dist = resolved_ui
    server.viewer_state_lock = threading.Lock()
    server.viewer_state = None
    server.viewer_state_received_at = None
    server.viewer_state_received_monotonic = None
    server.viewer_state_revoked_publishers = set()
    server.registration_bundle = resolved_registration
    server.registration_context = cached_registration_context
    server.registration_review = resolved_registration_review
    server.reviewed_registration_context = cached_reviewed_registration_context
    server.reviewed_registration_guards = reviewed_registration_guards
    server.registration_agent_summary = cached_registration_summary
    server.registration_review_lock = threading.Lock()
    server.registration_review_request_sha256 = None
    server.registration_review_payload = None
    server.registration_review_filename = None
    server.lesion_volume_comparison = resolved_lesion_volume_comparison
    server.lesion_volume_display_context = cached_lesion_volume_display_context
    server.lesion_volume_display_masks = cached_lesion_volume_display_masks
    server.lesion_volume_display_guard = lesion_volume_display_guard
    server.lesion_volume_display_instance_ids = lesion_volume_display_instance_ids
    server.lesion_volume_display_agent_summary = (
        cached_lesion_volume_display_summary
    )
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
    registration_bundle: Path | None = None,
    registration_review: Path | None = None,
    lesion_volume_comparison: Path | None = None,
    source_root: Path | None = None,
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
        registration_bundle=registration_bundle,
        registration_review=registration_review,
        lesion_volume_comparison=lesion_volume_comparison,
        source_root=source_root,
    )
    url_host = f"[{host}]" if ":" in host else host
    base_url = f"http://{url_host}:{server.server_port}"
    print(f"ScanView local source-read-only API: {base_url}")
    print(f"Bearer token: {server.token}")
    if server.ui_dist:
        session_url = (
            f"{base_url}/?session={quote(server.browser_bootstrap_token, safe='')}"
            f"{navigation_fragment or ''}"
        )
        print(f"ScanView local workspace: {session_url}")
        if open_browser:
            webbrowser.open(session_url)
    if server.registration_review is not None:
        registration_notice = (
            "Reviewed-registration display is browser-session-only and bound to "
            "the startup-validated review."
            if server.reviewed_registration_context is not None
            else "Reviewed-registration display is locked; ordinary DICOM remains available."
        )
    else:
        registration_notice = "Registration QA preview is human-session-only."
    if server.lesion_volume_comparison is not None:
        registration_notice = (
            "Reviewed native-boundary comparison is browser-session-only, "
            "unregistered, and bound to startup-validated local evidence."
            if server.lesion_volume_display_context is not None
            else "Reviewed native-boundary comparison display is locked; ordinary DICOM remains available."
        )
    print(
        "Source mutation and deletion are disabled; visit/review derivatives and opt-in "
        f"viewer state remain memory-only. {registration_notice} Press Ctrl-C to stop."
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
