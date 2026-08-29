from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import zipfile
from pathlib import Path
from types import ModuleType

import pytest


def _builder() -> ModuleType:
    script = Path(__file__).parents[3] / "scripts" / "build_offline_bundle.py"
    spec = importlib.util.spec_from_file_location("scanview_offline_builder", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _wheel(
    path: Path,
    *,
    name: str,
    version: str,
    pure: bool = True,
) -> Path:
    distribution = name.replace("-", "_")
    dist_info = f"{distribution}-{version}.dist-info"
    tag = "py3-none-any" if pure else "cp312-cp312-macosx_14_0_arm64"

    def fixed_info(member: str) -> zipfile.ZipInfo:
        return zipfile.ZipInfo(member, date_time=(2020, 2, 2, 0, 0, 0))

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr(
            fixed_info(f"{dist_info}/METADATA"),
            f"Metadata-Version: 2.4\nName: {name}\nVersion: {version}\n",
        )
        archive.writestr(
            fixed_info(f"{dist_info}/WHEEL"),
            "Wheel-Version: 1.0\n"
            f"Root-Is-Purelib: {'true' if pure else 'false'}\n"
            f"Tag: {tag}\n",
        )
        archive.writestr(fixed_info(f"{distribution}/__init__.py"), "")
    return path


def _inputs(tmp_path: Path) -> tuple[Path, Path]:
    return (
        _wheel(
            tmp_path / "scanview_agent-0.9.0-py3-none-any.whl",
            name="scanview-agent",
            version="0.9.0",
        ),
        _wheel(
            tmp_path / "pydicom-3.0.2-py3-none-any.whl",
            name="pydicom",
            version="3.0.2",
        ),
    )


def _build(tmp_path: Path, output_name: str = "output") -> Path:
    builder = _builder()
    scanview, pydicom = _inputs(tmp_path)
    return builder.build_offline_bundle(
        scanview_wheel=scanview,
        pydicom_wheel=pydicom,
        template_root=Path(__file__).parents[3] / "packaging" / "offline",
        output_dir=tmp_path / output_name,
    )


def _extract(archive_path: Path, destination: Path) -> Path:
    with zipfile.ZipFile(archive_path) as archive:
        archive.extractall(destination)
        top_levels = {name.split("/", 1)[0] for name in archive.namelist()}
    assert len(top_levels) == 1
    return destination / top_levels.pop()


def _verify(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(root / "verify.py"), str(root)],
        check=False,
        capture_output=True,
        text=True,
    )


def test_offline_bundle_is_exact_deterministic_and_local_only(tmp_path: Path) -> None:
    first = _build(tmp_path, "first")
    second = _build(tmp_path, "second")
    assert first.read_bytes() == second.read_bytes()

    with zipfile.ZipFile(first) as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        assert len(names) == len(set(names)) == 9
        assert all(name.startswith("scanview-offline-0.9.0/") for name in names)
        assert all(info.date_time == (2020, 2, 2, 0, 0, 0) for info in infos)
        manifest = json.loads(
            archive.read("scanview-offline-0.9.0/bundle.json")
        )
        requirements = archive.read(
            "scanview-offline-0.9.0/requirements.lock"
        ).decode()
        install = archive.read("scanview-offline-0.9.0/install.sh").decode()
        launch = archive.read("scanview-offline-0.9.0/launch.sh").decode()
        runtime_check = archive.read(
            "scanview-offline-0.9.0/runtime_check.py"
        ).decode()

    assert manifest["supported_platforms"] == ["macos", "linux"]
    assert manifest["runtime_network_required"] is False
    assert manifest["external_dicom_processing_api_required"] is False
    assert set(manifest["files"]) == {
        "README.md",
        "install.sh",
        "launch.sh",
        "requirements.lock",
        "runtime_check.py",
        "verify.py",
        "wheels/pydicom-3.0.2-py3-none-any.whl",
        "wheels/scanview_agent-0.9.0-py3-none-any.whl",
    }
    assert requirements.count("--hash=sha256:") == 2
    assert "--no-index" in install and "--require-hashes" in install
    assert "runtime_check.py" in install + launch
    assert '"external_dicom_processing_api_required": False' in runtime_check
    assert "scanview_agent.consultation_boards" in runtime_check
    assert "schema_count != 28" in runtime_check
    assert "scanview_agent.lesion_volume_reviews" in runtime_check
    assert "scanview_agent.lesion_volume_comparisons" in runtime_check
    assert "scanview_agent.lesion_volume_display" in runtime_check
    assert "scanview_agent.agent_access_audit" in runtime_check
    assert "scanview_agent.longitudinal_readiness" in runtime_check
    assert "scanview_agent.agent_consultation_plans" in runtime_check
    assert "scanview_agent.presentation_states" in runtime_check
    assert "http://" not in install + launch
    assert "https://" not in install + launch


