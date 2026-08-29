from __future__ import annotations

import json
import sys
import threading
from http import HTTPStatus
from http.client import HTTPConnection
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from scanview_agent.cli import main
from scanview_agent.longitudinal_readiness import (
    MAX_REPORTED_CANDIDATE_PAIRS,
    build_longitudinal_readiness,
)
from scanview_agent.server import create_server


PATIENT_A = "patient_aaaaaaaaaaaaaaaaaaaa"
PATIENT_B = "patient_bbbbbbbbbbbbbbbbbbbb"


def _series(
    index: int,
    *,
    modality: str = "MR",
    patient_context_id: str | None = PATIENT_A,
    description: str = "T1 POST",
    instance_count: int = 3,
) -> dict:
    return {
        "id": f"series_{index:020x}",
        "patient_context_id": patient_context_id,
        "modality": modality,
        "series_description": description,
        "image_type": ["ORIGINAL", "PRIMARY"],
        "instance_count": instance_count,
        "contrast_present": "POST" in description,
        "body_part": "BRAIN",
        "rows": 128,
        "columns": 128,
        "image_orientation_patient": [1, 0, 0, 0, 1, 0],
        "frame_of_reference_id": f"frame_{index:020x}",
        "instances": [],
        "review_status": "unreviewed",
    }


def _study(index: int, date: str | None, *series: dict) -> dict:
    return {
        "id": f"study_{index:020x}",
        "acquisition_date": date,
        "series": list(series),
        "review_status": "unreviewed",
    }


