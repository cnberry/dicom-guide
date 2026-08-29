from __future__ import annotations

import hashlib
import json
import os
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from scanview_agent import registration_display as registration_display_module
from scanview_agent.registration_display import (
    ALWAYS_LOCKED,
    SHARED_COVERAGE_ENFORCEMENT,
    reviewed_registration_display_context,
    reviewed_registration_display_errors,
    reviewed_registration_display_summary,
)
from scanview_agent.registration_reviews import (
    ACCEPTED_DECISION,
    build_registration_review,
    write_registration_review,
)
from test_registration_reviews import registration_bundle, review_request


def _schema() -> dict:
    repository_root = Path(__file__).parents[3]
    return json.loads(
        (
            repository_root
            / "schemas"
            / "scanview-reviewed-registration-display-v1.schema.json"
        ).read_text()
    )


def _saved_review(
    tmp_path: Path,
    bundle: Path,
    *,
    decision: str = ACCEPTED_DECISION,
) -> Path:
    request = review_request(
        decision=decision,
        quantitative=decision == ACCEPTED_DECISION,
    )
    request_path = tmp_path / f"{decision}-request.json"
    request_path.write_text(json.dumps(request))
    review_path = tmp_path / f"{decision}-review.json"
    write_registration_review(bundle, request_path, review_path)
    return review_path


def _write_private(path: Path, payload: bytes) -> Path:
    path.write_bytes(payload)
    path.chmod(0o600)
    return path


def test_accepted_live_review_produces_exact_hash_bound_context(tmp_path: Path) -> None:
    bundle = registration_bundle(tmp_path)
    review_path = _saved_review(tmp_path, bundle)
    record = json.loads(review_path.read_text())
    context = reviewed_registration_display_context(bundle, review_path)

    schema = _schema()
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(context)

    assert context["display_status"] == (
        "authorized_for_exploratory_shared_coverage_overlay_swipe"
    )
    assert context["intended_use"] == "shared_coverage_exploratory_overlay_swipe"
    assert context["scope"] == "shared_coverage"
    assert context["review"] == {
        "review_id": record["review_id"],
        "job_id": record["source_registration"]["job_id"],
        "decision": ACCEPTED_DECISION,
        "review_sha256": hashlib.sha256(review_path.read_bytes()).hexdigest(),
        "event_sha256": record["integrity"]["event_sha256"],
        "self_attested": True,
    }
    assert context["source"]["manifest_sha256"] == record["source_registration"][
        "manifest_sha256"
    ]
    assert context["source"]["bundle_sha256"] == record["source_registration"][
        "bundle_sha256"
    ]
    assert context["source"]["transform_sha256"] == record["source_registration"][
        "transform_sha256"
    ]
    assert context["source"]["bundle_files"] == record["source_registration"][
        "bundle_files"
    ]
    assert context["source"]["modality"] in {"MR", "CT"}
    assert context["source"]["fixed"]["acquisition_date"] < context["source"][
        "moving"
    ]["acquisition_date"]

    assert set(context["volumes"]) == {"fixed", "registered_moving"}
    assert "moving" not in context["volumes"]
    fixed = context["volumes"]["fixed"]
    registered = context["volumes"]["registered_moving"]
    assert fixed["role"] == "fixed_earlier_reference"
    assert fixed["filename"] == "fixed.nrrd"
    assert fixed["url"] == "/v1/reviewed-registration/files/fixed.nrrd"
    assert fixed["derived"] is True
    assert fixed["resampled"] is False
    assert registered["role"] == "moving_later_registered_to_fixed"
    assert registered["filename"] == "registered-moving.nrrd"
    assert registered["url"] == (
        "/v1/reviewed-registration/files/registered-moving.nrrd"
    )
    assert registered["derived"] is True
    assert registered["resampled"] is True
    assert fixed["geometry"] == registered["geometry"]
    assert fixed["geometry"] == record["source_registration"]["fixed_geometry"]

    policy = context["display_policy"]
    assert policy["allowed_modes"] == ["opacity", "swipe"]
    assert policy["always_locked"] == ALWAYS_LOCKED
    assert policy["native_moving_available"] is False
    assert policy["native_moving_withheld"] is True
    assert policy["shared_coverage_enforcement"] == SHARED_COVERAGE_ENFORCEMENT
    assert any("outside their shared anatomical coverage" in item for item in context["limitations"])
    assert any("no pixel-level" in item for item in context["limitations"])
    assert any("self asserted and unauthenticated" in item for item in context["limitations"])
    assert set(context["reviewer"]) == {
        "role",
        "training_status",
        "identity_status",
    }
    assert "name" not in json.dumps(context["reviewer"])
    assert "organization" not in context["reviewer"]
    assert str(bundle) not in json.dumps(context)
    assert str(review_path) not in json.dumps(context)


