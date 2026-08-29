from __future__ import annotations

import hashlib
import json
import stat
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError

from scanview_agent.registration import run_rigid_registration
from scanview_agent.registration_reviews import (
    ACCEPTED_DECISION,
    INSPECTION_MODES,
    QUALITATIVE_CHECKS,
    TOLERANCE_BASIS,
    build_registration_review,
    import_registration_review,
    registration_qa_agent_summary,
    registration_qa_context,
    registration_review_bytes,
    registration_review_errors,
    registration_review_summary,
    write_registration_review,
)
from test_registration import (
    FIXED_SERIES,
    MOVING_SERIES,
    fake_slicer,
    registration_catalog,
)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def registration_bundle(tmp_path: Path) -> Path:
    source_root = tmp_path / "dicom"
    catalog, registry, _ = registration_catalog(source_root)
    executable = fake_slicer(tmp_path / "Slicer")
    output = tmp_path / "registration"
    run_rigid_registration(
        catalog,
        registry,
        source_root=source_root,
        fixed_series_id=FIXED_SERIES,
        moving_series_id=MOVING_SERIES,
        output=output,
        slicer_executable=executable,
        expected_slicer_sha256=_sha256(executable.read_bytes()),
        attest_series_selection=True,
        timeout_seconds=60,
    )
    return output


def _recorded_quantitative() -> dict:
    return {
        "status": "recorded",
        "tolerance_mm": 1.0,
        "tolerance_basis": TOLERANCE_BASIS,
        "pairs": [
            {
                "label": "brainstem",
                "fixed_physical_mm": [10.0, 10.0, 10.0],
                "registered_moving_physical_mm": [10.1, 10.2, 10.3],
            },
            {
                "label": "ventricles",
                "fixed_physical_mm": [20.0, 22.0, 24.0],
                "registered_moving_physical_mm": [20.2, 22.1, 24.1],
            },
            {
                "label": "clivus",
                "fixed_physical_mm": [30.0, 35.0, 40.0],
                "registered_moving_physical_mm": [30.3, 35.2, 40.5],
            },
        ],
        "unavailable_reason": None,
    }


def _unavailable_quantitative() -> dict:
    return {
        "status": "unavailable",
        "tolerance_mm": None,
        "tolerance_basis": None,
        "pairs": [],
        "unavailable_reason": "Independent 3-D point pairs were not available.",
    }


def _full_inspection() -> dict:
    return {
        "planes": {
            "axial": {"normalized_min": 0.0, "normalized_max": 1.0},
            "coronal": {"normalized_min": 0.05, "normalized_max": 0.95},
            "sagittal": {"normalized_min": 0.01, "normalized_max": 0.99},
        },
        "modes": list(INSPECTION_MODES),
    }


def review_request(
    *,
    decision: str = ACCEPTED_DECISION,
    quantitative: bool = True,
) -> dict:
    accepted = decision == ACCEPTED_DECISION
    return {
        "schema_version": "2.0.0",
        "reviewer": {
            "name": "Synthetic Reviewer",
            "role": "clinician" if accepted else "patient_or_family",
            "organization": None,
            "training_status": (
                "self_attested_trained" if accepted else "self_attested_not_trained"
            ),
        },
        "attest": True,
        "decision": decision,
        "region_of_importance": "Reviewer-attested shared anatomy within moving-image sampling support.",
        "qualitative_checks": {
            key: accepted for key in QUALITATIVE_CHECKS
        },
        "inspection_evidence": _full_inspection() if accepted else {"planes": {}, "modes": []},
        "landmark_observations": [
            {"landmark": "brainstem", "status": "aligned", "note": "Reviewed."},
            {"landmark": "ventricles", "status": "aligned", "note": "Reviewed."},
            {
                "landmark": "outer_brain_or_skull_boundary",
                "status": "aligned",
                "note": "Reviewed throughout shared coverage.",
            },
        ],
        "quantitative_assessment": (
            _recorded_quantitative() if quantitative else _unavailable_quantitative()
        ),
        "regional_defects": [] if accepted else ["Synthetic mismatch."],
        "note": "Synthetic QA decision; not a medical conclusion.",
    }


