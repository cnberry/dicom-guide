#!/usr/bin/env python3
"""Build a self-contained DICOM Guide application archive for this host."""

from __future__ import annotations

import argparse
from hashlib import sha256
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import venv
import zipfile
from pathlib import Path


VERSION = "0.15.0"
PYINSTALLER_VERSION = "6.16.0"


def platform_tag(system_name: str | None = None, machine_name: str | None = None) -> str:
    observed_system = system_name or platform.system()
    observed_machine = machine_name or platform.machine()
    system = {
        "Darwin": "macos",
        "Linux": "linux",
        "Windows": "windows",
    }.get(observed_system)
    machine = {
        "x86_64": "x86_64",
        "AMD64": "x86_64",
        "arm64": "arm64",
        "ARM64": "arm64",
        "aarch64": "arm64",
    }.get(observed_machine)
    if not system or not machine:
        raise RuntimeError(f"unsupported build host: {observed_system} {observed_machine}")
    return f"{system}-{machine}"


def run(*arguments: str, cwd: Path | None = None) -> None:
    subprocess.run(arguments, cwd=cwd, check=True)


def archive_path(output: Path, tag: str) -> Path:
    suffix = ".zip" if tag.startswith("windows-") else ".tar.gz"
    return output / f"dicom-guide-{VERSION}-{tag}{suffix}"


def write_archive(root: Path, archive: Path, tag: str) -> None:
    if tag.startswith("windows-"):
        with zipfile.ZipFile(
            archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
        ) as bundle:
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    archive_name = (Path(root.name) / path.relative_to(root)).as_posix()
                    bundle.write(path, arcname=archive_name)
        return
    with tarfile.open(archive, "w:gz", format=tarfile.PAX_FORMAT) as bundle:
        bundle.add(root, arcname=root.name)


def write_checksum(archive: Path) -> Path:
    digest = sha256()
    with archive.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    checksum = archive.with_name(f"{archive.name}.sha256")
    checksum.write_text(f"{digest.hexdigest()}  {archive.name}\n", encoding="ascii")
    checksum.chmod(0o644)
    return checksum


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("release"))
    args = parser.parse_args()
    repository = Path(__file__).resolve().parents[1]
    if not (repository / "apps" / "viewer" / "dist" / "index.html").is_file():
        parser.error("viewer bundle is missing; run `pnpm build` first")

    output = args.output_dir.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    tag = platform_tag()
    archive = archive_path(output, tag)

    with tempfile.TemporaryDirectory(prefix="dicom-guide-native-") as temporary_value:
        temporary = Path(temporary_value)
        wheel_dir = temporary / "wheels"
        run(
            sys.executable,
            str(repository / "scripts" / "build_release.py"),
            "--output-dir",
            str(wheel_dir),
        )
        wheels = list(wheel_dir.glob("dicom_guide-*.whl"))
        if len(wheels) != 1:
            raise RuntimeError("expected exactly one DICOM Guide wheel")

        environment = temporary / "build-environment"
        venv.EnvBuilder(with_pip=True, clear=True).create(environment)
        python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        run(
            str(python),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            str(wheels[0]),
            f"pyinstaller=={PYINSTALLER_VERSION}",
        )
        run(
            str(python), "-m", "PyInstaller",
            "--clean", "--noconfirm", "--onedir",
            "--name", "dicom-guide",
            "--collect-data", "dicom_guide",
            "--distpath", str(temporary / "dist"),
            "--workpath", str(temporary / "work"),
            "--specpath", str(temporary / "spec"),
            str(repository / "packaging" / "native" / "entrypoint.py"),
        )

        root = temporary / f"dicom-guide-{VERSION}-{tag}"
        shutil.copytree(temporary / "dist" / "dicom-guide", root / "app")
        if tag.startswith("windows-"):
            templates = (
                ("install.ps1", "install.ps1"),
                ("README.windows.txt", "README.txt"),
            )
        else:
            templates = (
                ("install.sh", "install.sh"),
                ("uninstall.sh", "uninstall.sh"),
                ("README.txt", "README.txt"),
            )
        for source_name, target_name in templates:
            template = (repository / "packaging" / "native" / source_name).read_text()
            target = root / target_name
            target.write_text(template.replace("@VERSION@", VERSION))
        if not tag.startswith("windows-"):
            (root / "install.sh").chmod(0o755)
            (root / "uninstall.sh").chmod(0o755)
            executable = root / "app" / "dicom-guide"
            executable.chmod(executable.stat().st_mode | 0o111)
        write_archive(root, archive, tag)
    archive.chmod(0o644)
    write_checksum(archive)
    print(archive)


if __name__ == "__main__":
    main()
