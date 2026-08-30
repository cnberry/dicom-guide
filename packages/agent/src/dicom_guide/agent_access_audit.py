from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import stat
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1.0.0"
ARTIFACT_TYPE = "dicom-guide.agent-access-audit-event"
OUTCOME = "bearer_authorized_request"
ZERO_SHA256 = "0" * 64
MAX_AUDIT_BYTES = 64 * 1024 * 1024
MAX_EVENT_BYTES = 4096
SHA256 = re.compile(r"^[0-9a-f]{64}$")
TIMESTAMP = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
OPERATIONS = (
    "manifest_read",
    "viewer_state_read",
    "viewer_control_read",
    "viewer_control_command",
    "comparison_candidates_read",
    "longitudinal_readiness_read",
    "presentation_states_read",
    "source_segmentations_read",
    "native_boundary_summary_read",
    "registration_status_read",
    "native_dicom_instance_read",
    "browser_only_native_boundary_context_attempt",
    "browser_only_native_boundary_mask_attempt",
    "browser_only_source_segmentation_mask_attempt",
    "browser_only_registration_context_attempt",
    "browser_only_registration_volume_attempt",
)
EVENT_FIELDS = {
    "schema_version",
    "artifact_type",
    "sequence",
    "occurred_at",
    "authority",
    "operation",
    "outcome",
    "local_only",
    "contains_patient_content",
    "contains_token",
    "contains_path",
    "contains_request_target",
    "previous_event_sha256",
    "event_sha256",
}


def _canonical(value: dict[str, Any]) -> bytes:
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _strict_json(data: bytes) -> Any:
    def pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in values:
            if key in result:
                raise ValueError(f"duplicate JSON field: {key}")
            result[key] = value
        return result

    def invalid_constant(value: str) -> None:
        raise ValueError(f"unsupported JSON number: {value}")

    return json.loads(
        data.decode("utf-8"),
        object_pairs_hook=pairs,
        parse_constant=invalid_constant,
    )


def _event_base(event: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in event.items() if key != "event_sha256"}


