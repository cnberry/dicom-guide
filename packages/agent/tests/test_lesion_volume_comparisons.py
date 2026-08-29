from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from scanview_agent.lesion_volume_comparisons import (
    ATTESTATION,
    lesion_volume_comparison_archive_bytes,
    lesion_volume_comparison_from_transport,
    lesion_volume_comparison_summary,
    write_lesion_volume_comparison,
)
from test_lesion_volumes import _build_bundle, _build_review_bundle


def _request(
    *,
    decision: str = "accepted_for_volume_change_discussion",
) -> dict:
    accepted = decision == "accepted_for_volume_change_discussion"
    return {
        "schema_version": "1.0.0",
        "artifact_type": "scanview.lesion-volume-comparison-request",
        "reviewer": {
            "name": "Synthetic Pairing Reviewer",
            "role": "neuro_oncologist",
            "organization": "Synthetic clinic",
            "identity_verification": "self_asserted_unverified",
        },
        "decision": decision,
        "pairing": {
            "same_lesion_identity": "confirmed" if accepted else "uncertain",
            "same_represented_tissue": "confirmed" if accepted else "uncertain",
            "chronology": "confirmed" if accepted else "not_confirmed",
            "acquisition_comparability": "suitable" if accepted else "not_suitable",
            "boundary_comparability": "suitable" if accepted else "not_suitable",
            "registration_consideration": "not_required",
            "limitation_note": "",
            "treatment_context_note": "Synthetic treatment interval; no causal attribution.",
        },
        "checklist": {
            "both_original_sources_reviewed": accepted,
            "both_complete_boundaries_reviewed": accepted,
            "boundary_definitions_compared": accepted,
            "same_lesion_identity_reviewed": accepted,
            "same_represented_tissue_reviewed": accepted,
            "acquisition_differences_reviewed": accepted,
            "chronology_confirmed": accepted,
            "registration_need_reviewed": accepted,
        },
        "attestation": ATTESTATION,
    }


