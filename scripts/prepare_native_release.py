#!/usr/bin/env python3
"""Validate and assemble one complete set of native release assets."""

from __future__ import annotations

import argparse
from hashlib import sha256
from pathlib import Path
import re
import tomllib


PLATFORM_SUFFIXES = {
    "linux-x86_64": ".tar.gz",
    "macos-arm64": ".tar.gz",
    "macos-x86_64": ".tar.gz",
    "windows-x86_64": ".zip",
}
CHECKSUM_LINE = re.compile(r"^([0-9a-f]{64})  ([^/\\\r\n]+)\r?\n$")


def project_version(repository: Path) -> str:
    pyproject = repository / "packages" / "agent" / "pyproject.toml"
    with pyproject.open("rb") as stream:
        value = tomllib.load(stream).get("project", {}).get("version")
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", value):
        raise ValueError("project version must be a three-part numeric release")
    return value


def archive_names(version: str) -> list[str]:
    return [
        f"dicom-guide-{version}-{platform}{suffix}"
        for platform, suffix in sorted(PLATFORM_SUFFIXES.items())
    ]


def digest(path: Path) -> str:
    value = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def prepare_native_release(release_dir: Path, *, tag: str, repository: Path) -> Path:
    version = project_version(repository)
    expected_tag = f"v{version}"
    if tag != expected_tag:
        raise ValueError(f"release tag must be {expected_tag}, not {tag}")

    archives = archive_names(version)
    expected = set(archives) | {f"{name}.sha256" for name in archives}
    observed = {path.name for path in release_dir.iterdir() if path.is_file()}
    missing = sorted(expected - observed)
    unexpected = sorted(observed - expected)
    if missing or unexpected:
        details = []
        if missing:
            details.append(f"missing: {', '.join(missing)}")
        if unexpected:
            details.append(f"unexpected: {', '.join(unexpected)}")
        raise ValueError(f"native release asset set is invalid ({'; '.join(details)})")

    lines = []
    for name in archives:
        checksum_path = release_dir / f"{name}.sha256"
        match = CHECKSUM_LINE.fullmatch(checksum_path.read_text(encoding="ascii"))
        if match is None or match.group(2) != name:
            raise ValueError(f"checksum sidecar is malformed: {checksum_path.name}")
        observed_digest = digest(release_dir / name)
        if match.group(1) != observed_digest:
            raise ValueError(f"checksum mismatch: {name}")
        lines.append(f"{observed_digest}  {name}\n")

    aggregate = release_dir / "SHA256SUMS"
    aggregate.write_text("".join(lines), encoding="ascii")
    aggregate.chmod(0o644)
    return aggregate


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("release_dir", type=Path)
    parser.add_argument("--tag", required=True)
    args = parser.parse_args()
    repository = Path(__file__).resolve().parents[1]
    try:
        aggregate = prepare_native_release(
            args.release_dir.expanduser().resolve(),
            tag=args.tag,
            repository=repository,
        )
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(aggregate)


if __name__ == "__main__":
    main()
