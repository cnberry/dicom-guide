#!/usr/bin/env python3
"""Verify an extracted DICOM Guide offline bundle with the Python standard library."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path, PurePosixPath
from typing import Any


MAX_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_PAYLOAD_FILES = 128
MAX_PAYLOAD_FILE_BYTES = 256 * 1024 * 1024
MAX_PAYLOAD_TOTAL_BYTES = 512 * 1024 * 1024
SHA256 = re.compile(r"^[0-9a-f]{64}$")
MANIFEST_FIELDS = {
    "schema_version",
    "artifact_type",
    "project",
    "version",
    "supported_platforms",
    "requires_python",
    "runtime_network_required",
    "external_dicom_processing_api_required",
    "install_command",
    "launch_command",
    "runtime_dependencies",
    "integrity_scope",
    "files",
}


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

    return json.loads(data, object_pairs_hook=pairs, parse_constant=invalid_constant)


def _safe_relative_name(value: str) -> bool:
    path = PurePosixPath(value)
    return (
        bool(value)
        and len(value) <= 512
        and not path.is_absolute()
        and path.as_posix() == value
        and ".." not in path.parts
        and path.parts[0] != ".dicom-guide-runtime"
        and value != "bundle.json"
    )


def _read_stable(
    path: Path,
    expected_bytes: int | None = None,
    *,
    maximum_bytes: int = MAX_PAYLOAD_FILE_BYTES,
) -> tuple[bytes, str]:
    descriptor = -1
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("bundle payload is not a regular file")
        if expected_bytes is not None and before.st_size != expected_bytes:
            raise ValueError("bundle payload byte count changed")
        if before.st_size > maximum_bytes:
            raise ValueError("bundle payload exceeds the verification safety limit")
        content = bytearray()
        digest = hashlib.sha256()
        while chunk := os.read(descriptor, 1024 * 1024):
            content.extend(chunk)
            digest.update(chunk)
            if len(content) > maximum_bytes:
                raise ValueError("bundle payload exceeds the verification safety limit")
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
            raise ValueError("bundle payload changed while it was verified")
        return bytes(content), digest.hexdigest()
    except OSError as error:
        raise ValueError("bundle payload cannot be read safely") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _manifest(root: Path) -> dict[str, Any]:
    manifest_path = root / "bundle.json"
    if manifest_path.is_symlink():
        raise ValueError("bundle manifest must not be a symbolic link")
    content, _ = _read_stable(manifest_path, maximum_bytes=MAX_MANIFEST_BYTES)
    value = _strict_json(content)
    if not isinstance(value, dict) or set(value) != MANIFEST_FIELDS:
        raise ValueError("bundle manifest fields are incomplete or unsupported")
    expected = {
        "schema_version": "1.0.0",
        "artifact_type": "dicom_guide_offline_runtime_bundle",
        "project": "DICOM Guide",
        "version": "0.15.0",
        "supported_platforms": ["macos", "linux"],
        "requires_python": ">=3.11",
        "runtime_network_required": False,
        "external_dicom_processing_api_required": False,
        "install_command": "sh install.sh",
        "launch_command": "sh launch.sh '/absolute/path/to/DICOM'",
        "runtime_dependencies": [{"name": "pydicom", "version": "3.0.2"}],
        "integrity_scope": (
            "SHA-256 corruption evidence for bundle payloads; not a publisher "
            "signature or clinical authentication"
        ),
    }
    if any(value.get(key) != expected_value for key, expected_value in expected.items()):
        raise ValueError("bundle manifest contract is unsupported")
    return value


def _actual_payloads(root: Path) -> tuple[set[str], set[str]]:
    files: set[str] = set()
    directories: set[str] = set()
    runtime = root / ".dicom-guide-runtime"
    if runtime.exists() or runtime.is_symlink():
        if runtime.is_symlink() or not runtime.is_dir():
            raise ValueError("installed runtime path must be a local directory")
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if relative.parts[0] == ".dicom-guide-runtime":
            continue
        name = relative.as_posix()
        if path.is_symlink():
            raise ValueError(f"symbolic links are unsupported in the bundle: {name}")
        if path.is_file():
            files.add(name)
        elif path.is_dir():
            directories.add(name)
        else:
            raise ValueError(f"unsupported bundle entry: {name}")
    return files, directories


def verify_bundle(requested_root: Path) -> dict[str, Any]:
    requested_root = requested_root.expanduser()
    if requested_root.is_symlink():
        raise ValueError("bundle root must not be a symbolic link")
    root = requested_root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("bundle root must be a directory")
    manifest = _manifest(root)
    records = manifest.get("files")
    if not isinstance(records, dict) or not 1 <= len(records) <= MAX_PAYLOAD_FILES:
        raise ValueError("bundle file manifest is invalid")
    expected_files = set(records) | {"bundle.json"}
    expected_directories = {
        PurePosixPath(name).parent.as_posix()
        for name in records
        if PurePosixPath(name).parent.as_posix() != "."
    }
    actual_files, actual_directories = _actual_payloads(root)
    if actual_files != expected_files or actual_directories != expected_directories:
        raise ValueError("bundle entries do not exactly match the manifest")

    total = 0
    for name, record in records.items():
        if not isinstance(name, str) or not _safe_relative_name(name):
            raise ValueError("bundle manifest contains an unsafe payload path")
        if not isinstance(record, dict) or set(record) != {"byte_count", "sha256"}:
            raise ValueError(f"bundle file record is invalid: {name}")
        byte_count = record.get("byte_count")
        digest = record.get("sha256")
        if (
            not isinstance(byte_count, int)
            or isinstance(byte_count, bool)
            or byte_count <= 0
            or byte_count > MAX_PAYLOAD_FILE_BYTES
            or not isinstance(digest, str)
            or not SHA256.fullmatch(digest)
        ):
            raise ValueError(f"bundle file record is invalid: {name}")
        total += byte_count
        if total > MAX_PAYLOAD_TOTAL_BYTES:
            raise ValueError("bundle payload exceeds the verification safety limit")
        _, observed_digest = _read_stable(root / PurePosixPath(name), byte_count)
        if observed_digest != digest:
            raise ValueError(f"bundle payload digest disagrees with the manifest: {name}")
    return {
        "valid": True,
        "artifact_type": manifest["artifact_type"],
        "version": manifest["version"],
        "payload_files": len(records),
        "runtime_network_required": False,
        "external_dicom_processing_api_required": False,
    }


def main() -> None:
    root = Path(sys.argv[1]) if len(sys.argv) == 2 else Path(__file__).resolve().parent
    if len(sys.argv) > 2:
        raise SystemExit("usage: verify.py [EXTRACTED_BUNDLE_DIRECTORY]")
    try:
        result = verify_bundle(root)
    except (json.JSONDecodeError, OSError, ValueError) as error:
        print(f"DICOM Guide offline bundle verification failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
