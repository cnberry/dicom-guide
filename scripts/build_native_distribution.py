#!/usr/bin/env python3
"""Build a self-contained DICOM Guide application archive for this host."""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import venv
from pathlib import Path


VERSION = "0.15.0"
PYINSTALLER_VERSION = "6.16.0"


def platform_tag() -> str:
    system = {"Darwin": "macos", "Linux": "linux"}.get(platform.system())
    machine = {"x86_64": "x86_64", "AMD64": "x86_64", "arm64": "arm64", "aarch64": "arm64"}.get(platform.machine())
    if not system or not machine:
        raise RuntimeError(f"unsupported build host: {platform.system()} {platform.machine()}")
    return f"{system}-{machine}"


def run(*arguments: str, cwd: Path | None = None) -> None:
    subprocess.run(arguments, cwd=cwd, check=True)


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
    archive = output / f"dicom-guide-{VERSION}-{tag}.tar.gz"

    with tempfile.TemporaryDirectory(prefix="dicom-guide-native-") as temporary_value:
        temporary = Path(temporary_value)
        wheel_dir = temporary / "wheels"
        run(sys.executable, str(repository / "scripts" / "build_release.py"), "--output-dir", str(wheel_dir))
        wheels = list(wheel_dir.glob("dicom_guide-*.whl"))
        if len(wheels) != 1:
            raise RuntimeError("expected exactly one DICOM Guide wheel")

        environment = temporary / "build-environment"
        venv.EnvBuilder(with_pip=True, clear=True).create(environment)
        python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        run(str(python), "-m", "pip", "install", "--disable-pip-version-check", str(wheels[0]), f"pyinstaller=={PYINSTALLER_VERSION}")
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
        for name in ("install.sh", "README.txt"):
            template = (repository / "packaging" / "native" / name).read_text()
            target = root / name
            target.write_text(template.replace("@VERSION@", VERSION))
        (root / "install.sh").chmod(0o755)
        executable = root / "app" / "dicom-guide"
        executable.chmod(executable.stat().st_mode | 0o111)
        with tarfile.open(archive, "w:gz", format=tarfile.PAX_FORMAT) as bundle:
            bundle.add(root, arcname=root.name)
    archive.chmod(0o644)
    print(archive)


if __name__ == "__main__":
    main()