def test_accepted_live_summary_is_small_privacy_safe_and_authorized(
    tmp_path: Path,
) -> None:
    bundle = registration_bundle(tmp_path)
    review_path = _saved_review(tmp_path, bundle)
    summary = reviewed_registration_display_summary(bundle, review_path)
    assert summary == {
        "schema_version": "1.0.0",
        "artifact_type": "reviewed_registration_display_summary",
        "available": True,
        "display_status": "authorized",
        "display_authorized": True,
        "review_status": ACCEPTED_DECISION,
        "intended_use": "shared_coverage_exploratory_overlay_swipe",
        "scope": "shared_coverage",
        "allowed_display_modes": ["opacity", "swipe"],
        "external_api_required": False,
        "errors": [],
    }
    serialized = json.dumps(summary)
    assert str(bundle) not in serialized
    assert str(review_path) not in serialized
    assert "study_" not in serialized
    assert "series_" not in serialized
    assert "acquisition_date" not in serialized
    assert "sha256" not in serialized
    assert reviewed_registration_display_errors(bundle, review_path) == []


def test_accepted_review_exceeding_display_byte_caps_remains_locked(
    tmp_path: Path,
    monkeypatch,
) -> None:
    bundle = registration_bundle(tmp_path)
    review_path = _saved_review(tmp_path, bundle)
    monkeypatch.setattr(
        registration_display_module,
        "MAX_REVIEWED_ENCODED_VOLUME_BYTES",
        1,
    )
    summary = reviewed_registration_display_summary(bundle, review_path)
    assert summary["available"] is False
    assert summary["display_status"] == "invalid"
    assert summary["display_authorized"] is False
    assert summary["allowed_display_modes"] == []
    assert summary["errors"] == [
        "reviewed registration volumes exceed the display safety limit"
    ]


def test_rejected_review_is_valid_but_remains_locked(tmp_path: Path) -> None:
    bundle = registration_bundle(tmp_path)
    review_path = _saved_review(tmp_path, bundle, decision="rejected")
    summary = reviewed_registration_display_summary(bundle, review_path)
    assert summary["available"] is True
    assert summary["display_status"] == "locked"
    assert summary["display_authorized"] is False
    assert summary["review_status"] == "rejected"
    assert summary["scope"] == "none"
    assert summary["allowed_display_modes"] == []
    assert summary["errors"] == ["registration review did not authorize display"]
    with pytest.raises(ValueError, match="not authorized"):
        reviewed_registration_display_context(bundle, review_path)


def test_standalone_review_bytes_never_authorize_display(tmp_path: Path) -> None:
    bundle = registration_bundle(tmp_path)
    review_path = _saved_review(tmp_path, bundle)
    payload = review_path.read_bytes()
    summary = reviewed_registration_display_summary(bundle, payload)
    assert summary["available"] is False
    assert summary["display_status"] == "invalid"
    assert summary["display_authorized"] is False
    assert summary["review_status"] == "invalid"
    assert summary["allowed_display_modes"] == []
    assert "standalone" in " ".join(summary["errors"])
    with pytest.raises(ValueError, match="not authorized"):
        reviewed_registration_display_context(bundle, payload)


def test_missing_inputs_are_unavailable_and_locked(tmp_path: Path) -> None:
    bundle = registration_bundle(tmp_path)
    review_path = _saved_review(tmp_path, bundle)
    for registration_directory, review_source in (
        (None, review_path),
        (bundle, None),
        (tmp_path / "missing-bundle", review_path),
        (bundle, tmp_path / "missing-review.json"),
    ):
        summary = reviewed_registration_display_summary(
            registration_directory,
            review_source,
        )
        assert summary["available"] is False
        assert summary["display_status"] == "unavailable"
        assert summary["display_authorized"] is False
        assert summary["allowed_display_modes"] == []


def test_tampered_or_mismatched_review_is_invalid_and_locked(tmp_path: Path) -> None:
    first_root = tmp_path / "first"
    first_root.mkdir()
    first_bundle = registration_bundle(first_root)
    review_path = _saved_review(first_root, first_bundle)

    record = json.loads(review_path.read_text())
    record["note"] = "Changed after the review was saved."
    review_path.write_text(json.dumps(record))
    review_path.chmod(0o600)
    tampered = reviewed_registration_display_summary(first_bundle, review_path)
    assert tampered["display_status"] == "invalid"
    assert tampered["display_authorized"] is False
    assert "tampered" in " ".join(tampered["errors"])

    review_path.unlink()
    review_path = _saved_review(first_root, first_bundle)
    second_root = tmp_path / "second"
    second_root.mkdir()
    second_bundle = registration_bundle(second_root)
    mismatched = reviewed_registration_display_summary(second_bundle, review_path)
    assert mismatched["display_status"] == "invalid"
    assert mismatched["display_authorized"] is False
    assert "another bundle" in " ".join(mismatched["errors"])


