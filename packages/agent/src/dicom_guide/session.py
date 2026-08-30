from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path
from typing import Any


def session_path() -> Path:
    explicit = os.environ.get("DICOM_GUIDE_STATE_HOME")
    if explicit:
        base = Path(explicit).expanduser()
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "DICOM Guide"
    elif runtime_home := os.environ.get("XDG_RUNTIME_DIR"):
        base = Path(runtime_home) / "dicom-guide"
    else:
        base = Path("/tmp") / f"dicom-guide-{os.getuid()}"
    return base / "session.json"


def write_session(base_url: str, token: str) -> Path:
    path = session_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    payload = {
        "schema_version": "1.0.0",
        "base_url": base_url,
        "token": token,
        "pid": os.getpid(),
    }
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
        path.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def active_session() -> dict[str, Any] | None:
    path = session_path()
    try:
        if stat.S_IMODE(path.stat().st_mode) != 0o600:
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
        if (
            not isinstance(value, dict)
            or value.get("schema_version") != "1.0.0"
            or not isinstance(value.get("base_url"), str)
            or not isinstance(value.get("token"), str)
            or not isinstance(value.get("pid"), int)
        ):
            return None
        os.kill(value["pid"], 0)
        return value
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def clear_session() -> None:
    path = session_path()
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(value, dict) and value.get("pid") == os.getpid():
            path.unlink(missing_ok=True)
    except (OSError, json.JSONDecodeError):
        pass
