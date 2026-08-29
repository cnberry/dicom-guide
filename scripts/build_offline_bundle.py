#!/usr/bin/env python3
"""Build a verifiable offline ScanView runtime bundle for macOS and Linux."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import zipfile
from email.parser import BytesParser
from pathlib import Path, PurePosixPath
from typing import Any, NamedTuple


PROJECT_NAME = "scanview-agent"
PROJECT_VERSION = "0.9.0"
PYDICOM_VERSION = "3.0.2"
BUNDLE_SCHEMA_VERSION = "1.0.0"
BUNDLE_ARTIFACT_TYPE = "scanview_offline_runtime_bundle"
BUNDLE_DIRECTORY = f"scanview-offline-{PROJECT_VERSION}"
BUNDLE_FILENAME = f"{BUNDLE_DIRECTORY}.zip"
FIXED_ZIP_TIMESTAMP = (2020, 2, 2, 0, 0, 0)
MAX_WHEEL_MEMBER_BYTES = 128 * 1024 * 1024
MAX_WHEEL_TOTAL_BYTES = 256 * 1024 * 1024
TEMPLATE_FILES = (
    "README.md",
    "install.sh",
    "launch.sh",
    "runtime_check.py",
    "verify.py",
)
EXECUTABLE_TEMPLATES = {"install.sh", "launch.sh", "verify.py"}


class WheelIdentity(NamedTuple):
    name: str
    version: str
    filename: str


def _normalized_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def _safe_member_name(value: str) -> bool:
    path = PurePosixPath(value)
    return (
        bool(value)
        and not path.is_absolute()
        and path.as_posix() == value
        and ".." not in path.parts
    )


def _wheel_identity(
    path: Path,
    *,
    expected_name: str,
    expected_version: str,
) -> WheelIdentity:
    if (
        path.is_symlink()
        or not path.is_file()
        or path.suffix != ".whl"
        or not re.fullmatch(r"[A-Za-z0-9_.-]+\.whl", path.name)
    ):
        raise ValueError(f"required wheel is unavailable: {expected_name}")
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(names) != len(set(names)) or any(
                not _safe_member_name(name) for name in names
            ):
                raise ValueError(f"wheel has ambiguous or unsafe members: {path.name}")
            if any(info.flag_bits & 0x1 for info in infos):
                raise ValueError(f"encrypted wheel is unsupported: {path.name}")
            if any(info.file_size > MAX_WHEEL_MEMBER_BYTES for info in infos) or sum(
                info.file_size for info in infos
            ) > MAX_WHEEL_TOTAL_BYTES:
                raise ValueError(f"wheel exceeds the packaging safety limit: {path.name}")
            metadata_names = [
                name for name in names if name.endswith(".dist-info/METADATA")
            ]
            wheel_names = [name for name in names if name.endswith(".dist-info/WHEEL")]
            if len(metadata_names) != 1 or len(wheel_names) != 1:
                raise ValueError(f"wheel metadata is incomplete: {path.name}")
            metadata = BytesParser().parsebytes(archive.read(metadata_names[0]))
            wheel_metadata = BytesParser().parsebytes(archive.read(wheel_names[0]))
    except (OSError, zipfile.BadZipFile, KeyError) as error:
        raise ValueError(f"wheel could not be read safely: {path.name}") from error

    name = metadata.get("Name", "")
    version = metadata.get("Version", "")
    tags = wheel_metadata.get_all("Tag", [])
    if _normalized_name(name) != _normalized_name(expected_name) or version != expected_version:
        raise ValueError(f"wheel identity does not match the pinned runtime: {path.name}")
    if wheel_metadata.get("Root-Is-Purelib", "").lower() != "true" or not any(
        tag == "py3-none-any" for tag in tags
    ):
        raise ValueError(
            f"offline bundle accepts only cross-platform pure-Python wheels: {path.name}"
        )
    return WheelIdentity(name=name, version=version, filename=path.name)


def _digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            value.update(chunk)
    return value.hexdigest()


def _write_new(path: Path, payload: bytes, mode: int) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def _copy_new(source: Path, destination: Path, mode: int) -> None:
    _write_new(destination, source.read_bytes(), mode)


def _file_record(path: Path) -> dict[str, Any]:
    return {
        "byte_count": path.stat().st_size,
        "sha256": _digest(path),
    }


def _requirements(
    scanview: WheelIdentity,
    scanview_hash: str,
    pydicom: WheelIdentity,
    pydicom_hash: str,
) -> bytes:
    return (
        "# Hash-locked runtime requirements; install only with --no-index.\n"
        f"{scanview.name}=={scanview.version} --hash=sha256:{scanview_hash}\n"
        f"{pydicom.name}=={pydicom.version} --hash=sha256:{pydicom_hash}\n"
    ).encode()


def _manifest(bundle_root: Path) -> dict[str, Any]:
    files = {
        path.relative_to(bundle_root).as_posix(): _file_record(path)
        for path in sorted(bundle_root.rglob("*"))
        if path.is_file() and path.name != "bundle.json"
    }
    return {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "artifact_type": BUNDLE_ARTIFACT_TYPE,
        "project": "ScanView",
        "version": PROJECT_VERSION,
        "supported_platforms": ["macos", "linux"],
        "requires_python": ">=3.11",
        "runtime_network_required": False,
        "external_dicom_processing_api_required": False,
        "install_command": "sh install.sh",
        "launch_command": "sh launch.sh '/absolute/path/to/DICOM'",
        "runtime_dependencies": [
            {"name": "pydicom", "version": PYDICOM_VERSION},
        ],
        "integrity_scope": (
            "SHA-256 corruption evidence for bundle payloads; not a publisher "
            "signature or clinical authentication"
        ),
        "files": files,
    }


def _archive(bundle_root: Path, output: Path) -> None:
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"offline bundle already exists: {output}")
    temporary = output.with_name(f".{output.name}.{os.getpid()}.tmp")
    if temporary.exists() or temporary.is_symlink():
        raise FileExistsError(f"offline bundle temporary path already exists: {temporary}")
    try:
        with zipfile.ZipFile(temporary, "x", compression=zipfile.ZIP_STORED) as archive:
            for path in sorted(bundle_root.rglob("*")):
                if not path.is_file():
                    continue
                relative = path.relative_to(bundle_root).as_posix()
                info = zipfile.ZipInfo(
                    f"{BUNDLE_DIRECTORY}/{relative}",
                    date_time=FIXED_ZIP_TIMESTAMP,
                )
                info.create_system = 3
                mode = 0o755 if relative in EXECUTABLE_TEMPLATES else 0o644
                info.external_attr = (stat.S_IFREG | mode) << 16
                info.compress_type = zipfile.ZIP_STORED
                archive.writestr(info, path.read_bytes())
        descriptor = os.open(temporary, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.link(temporary, output, follow_symlinks=False)
        temporary.unlink()
        parent_descriptor = os.open(output.parent, os.O_RDONLY)
        try:
            os.fsync(parent_descriptor)
        finally:
            os.close(parent_descriptor)
    finally:
        temporary.unlink(missing_ok=True)


def build_offline_bundle(
    *,
    scanview_wheel: Path,
    pydicom_wheel: Path,
    template_root: Path,
    output_dir: Path,
) -> Path:
    scanview = _wheel_identity(
        scanview_wheel,
        expected_name=PROJECT_NAME,
        expected_version=PROJECT_VERSION,
    )
    pydicom = _wheel_identity(
        pydicom_wheel,
        expected_name="pydicom",
        expected_version=PYDICOM_VERSION,
    )
    for name in TEMPLATE_FILES:
        template = template_root / name
        if template.is_symlink() or not template.is_file():
            raise ValueError(f"offline bundle template is unavailable: {name}")

    output_dir.mkdir(parents=True, exist_ok=True)
    output_dir = output_dir.resolve(strict=True)
    output = output_dir / BUNDLE_FILENAME
    with tempfile.TemporaryDirectory(prefix="scanview-offline-stage-") as temporary:
        bundle_root = Path(temporary) / BUNDLE_DIRECTORY
        wheels = bundle_root / "wheels"
        wheels.mkdir(parents=True, mode=0o700)
        scanview_destination = wheels / scanview.filename
        pydicom_destination = wheels / pydicom.filename
        _copy_new(scanview_wheel, scanview_destination, 0o600)
        _copy_new(pydicom_wheel, pydicom_destination, 0o600)
        for name in TEMPLATE_FILES:
            mode = 0o700 if name in EXECUTABLE_TEMPLATES else 0o600
            _copy_new(template_root / name, bundle_root / name, mode)
        requirements = _requirements(
            scanview,
            _digest(scanview_destination),
            pydicom,
            _digest(pydicom_destination),
        )
        _write_new(bundle_root / "requirements.lock", requirements, 0o600)
        manifest = _manifest(bundle_root)
        manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
        _write_new(bundle_root / "bundle.json", manifest_bytes, 0o600)
        subprocess.run(
            [sys.executable, str(bundle_root / "verify.py"), str(bundle_root)],
            check=True,
        )
        _archive(bundle_root, output)
    return output


def _single_wheel(directory: Path, project: str) -> Path:
    wheels = sorted(directory.glob("*.whl"))
    if len(wheels) != 1:
        raise ValueError(f"expected exactly one {project} wheel")
    return wheels[0]


def _prepare_scanview_wheel(repository: Path, temporary: Path) -> Path:
    destination = temporary / "scanview-wheel"
    destination.mkdir()
    subprocess.run(
        [
            sys.executable,
            str(repository / "scripts" / "build_release.py"),
            "--output-dir",
            str(destination),
        ],
        check=True,
    )
    return _single_wheel(destination, PROJECT_NAME)


def _prepare_pydicom_wheel(temporary: Path) -> Path:
    destination = temporary / "pydicom-wheel"
    destination.mkdir()
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "download",
            "--disable-pip-version-check",
            "--only-binary=:all:",
            "--no-deps",
            "--dest",
            str(destination),
            f"pydicom=={PYDICOM_VERSION}",
        ],
        check=True,
    )
    return _single_wheel(destination, "pydicom")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("release"),
        help="Directory for the non-overwriting offline ZIP (default: ./release)",
    )
    parser.add_argument(
        "--scanview-wheel",
        type=Path,
        help="Use an existing UI-embedded ScanView wheel instead of building one",
    )
    parser.add_argument(
        "--pydicom-wheel",
        type=Path,
        help=f"Use an existing pydicom {PYDICOM_VERSION} wheel instead of downloading one",
    )
    args = parser.parse_args()

    repository = Path(__file__).resolve().parents[1]
    template_root = repository / "packaging" / "offline"
    try:
        with tempfile.TemporaryDirectory(prefix="scanview-offline-input-") as temporary_name:
            temporary = Path(temporary_name)
            scanview_wheel = (
                args.scanview_wheel.expanduser().resolve(strict=True)
                if args.scanview_wheel
                else _prepare_scanview_wheel(repository, temporary)
            )
            pydicom_wheel = (
                args.pydicom_wheel.expanduser().resolve(strict=True)
                if args.pydicom_wheel
                else _prepare_pydicom_wheel(temporary)
            )
            output = build_offline_bundle(
                scanview_wheel=scanview_wheel,
                pydicom_wheel=pydicom_wheel,
                template_root=template_root,
                output_dir=args.output_dir.expanduser(),
            )
    except (FileExistsError, OSError, subprocess.CalledProcessError, ValueError) as error:
        parser.error(str(error))
    print(output)


if __name__ == "__main__":
    main()
