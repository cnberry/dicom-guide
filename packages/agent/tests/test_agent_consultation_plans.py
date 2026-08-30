from __future__ import annotations

import copy
import json
import sys
import threading
from http import HTTPStatus
from http.client import HTTPConnection
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from dicom_guide.agent_consultation_plans import (
    ARTIFACT_TYPE,
    MAX_HEADING_CHARACTERS,
    MAX_PLAN_BYTES,
    MEDIA_TYPE,
    REQUEST_ARTIFACT_TYPE,
    agent_consultation_plan_summary,
    build_agent_consultation_plan,
    load_strict_json,
    validate_agent_consultation_plan,
)
from dicom_guide.cli import main
from dicom_guide.server import create_server


PATIENT_A = "patient_aaaaaaaaaaaaaaaaaaaa"
PATIENT_B = "patient_bbbbbbbbbbbbbbbbbbbb"


def _instance(index: int) -> dict:
    return {
        "id": f"instance_{index:020x}",
        "instance_number": index,
        "bytes": 128,
        "sha256": f"{index:064x}",
    }


def _series(
    index: int,
    *,
    modality: str,
    patient_context_id: str = PATIENT_A,
) -> dict:
    return {
        "id": f"series_{index:020x}",
        "patient_context_id": patient_context_id,
        "modality": modality,
        "series_description": f"SYNTHETIC {modality}",
        "image_type": ["ORIGINAL", "PRIMARY"],
        "instance_count": 2,
        "instances": [_instance(index * 10 + 1), _instance(index * 10 + 2)],
        "review_status": "unreviewed",
    }


def _study(index: int, *series: dict) -> dict:
    return {
        "id": f"study_{index:020x}",
        "acquisition_date": f"20260{index}01",
        "series": list(series),
        "review_status": "unreviewed",
    }


def _catalog() -> dict:
    return {
        "schema_version": "1.0.0",
        "generated_at": "2026-08-29T09:00:00Z",
        "privacy": {
            "classification": "sensitive_local_medical_data",
            "direct_identifier_tags_excluded": True,
            "deidentified": False,
            "warning": "synthetic",
        },
        "source": {
            "root_label": "PRIVATE-SYNTHETIC-SOURCE",
            "immutable": True,
            "dicom_instances": 4,
            "skipped_non_image_files": 0,
        },
        "studies": [
            _study(1, _series(1, modality="MR")),
            _study(2, _series(2, modality="CT")),
        ],
        "agent_contract": {
            "review_status": "unreviewed",
            "observations": [],
            "computed_results": [],
            "candidate_interpretations": [],
            "limitations": [],
            "missing_context": [],
            "questions_for_clinician": [],
        },
    }


def _request() -> dict:
    return {
        "schema_version": "1.0.0",
        "artifact_type": REQUEST_ARTIFACT_TYPE,
        "items": [
            {
                "series_id": "series_00000000000000000001",
                "instance_id": "instance_0000000000000000000b",
                "discussion_heading": "MRI overview — ask what anatomy matters",
            },
            {
                "series_id": "series_00000000000000000002",
                "instance_id": "instance_00000000000000000015",
                "discussion_heading": "CT overview — ask what is complementary",
            },
        ],
    }


def _plan() -> dict:
    return build_agent_consultation_plan(
        _catalog(),
        _request(),
        generated_at="2026-08-29T09:01:00Z",
    )


def _schema() -> dict:
    return json.loads(
        (
            Path(__file__).parents[3]
            / "schemas"
            / "dicom-guide-consultation-plan-v1.schema.json"
        ).read_text()
    )