def _validate_event(
    event: Any,
    *,
    expected_sequence: int,
    expected_previous_sha256: str,
) -> str:
    if not isinstance(event, dict) or set(event) != EVENT_FIELDS:
        raise ValueError("audit event fields are incomplete or unsupported")
    if (
        event["schema_version"] != SCHEMA_VERSION
        or event["artifact_type"] != ARTIFACT_TYPE
        or type(event["sequence"]) is not int
        or event["sequence"] != expected_sequence
        or not isinstance(event["occurred_at"], str)
        or not TIMESTAMP.fullmatch(event["occurred_at"])
        or event["authority"] != "bearer_agent"
        or event["operation"] not in OPERATIONS
        or event["outcome"] != OUTCOME
        or event["local_only"] is not True
        or event["contains_patient_content"] is not False
        or event["contains_token"] is not False
        or event["contains_path"] is not False
        or event["contains_request_target"] is not False
        or event["previous_event_sha256"] != expected_previous_sha256
        or not isinstance(event["event_sha256"], str)
        or not SHA256.fullmatch(event["event_sha256"])
    ):
        raise ValueError("audit event contract is invalid")
    try:
        datetime.strptime(event["occurred_at"], "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as error:
        raise ValueError("audit event timestamp is invalid") from error
    digest = hashlib.sha256(_canonical(_event_base(event))).hexdigest()
    if event["event_sha256"] != digest:
        raise ValueError("audit event hash is invalid")
    return digest


def _validate_payload(payload: bytes) -> tuple[int, str]:
    if len(payload) > MAX_AUDIT_BYTES:
        raise ValueError("audit log exceeds the supported size")
    if not payload:
        return 0, ZERO_SHA256
    if not payload.endswith(b"\n"):
        raise ValueError("audit log has a partial final event")
    previous = ZERO_SHA256
    count = 0
    for line in payload.splitlines():
        if not line or len(line) > MAX_EVENT_BYTES:
            raise ValueError("audit log contains an invalid event size")
        try:
            event = _strict_json(line)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
            raise ValueError("audit log contains invalid strict JSON") from error
        count += 1
        previous = _validate_event(
            event,
            expected_sequence=count,
            expected_previous_sha256=previous,
        )
    return count, previous


def _validate_descriptor(descriptor: int) -> os.stat_result:
    metadata = os.fstat(descriptor)
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError("agent audit log must be a regular file")
    if metadata.st_uid != os.getuid() or metadata.st_nlink != 1:
        raise ValueError("agent audit log must be owner-controlled and unlinked")
    if stat.S_IMODE(metadata.st_mode) & 0o077:
        raise ValueError("agent audit log permissions must exclude group and other access")
    if metadata.st_size > MAX_AUDIT_BYTES:
        raise ValueError("audit log exceeds the supported size")
    return metadata


def _read_descriptor(descriptor: int) -> bytes:
    before = _validate_descriptor(descriptor)
    os.lseek(descriptor, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    remaining = before.st_size
    while remaining:
        chunk = os.read(descriptor, min(1024 * 1024, remaining))
        if not chunk:
            raise ValueError("audit log changed while it was read")
        chunks.append(chunk)
        remaining -= len(chunk)
    after = os.fstat(descriptor)
    identity_before = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    identity_after = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    )
    if identity_before != identity_after:
        raise ValueError("audit log changed while it was read")
    return b"".join(chunks)


def _safe_open(path: Path, flags: int, mode: int | None = None) -> int:
    absolute = Path(os.path.abspath(os.fspath(path.expanduser())))
    requested_flags = flags | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        if mode is None:
            return os.open(absolute, requested_flags)
        return os.open(absolute, requested_flags, mode)
    except OSError as error:
        raise ValueError("agent audit log cannot be opened safely") from error


def agent_access_audit_summary(path: Path) -> dict[str, Any]:
    descriptor = -1
    try:
        descriptor = _safe_open(path, os.O_RDONLY)
        payload = _read_descriptor(descriptor)
        count, last_sha256 = _validate_payload(payload)
        return {
            "valid": True,
            "errors": [],
            "schema_version": SCHEMA_VERSION,
            "artifact_type": "dicom-guide.agent-access-audit-summary",
            "event_count": count,
            "first_sequence": 1 if count else None,
            "last_sequence": count if count else None,
            "last_event_sha256": last_sha256 if count else None,
            "local_only": True,
            "contains_patient_content": False,
            "contains_tokens": False,
            "contains_paths": False,
            "contains_request_targets": False,
        }
    except (OSError, TypeError, ValueError) as error:
        return {
            "valid": False,
            "errors": [str(error)],
            "schema_version": SCHEMA_VERSION,
            "artifact_type": "dicom-guide.agent-access-audit-summary",
            "event_count": 0,
            "first_sequence": None,
            "last_sequence": None,
            "last_event_sha256": None,
            "local_only": True,
            "contains_patient_content": False,
            "contains_tokens": False,
            "contains_paths": False,
            "contains_request_targets": False,
        }
    finally:
        if descriptor >= 0:
            os.close(descriptor)


class AgentAccessAudit:
    def __init__(
        self,
        descriptor: int,
        sequence: int,
        previous_sha256: str,
        expected_size: int,
        expected_mtime_ns: int,
        expected_ctime_ns: int,
    ) -> None:
        self._descriptor = descriptor
        self._sequence = sequence
        self._previous_sha256 = previous_sha256
        self._expected_size = expected_size
        self._expected_mtime_ns = expected_mtime_ns
        self._expected_ctime_ns = expected_ctime_ns
        self._failed = False
        self._lock = threading.Lock()

    @classmethod
    def open(cls, path: Path) -> "AgentAccessAudit":
        descriptor = _safe_open(path, os.O_RDWR | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                raise ValueError("agent audit log is already in use") from error
            payload = _read_descriptor(descriptor)
            sequence, previous = _validate_payload(payload)
            metadata = os.fstat(descriptor)
            return cls(
                descriptor,
                sequence,
                previous,
                len(payload),
                metadata.st_mtime_ns,
                metadata.st_ctime_ns,
            )
        except BaseException:
            os.close(descriptor)
            raise

    def record(self, operation: str) -> dict[str, Any]:
        if operation not in OPERATIONS:
            raise ValueError("agent audit operation is unsupported")
        with self._lock:
            if self._descriptor < 0 or self._failed:
                raise OSError("agent audit log is unavailable")
            sequence = self._sequence + 1
            base = {
                "schema_version": SCHEMA_VERSION,
                "artifact_type": ARTIFACT_TYPE,
                "sequence": sequence,
                "occurred_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "authority": "bearer_agent",
                "operation": operation,
                "outcome": OUTCOME,
                "local_only": True,
                "contains_patient_content": False,
                "contains_token": False,
                "contains_path": False,
                "contains_request_target": False,
                "previous_event_sha256": self._previous_sha256,
            }
            digest = hashlib.sha256(_canonical(base)).hexdigest()
            event = {**base, "event_sha256": digest}
            payload = _canonical(event) + b"\n"
            if len(payload) > MAX_EVENT_BYTES:
                raise OSError("agent audit event exceeds the supported size")
            metadata = _validate_descriptor(self._descriptor)
            if (
                metadata.st_size != self._expected_size
                or metadata.st_mtime_ns != self._expected_mtime_ns
                or metadata.st_ctime_ns != self._expected_ctime_ns
                or self._expected_size + len(payload) > MAX_AUDIT_BYTES
            ):
                self._failed = True
                raise OSError("agent audit log changed or reached its size limit")
            try:
                written = 0
                while written < len(payload):
                    count = os.write(self._descriptor, payload[written:])
                    if count < 1:
                        raise OSError("agent audit event could not be appended")
                    written += count
                os.fsync(self._descriptor)
            except OSError:
                self._failed = True
                raise
            self._sequence = sequence
            self._previous_sha256 = digest
            self._expected_size += len(payload)
            metadata = os.fstat(self._descriptor)
            self._expected_mtime_ns = metadata.st_mtime_ns
            self._expected_ctime_ns = metadata.st_ctime_ns
            return event

    def close(self) -> None:
        with self._lock:
            if self._descriptor < 0:
                return
            descriptor = self._descriptor
            self._descriptor = -1
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)

    @property
    def event_count(self) -> int:
        with self._lock:
            return self._sequence
