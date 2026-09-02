from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest


def _provenance_module() -> ModuleType:
    script = Path(__file__).parents[3] / "scripts" / "create_release_provenance.py"
    spec = importlib.util.spec_from_file_location("dicom_guide_provenance", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


provenance = _provenance_module()


def _predicate(**overrides: str) -> dict[str, object]:
    values = {
        "repository": "cnberry/dicom-guide",
        "repository_id": "123",
        "repository_owner_id": "456",
        "ref": "refs/heads/main",
        "sha": "a" * 40,
        "event_name": "workflow_dispatch",
        "run_id": "789",
        "run_attempt": "1",
        "release_tag": "v0.16.0",
    }
    values.update(overrides)
    return provenance.release_provenance(**values)


def test_manual_release_predicate_captures_workflow_input_and_source() -> None:
    predicate = _predicate()
    definition = predicate["buildDefinition"]
    assert isinstance(definition, dict)
    assert definition["buildType"] == provenance.BUILD_TYPE
    assert definition["externalParameters"] == {
        "inputs": {"release_tag": "v0.16.0"},
        "workflow": {
            "path": ".github/workflows/release.yml",
            "ref": "refs/heads/main",
            "repository": "https://github.com/cnberry/dicom-guide",
        },
    }
    assert definition["resolvedDependencies"] == [
        {
            "uri": "git+https://github.com/cnberry/dicom-guide@refs/heads/main",
            "digest": {"gitCommit": "a" * 40},
        }
    ]


def test_tag_push_omits_manual_inputs() -> None:
    predicate = _predicate(event_name="push", ref="refs/tags/v0.16.0")
    definition = predicate["buildDefinition"]
    assert isinstance(definition, dict)
    external = definition["externalParameters"]
    assert isinstance(external, dict)
    assert "inputs" not in external


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("repository", "not-a-slug"),
        ("ref", "main"),
        ("sha", "short"),
        ("event_name", "pull_request"),
        ("run_id", "not-numeric"),
        ("release_tag", "0.16.0"),
    ],
)
def test_rejects_ambiguous_provenance_inputs(field: str, value: str) -> None:
    with pytest.raises(ValueError):
        _predicate(**{field: value})