def _http(
    port: int,
    method: str,
    path: str,
    *,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    connection.request(method, path, body=body, headers=headers or {})
    response = connection.getresponse()
    result = response.status, dict(response.getheaders()), response.read()
    connection.close()
    return result


def test_plan_is_schema_valid_catalog_bound_and_navigation_only() -> None:
    catalog = _catalog()
    plan = build_agent_consultation_plan(
        catalog,
        _request(),
        generated_at="2026-08-29T09:01:00Z",
    )

    Draft202012Validator.check_schema(_schema())
    Draft202012Validator(_schema(), format_checker=FormatChecker()).validate(plan)
    assert plan["artifact_type"] == ARTIFACT_TYPE
    assert plan["relationship"]["modalities_present"] == ["MR", "CT"]
    assert plan["relationship"]["distinct_source_study_count"] == 2
    assert plan["privacy"]["discussion_headings_may_contain_identifiers"] is True
    assert plan["permissions"]["exact_source_navigation_authorized"] is True
    assert plan["clinical_interpretations"] == []
    assert not any(
        value
        for key, value in plan["permissions"].items()
        if key != "exact_source_navigation_authorized"
    )
    assert validate_agent_consultation_plan(catalog, plan) == plan
    assert "PRIVATE-SYNTHETIC-SOURCE" not in json.dumps(plan)


def test_strict_json_refuses_duplicate_fields_and_nonfinite_constants() -> None:
    with pytest.raises(ValueError, match="duplicate JSON field"):
        load_strict_json('{"local_only":true,"local_only":true}')
    with pytest.raises(ValueError, match="unsupported JSON constant"):
        load_strict_json('{"item_count":NaN}')


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (
            lambda catalog, request: request["items"][1].update(
                {"instance_id": request["items"][0]["instance_id"]}
            ),
            "selected series",
        ),
        (
            lambda catalog, request: request["items"][1].update(
                {"series_id": request["items"][0]["series_id"]}
            ),
            "instance does not belong",
        ),
        (
            lambda catalog, request: catalog["studies"][1]["series"][0].update(
                {"patient_context_id": PATIENT_B}
            ),
            "one opaque patient context",
        ),
        (
            lambda catalog, request: catalog["studies"][1]["series"][0].update(
                {"modality": "MR"}
            ),
            "at least one MR and one CT",
        ),
        (
            lambda catalog, request: catalog["studies"][0]["series"].append(
                catalog["studies"].pop()["series"][0]
            ),
            "at least two source studies",
        ),
    ],
)
def test_plan_relationships_fail_closed(mutator, message: str) -> None:
    catalog = _catalog()
    request = _request()
    mutator(catalog, request)
    with pytest.raises(ValueError, match=message):
        build_agent_consultation_plan(catalog, request)


def test_request_shape_headings_count_and_catalog_tamper_fail_closed() -> None:
    request = _request()
    request["extra"] = True
    with pytest.raises(ValueError, match="unsupported fields"):
        build_agent_consultation_plan(_catalog(), request)

    for heading in (" spaced ", "control\nheading", "x" * (MAX_HEADING_CHARACTERS + 1)):
        request = _request()
        request["items"][0]["discussion_heading"] = heading
        with pytest.raises(ValueError, match="discussion heading"):
            build_agent_consultation_plan(_catalog(), request)

    request = _request()
    request["items"] = request["items"][:1]
    with pytest.raises(ValueError, match="2 to 8"):
        build_agent_consultation_plan(_catalog(), request)

    catalog = _catalog()
    plan = build_agent_consultation_plan(catalog, _request())
    regenerated = copy.deepcopy(catalog)
    regenerated["generated_at"] = "2026-08-29T09:05:00Z"
    assert validate_agent_consultation_plan(regenerated, plan) == plan

    catalog["source"]["dicom_instances"] = 5
    with pytest.raises(ValueError, match="exact local catalog"):
        validate_agent_consultation_plan(catalog, plan)