@pytest.mark.parametrize("link_kind", ["symlink", "hardlink"])
def test_linked_review_is_invalid_and_locked(tmp_path: Path, link_kind: str) -> None:
    bundle = registration_bundle(tmp_path)
    review_path = _saved_review(tmp_path, bundle)
    linked = tmp_path / "linked-review.json"
    if link_kind == "symlink":
        linked.symlink_to(review_path)
    else:
        os.link(review_path, linked)
    summary = reviewed_registration_display_summary(bundle, linked)
    assert summary["display_status"] == "invalid"
    assert summary["display_authorized"] is False
    assert summary["allowed_display_modes"] == []


def test_non_owner_only_review_is_invalid_and_locked(tmp_path: Path) -> None:
    bundle = registration_bundle(tmp_path)
    review_path = _saved_review(tmp_path, bundle)
    review_path.chmod(0o644)
    summary = reviewed_registration_display_summary(bundle, review_path)
    assert summary["display_status"] == "invalid"
    assert summary["display_authorized"] is False
    assert "unsafe" in " ".join(summary["errors"])


def test_owner_only_review_read_rejects_same_size_metadata_change(
    tmp_path: Path,
    monkeypatch,
) -> None:
    review_path = _write_private(tmp_path / "changing-review.json", b"x" * 70_000)
    real_read = registration_display_module.os.read
    changed = False

    def read_then_touch(descriptor: int, size: int) -> bytes:
        nonlocal changed
        payload = real_read(descriptor, size)
        if not changed:
            changed = True
            metadata = review_path.stat()
            os.utime(
                review_path,
                ns=(metadata.st_atime_ns, metadata.st_mtime_ns + 1_000_000),
            )
        return payload

    monkeypatch.setattr(registration_display_module.os, "read", read_then_touch)
    with pytest.raises(ValueError, match="changed while it was read"):
        registration_display_module._read_owner_only_review(review_path)


@pytest.mark.parametrize(
    "payload",
    [
        b"not JSON",
        b'{"outer":{"decision":"accepted","decision":"rejected"}}',
        b'{"value":NaN}',
        b'{"value":"unsafe\\u0000control"}',
    ],
)
def test_malformed_duplicate_nonfinite_and_control_json_fail_closed(
    tmp_path: Path,
    payload: bytes,
) -> None:
    bundle = registration_bundle(tmp_path)
    review_path = _write_private(tmp_path / "unsafe-review.json", payload)
    summary = reviewed_registration_display_summary(bundle, review_path)
    assert summary["available"] is False
    assert summary["display_status"] == "invalid"
    assert summary["display_authorized"] is False
    assert summary["allowed_display_modes"] == []
    with pytest.raises(ValueError, match="not authorized"):
        reviewed_registration_display_context(bundle, review_path)


def test_invalid_bundle_metadata_integrity_and_links_keep_display_locked(
    tmp_path: Path,
) -> None:
    cases = []
    for name in ("mode", "tamper", "link"):
        root = tmp_path / name
        root.mkdir()
        bundle = registration_bundle(root)
        review_path = _saved_review(root, bundle)
        if name == "mode":
            bundle.chmod(0o755)
        elif name == "tamper":
            registration = bundle / "registration.json"
            registration.write_bytes(registration.read_bytes() + b" ")
        else:
            os.link(bundle / "fixed.nrrd", root / "fixed-hardlink.nrrd")
        cases.append((bundle, review_path))

    for bundle, review_path in cases:
        summary = reviewed_registration_display_summary(bundle, review_path)
        assert summary["available"] is False
        assert summary["display_status"] == "invalid"
        assert summary["display_authorized"] is False
        assert summary["allowed_display_modes"] == []
        assert "bundle" in " ".join(summary["errors"])


def test_malformed_nested_review_never_throws_from_summary(tmp_path: Path) -> None:
    bundle = registration_bundle(tmp_path)
    record = build_registration_review(bundle, review_request())
    malformed = deepcopy(record)
    malformed["source_registration"]["bundle_files"] = [None]
    path = _write_private(
        tmp_path / "malformed-nested.json",
        json.dumps(malformed).encode(),
    )
    summary = reviewed_registration_display_summary(bundle, path)
    assert summary["display_status"] == "invalid"
    assert summary["display_authorized"] is False
