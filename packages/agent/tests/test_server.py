from __future__ import annotations

import io
import json
import threading
import zipfile
from http import HTTPStatus
from http.client import HTTPConnection
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from pydicom.uid import generate_uid

import dicom_guide.server as server_module
from dicom_guide.catalog import build_catalog
from dicom_guide.lesion_volume_comparisons import lesion_volume_comparison_summary
from dicom_guide.lesion_volume_comparisons import lesion_volume_comparison_archive_bytes
from dicom_guide.registration_reviews import write_registration_review
from dicom_guide.server import create_server
from test_catalog import write_dicom
from test_registration_reviews import registration_bundle, review_request
from test_lesion_volume_comparisons import _pair


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


def test_unified_server_serves_clean_loopback_workspace_and_dicom(
    tmp_path: Path,
) -> None:
    ui_dist = tmp_path / "ui"
    assets = ui_dist / "assets"
    assets.mkdir(parents=True)
    (ui_dist / "index.html").write_text("<!doctype html><title>DICOM Guide test</title>")
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
        status, headers, body = request(port, "/")
        assert status == HTTPStatus.OK
        assert body.startswith(b"<!doctype html>")
        assert "default-src 'self'" in headers["Content-Security-Policy"]
        assert "Set-Cookie" not in headers

        status, _, body = request(port, "/v1/manifest")
        assert status == HTTPStatus.OK
        assert json.loads(body)["schema_version"] == "1.0.0"

        status, headers, body = request(
            port,
            f"/v1/instances/{instance_id}",
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


def test_packaged_viewer_switches_local_source_without_browser_file_materialization(
    tmp_path: Path,
) -> None:
    ui_dist = tmp_path / "ui"
    ui_dist.mkdir()
    (ui_dist / "index.html").write_text("<!doctype html><title>DICOM Guide test</title>")
    first_root = tmp_path / "synthetic-first"
    second_root = tmp_path / "synthetic-second"
    empty_root = tmp_path / "synthetic-empty"
    first_root.mkdir()
    second_root.mkdir()
    empty_root.mkdir()
    for root, date, description in (
        (first_root, "20260101", "Synthetic first MPR"),
        (second_root, "20260202", "Synthetic second MPR"),
    ):
        study_uid = generate_uid()
        series_uid = generate_uid()
        for instance in range(1, 4):
            write_dicom(
                root / f"image-{instance}.dcm",
                study_uid=study_uid,
                series_uid=series_uid,
                date=date,
                instance=instance,
                description=description,
            )

    first_catalog, first_registry = build_catalog(first_root, include_hashes=False)
    selections: list[Path | None] = [second_root, None, empty_root]
    picker_calls = 0

    def select_folder() -> Path | None:
        nonlocal picker_calls
        picker_calls += 1
        return selections.pop(0)

    server = create_server(
        first_catalog,
        first_registry,
        port=0,
        token="folder-switch-token",
        ui_dist=ui_dist,
        source_root=first_root,
        include_hashes=False,
        folder_picker=select_folder,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_port
    headers = {
        "Origin": f"http://127.0.0.1:{port}",
        "Host": f"127.0.0.1:{port}",
        "Content-Type": "application/json",
    }
    first_instance_id = next(iter(first_registry))
    try:
        status, _, _ = post(
            port,
            "/v1/local-folders/select",
            b"{}",
            headers={**headers, "Origin": "http://example.invalid"},
        )
        assert status == HTTPStatus.FORBIDDEN
        assert picker_calls == 0

        status, _, body = post(
            port, "/v1/local-folders/select", b"{}", headers=headers
        )
        assert status == HTTPStatus.OK
        summary = json.loads(body)
        assert summary == {
            "status": "selected",
            "source_revision": 1,
            "study_count": 1,
            "renderable_series": 1,
            "dicom_instances": 3,
        }
        assert str(second_root) not in body.decode()

        status, _, body = request(port, "/v1/manifest")
        assert status == HTTPStatus.OK
        selected_manifest = json.loads(body)
        assert selected_manifest["source"]["root_label"] == second_root.name
        assert selected_manifest["studies"][0]["series"][0]["series_description"] == (
            "Synthetic second MPR"
        )
        second_instance_id = selected_manifest["studies"][0]["series"][0][
            "instances"
        ][0]["id"]
        status, _, _ = request(port, f"/v1/instances/{first_instance_id}")
        assert status == HTTPStatus.NOT_FOUND
        status, _, body = request(port, f"/v1/instances/{second_instance_id}")
        assert status == HTTPStatus.OK
        assert body.startswith(b"\x00" * 32)

        status, _, body = post(
            port, "/v1/local-folders/select", b"{}", headers=headers
        )
        assert status == HTTPStatus.OK
        assert json.loads(body) == {"status": "cancelled"}
        status, _, body = request(port, "/v1/manifest")
        assert json.loads(body)["source"]["root_label"] == second_root.name

        status, _, body = post(
            port, "/v1/local-folders/select", b"{}", headers=headers
        )
        assert status == HTTPStatus.UNPROCESSABLE_ENTITY
        assert json.loads(body) == {"error": "no_renderable_dicom"}
        status, _, body = request(port, "/v1/manifest")
        assert json.loads(body)["source"]["root_label"] == second_root.name
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_local_server_assembles_source_recursive_lesion_volume_comparison(
    tmp_path: Path,
) -> None:
    baseline, followup, pairing_request, source_root = _pair(tmp_path)
    catalog, registry = build_catalog(source_root, include_hashes=True)
    transport = io.BytesIO()
    with zipfile.ZipFile(transport, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("baseline-review.zip", baseline.read_bytes())
        archive.writestr("followup-review.zip", followup.read_bytes())
        archive.writestr("pairing-request.json", pairing_request.read_bytes())
    server = create_server(
        catalog,
        registry,
        port=0,
        token="volume-comparison-token",
        source_root=source_root,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_port
    headers = {
        "Authorization": "Bearer volume-comparison-token",
        "Origin": f"http://127.0.0.1:{port}",
        "Host": f"127.0.0.1:{port}",
        "Content-Type": "application/vnd.dicom-guide.lesion-volume-comparison-input+zip",
    }
    try:
        status, response_headers, body = post(
            port,
            "/v1/lesion-volume-comparisons",
            transport.getvalue(),
            headers={key: value for key, value in headers.items() if key != "Authorization"},
        )
        assert status == HTTPStatus.OK
        assert response_headers["Content-Type"] == "application/zip"

        wrong_origin = {**headers, "Origin": "http://example.invalid"}
        status, _, body = post(
            port,
            "/v1/lesion-volume-comparisons",
            transport.getvalue(),
            headers=wrong_origin,
        )
        assert status == HTTPStatus.FORBIDDEN

        status, response_headers, body = post(
            port,
            "/v1/lesion-volume-comparisons",
            transport.getvalue(),
            headers=headers,
        )
        assert status == HTTPStatus.OK
        assert response_headers["Content-Type"] == "application/zip"
        assert response_headers["Cache-Control"] == "no-store"
        assert "dicom-guide-lesion-volume-comparison" in response_headers["Content-Disposition"]
        summary = lesion_volume_comparison_summary(
            io.BytesIO(body), source_root, catalog=catalog
        )
        assert summary["valid"]
        assert summary["percent_volume_change"] == pytest.approx(100 / 3)
        assert not summary["response_classification"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize("mutated_input", ["comparison", "native_source"])
def test_reviewed_native_boundary_display_is_cached_guarded_and_loopback_available(
    tmp_path: Path, mutated_input: str,
) -> None:
    baseline, followup, pairing_request, source_root = _pair(tmp_path)
    catalog, registry = build_catalog(source_root, include_hashes=True)
    comparison = tmp_path / "accepted-comparison.zip"
    comparison.write_bytes(
        lesion_volume_comparison_archive_bytes(
            baseline,
            followup,
            pairing_request,
            source_root,
            catalog=catalog,
            comparison_id="volume_pair_33333333-3333-4333-8333-333333333333",
            created_at="2026-02-02T12:00:00Z",
        )
    )
    server = create_server(
        catalog,
        registry,
        port=0,
        token="native-boundary-token",
        source_root=source_root,
        lesion_volume_comparison=comparison,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_port
    bearer = {"Authorization": "Bearer native-boundary-token"}
    try:
        status, _, body = request(
            port, "/v1/lesion-volume-comparison-display", headers=bearer
        )
        assert status == HTTPStatus.OK
        summary = json.loads(body)
        assert summary["available"] is True
        assert summary["source_validated"] is True
        assert summary["native_spaces"] == 2
        assert summary["registered"] is False
        assert summary["browser_session_required_for_pixels"] is False
        assert summary["external_api_required"] is False
        assert summary["response_classification"] is False
        assert "Synthetic Pairing Reviewer" not in body.decode()
        assert "Synthetic clinic" not in body.decode()
        assert str(source_root) not in body.decode()

        status, _, body = request(
            port,
            "/v1/lesion-volume-comparison-display/context",
            headers=bearer,
        )
        assert status == HTTPStatus.OK
        context = json.loads(body)
        status, _, body = request(
            port,
            "/v1/lesion-volume-comparison-display/masks/baseline",
            headers=bearer,
        )
        assert status == HTTPStatus.OK
        schema = json.loads(
            (
                Path(__file__).parents[3]
                / "schemas"
                / "dicom-guide-native-boundary-display-v1.schema.json"
            ).read_text()
        )
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(
            schema, format_checker=FormatChecker()
        ).validate(context)
        assert context["display_label"] == "REVIEWED NATIVE BOUNDARIES — UNREGISTERED"
        assert context["navigation_policy"]["registered"] is False
        assert context["navigation_policy"]["default_linked"] is False
        assert "spatial_overlay" in context["display_policy"]["always_locked"]
        assert context["comparison"]["response_assessment"] == "not_performed"

        for role in ("baseline", "followup"):
            status, mask_headers, mask = request(
                port,
                f"/v1/lesion-volume-comparison-display/masks/{role}",
            )
            descriptor = context["timepoints"][role]["mask"]
            assert status == HTTPStatus.OK
            assert mask_headers["Content-Type"] == (
                "application/vnd.dicom-guide.native-binary-mask"
            )
            assert mask_headers["Cache-Control"] == "no-store"
            assert mask_headers["X-Content-SHA256"] == descriptor["sha256"]
            assert len(mask) == descriptor["bytes"]
            assert set(mask) <= {0, 1}
            assert sum(mask) == context["timepoints"][role]["foreground_voxel_count"]

        if mutated_input == "comparison":
            payload = comparison.read_bytes()
            comparison.write_bytes(payload + b"changed")
        else:
            source = next(iter(registry.values()))
            payload = source.read_bytes()
            source.write_bytes(payload + b"changed")
        status, _, body = request(
            port,
            "/v1/lesion-volume-comparison-display/context",
        )
        assert status == HTTPStatus.LOCKED
        assert json.loads(body) == {"error": "native_boundary_display_inputs_changed"}
        status, _, body = request(
            port, "/v1/lesion-volume-comparison-display", headers=bearer
        )
        assert status == HTTPStatus.OK
        changed_summary = json.loads(body)
        assert changed_summary["available"] is False
        assert changed_summary["display_status"] == "invalid"
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
    (ui_dist / "index.html").write_text("DICOM Guide")
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


def test_registration_qa_preview_is_loopback_available_and_review_is_idempotent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    bundle = registration_bundle(tmp_path)
    ui_dist = tmp_path / "ui"
    ui_dist.mkdir()
    (ui_dist / "index.html").write_text("DICOM Guide QA")
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
        status, _, body = post(
            port,
            "/v1/local-folders/select",
            b"{}",
            headers={
                "Origin": f"http://127.0.0.1:{port}",
                "Host": f"127.0.0.1:{port}",
                "Content-Type": "application/json",
            },
        )
        assert status == HTTPStatus.LOCKED
        assert json.loads(body) == {"error": "source_locked"}

        status, _, body = request(port, "/v1/registration-qa", headers=bearer)
        assert status == HTTPStatus.OK
        agent_summary = json.loads(body)
        assert agent_summary["available"] is True
        assert agent_summary["display_unlocked"] is False
        assert str(bundle) not in body.decode()

        status, _, body = request(
            port,
            "/v1/registration-qa/preview",
        )
        assert status == HTTPStatus.OK
        browser: dict[str, str] = {}
        preview = json.loads(body)
        assert preview["qa_preview_only"] is True
        assert preview["watermark"] == "UNAPPROVED REGISTRATION — QA ONLY"
        assert str(bundle) not in body.decode()

        status, volume_headers, volume = request(
            port,
            "/v1/registration-qa/files/fixed.nrrd",
            headers=browser,
        )
        assert status == HTTPStatus.OK
        assert volume_headers["Content-Type"] == "application/vnd.nrrd"
        assert volume_headers["Cache-Control"] == "no-store"
        assert volume == (bundle / "fixed.nrrd").read_bytes()
        status, mask_headers, mask = request(
            port,
            "/v1/registration-qa/files/registered-moving-coverage.nrrd",
            headers=browser,
        )
        assert status == HTTPStatus.OK
        assert mask_headers["Content-Type"] == "application/vnd.nrrd"
        assert mask_headers["X-Content-SHA256"] == preview["coverage_mask"]["sha256"]
        assert mask == (bundle / "registered-moving-coverage.nrrd").read_bytes()
        assert context_calls == 1

        payload = json.dumps(review_request(decision="rejected")).encode()
        status, _, _ = post(
            port,
            "/v1/registration-reviews",
            payload,
            headers={
                "Origin": "http://example.invalid",
                "Host": f"127.0.0.1:{port}",
                "Content-Type": "application/vnd.dicom-guide.registration-review-input+json",
            },
        )
        assert status == HTTPStatus.FORBIDDEN

        review_headers = {
            "Origin": f"http://127.0.0.1:{port}",
            "Host": f"127.0.0.1:{port}",
            "Content-Type": "application/vnd.dicom-guide.registration-review-input+json",
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
            "application/vnd.dicom-guide.registration-review+json"
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


def test_accepted_reviewed_registration_is_cached_and_loopback_available(
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
    (ui_dist / "index.html").write_text("DICOM Guide reviewed registration")

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

        browser: dict[str, str] = {}

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
        assert context["coverage_mask"]["filename"] == (
            "registered-moving-coverage.nrrd"
        )
        assert context["display_policy"]["sampling_support_enforcement"] == (
            "required_pixel_mask"
        )
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
        status, mask_headers, mask = request(
            port,
            "/v1/reviewed-registration/files/registered-moving-coverage.nrrd",
            headers=browser,
        )
        assert status == HTTPStatus.OK
        assert mask_headers["X-Content-SHA256"] == context["coverage_mask"]["sha256"]
        assert mask == (bundle / "registered-moving-coverage.nrrd").read_bytes()
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
    (ui_dist / "index.html").write_text("DICOM Guide ordinary DICOM")

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

            browser: dict[str, str] = {}

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
                "/v1/reviewed-registration/files/registered-moving-coverage.nrrd",
                "/v1/reviewed-registration/files/registered-moving.nrrd",
                "/v1/registration-qa/preview",
                "/v1/registration-qa/files/fixed.nrrd",
                "/v1/registration-qa/files/moving.nrrd",
                "/v1/registration-qa/files/registered-moving-coverage.nrrd",
                "/v1/registration-qa/files/registered-moving.nrrd",
            ):
                status, _, body = request(port, path, headers=browser)
                assert status == HTTPStatus.NOT_FOUND
                assert json.loads(body) == {"error": "not_found"}
        finally:
            server.shutdown()
            server.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize(
    "changed_filename",
    ["engine-report.json", "registered-moving-coverage.nrrd"],
)
def test_reviewed_registration_relocks_when_any_live_evidence_changes(
    tmp_path: Path,
    changed_filename: str,
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
        browser: dict[str, str] = {}
        changed = bundle / changed_filename
        changed.write_bytes(changed.read_bytes() + b" ")

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