def test_summary_is_privacy_minimized_and_tamper_withholds_navigation() -> None:
    catalog = _catalog()
    plan = _plan()
    valid = agent_consultation_plan_summary(catalog, plan)
    assert valid["valid"] is True
    assert valid["item_count"] == 2
    assert valid["exact_source_navigation_authorized"] is True
    assert valid["contains_prompts"] is False
    assert valid["contains_source_ids"] is False
    serialized = json.dumps(valid)
    assert "MRI overview" not in serialized
    assert "series_" not in serialized
    assert "instance_" not in serialized

    plan["permissions"]["diagnosis_authorized"] = True
    invalid = agent_consultation_plan_summary(catalog, plan)
    assert invalid["valid"] is False
    assert invalid["item_count"] == 0
    assert invalid["exact_source_navigation_authorized"] is False


def test_cli_creates_owner_only_plan_and_privacy_validates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    manifest = tmp_path / "manifest.json"
    request = tmp_path / "request.json"
    output = tmp_path / "plan.json"
    manifest.write_text(json.dumps(_catalog()))
    request.write_text(json.dumps(_request()))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "dicom-guide",
            "create-consultation-plan",
            str(manifest),
            str(request),
            "--output",
            str(output),
        ],
    )
    main()
    assert output.stat().st_mode & 0o777 == 0o600
    assert json.loads(output.read_text())["artifact_type"] == ARTIFACT_TYPE

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "dicom-guide",
            "validate-consultation-plan",
            str(manifest),
            str(output),
        ],
    )
    main()
    summary = json.loads(capsys.readouterr().out)
    assert summary["valid"] is True
    assert summary["contains_prompts"] is False
    assert summary["contains_source_ids"] is False


def test_loopback_browser_endpoint_enforces_origin_media_size_and_catalog() -> None:
    catalog = _catalog()
    plan = _plan()
    body = json.dumps(plan).encode()
    server = create_server(catalog, {}, port=0, token="agent-plan-bearer-token")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_port
    path = "/v1/agent-consultation-plans/validate"
    origin = f"http://127.0.0.1:{port}"
    try:
        status, _, _ = _http(
            port,
            "POST",
            path,
            body=body,
            headers={
                "Content-Type": MEDIA_TYPE,
            },
        )
        assert status == HTTPStatus.FORBIDDEN

        status, _, _ = _http(
            port,
            "POST",
            path,
            body=body,
            headers={"Content-Type": MEDIA_TYPE},
        )
        assert status == HTTPStatus.FORBIDDEN

        status, _, _ = _http(
            port,
            "POST",
            path,
            body=body,
            headers={
                "Origin": origin,
                "Content-Type": "application/json",
            },
        )
        assert status == HTTPStatus.UNSUPPORTED_MEDIA_TYPE

        status, headers, response = _http(
            port,
            "POST",
            path,
            body=body,
            headers={
                "Origin": origin,
                "Content-Type": MEDIA_TYPE,
            },
        )
        assert status == HTTPStatus.OK
        assert headers["Cache-Control"] == "no-store"
        summary = json.loads(response)
        assert summary["valid"] is True
        assert summary["item_count"] == 2
        assert "MRI overview" not in response.decode()

        duplicate_body = body.decode().replace(
            '"local_only": true',
            '"local_only": true, "local_only": true',
            1,
        ).encode()
        status, _, _ = _http(
            port,
            "POST",
            path,
            body=duplicate_body,
            headers={
                "Origin": origin,
                "Content-Type": MEDIA_TYPE,
            },
        )
        assert status == HTTPStatus.UNPROCESSABLE_ENTITY

        tampered = copy.deepcopy(plan)
        tampered["items"][0]["modality"] = "CT"
        status, _, response = _http(
            port,
            "POST",
            path,
            body=json.dumps(tampered).encode(),
            headers={
                "Origin": origin,
                "Content-Type": MEDIA_TYPE,
            },
        )
        assert status == HTTPStatus.UNPROCESSABLE_ENTITY
        assert "discussion_heading" not in response.decode()

        status, _, _ = _http(
            port,
            "POST",
            path,
            body=b"x" * (MAX_PLAN_BYTES + 1),
            headers={
                "Origin": origin,
                "Content-Type": MEDIA_TYPE,
            },
        )
        assert status == HTTPStatus.REQUEST_ENTITY_TOO_LARGE
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