def _catalog(*studies: dict) -> dict:
    return {
        "schema_version": "1.0.0",
        "generated_at": "2026-08-29T08:00:00Z",
        "privacy": {
            "classification": "sensitive_local_medical_data",
            "direct_identifier_tags_excluded": True,
            "deidentified": False,
            "warning": "synthetic",
        },
        "source": {
            "root_label": "SYNTHETIC-ONLY",
            "immutable": True,
            "dicom_instances": sum(
                series["instance_count"] for study in studies for series in study["series"]
            ),
            "skipped_non_image_files": 0,
        },
        "studies": list(studies),
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


def _schema() -> dict:
    return json.loads(
        (
            Path(__file__).parents[3]
            / "schemas"
            / "scanview-longitudinal-readiness-v1.schema.json"
        ).read_text()
    )


def _request(
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


def test_current_mr_ct_shape_reports_missing_same_modality_followup_without_authority() -> None:
    catalog = _catalog(
        _study(1, "20260101", _series(1, description="SENSITIVE SECRET MRI")),
        _study(2, "20260102", _series(2, modality="CT", description="OTHER CT")),
    )
    report = build_longitudinal_readiness(
        catalog,
        generated_at="2026-08-29T08:01:00Z",
    )

    Draft202012Validator.check_schema(_schema())
    Draft202012Validator(_schema(), format_checker=FormatChecker()).validate(report)
    assert report["state"] == "no_same_modality_longitudinal_pair"
    assert report["source_summary"]["study_count"] == 2
    assert report["source_summary"]["candidate_pair_count"] == 0
    assert report["missing_data"] == ["future_distinct_study_same_modality_series"]
    assert [item["state"] for item in report["modality_readiness"]] == [
        "needs_distinct_study",
        "needs_distinct_study",
    ]
    assert not any(report["permissions"].values())
    serialized = json.dumps(report)
    assert "SENSITIVE SECRET" not in serialized
    assert "OTHER CT" not in serialized
    assert "SYNTHETIC-ONLY" not in serialized
    assert report["privacy"]["contains_pixels"] is False
    assert report["privacy"]["contains_paths"] is False


def test_same_patient_mr_pair_is_metadata_candidate_only() -> None:
    catalog = _catalog(
        _study(1, "20260101", _series(1)),
        _study(2, "20260201", _series(2)),
    )
    report = build_longitudinal_readiness(catalog)

    Draft202012Validator(_schema(), format_checker=FormatChecker()).validate(report)
    assert report["state"] == "candidate_pairs_require_human_review"
    assert report["missing_data"] == []
    assert report["source_summary"]["candidate_pair_count"] == 1
    assert report["modality_readiness"][0]["state"] == (
        "candidate_pairs_require_human_review"
    )
    candidate = report["candidate_pairs"][0]
    assert candidate["baseline_series_id"] == "series_00000000000000000001"
    assert candidate["followup_series_id"] == "series_00000000000000000002"
    assert candidate["review_status"] == "unreviewed"
    assert candidate["auto_approved"] is False
    assert "registration_required" in candidate["warnings"]
    assert "reasons" not in candidate
    assert not any(report["permissions"].values())


def test_cross_patient_missing_dates_and_ineligible_series_fail_closed() -> None:
    cross_patient = build_longitudinal_readiness(
        _catalog(
            _study(1, "20260101", _series(1, patient_context_id=PATIENT_A)),
            _study(2, "20260201", _series(2, patient_context_id=PATIENT_B)),
        )
    )
    assert cross_patient["candidate_pairs"] == []
    assert cross_patient["modality_readiness"][0]["state"] == (
        "needs_same_patient_context"
    )
    assert cross_patient["missing_data"] == ["same_patient_context_across_exams"]

    missing_date = build_longitudinal_readiness(
        _catalog(
            _study(1, None, _series(1)),
            _study(2, "20260201", _series(2)),
        )
    )
    assert missing_date["modality_readiness"][0]["state"] == "needs_complete_dates"
    assert missing_date["missing_data"] == ["complete_acquisition_dates"]

    localizers = build_longitudinal_readiness(
        _catalog(
            _study(1, "20260101", _series(1, description="LOCALIZER")),
            _study(2, "20260201", _series(2, description="SCOUT")),
        )
    )
    assert localizers["source_summary"]["eligible_series_count"] == 0
    assert localizers["modality_readiness"][0]["state"] == "no_eligible_series"
    assert localizers["missing_data"] == ["eligible_mr_or_ct_stack"]


def test_empty_invalid_and_oversized_candidate_sets_are_bounded() -> None:
    empty = build_longitudinal_readiness(_catalog())
    assert empty["state"] == "no_dicom_studies"
    assert empty["missing_data"] == ["dicom_studies"]
    Draft202012Validator(_schema(), format_checker=FormatChecker()).validate(empty)

    invalid = _catalog(_study(1, "20260231", _series(1)))
    with pytest.raises(ValueError, match="acquisition date"):
        build_longitudinal_readiness(invalid)

    many = _catalog(
        *[
            _study(index, f"202601{index:02d}", _series(index))
            for index in range(1, 25)
        ]
    )
    bounded = build_longitudinal_readiness(many)
    assert bounded["source_summary"]["candidate_pair_count"] == 276
    assert bounded["source_summary"]["reported_candidate_pair_count"] == (
        MAX_REPORTED_CANDIDATE_PAIRS
    )
    assert bounded["source_summary"]["candidate_pairs_truncated"] is True
    assert len(bounded["candidate_pairs"]) == MAX_REPORTED_CANDIDATE_PAIRS
    Draft202012Validator(_schema(), format_checker=FormatChecker()).validate(bounded)


def test_readiness_cli_writes_owner_only_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = tmp_path / "manifest.json"
    output = tmp_path / "readiness.json"
    manifest.write_text(
        json.dumps(
            _catalog(
                _study(1, "20260101", _series(1)),
                _study(2, "20260201", _series(2)),
            )
        )
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["scanview-agent", "readiness", str(manifest), "--output", str(output)],
    )

    main()

    report = json.loads(output.read_text())
    assert report["artifact_type"] == "scanview.longitudinal-readiness"
    assert report["source_summary"]["candidate_pair_count"] == 1
    assert output.stat().st_mode & 0o777 == 0o600


def test_loopback_readiness_is_authenticated_no_store_and_schema_valid() -> None:
    catalog = _catalog(
        _study(1, "20260101", _series(1)),
        _study(2, "20260201", _series(2)),
    )
    server = create_server(catalog, {}, port=0, token="synthetic-readiness-token")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        assert _request(server.server_port, "/v1/longitudinal-readiness")[0] == (
            HTTPStatus.UNAUTHORIZED
        )
        status, headers, body = _request(
            server.server_port,
            "/v1/longitudinal-readiness",
            headers={"Authorization": "Bearer synthetic-readiness-token"},
        )
        assert status == HTTPStatus.OK
        assert headers["Cache-Control"] == "no-store"
        report = json.loads(body)
        Draft202012Validator(_schema(), format_checker=FormatChecker()).validate(report)
        assert report["source_summary"]["candidate_pair_count"] == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
