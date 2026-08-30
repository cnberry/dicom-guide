from __future__ import annotations

import json
import stat
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from dicom_guide.cli import main
from dicom_guide.navigation import build_navigation_intent


SERIES_A = "series_0123456789abcdef0123"
INSTANCE_A = "instance_0123456789abcdef0123"
SERIES_B = "series_1123456789abcdef0123"
INSTANCE_B = "instance_1123456789abcdef0123"


def catalog() -> dict:
    return {
        "schema_version": "1.0.0",
        "source": {"dicom_instances": 2},
        "studies": [
            {
                "id": "study_0123456789abcdef0123",
                "series": [
                    {
                        "id": SERIES_A,
                        "modality": "MR",
                        "instances": [{"id": INSTANCE_A}],
                    }
                ],
            },
            {
                "id": "study_1123456789abcdef0123",
                "series": [
                    {
                        "id": SERIES_B,
                        "modality": "MR",
                        "instances": [{"id": INSTANCE_B}],
                    }
                ],
            },
        ],
    }


def test_navigation_intent_is_exact_local_and_schema_valid() -> None:
    intent = build_navigation_intent(
        catalog(),
        baseline_series_id=SERIES_A,
        baseline_instance_id=INSTANCE_A,
        followup_series_id=SERIES_B,
        followup_instance_id=INSTANCE_B,
        base_url="http://127.0.0.1:8765/",
    )

    assert intent["fragment"] == (
        f"#dicom-guide-v1?baseline_series={SERIES_A}&baseline_instance={INSTANCE_A}"
        f"&followup_series={SERIES_B}&followup_instance={INSTANCE_B}"
    )
    assert intent["url"] == f"http://127.0.0.1:8765/{intent['fragment']}"
    assert intent["pairing_status"] == "not_assessed"
    repository_root = Path(__file__).parents[3]
    schema = json.loads(
        (repository_root / "schemas" / "dicom-guide-navigation-intent-v1.schema.json").read_text()
    )
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(intent)


def test_navigation_refuses_unknown_misowned_or_partial_targets() -> None:
    with pytest.raises(ValueError, match="manifest v1"):
        build_navigation_intent(  # type: ignore[arg-type]
            [],
            baseline_series_id=SERIES_A,
            baseline_instance_id=INSTANCE_A,
        )
    with pytest.raises(ValueError, match="does not belong"):
        build_navigation_intent(
            catalog(),
            baseline_series_id=SERIES_A,
            baseline_instance_id=INSTANCE_B,
        )
    with pytest.raises(ValueError, match="both a series and instance"):
        build_navigation_intent(
            catalog(),
            baseline_series_id=SERIES_A,
            baseline_instance_id=INSTANCE_A,
            followup_series_id=SERIES_B,
        )
    with pytest.raises(ValueError, match="distinct series"):
        build_navigation_intent(
            catalog(),
            baseline_series_id=SERIES_A,
            baseline_instance_id=INSTANCE_A,
            followup_series_id=SERIES_A,
            followup_instance_id=INSTANCE_A,
        )


def test_navigation_refuses_non_loopback_or_credentialed_urls() -> None:
    for base_url in (
        "https://127.0.0.1:8765/",
        "http://example.com:8765/",
        "http://user:secret@127.0.0.1:8765/",
        "http://127.0.0.1:8765/?session=secret",
    ):
        with pytest.raises(ValueError, match="plain loopback"):
            build_navigation_intent(
                catalog(),
                baseline_series_id=SERIES_A,
                baseline_instance_id=INSTANCE_A,
                base_url=base_url,
            )
    ipv6 = build_navigation_intent(
        catalog(),
        baseline_series_id=SERIES_A,
        baseline_instance_id=INSTANCE_A,
        base_url="http://[::1]:8765/",
    )
    assert ipv6["url"].startswith("http://[::1]:8765/#dicom-guide-v1?")


def test_viewer_link_cli_writes_owner_only_versioned_intent(
    tmp_path: Path, monkeypatch
) -> None:
    manifest_path = tmp_path / "manifest.json"
    output_path = tmp_path / "viewer-link.json"
    manifest_path.write_text(json.dumps(catalog()))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "dicom-guide",
            "viewer-link",
            str(manifest_path),
            "--baseline-series",
            SERIES_A,
            "--baseline-instance",
            INSTANCE_A,
            "--output",
            str(output_path),
        ],
    )

    main()

    intent = json.loads(output_path.read_text())
    assert intent["baseline"] == {"series_id": SERIES_A, "instance_id": INSTANCE_A}
    assert "url" not in intent
    assert stat.S_IMODE(output_path.stat().st_mode) == 0o600