def _schema() -> dict:
    repository_root = Path(__file__).parents[3]
    return json.loads(
        (
            repository_root
            / "schemas"
            / "scanview-registration-qa-review-v2.schema.json"
        ).read_text()
    )


def test_registration_qa_context_is_human_only_and_source_anchored(tmp_path: Path) -> None:
    bundle = registration_bundle(tmp_path)
    context = registration_qa_context(bundle)
    assert context["mode"] == "human_qa_preview"
    assert context["qa_preview_only"] is True
    assert context["watermark"] == "UNAPPROVED REGISTRATION — QA ONLY"
    assert context["intended_use"] == "shared_coverage_exploratory_overlay_swipe"
    assert context["allowed_decisions"] == [ACCEPTED_DECISION, "rejected"]
    assert context["display_policy"]["accepted_unlocks"] == ["overlay", "swipe"]
    assert "subtraction" in context["display_policy"]["always_locked"]
    assert set(context["volumes"]) == {"fixed", "moving", "registered_moving"}
    assert set(context["coverage_mask"]) == {
        "role",
        "filename",
        "url",
        "bytes",
        "sha256",
        "derived",
        "scalar_type",
        "binary_values",
        "semantics",
        "geometry",
    }
    assert context["coverage_mask"]["role"] == (
        "registered_moving_sampling_support_in_fixed_geometry"
    )
    assert context["coverage_mask"]["filename"] == "registered-moving-coverage.nrrd"
    assert context["coverage_mask"]["scalar_type"] == "uint8"
    assert context["coverage_mask"]["binary_values"] == [0, 1]
    assert context["coverage_mask"]["semantics"] == (
        "technical_sampling_support_not_anatomy_or_segmentation"
    )
    assert context["coverage_mask"]["geometry"] == context["volumes"]["fixed"][
        "geometry"
    ]
    assert context["display_policy"]["sampling_support_enforcement"] == (
        "required_pixel_mask"
    )
    assert context["display_policy"]["shared_anatomy_scope"] == (
        "reviewer_attested_visual_only"
    )
    assert context["volumes"]["registered_moving"]["resampled"] is True
    assert context["volumes"]["fixed"]["geometry"]["sizes"] == [2, 2, 2]
    assert str(bundle) not in json.dumps(context)

    agent = registration_qa_agent_summary(bundle)
    assert agent["available"] is True
    assert agent["display_unlocked"] is False
    assert agent["human_preview_required"] is True
    assert agent["external_api_required"] is False
    assert str(bundle) not in json.dumps(agent)


def test_acceptance_is_hash_linked_schema_valid_and_requires_live_bundle(
    tmp_path: Path,
) -> None:
    bundle = registration_bundle(tmp_path)
    record = build_registration_review(
        bundle,
        review_request(),
        created_at="2026-08-28T23:00:00Z",
    )
    assert record["review_status"] == ACCEPTED_DECISION
    assert record["scope"] == "shared_coverage"
    assert record["display_unlocks"] == {
        "overlay": True,
        "swipe": True,
        "subtraction": False,
        "mask_propagation": False,
        "segmentation": False,
        "resampled_image_measurements": False,
        "response_conclusions": False,
    }
    assert record["quantitative_assessment"]["tolerance_mm"] == 1.0
    assert record["quantitative_assessment"]["tolerance_basis"] == TOLERANCE_BASIS
    assert record["quantitative_assessment"]["maximum_residual_mm"] > 0.5
    assert record["integrity"]["unverified_previous_review_sha256"] is None
    assert record["integrity"]["event_sha256"]
    source = record["source_registration"]
    assert source["coverage_mask_sha256"] == next(
        item["sha256"]
        for item in source["bundle_files"]
        if item["name"] == "registered-moving-coverage.nrrd"
    )
    assert source["coverage_mask_geometry"] == source["fixed_geometry"]
    assert source["coverage_mask_geometry"] == source["registered_geometry"]
    assert source["coverage_mask"]["semantics"] == (
        "technical_sampling_support_not_anatomy_or_segmentation"
    )
    assert source["coverage_mask"]["total_voxel_count"] == 8
    assert 0 < source["coverage_mask"]["foreground_voxel_count"] <= 8
    assert any("not a digital signature" in item for item in record["limitations"])
    assert registration_review_errors(record, registration_directory=bundle) == []

    schema = _schema()
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(record)

    standalone = registration_review_summary(json.dumps(record).encode())
    assert standalone["valid"] is True
    assert standalone["source_integrity"] is False
    assert standalone["display_unlocked"] is False

    live = registration_review_summary(
        json.dumps(record).encode(), registration_directory=bundle
    )
    assert live["valid"] is True
    assert live["source_integrity"] is True
    assert live["display_unlocked"] is True