def _write_request(tmp_path: Path, value: dict, name: str = "pairing-request.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(value, indent=2) + "\n")
    return path


def _pair(
    tmp_path: Path,
    *,
    baseline_date: str | None = "20260101",
    followup_date: str | None = "20260201",
    baseline_patient: str = "SYNTHETIC",
    followup_patient: str = "SYNTHETIC",
    baseline_modality: str = "MR",
    followup_modality: str = "MR",
    baseline_instance_dates: list[str | None] | None = None,
) -> tuple[Path, Path, Path, Path]:
    source_root = tmp_path / "source"
    baseline_evidence = _build_bundle(
        tmp_path,
        source_root=source_root,
        source_prefix="baseline",
        acquisition_date=baseline_date,
        instance_acquisition_dates=baseline_instance_dates,
        patient_id=baseline_patient,
        use_catalog_ids=True,
        artifact_id="seg_11111111-1111-4111-8111-111111111111",
        foreground_voxels=3,
        modality=baseline_modality,
    )
    followup_evidence = _build_bundle(
        tmp_path,
        source_root=source_root,
        source_prefix="followup",
        acquisition_date=followup_date,
        patient_id=followup_patient,
        use_catalog_ids=True,
        artifact_id="seg_22222222-2222-4222-8222-222222222222",
        foreground_voxels=4,
        modality=followup_modality,
    )
    baseline, _, _, _ = _build_review_bundle(
        tmp_path,
        evidence_bundle=baseline_evidence,
        review_id="review_11111111-1111-4111-8111-111111111111",
        output_name="baseline-review.zip",
    )
    followup, _, _, _ = _build_review_bundle(
        tmp_path,
        evidence_bundle=followup_evidence,
        review_id="review_22222222-2222-4222-8222-222222222222",
        output_name="followup-review.zip",
    )
    request = _write_request(tmp_path, _request())
    return baseline, followup, request, source_root


def _replace_member(
    archive_bytes: bytes,
    destination: Path,
    replacements: dict[str, bytes],
) -> Path:
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as original, zipfile.ZipFile(
        destination, "w", compression=zipfile.ZIP_DEFLATED
    ) as changed:
        for name in original.namelist():
            changed.writestr(name, replacements.get(name, original.read(name)))
    return destination


def test_builds_and_recursively_validates_qualified_volume_change(tmp_path: Path) -> None:
    baseline, followup, request, source_root = _pair(tmp_path)
    payload = lesion_volume_comparison_archive_bytes(
        baseline,
        followup,
        request,
        source_root,
        comparison_id="volume_pair_33333333-3333-4333-8333-333333333333",
        created_at="2026-02-02T12:00:00Z",
    )
    summary = lesion_volume_comparison_summary(io.BytesIO(payload), source_root)

    assert summary["valid"]
    assert summary["decision"] == "accepted_for_volume_change_discussion"
    assert summary["source_validated"]
    assert summary["baseline_reviewed_volume_ml"] == pytest.approx(0.00225)
    assert summary["followup_reviewed_volume_ml"] == pytest.approx(0.003)
    assert summary["absolute_volume_change_ml"] == pytest.approx(0.00075)
    assert summary["percent_volume_change"] == pytest.approx(100 / 3)
    assert summary["numeric_direction"] == "increased"
    assert summary["elapsed_days"] == 31
    assert summary["evidence_use"] == "qualified_reviewed_volume_change_for_discussion_only"
    assert not summary["spatial_overlay"]
    assert not summary["voxelwise_change_localization"]
    assert not summary["causal_treatment_attribution"]
    assert not summary["response_classification"]
    assert not summary["diagnosis"]
    assert not summary["clinical_conclusion"]

    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        assert set(archive.namelist()) == {
            "comparison.json",
            "baseline-review.zip",
            "followup-review.zip",
            "review.html",
            "README.txt",
        }
        record = json.loads(archive.read("comparison.json"))
        page = archive.read("review.html").decode()
    schema = json.loads(
        (
            Path(__file__).parents[3]
            / "schemas"
            / "scanview-lesion-volume-comparison-review-v1.schema.json"
        ).read_text()
    )
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(record)
    assert "NOT A RESPONSE CLASSIFICATION" in page
    assert "NO TREATMENT CAUSALITY" in page
    serialized = json.dumps(summary)
    assert "Synthetic Pairing Reviewer" not in serialized
    assert "Synthetic clinic" not in serialized
    assert record["timepoints"]["baseline"]["study_id"] not in serialized


def test_revision_record_is_valid_but_withholds_change(tmp_path: Path) -> None:
    baseline, followup, _, source_root = _pair(tmp_path)
    request = _write_request(tmp_path, _request(decision="revision_requested"))
    payload = lesion_volume_comparison_archive_bytes(
        baseline, followup, request, source_root
    )
    summary = lesion_volume_comparison_summary(io.BytesIO(payload), source_root)
    assert summary["valid"]
    assert summary["decision"] == "revision_requested"
    assert summary["baseline_reviewed_volume_ml"] is None
    assert summary["percent_volume_change"] is None
    assert summary["evidence_use"] == "pairing_revision_or_rejection_only"


def test_rejects_cross_patient_and_same_review_pairs(tmp_path: Path) -> None:
    baseline, followup, request, source_root = _pair(
        tmp_path,
        followup_patient="SYNTHETIC-OTHER",
    )
    with pytest.raises(ValueError, match="patient context"):
        lesion_volume_comparison_archive_bytes(
            baseline, followup, request, source_root
        )

    clean = tmp_path / "clean"
    clean.mkdir()
    baseline, _, request, source_root = _pair(clean)
    with pytest.raises(ValueError, match="distinct studies"):
        lesion_volume_comparison_archive_bytes(
            baseline, baseline, request, source_root
        )


def test_rejects_cross_modality_boundary_reviews(tmp_path: Path) -> None:
    baseline, followup, request, source_root = _pair(
        tmp_path,
        followup_modality="CT",
    )
    with pytest.raises(ValueError, match="same modality"):
        lesion_volume_comparison_archive_bytes(
            baseline, followup, request, source_root
        )


def test_explicit_catalog_is_authoritative_even_when_empty(tmp_path: Path) -> None:
    baseline, followup, request, source_root = _pair(tmp_path)
    with pytest.raises(ValueError, match="not an exact member"):
        lesion_volume_comparison_archive_bytes(
            baseline,
            followup,
            request,
            source_root,
            catalog={},
        )


def test_rejects_reversed_or_missing_live_dicom_chronology(tmp_path: Path) -> None:
    reversed_dir = tmp_path / "reversed"
    reversed_dir.mkdir()
    baseline, followup, request, source_root = _pair(
        reversed_dir,
        baseline_date="20260301",
        followup_date="20260201",
    )
    with pytest.raises(ValueError, match="must precede"):
        lesion_volume_comparison_archive_bytes(
            baseline, followup, request, source_root
        )

    inconsistent_dir = tmp_path / "inconsistent"
    inconsistent_dir.mkdir()
    baseline, followup, request, source_root = _pair(
        inconsistent_dir,
        baseline_instance_dates=["20260101", "20260102", "20260101"],
    )
    with pytest.raises(ValueError, match="do not share one exact"):
        lesion_volume_comparison_archive_bytes(
            baseline, followup, request, source_root
        )

    missing_dir = tmp_path / "missing"
    missing_dir.mkdir()
    baseline, followup, request, source_root = _pair(
        missing_dir,
        baseline_date=None,
    )
    with pytest.raises(ValueError, match="acquisition date"):
        lesion_volume_comparison_archive_bytes(
            baseline, followup, request, source_root
        )


def test_acceptance_requires_every_pairing_judgment_and_check(tmp_path: Path) -> None:
    baseline, followup, _, source_root = _pair(tmp_path)
    request_value = _request()
    request_value["pairing"]["same_lesion_identity"] = "uncertain"
    request_value["checklist"]["same_lesion_identity_reviewed"] = False
    request = _write_request(tmp_path, request_value)
    with pytest.raises(ValueError, match="confirmed same-lesion"):
        lesion_volume_comparison_archive_bytes(
            baseline, followup, request, source_root
        )


def test_documented_limitations_require_a_note(tmp_path: Path) -> None:
    baseline, followup, _, source_root = _pair(tmp_path)
    request_value = _request()
    request_value["pairing"]["acquisition_comparability"] = "suitable_with_limitations"
    request = _write_request(tmp_path, request_value)
    with pytest.raises(ValueError, match="require a note"):
        lesion_volume_comparison_archive_bytes(
            baseline, followup, request, source_root
        )


def test_source_tamper_withholds_all_comparison_values(tmp_path: Path) -> None:
    baseline, followup, request, source_root = _pair(tmp_path)
    payload = lesion_volume_comparison_archive_bytes(
        baseline, followup, request, source_root
    )
    with (source_root / "followup-0.dcm").open("ab") as stream:
        stream.write(b"changed")
    summary = lesion_volume_comparison_summary(io.BytesIO(payload), source_root)
    assert not summary["valid"]
    assert summary["baseline_reviewed_volume_ml"] is None
    assert summary["percent_volume_change"] is None
    assert summary["evidence_use"] == "none"


def test_rejects_numeric_record_or_static_page_tamper(tmp_path: Path) -> None:
    baseline, followup, request, source_root = _pair(tmp_path)
    payload = lesion_volume_comparison_archive_bytes(
        baseline, followup, request, source_root
    )
    with zipfile.ZipFile(io.BytesIO(payload)) as original:
        record = json.loads(original.read("comparison.json"))
        page = original.read("review.html")
    record["comparison"]["percent_change"] = 99
    changed = _replace_member(
        payload,
        tmp_path / "changed-comparison.zip",
        {"comparison.json": (json.dumps(record, indent=2) + "\n").encode()},
    )
    summary = lesion_volume_comparison_summary(changed, source_root)
    assert not summary["valid"]
    assert any("percent_change" in error or "exact nested reviews" in error for error in summary["errors"])

    page_record = json.loads(json.dumps(record))
    page_record["comparison"]["percent_change"] = 100 / 3
    page_record["files"]["review_page"]["bytes"] = len(page + b"changed")
    import hashlib

    page_record["files"]["review_page"]["sha256"] = hashlib.sha256(page + b"changed").hexdigest()
    changed_page = _replace_member(
        payload,
        tmp_path / "changed-page.zip",
        {
            "comparison.json": (json.dumps(page_record, indent=2) + "\n").encode(),
            "review.html": page + b"changed",
        },
    )
    summary = lesion_volume_comparison_summary(changed_page, source_root)
    assert not summary["valid"]
    assert "review.html does not exactly present the validated comparison record" in summary["errors"]


def test_transport_shape_and_non_overwriting_private_output(tmp_path: Path) -> None:
    baseline, followup, request, source_root = _pair(tmp_path)
    transport = io.BytesIO()
    with zipfile.ZipFile(transport, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("baseline-review.zip", baseline.read_bytes())
        archive.writestr("followup-review.zip", followup.read_bytes())
        archive.writestr("pairing-request.json", request.read_bytes())
    payload = lesion_volume_comparison_from_transport(
        transport.getvalue(), source_root
    )
    assert lesion_volume_comparison_summary(io.BytesIO(payload), source_root)["valid"]

    output = tmp_path / "saved-comparison.zip"
    summary = write_lesion_volume_comparison(
        baseline, followup, request, source_root, output
    )
    assert summary["valid"]
    assert output.stat().st_mode & 0o777 == 0o600
    with pytest.raises(ValueError, match="already exists"):
        write_lesion_volume_comparison(
            baseline, followup, request, source_root, output
        )

    with zipfile.ZipFile(transport, "a") as archive:
        archive.writestr("extra.txt", "no")
    with pytest.raises(ValueError, match="exactly"):
        lesion_volume_comparison_from_transport(transport.getvalue(), source_root)


def test_rejects_extra_output_member_and_duplicate_json_fields(tmp_path: Path) -> None:
    baseline, followup, request, source_root = _pair(tmp_path)
    payload = lesion_volume_comparison_archive_bytes(
        baseline, followup, request, source_root
    )
    extra = _replace_member(payload, tmp_path / "extra.zip", {})
    with zipfile.ZipFile(extra, "a") as archive:
        archive.writestr("extra.txt", "no")
    summary = lesion_volume_comparison_summary(extra, source_root)
    assert not summary["valid"]
    assert summary["evidence_use"] == "none"

    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        original = archive.read("comparison.json")
    duplicate = b'{"schema_version":"1.0.0",' + original[1:]
    changed = _replace_member(
        payload,
        tmp_path / "duplicate.zip",
        {"comparison.json": duplicate},
    )
    summary = lesion_volume_comparison_summary(changed, source_root)
    assert not summary["valid"]
    assert "comparison.json is not strict valid UTF-8 JSON" in summary["errors"]


def test_malformed_pairing_record_fails_closed_without_an_exception(tmp_path: Path) -> None:
    baseline, followup, request, source_root = _pair(tmp_path)
    payload = lesion_volume_comparison_archive_bytes(
        baseline, followup, request, source_root
    )
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        record = json.loads(archive.read("comparison.json"))
    record["pairing_review"] = []
    changed = _replace_member(
        payload,
        tmp_path / "malformed-pairing.zip",
        {"comparison.json": (json.dumps(record, indent=2) + "\n").encode()},
    )

    summary = lesion_volume_comparison_summary(changed, source_root)

    assert not summary["valid"]
    assert "pairing_review is invalid" in summary["errors"]
    assert summary["percent_volume_change"] is None
    assert summary["evidence_use"] == "none"
