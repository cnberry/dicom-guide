from __future__ import annotations

from hashlib import sha256
import importlib.util
from pathlib import Path
from types import ModuleType

import pytest


def _release_module() -> ModuleType:
    script = Path(__file__).parents[3] / "scripts" / "prepare_native_release.py"
    spec = importlib.util.spec_from_file_location("dicom_guide_native_release", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


release = _release_module()


def _repository(tmp_path: Path, version: str = "0.16.0") -> Path:
    repository = tmp_path / "repository"
    package = repository / "packages" / "agent"
    package.mkdir(parents=True)
    (package / "pyproject.toml").write_text(
        f'[project]\nname = "dicom-guide"\nversion = "{version}"\n'
    )
    return repository


def _release_dir(tmp_path: Path, version: str = "0.16.0") -> Path:
    directory = tmp_path / "release"
    directory.mkdir()
    for index, name in enumerate(release.archive_names(version)):
        payload = f"synthetic native package {index}".encode()
        (directory / name).write_bytes(payload)
        digest = sha256(payload).hexdigest()
        (directory / f"{name}.sha256").write_text(f"{digest}  {name}\n")
    return directory


def test_prepares_exact_complete_release_and_aggregate_checksums(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    directory = _release_dir(tmp_path)
    windows = directory / "dicom-guide-0.16.0-windows-x86_64.zip.sha256"
    windows.write_bytes(windows.read_text().rstrip("\n").encode() + b"\r\n")

    aggregate = release.prepare_native_release(
        directory, tag="v0.16.0", repository=repository
    )

    names = [line.split("  ", 1)[1] for line in aggregate.read_text().splitlines()]
    assert names == release.archive_names("0.16.0")


def test_rejects_tag_that_does_not_match_the_packaged_version(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="release tag must be v0.16.0"):
        release.prepare_native_release(
            _release_dir(tmp_path),
            tag="v0.15.1",
            repository=_repository(tmp_path),
        )


@pytest.mark.parametrize("failure", ["missing", "unexpected", "corrupt"])
def test_rejects_incomplete_or_unverified_release_set(
    tmp_path: Path, failure: str
) -> None:
    repository = _repository(tmp_path)
    directory = _release_dir(tmp_path)
    first = release.archive_names("0.16.0")[0]
    if failure == "missing":
        (directory / first).unlink()
    elif failure == "unexpected":
        (directory / "unreviewed.txt").write_text("not a release asset")
    else:
        (directory / first).write_bytes(b"changed after checksum")

    with pytest.raises(ValueError):
        release.prepare_native_release(
            directory, tag="v0.16.0", repository=repository
        )