def test_rejected_records_remain_flexible_and_locked(tmp_path: Path) -> None:
    bundle = registration_bundle(tmp_path)
    request = review_request(decision="rejected", quantitative=False)
    request["landmark_observations"] = [
        {"landmark": "brainstem", "status": "not_visible", "note": "Not visible."}
    ]
    record = build_registration_review(bundle, request)
    assert record["review_status"] == "rejected"
    assert record["scope"] == "none"
    assert not any(record["display_unlocks"].values())
    assert "SPATIAL ERROR NOT QUANTIFIED" in record["display_label"]
    Draft202012Validator(_schema(), format_checker=FormatChecker()).validate(record)


@pytest.mark.parametrize(
    ("role", "training"),
    [
        ("clinician", "self_attested_not_trained"),
        ("medical_physicist", "self_attested_not_trained"),
        ("patient_or_family", "self_attested_trained"),
        ("researcher_or_engineer", "self_attested_trained"),
    ],
)
def test_acceptance_requires_trained_clinician_or_physicist(
    tmp_path: Path,
    role: str,
    training: str,
) -> None:
    bundle = registration_bundle(tmp_path)
    request = review_request()
    request["reviewer"]["role"] = role
    request["reviewer"]["training_status"] = training
    with pytest.raises(ValueError, match="trained clinician or medical physicist"):
        build_registration_review(bundle, request)

    accepted = review_request()
    accepted["reviewer"]["role"] = "medical_physicist"
    assert build_registration_review(bundle, accepted)["review_status"] == ACCEPTED_DECISION


@pytest.mark.parametrize("status", ["uncertain", "not_visible", "misaligned"])
def test_acceptance_requires_three_observations_all_aligned(
    tmp_path: Path,
    status: str,
) -> None:
    bundle = registration_bundle(tmp_path)
    request = review_request()
    request["landmark_observations"][1]["status"] = status
    with pytest.raises(ValueError, match="every observation aligned"):
        build_registration_review(bundle, request)

    too_few = review_request()
    too_few["landmark_observations"] = too_few["landmark_observations"][:2]
    with pytest.raises(ValueError, match="at least three observations"):
        build_registration_review(bundle, too_few)


def test_acceptance_requires_fixed_tolerance_and_true_3d_pairs(tmp_path: Path) -> None:
    bundle = registration_bundle(tmp_path)

    unavailable = review_request(quantitative=False)
    with pytest.raises(ValueError, match="recorded 3-D landmark pairs"):
        build_registration_review(bundle, unavailable)

    arbitrary = review_request()
    arbitrary["quantitative_assessment"]["tolerance_mm"] = 100.0
    with pytest.raises(ValueError, match="maximum fixed-volume voxel spacing"):
        build_registration_review(bundle, arbitrary)

    posthoc_basis = review_request()
    posthoc_basis["quantitative_assessment"]["tolerance_basis"] = "Chosen after review."
    with pytest.raises(ValueError, match="basis is fixed"):
        build_registration_review(bundle, posthoc_basis)

    out_of_plane_failure = review_request()
    out_of_plane_failure["quantitative_assessment"]["pairs"][2][
        "registered_moving_physical_mm"
    ][2] = 42.0
    with pytest.raises(ValueError, match="exceeds its predeclared tolerance"):
        build_registration_review(bundle, out_of_plane_failure)

    planar = review_request()
    for pair in planar["quantitative_assessment"]["pairs"]:
        pair["fixed_physical_mm"][2] = 10.0
        pair["registered_moving_physical_mm"][2] = 10.1
    with pytest.raises(ValueError, match="all three patient-space dimensions"):
        build_registration_review(bundle, planar)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda evidence: evidence["planes"].pop("sagittal"),
        lambda evidence: evidence["planes"]["axial"].update(normalized_min=0.051),
        lambda evidence: evidence["planes"]["coronal"].update(normalized_max=0.949),
        lambda evidence: evidence["modes"].remove("swipe"),
    ],
)
def test_acceptance_requires_full_inspection_evidence(
    tmp_path: Path,
    mutation,
) -> None:
    bundle = registration_bundle(tmp_path)
    request = review_request()
    mutation(request["inspection_evidence"])
    with pytest.raises(ValueError, match="full normalized coverage"):
        build_registration_review(bundle, request)


