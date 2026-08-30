from __future__ import annotations

import json
import os
import stat

from dicom_guide.session import active_session, clear_session, session_path, write_session


def test_session_is_owner_only_discoverable_and_cleared(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DICOM_GUIDE_STATE_HOME", str(tmp_path))
    path = write_session("http://127.0.0.1:8765", "private-token")

    assert path == session_path()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert active_session() == {
        "schema_version": "1.0.0",
        "base_url": "http://127.0.0.1:8765",
        "token": "private-token",
        "pid": os.getpid(),
    }

    clear_session()
    assert not path.exists()


def test_session_rejects_insecure_or_stale_records(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DICOM_GUIDE_STATE_HOME", str(tmp_path))
    path = write_session("http://127.0.0.1:8765", "private-token")
    path.chmod(0o644)
    assert active_session() is None

    path.chmod(0o600)
    value = json.loads(path.read_text())
    value["pid"] = 999_999_999
    path.write_text(json.dumps(value))
    path.chmod(0o600)
    assert active_session() is None