def test_verifier_accepts_runtime_but_rejects_tamper_and_extra_files(
    tmp_path: Path,
) -> None:
    root = _extract(_build(tmp_path), tmp_path / "extracted")
    result = _verify(root)
    assert result.returncode == 0
    assert json.loads(result.stdout)["payload_files"] == 8

    (root / ".scanview-runtime").mkdir()
    (root / ".scanview-runtime" / "installed-runtime-file").write_text("local")
    assert _verify(root).returncode == 0

    (root / "README.md").write_text("tampered")
    result = _verify(root)
    assert result.returncode == 1
    assert "digest disagrees" in result.stderr or "byte count changed" in result.stderr

    (root / "README.md").write_bytes(
        zipfile.ZipFile(_build(tmp_path, "fresh")).read(
            "scanview-offline-0.9.0/README.md"
        )
    )
    (root / "extra.txt").write_text("unsupported")
    result = _verify(root)
    assert result.returncode == 1
    assert "do not exactly match" in result.stderr


def test_verifier_rejects_duplicate_manifest_fields_and_symlink_payload(
    tmp_path: Path,
) -> None:
    archive = _build(tmp_path)
    duplicate_root = _extract(archive, tmp_path / "duplicate")
    manifest = duplicate_root / "bundle.json"
    manifest.write_text(
        manifest.read_text().replace(
            '"artifact_type":',
            '"artifact_type": "duplicate", "artifact_type":',
            1,
        )
    )
    result = _verify(duplicate_root)
    assert result.returncode == 1
    assert "duplicate JSON field" in result.stderr

    symlink_root = _extract(archive, tmp_path / "symlink")
    readme = symlink_root / "README.md"
    readme.unlink()
    readme.symlink_to("install.sh")
    result = _verify(symlink_root)
    assert result.returncode == 1
    assert "symbolic links are unsupported" in result.stderr


def test_bundle_rejects_wrong_or_platform_specific_wheels(tmp_path: Path) -> None:
    builder = _builder()
    scanview, pydicom = _inputs(tmp_path)
    wrong = _wheel(
        tmp_path / "pydicom-3.0.1-py3-none-any.whl",
        name="pydicom",
        version="3.0.1",
    )
    with pytest.raises(ValueError, match="identity does not match"):
        builder.build_offline_bundle(
            scanview_wheel=scanview,
            pydicom_wheel=wrong,
            template_root=Path(__file__).parents[3] / "packaging" / "offline",
            output_dir=tmp_path / "wrong-output",
        )

    platform_wheel = _wheel(
        tmp_path / "pydicom-3.0.2-cp312-cp312-macosx_14_0_arm64.whl",
        name="pydicom",
        version="3.0.2",
        pure=False,
    )
    with pytest.raises(ValueError, match="cross-platform pure-Python"):
        builder.build_offline_bundle(
            scanview_wheel=scanview,
            pydicom_wheel=platform_wheel,
            template_root=Path(__file__).parents[3] / "packaging" / "offline",
            output_dir=tmp_path / "platform-output",
        )

    unsafe_wheel = _wheel(
        tmp_path / "pydicom-3.0.2-py3-none-any-unsafe.whl",
        name="pydicom",
        version="3.0.2",
    )
    with zipfile.ZipFile(unsafe_wheel, "a") as archive:
        archive.writestr("pydicom//ambiguous.py", "")
    with pytest.raises(ValueError, match="ambiguous or unsafe members"):
        builder.build_offline_bundle(
            scanview_wheel=scanview,
            pydicom_wheel=unsafe_wheel,
            template_root=Path(__file__).parents[3] / "packaging" / "offline",
            output_dir=tmp_path / "unsafe-output",
        )


def test_bundle_output_is_non_overwriting(tmp_path: Path) -> None:
    builder = _builder()
    scanview, pydicom = _inputs(tmp_path)
    template_root = Path(__file__).parents[3] / "packaging" / "offline"
    output_dir = tmp_path / "output"
    builder.build_offline_bundle(
        scanview_wheel=scanview,
        pydicom_wheel=pydicom,
        template_root=template_root,
        output_dir=output_dir,
    )
    with pytest.raises(FileExistsError):
        builder.build_offline_bundle(
            scanview_wheel=scanview,
            pydicom_wheel=pydicom,
            template_root=template_root,
            output_dir=output_dir,
        )