def test_acceptance_requires_explicit_coverage_boundary_attestation(
    tmp_path: Path,
) -> None:
    bundle = registration_bundle(tmp_path)
    request = review_request()
    request["qualitative_checks"][
        "coverage_mask_boundary_and_excluded_region_reviewed"
    ] = False
    with pytest.raises(ValueError, match="every qualitative check"):
        build_registration_review(bundle, request)


def test_strict_json_rejects_duplicates_nonfinite_and_controls(tmp_path: Path) -> None:
    bundle = registration_bundle(tmp_path)
    for payload in (
        b'{"schema_version":"2.0.0","schema_version":"2.0.0"}',
        b'{"schema_version":NaN}',
    ):
        with pytest.raises(ValueError, match="invalid JSON"):
            registration_review_bytes(bundle, payload)
        assert registration_review_summary(payload)["valid"] is False

    controlled = review_request()
    controlled["note"] = "unsafe\u0000note"
    with pytest.raises(ValueError, match="invalid JSON"):
        registration_review_bytes(bundle, json.dumps(controlled).encode())


def test_malformed_nested_collections_fail_closed_without_throwing(tmp_path: Path) -> None:
    bundle = registration_bundle(tmp_path)
    record = build_registration_review(bundle, review_request())
    mutations = []
    for path, replacement in (
        (("quantitative_assessment", "pairs"), None),
        (("inspection_evidence", "planes"), []),
        (("source_registration", "bundle_files"), [None]),
        (("landmark_observations",), {"unexpected": True}),
        (("regional_defects",), [None]),
    ):
        malformed = deepcopy(record)
        target = malformed
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = replacement
        mutations.append(malformed)
    for malformed in mutations:
        errors = registration_review_errors(malformed)
        assert errors
        assert registration_review_summary(json.dumps(malformed).encode())["display_unlocked"] is False


@pytest.mark.parametrize(
    "tamper",
    ["digest", "geometry", "date", "coverage_digest", "coverage_semantics", "coverage_count"],
)
def test_standalone_anchor_checks_internal_consistency(tmp_path: Path, tamper: str) -> None:
    bundle = registration_bundle(tmp_path)
    record = build_registration_review(bundle, review_request())
    altered = deepcopy(record)
    source = altered["source_registration"]
    if tamper == "digest":
        source["transform_sha256"] = "0" * 64
    elif tamper == "geometry":
        source["registered_geometry"]["voxel_spacing_mm"][0] = 2.0
    elif tamper == "coverage_digest":
        source["coverage_mask_sha256"] = "0" * 64
    elif tamper == "coverage_semantics":
        source["coverage_mask"]["semantics"] = "anatomy"
    elif tamper == "coverage_count":
        source["coverage_mask"]["foreground_voxel_count"] = 0
    else:
        source["moving"]["acquisition_date"] = source["fixed"]["acquisition_date"]
    assert "source registration is invalid" in " ".join(registration_review_errors(altered))
    summary = registration_review_summary(json.dumps(altered).encode())
    assert summary["valid"] is False
    assert summary["display_unlocked"] is False


def test_v1_review_record_fails_closed(tmp_path: Path) -> None:
    bundle = registration_bundle(tmp_path)
    record = build_registration_review(bundle, review_request())
    record["schema_version"] = "1.0.0"
    summary = registration_review_summary(
        json.dumps(record).encode(), registration_directory=bundle
    )
    assert summary["valid"] is False
    assert summary["display_unlocked"] is False


