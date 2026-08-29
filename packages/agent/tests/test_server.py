from __future__ import annotations

import json
import threading
from http import HTTPStatus
from http.client import HTTPConnection
from pathlib import Path

import pytest

import scanview_agent.server as server_module
from scanview_agent.registration_reviews import write_registration_review
from scanview_agent.server import create_server
from test_registration_reviews import registration_bundle, review_request


def request(
    port: int, path: str, *, headers: dict[str, str] | None = None
) -> tuple[int, dict[str, str], bytes]:
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    connection.request("GET", path, headers=headers or {})
    response = connection.getresponse()
    result = response.status, dict(response.getheaders()), response.read()
    connection.close()
    return result


def post(
    port: int,
    path: str,
    body: bytes,
    *,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    connection.request("POST", path, body=body, headers=headers or {})
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
        assert server.browser_bootstrap_token != server.token
        assert server.browser_session_token != server.token
        assert server.browser_session_token != server.browser_bootstrap_token
        status, headers, body = request(port, "/")
        assert status == HTTPStatus.OK
        assert body.startswith(b"<!doctype html>")
        assert "default-src 'self'" in headers["Content-Security-Policy"]

        status, _, body = request(port, "/v1/manifest")
        assert status == HTTPStatus.UNAUTHORIZED
        assert json.loads(body) == {"error": "unauthorized"}

        status, forged_headers, _ = request(
            port, "/?session=test-session-token"
        )
        assert status == HTTPStatus.OK
        assert "Set-Cookie" not in forged_headers

        status, headers, _ = request(
            port, f"/?session={server.browser_bootstrap_token}"
        )
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
        assert len(headers["X-Content-SHA256"]) == 64
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


@pytest.mark.parametrize("change", ["symlink", "in_place"])
def test_native_dicom_stream_refuses_sources_changed_after_startup(
    tmp_path: Path,
    change: str,
) -> None:
    source = tmp_path / "indexed.dcm"
    source.write_bytes(b"DICM-indexed")
    instance_id = "instance_0123456789abcdef0123"
    server = create_server(
        {
            "schema_version": "1.0.0",
            "source": {"dicom_instances": 1},
            "studies": [],
        },
        {instance_id: source},
        port=0,
        token="dicom-guard-token",
    )
    if change == "symlink":
        original = tmp_path / "original.dcm"
        source.rename(original)
        arbitrary = tmp_path / "arbitrary"
        arbitrary.write_bytes(b"arbitrary bytes must never be served")
        source.symlink_to(arbitrary)
    else:
        source.write_bytes(b"DICM-changed")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, _, body = request(
            server.server_port,
            f"/v1/instances/{instance_id}",
            headers={"Authorization": "Bearer dicom-guard-token"},
        )
        assert status == HTTPStatus.CONFLICT
        assert json.loads(body) == {"error": "dicom_source_changed"}
        assert b"arbitrary bytes" not in body
        assert b"DICM-changed" not in body
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


def test_registration_qa_preview_is_browser_only_and_review_is_idempotent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    bundle = registration_bundle(tmp_path)
    ui_dist = tmp_path / "ui"
    ui_dist.mkdir()
    (ui_dist / "index.html").write_text("ScanView QA")
    original_context = server_module.registration_qa_context
    original_review_builder = server_module.registration_review_bytes
    context_calls = 0

    def counted_context(directory: Path) -> dict:
        nonlocal context_calls
        context_calls += 1
        return original_context(directory)

    review_build_calls = 0

    def build_review_once(
        directory: Path,
        request_bytes: bytes,
        *,
        created_at: str,
    ) -> bytes:
        nonlocal review_build_calls
        review_build_calls += 1
        assert directory == bundle.resolve()
        assert created_at.endswith("Z")
        return original_review_builder(
            directory,
            request_bytes,
            created_at=created_at,
        )

    monkeypatch.setattr(server_module, "registration_qa_context", counted_context)
    monkeypatch.setattr(server_module, "registration_review_bytes", build_review_once)
    server = create_server(
        {
            "schema_version": "1.0.0",
            "source": {"dicom_instances": 0},
            "studies": [],
        },
        {},
        port=0,
        token="qa-session-token",
        ui_dist=ui_dist,
        registration_bundle=bundle,
    )
    assert context_calls == 1
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_port
    bearer = {"Authorization": "Bearer qa-session-token"}
    try:
        status, _, body = request(port, "/v1/registration-qa", headers=bearer)
        assert status == HTTPStatus.OK
        agent_summary = json.loads(body)
        assert agent_summary["available"] is True
        assert agent_summary["display_unlocked"] is False
        assert str(bundle) not in body.decode()

        status, _, body = request(port, "/v1/registration-qa/preview", headers=bearer)
        assert status == HTTPStatus.FORBIDDEN
        assert json.loads(body) == {"error": "browser_session_required"}

        forged_browser = {"Cookie": "scanview_session=qa-session-token"}
        status, _, body = request(
            port,
            "/v1/registration-qa/preview",
            headers=forged_browser,
        )
        assert status == HTTPStatus.UNAUTHORIZED
        assert json.loads(body) == {"error": "unauthorized"}

        status, headers, _ = request(
            port, f"/?session={server.browser_bootstrap_token}"
        )
        assert status == HTTPStatus.SEE_OTHER
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        assert server.browser_session_token in cookie
        assert "qa-session-token" not in cookie
        browser = {"Cookie": cookie}

        status, _, body = request(
            port,
            "/v1/registration-qa/preview",
            headers=browser,
        )
        assert status == HTTPStatus.OK
        preview = json.loads(body)
        assert preview["qa_preview_only"] is True
        assert preview["watermark"] == "UNAPPROVED REGISTRATION — QA ONLY"
        assert str(bundle) not in body.decode()

        status, _, _ = request(
            port,
            "/v1/registration-qa/files/fixed.nrrd",
            headers=bearer,
        )
        assert status == HTTPStatus.FORBIDDEN
        status, volume_headers, volume = request(
            port,
            "/v1/registration-qa/files/fixed.nrrd",
            headers=browser,
        )
        assert status == HTTPStatus.OK
        assert volume_headers["Content-Type"] == "application/vnd.nrrd"
        assert volume_headers["Cache-Control"] == "no-store"
        assert volume == (bundle / "fixed.nrrd").read_bytes()
        assert context_calls == 1

        payload = json.dumps(review_request(decision="rejected")).encode()
        status, _, _ = post(
            port,
            "/v1/registration-reviews",
            payload,
            headers={
                "Cookie": cookie,
                "Origin": "http://example.invalid",
                "Host": f"127.0.0.1:{port}",
                "Content-Type": "application/vnd.scanview.registration-review-input+json",
            },
        )
        assert status == HTTPStatus.FORBIDDEN

        review_headers = {
            "Cookie": cookie,
            "Origin": f"http://127.0.0.1:{port}",
            "Host": f"127.0.0.1:{port}",
            "Content-Type": "application/vnd.scanview.registration-review-input+json",
        }
        status, response_headers, body = post(
            port,
            "/v1/registration-reviews",
            payload,
            headers=review_headers,
        )
        assert status == HTTPStatus.OK
        assert response_headers["Cache-Control"] == "no-store"
        assert response_headers["Content-Type"] == (
            "application/vnd.scanview.registration-review+json"
        )
        record = json.loads(body)
        assert record["review_status"] == "rejected"
        assert record["display_unlocks"]["overlay"] is False
        assert record["display_unlocks"]["subtraction"] is False
        assert str(bundle) not in body.decode()
        assert review_build_calls == 1
        first_body = body
        first_filename = response_headers["Content-Disposition"]

        status, retry_headers, body = post(
            port,
            "/v1/registration-reviews",
            payload,
            headers=review_headers,
        )
        assert status == HTTPStatus.OK
        assert body == first_body
        assert retry_headers["Content-Disposition"] == first_filename
        assert review_build_calls == 1

        different_payload = review_request(decision="rejected")
        different_payload["note"] = "A different rejected QA request."
        status, _, body = post(
            port,
            "/v1/registration-reviews",
            json.dumps(different_payload).encode(),
            headers=review_headers,
        )
        assert status == HTTPStatus.CONFLICT
        assert json.loads(body) == {"error": "registration_review_already_created"}
        assert review_build_calls == 1

        fixed = bundle / "fixed.nrrd"
        fixed_payload = fixed.read_bytes()
        fixed.write_bytes(fixed_payload[:-1] + bytes([fixed_payload[-1] ^ 0x01]))
        status, _, body = request(
            port,
            "/v1/registration-qa/files/fixed.nrrd",
            headers=browser,
        )
        assert status == HTTPStatus.CONFLICT
        assert json.loads(body) == {"error": "registration_bundle_invalid"}
        fixed.write_bytes(fixed_payload)

        original_fixed = tmp_path / "fixed-original.nrrd"
        fixed.rename(original_fixed)
        fixed.symlink_to(original_fixed)
        status, _, body = request(
            port,
            "/v1/registration-qa/files/fixed.nrrd",
            headers=browser,
        )
        assert status == HTTPStatus.CONFLICT
        assert json.loads(body) == {"error": "registration_bundle_invalid"}
        assert context_calls == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_accepted_reviewed_registration_is_cached_and_browser_only(
    tmp_path: Path,
    monkeypatch,
) -> None:
    bundle = registration_bundle(tmp_path)
    review_input = tmp_path / "accepted-review-input.json"
    review_input.write_text(json.dumps(review_request()))
    review = tmp_path / "accepted-review.json"
    write_registration_review(bundle, review_input, review)
    ui_dist = tmp_path / "ui"
    ui_dist.mkdir()
    (ui_dist / "index.html").write_text("ScanView reviewed registration")

    original_summary = server_module.reviewed_registration_display_summary
    original_context = server_module.reviewed_registration_display_context
    summary_calls = 0
    context_calls = 0

    def counted_summary(
        registration_directory: Path | None,
        review_source: Path | bytes | None,
    ) -> dict:
        nonlocal summary_calls
        summary_calls += 1
        return original_summary(registration_directory, review_source)

    def counted_context(
        registration_directory: Path,
        review_source: Path | bytes,
    ) -> dict:
        nonlocal context_calls
        context_calls += 1
        return original_context(registration_directory, review_source)

    monkeypatch.setattr(
        server_module,
        "reviewed_registration_display_summary",
        counted_summary,
    )
    monkeypatch.setattr(
        server_module,
        "reviewed_registration_display_context",
        counted_context,
    )
    server = create_server(
        {
            "schema_version": "1.0.0",
            "source": {"dicom_instances": 0},
            "studies": [],
        },
        {},
        port=0,
        token="reviewed-session-token",
        ui_dist=ui_dist,
        registration_bundle=bundle,
        registration_review=review,
    )
    assert summary_calls == 1
    assert context_calls == 1
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_port
    bearer = {"Authorization": "Bearer reviewed-session-token"}
    try:
        status, _, body = request(port, "/v1/registration-qa", headers=bearer)
        assert status == HTTPStatus.OK
        summary = json.loads(body)
        assert summary["display_authorized"] is True
        assert summary["allowed_display_modes"] == ["opacity", "swipe"]
        assert str(bundle) not in body.decode()
        assert str(review) not in body.decode()

        status, _, body = request(
            port,
            "/v1/reviewed-registration/display",
            headers=bearer,
        )
        assert status == HTTPStatus.FORBIDDEN
        assert json.loads(body) == {"error": "browser_session_required"}
        status, _, body = request(
            port,
            "/v1/reviewed-registration/files/fixed.nrrd",
            headers=bearer,
        )
        assert status == HTTPStatus.FORBIDDEN
        assert json.loads(body) == {"error": "browser_session_required"}

        status, headers, _ = request(
            port, f"/?session={server.browser_bootstrap_token}"
        )
        assert status == HTTPStatus.SEE_OTHER
        browser = {"Cookie": headers["Set-Cookie"].split(";", 1)[0]}

        status, context_headers, body = request(
            port,
            "/v1/reviewed-registration/display",
            headers=browser,
        )
        assert status == HTTPStatus.OK
        assert context_headers["Cache-Control"] == "no-store"
        context = json.loads(body)
        assert context["display_status"] == (
            "authorized_for_exploratory_shared_coverage_overlay_swipe"
        )
        assert set(context["volumes"]) == {"fixed", "registered_moving"}
        assert str(bundle) not in body.decode()
        assert str(review) not in body.decode()

        status, volume_headers, volume = request(
            port,
            "/v1/reviewed-registration/files/fixed.nrrd",
            headers=browser,
        )
        assert status == HTTPStatus.OK
        assert volume_headers["Content-Type"] == "application/vnd.nrrd"
        assert volume_headers["Cache-Control"] == "no-store"
        assert volume == (bundle / "fixed.nrrd").read_bytes()
        status, _, volume = request(
            port,
            "/v1/reviewed-registration/files/registered-moving.nrrd",
            headers=browser,
        )
        assert status == HTTPStatus.OK
        assert volume == (bundle / "registered-moving.nrrd").read_bytes()
        status, _, body = request(
            port,
            "/v1/reviewed-registration/files/moving.nrrd",
            headers=browser,
        )
        assert status == HTTPStatus.NOT_FOUND
        assert json.loads(body) == {"error": "not_found"}

        # Reviewed-display mode must not silently reopen the unapproved QA workspace.
        status, _, body = request(
            port,
            "/v1/registration-qa/preview",
            headers=browser,
        )
        assert status == HTTPStatus.NOT_FOUND
        assert json.loads(body) == {"error": "not_found"}
        status, _, body = request(
            port,
            "/v1/registration-qa/files/registered-moving.nrrd",
            headers=browser,
        )
        assert status == HTTPStatus.NOT_FOUND
        assert json.loads(body) == {"error": "not_found"}

        fixed = bundle / "fixed.nrrd"
        fixed_payload = fixed.read_bytes()
        fixed.write_bytes(fixed_payload[:-1] + bytes([fixed_payload[-1] ^ 0x01]))
        status, _, body = request(
            port,
            "/v1/reviewed-registration/files/fixed.nrrd",
            headers=browser,
        )
        assert status == HTTPStatus.CONFLICT
        assert json.loads(body) == {"error": "reviewed_registration_changed"}
        fixed.write_bytes(fixed_payload)
        assert summary_calls == 1
        assert context_calls == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_rejected_or_tampered_review_keeps_dicom_but_all_registration_pixels_locked(
    tmp_path: Path,
) -> None:
    bundle = registration_bundle(tmp_path)
    rejected_input = tmp_path / "rejected-review-input.json"
    rejected_input.write_text(json.dumps(review_request(decision="rejected")))
    rejected_review = tmp_path / "rejected-review.json"
    write_registration_review(bundle, rejected_input, rejected_review)

    accepted_input = tmp_path / "accepted-review-input.json"
    accepted_input.write_text(json.dumps(review_request()))
    tampered_review = tmp_path / "tampered-review.json"
    write_registration_review(bundle, accepted_input, tampered_review)
    tampered = json.loads(tampered_review.read_text())
    tampered["note"] = "Changed after the accepted review was recorded."
    tampered_review.write_text(json.dumps(tampered))

    dicom = tmp_path / "ordinary-dicom"
    dicom.write_bytes(b"DICM-still-available")
    instance_id = "instance_abcdef0123456789abcd"
    catalog = {
        "schema_version": "1.0.0",
        "source": {"dicom_instances": 1},
        "studies": [],
    }
    ui_dist = tmp_path / "ui"
    ui_dist.mkdir()
    (ui_dist / "index.html").write_text("ScanView ordinary DICOM")

    for review, expected_status, expected_available in (
        (rejected_review, "locked", True),
        (tampered_review, "invalid", False),
    ):
        server = create_server(
            catalog,
            {instance_id: dicom},
            port=0,
            token="locked-session-token",
            ui_dist=ui_dist,
            registration_bundle=bundle,
            registration_review=review,
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_port
        bearer = {"Authorization": "Bearer locked-session-token"}
        try:
            status, _, body = request(port, "/v1/registration-qa", headers=bearer)
            assert status == HTTPStatus.OK
            summary = json.loads(body)
            assert summary["available"] is expected_available
            assert summary["display_status"] == expected_status
            assert summary["display_authorized"] is False
            assert summary["allowed_display_modes"] == []
            assert str(bundle) not in body.decode()
            assert str(review) not in body.decode()

            status, headers, _ = request(
                port, f"/?session={server.browser_bootstrap_token}"
            )
            assert status == HTTPStatus.SEE_OTHER
            browser = {"Cookie": headers["Set-Cookie"].split(";", 1)[0]}

            status, _, body = request(
                port,
                f"/v1/instances/{instance_id}",
                headers=browser,
            )
            assert status == HTTPStatus.OK
            assert body == b"DICM-still-available"

            status, _, body = request(
                port,
                "/v1/reviewed-registration/display",
                headers=browser,
            )
            assert status == HTTPStatus.LOCKED
            assert json.loads(body) == {"error": "reviewed_registration_locked"}

            for path in (
                "/v1/reviewed-registration/files/fixed.nrrd",
                "/v1/reviewed-registration/files/registered-moving.nrrd",
                "/v1/registration-qa/preview",
                "/v1/registration-qa/files/fixed.nrrd",
                "/v1/registration-qa/files/moving.nrrd",
                "/v1/registration-qa/files/registered-moving.nrrd",
            ):
                status, _, body = request(port, path, headers=browser)
                assert status == HTTPStatus.NOT_FOUND
                assert json.loads(body) == {"error": "not_found"}
        finally:
            server.shutdown()
            server.server_close()
        thread.join(timeout=5)


def test_reviewed_registration_relocks_when_any_live_evidence_changes(
    tmp_path: Path,
) -> None:
    bundle = registration_bundle(tmp_path)
    review_input = tmp_path / "accepted-review-input.json"
    review_input.write_text(json.dumps(review_request()))
    review = tmp_path / "accepted-review.json"
    write_registration_review(bundle, review_input, review)
    server = create_server(
        {"schema_version": "1.0.0", "source": {"dicom_instances": 0}, "studies": []},
        {},
        port=0,
        token="freshness-token",
        registration_bundle=bundle,
        registration_review=review,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, headers, _ = request(
            server.server_port,
            f"/?session={server.browser_bootstrap_token}",
        )
        assert status == HTTPStatus.SEE_OTHER
        browser = {"Cookie": headers["Set-Cookie"].split(";", 1)[0]}
        engine_report = bundle / "engine-report.json"
        engine_report.write_bytes(engine_report.read_bytes() + b" ")

        status, _, body = request(
            server.server_port,
            "/v1/reviewed-registration/display",
            headers=browser,
        )
        assert status == HTTPStatus.LOCKED
        assert json.loads(body) == {"error": "reviewed_registration_changed"}
        status, _, body = request(
            server.server_port,
            "/v1/reviewed-registration/files/fixed.nrrd",
            headers=browser,
        )
        assert status == HTTPStatus.CONFLICT
        assert json.loads(body) == {"error": "reviewed_registration_changed"}
        status, _, body = request(
            server.server_port,
            "/v1/registration-qa",
            headers={"Authorization": "Bearer freshness-token"},
        )
        assert status == HTTPStatus.OK
        summary = json.loads(body)
        assert summary["display_authorized"] is False
        assert summary["display_status"] == "invalid"
        assert summary["allowed_display_modes"] == []
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_reviewed_registration_refuses_evidence_changed_during_startup_validation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    bundle = registration_bundle(tmp_path)
    review_input = tmp_path / "accepted-review-input.json"
    review_input.write_text(json.dumps(review_request()))
    review = tmp_path / "accepted-review.json"
    write_registration_review(bundle, review_input, review)
    original_context = server_module.reviewed_registration_display_context

    def context_then_change(
        registration_directory: Path,
        review_source: Path | bytes,
    ) -> dict:
        context = original_context(registration_directory, review_source)
        engine_report = bundle / "engine-report.json"
        engine_report.write_bytes(engine_report.read_bytes() + b" ")
        return context

    monkeypatch.setattr(
        server_module,
        "reviewed_registration_display_context",
        context_then_change,
    )
    server = create_server(
        {"schema_version": "1.0.0", "source": {"dicom_instances": 0}, "studies": []},
        {},
        port=0,
        registration_bundle=bundle,
        registration_review=review,
    )
    try:
        assert server.reviewed_registration_context is None
        assert server.registration_agent_summary["display_authorized"] is False
        assert server.registration_agent_summary["display_status"] == "invalid"
    finally:
        server.server_close()


def test_server_preserves_registration_bundle_and_review_symlink_rejection(
    tmp_path: Path,
) -> None:
    bundle = registration_bundle(tmp_path)
    review_input = tmp_path / "accepted-review-input.json"
    review_input.write_text(json.dumps(review_request()))
    review = tmp_path / "accepted-review.json"
    write_registration_review(bundle, review_input, review)
    bundle_link = tmp_path / "registration-link"
    bundle_link.symlink_to(bundle, target_is_directory=True)
    review_link = tmp_path / "review-link.json"
    review_link.symlink_to(review)
    catalog = {
        "schema_version": "1.0.0",
        "source": {"dicom_instances": 0},
        "studies": [],
    }

    with pytest.raises(ValueError, match="valid pending-QA"):
        create_server(catalog, {}, port=0, registration_bundle=bundle_link)

    for candidate_bundle, candidate_review in (
        (bundle_link, review),
        (bundle, review_link),
    ):
        server = create_server(
            catalog,
            {},
            port=0,
            registration_bundle=candidate_bundle,
            registration_review=candidate_review,
        )
        try:
            assert server.reviewed_registration_context is None
            assert server.registration_agent_summary["display_authorized"] is False
            assert server.registration_agent_summary["display_status"] == "invalid"
        finally:
            server.server_close()
