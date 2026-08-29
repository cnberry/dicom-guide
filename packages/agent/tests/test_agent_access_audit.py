from __future__ import annotations

import json
import os
import sys
import threading
from http import HTTPStatus
from http.client import HTTPConnection
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from scanview_agent.agent_access_audit import (
    AgentAccessAudit,
    agent_access_audit_summary,
)
from scanview_agent.cli import main
from scanview_agent.server import create_server


INSTANCE_ID = "instance_0123456789abcdef0123"


def request(
    port: int,
    path: str,
    *,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    connection.request("GET", path, headers=headers or {})
    response = connection.getresponse()
    result = response.status, dict(response.getheaders()), response.read()
    connection.close()
    return result


def test_agent_access_audit_appends_resumes_and_validates_schema(tmp_path: Path) -> None:
    path = tmp_path / "agent-access.jsonl"
    audit = AgentAccessAudit.open(path)
    first = audit.record("manifest_read")
    second = audit.record("viewer_state_read")
    assert audit.event_count == 2
    assert first["previous_event_sha256"] == "0" * 64
    assert second["previous_event_sha256"] == first["event_sha256"]
    assert agent_access_audit_summary(path)["event_count"] == 2
    audit.close()

    resumed = AgentAccessAudit.open(path)
    third = resumed.record("native_dicom_instance_read")
    resumed.close()
    assert third["sequence"] == 3
    assert third["previous_event_sha256"] == second["event_sha256"]

    events = [json.loads(line) for line in path.read_text().splitlines()]
    schema = json.loads(
        (
            Path(__file__).parents[3]
            / "schemas"
            / "scanview-agent-access-audit-event-v1.schema.json"
        ).read_text()
    )
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    for event in events:
        validator.validate(event)
        assert event["contains_patient_content"] is False
        assert event["contains_token"] is False
        assert event["contains_path"] is False
        assert event["contains_request_target"] is False
    summary = agent_access_audit_summary(path)
    assert summary["valid"] is True
    assert summary["event_count"] == 3
    assert summary["last_event_sha256"] == third["event_sha256"]
    assert stat_mode(path) == 0o600


def stat_mode(path: Path) -> int:
    return path.stat().st_mode & 0o777


def test_agent_access_audit_rejects_tamper_links_permissions_and_concurrent_writer(
    tmp_path: Path,
) -> None:
    path = tmp_path / "agent-access.jsonl"
    audit = AgentAccessAudit.open(path)
    audit.record("manifest_read")
    with pytest.raises(ValueError, match="already in use"):
        AgentAccessAudit.open(path)
    audit.close()

    payload = path.read_bytes()
    path.write_bytes(payload.replace(b"manifest_read", b"viewer_state_read"))
    assert agent_access_audit_summary(path)["valid"] is False
    with pytest.raises(ValueError, match="hash"):
        AgentAccessAudit.open(path)

    broad = tmp_path / "broad.jsonl"
    broad.write_text("")
    broad.chmod(0o644)
    with pytest.raises(ValueError, match="permissions"):
        AgentAccessAudit.open(broad)

    target = tmp_path / "target.jsonl"
    target.write_text("")
    target.chmod(0o600)
    symlink = tmp_path / "symlink.jsonl"
    symlink.symlink_to(target)
    with pytest.raises(ValueError, match="opened safely"):
        AgentAccessAudit.open(symlink)

    hardlink = tmp_path / "hardlink.jsonl"
    os.link(target, hardlink)
    with pytest.raises(ValueError, match="owner-controlled and unlinked"):
        AgentAccessAudit.open(target)


def test_agent_access_audit_cli_returns_only_privacy_minimized_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "agent-access.jsonl"
    audit = AgentAccessAudit.open(path)
    audit.record("manifest_read")
    audit.close()
    monkeypatch.setattr(sys, "argv", ["scanview-agent", "verify-agent-audit", str(path)])
    main()
    output = capsys.readouterr().out
    summary = json.loads(output)
    assert summary["valid"] is True
    assert summary["event_count"] == 1
    assert str(path) not in output
    assert "manifest_read" not in output


def test_agent_access_audit_cli_rejects_unsafe_startup_without_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    source_root = tmp_path / "synthetic-empty-source"
    source_root.mkdir()
    audit_path = tmp_path / "unsafe-agent-access.jsonl"
    audit_path.write_text("")
    audit_path.chmod(0o644)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "scanview-agent",
            "serve",
            str(source_root),
            "--port",
            "0",
            "--agent-audit-log",
            str(audit_path),
        ],
    )

    with pytest.raises(SystemExit) as exit_info:
        main()

    assert exit_info.value.code == 2
    error = capsys.readouterr().err
    assert "permissions must exclude group and other access" in error
    assert "Traceback" not in error