def test_schema_rejects_semantically_unsafe_accepted_record(tmp_path: Path) -> None:
    bundle = registration_bundle(tmp_path)
    record = build_registration_review(bundle, review_request())
    validator = Draft202012Validator(_schema(), format_checker=FormatChecker())

    untrained = deepcopy(record)
    untrained["reviewer"]["training_status"] = "self_attested_not_trained"
    with pytest.raises(ValidationError):
        validator.validate(untrained)

    incomplete = deepcopy(record)
    incomplete["inspection_evidence"]["planes"]["axial"]["normalized_max"] = 0.5
    with pytest.raises(ValidationError):
        validator.validate(incomplete)

    unsafe_coverage_claim = deepcopy(record)
    unsafe_coverage_claim["source_registration"]["coverage_mask"][
        "semantics"
    ] = "anatomy"
    with pytest.raises(ValidationError):
        validator.validate(unsafe_coverage_claim)


def test_registration_qa_rejects_tampering_and_writes_atomically(tmp_path: Path) -> None:
    bundle = registration_bundle(tmp_path)
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(review_request(decision="rejected", quantitative=False)))
    first = tmp_path / "review-1.json"
    record = write_registration_review(bundle, request_path, first)
    assert record["review_status"] == "rejected"
    assert stat.S_IMODE(first.stat().st_mode) == 0o600
    assert not list(tmp_path.glob(".review-1.json.*.tmp"))

    original = first.read_bytes()
    with pytest.raises(FileExistsError):
        write_registration_review(bundle, request_path, first)
    assert first.read_bytes() == original
    assert not list(tmp_path.glob(".review-1.json.*.tmp"))

    second = tmp_path / "review-2.json"
    write_registration_review(
        bundle,
        request_path,
        second,
        previous_review=first,
    )
    second_record = json.loads(second.read_text())
    assert second_record["integrity"]["unverified_previous_review_sha256"] == _sha256(
        first.read_bytes()
    )
    assert registration_review_summary(second, registration_directory=bundle)["valid"] is True

    tampered = deepcopy(second_record)
    tampered["note"] = "Changed after review."
    assert "event hash" in " ".join(registration_review_errors(tampered))

    registration_path = bundle / "registration.json"
    registration_payload = registration_path.read_bytes()
    registration_path.write_bytes(registration_payload + b" ")
    summary = registration_review_summary(second, registration_directory=bundle)
    assert summary["valid"] is False
    assert summary["display_unlocked"] is False
    registration_path.write_bytes(registration_payload)


def test_downloaded_review_import_validates_live_bundle_and_seals_owner_only(
    tmp_path: Path,
) -> None:
    bundle = registration_bundle(tmp_path)
    record = build_registration_review(bundle, review_request())
    downloaded = tmp_path / "browser-download.json"
    payload = json.dumps(record, indent=2).encode() + b"\n"
    downloaded.write_bytes(payload)
    downloaded.chmod(0o644)
    sealed = tmp_path / "sealed-review.json"

    summary = import_registration_review(bundle, downloaded, sealed)
    assert summary["valid"] is True
    assert summary["source_integrity"] is True
    assert summary["display_unlocked"] is True
    assert sealed.read_bytes() == payload
    metadata = sealed.stat()
    assert stat.S_IMODE(metadata.st_mode) == 0o600
    assert metadata.st_nlink == 1
    with pytest.raises(FileExistsError):
        import_registration_review(bundle, downloaded, sealed)

    tampered = json.loads(downloaded.read_text())
    tampered["note"] = "Changed after browser download."
    downloaded.write_text(json.dumps(tampered))
    refused = tmp_path / "refused-review.json"
    with pytest.raises(ValueError, match="invalid or for another live bundle"):
        import_registration_review(bundle, downloaded, refused)
    assert not refused.exists()

    symlink = tmp_path / "download-link.json"
    symlink.symlink_to(downloaded)
    with pytest.raises(ValueError, match="cannot be read safely"):
        import_registration_review(bundle, symlink, tmp_path / "symlink-refused.json")

    oversized = tmp_path / "oversized-download.json"
    with oversized.open("wb") as stream:
        stream.truncate(4 * 1024 * 1024 + 1)
    with pytest.raises(ValueError, match="too large"):
        import_registration_review(bundle, oversized, tmp_path / "oversized-refused.json")
