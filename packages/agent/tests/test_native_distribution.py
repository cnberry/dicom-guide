from __future__ import annotations

import tarfile
import zipfile
import importlib.util
from hashlib import sha256
from pathlib import Path
from types import ModuleType

import pytest


def _builder() -> ModuleType:
    script = Path(__file__).parents[3] / "scripts" / "build_native_distribution.py"
    spec = importlib.util.spec_from_file_location("dicom_guide_native_builder", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


native = _builder()


@pytest.mark.parametrize(
    ("system", "machine", "expected"),
    [
        ("Darwin", "arm64", "macos-arm64"),
        ("Darwin", "x86_64", "macos-x86_64"),
        ("Linux", "AMD64", "linux-x86_64"),
        ("Windows", "AMD64", "windows-x86_64"),
        ("Windows", "ARM64", "windows-arm64"),
    ],
)
def test_platform_tag(system: str, machine: str, expected: str) -> None:
    assert native.platform_tag(system, machine) == expected


def test_platform_tag_rejects_unknown_host() -> None:
    with pytest.raises(RuntimeError, match="unsupported build host: Plan9 mips"):
        native.platform_tag("Plan9", "mips")


def test_windows_archive_and_checksum(tmp_path) -> None:
    root = tmp_path / "dicom-guide-0.16.0-windows-x86_64"
    (root / "app").mkdir(parents=True)
    (root / "app" / "dicom-guide.exe").write_bytes(b"synthetic executable")
    (root / "install.ps1").write_text("Write-Host synthetic")
    archive = native.archive_path(tmp_path, "windows-x86_64")

    native.write_archive(root, archive, "windows-x86_64")
    checksum = native.write_checksum(archive)

    with zipfile.ZipFile(archive) as bundle:
        assert set(bundle.namelist()) == {
            f"{root.name}/app/dicom-guide.exe",
            f"{root.name}/install.ps1",
        }
    assert checksum.read_text().split()[0] == sha256(archive.read_bytes()).hexdigest()


def test_unix_archive_keeps_one_top_level_directory(tmp_path) -> None:
    root = tmp_path / "dicom-guide-0.16.0-linux-x86_64"
    root.mkdir()
    (root / "install.sh").write_text("#!/bin/sh\n")
    archive = native.archive_path(tmp_path, "linux-x86_64")

    native.write_archive(root, archive, "linux-x86_64")

    with tarfile.open(archive) as bundle:
        assert f"{root.name}/install.sh" in bundle.getnames()


def test_unix_templates_include_reversible_user_install() -> None:
    root = Path(__file__).parents[3]
    install = (root / "packaging/native/install.sh").read_text()
    uninstall = (root / "packaging/native/uninstall.sh").read_text()

    assert 'prefix="$HOME/.local"' in install
    assert "Administrator access is unavailable; installing for this user instead." in install
    assert 'rm -r "$install_dir"' in uninstall