def test_configured_server_audits_only_privacy_minimized_bearer_operation_classes(
    tmp_path: Path,
) -> None:
    source = tmp_path / "synthetic-source.dcm"
    source.write_bytes(b"DICM-synthetic-agent-audit")
    audit_path = tmp_path / "agent-access.jsonl"
    catalog = {
        "schema_version": "1.0.0",
        "source": {"dicom_instances": 1},
        "studies": [
            {
                "id": "study_0123456789abcdef0123",
                "acquisition_date": "20260101",
                "series": [
                    {
                        "id": "series_0123456789abcdef0123",
                        "patient_context_id": "patient_0123456789abcdef0123",
                        "modality": "MR",
                        "series_description": "SYNTHETIC T1",
                        "image_type": ["ORIGINAL", "PRIMARY"],
                        "instance_count": 1,
                        "instances": [{"id": INSTANCE_ID, "bytes": source.stat().st_size}],
                    }
                ],
            }
        ],
    }
    token = "synthetic-agent-audit-secret-token"
    server = create_server(
        catalog,
        {INSTANCE_ID: source},
        port=0,
        token=token,
        agent_audit_log=audit_path,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_port
    bearer = {"Authorization": f"Bearer {token}"}
    try:
        assert request(port, "/v1/manifest")[0] == HTTPStatus.UNAUTHORIZED
        status, headers, _ = request(
            port, f"/?session={server.browser_bootstrap_token}"
        )
        assert status == HTTPStatus.SEE_OTHER
        browser = {"Cookie": headers["Set-Cookie"].split(";", 1)[0]}
        assert request(port, "/v1/manifest", headers=browser)[0] == HTTPStatus.OK
        assert server.agent_access_audit is not None
        assert server.agent_access_audit.event_count == 0

        cases = [
            ("/v1/manifest", HTTPStatus.OK),
            ("/v1/viewer-state", HTTPStatus.OK),
            ("/v1/comparison-candidates", HTTPStatus.OK),
            ("/v1/longitudinal-readiness", HTTPStatus.OK),
            ("/v1/presentation-states", HTTPStatus.OK),
            ("/v1/source-segmentations", HTTPStatus.OK),
            ("/v1/lesion-volume-comparison-display", HTTPStatus.OK),
            ("/v1/registration-qa", HTTPStatus.OK),
            (f"/v1/instances/{INSTANCE_ID}", HTTPStatus.OK),
            (
                f"/v1/source-segmentations/{INSTANCE_ID}/masks/1",
                HTTPStatus.FORBIDDEN,
            ),
            (
                "/v1/lesion-volume-comparison-display/context",
                HTTPStatus.FORBIDDEN,
            ),
            (
                "/v1/lesion-volume-comparison-display/masks/baseline",
                HTTPStatus.FORBIDDEN,
            ),
            ("/v1/registration-qa/preview", HTTPStatus.FORBIDDEN),
            ("/v1/registration-qa/files/fixed.nrrd", HTTPStatus.NOT_FOUND),
        ]
        for path, expected in cases:
            assert request(port, path, headers=bearer)[0] == expected
        assert server.agent_access_audit.event_count == len(cases)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    summary = agent_access_audit_summary(audit_path)
    assert summary["valid"] is True
    assert summary["event_count"] == 14
    events = [json.loads(line) for line in audit_path.read_text().splitlines()]
    assert [event["operation"] for event in events] == [
        "manifest_read",
        "viewer_state_read",
        "comparison_candidates_read",
        "longitudinal_readiness_read",
        "presentation_states_read",
        "source_segmentations_read",
        "native_boundary_summary_read",
        "registration_status_read",
        "native_dicom_instance_read",
        "browser_only_source_segmentation_mask_attempt",
        "browser_only_native_boundary_context_attempt",
        "browser_only_native_boundary_mask_attempt",
        "browser_only_registration_context_attempt",
        "browser_only_registration_volume_attempt",
    ]
    serialized = audit_path.read_text()
    assert token not in serialized
    assert INSTANCE_ID not in serialized
    assert str(source) not in serialized
    assert "/v1/" not in serialized
    assert b"DICM-synthetic-agent-audit" not in audit_path.read_bytes()


def test_configured_audit_change_fails_bearer_access_closed_without_blocking_browser(
    tmp_path: Path,
) -> None:
    audit_path = tmp_path / "agent-access.jsonl"
    server = create_server(
        {"schema_version": "1.0.0", "source": {"dicom_instances": 0}, "studies": []},
        {},
        port=0,
        token="audit-failure-token",
        agent_audit_log=audit_path,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_port
    bearer = {"Authorization": "Bearer audit-failure-token"}
    try:
        assert request(port, "/v1/manifest", headers=bearer)[0] == HTTPStatus.OK
        with audit_path.open("ab") as stream:
            stream.write(b"external-change\n")
        status, _, body = request(port, "/v1/manifest", headers=bearer)
        assert status == HTTPStatus.SERVICE_UNAVAILABLE
        assert json.loads(body) == {"error": "agent_access_audit_unavailable"}

        status, headers, _ = request(
            port, f"/?session={server.browser_bootstrap_token}"
        )
        assert status == HTTPStatus.SEE_OTHER
        browser = {"Cookie": headers["Set-Cookie"].split(";", 1)[0]}
        assert request(port, "/v1/manifest", headers=browser)[0] == HTTPStatus.OK
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    assert agent_access_audit_summary(audit_path)["valid"] is False
