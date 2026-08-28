#!/usr/bin/env python3
"""Resumable, lossless directory copy with a byte-for-byte SHA-256 manifest.

This script never removes destination files and never modifies the source. It is
intended for removable medical-media ingestion after any Finder copy has stopped.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def files_under(root: Path) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for directory, names, files in os.walk(root):
        names.sort()
        files.sort()
        for filename in files:
            path = Path(directory, filename)
            if path.is_file() and not path.is_symlink():
                result[path.relative_to(root).as_posix()] = path
    return result


def copy_atomic(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.scanview-part-", dir=destination.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        shutil.copy2(source, temporary)
        with temporary.open("rb") as stream:
            os.fsync(stream.fileno())
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Do not repair missing or mismatched destination files",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        help="Manifest path (default: destination/.scanview-copy-manifest.json)",
    )
    args = parser.parse_args()

    source = args.source.expanduser().resolve(strict=True)
    destination = args.destination.expanduser().resolve(strict=True)
    if not source.is_dir() or not destination.is_dir():
        parser.error("source and destination must already exist as directories")
    if source == destination or source in destination.parents or destination in source.parents:
        parser.error("source and destination must be separate directory trees")

    source_files = files_under(source)
    destination_files = files_under(destination)
    print(f"Source inventory: {len(source_files)} files", flush=True)
    print(f"Destination inventory: {len(destination_files)} files", flush=True)

    repaired = []
    entries = []
    failures = []
    for index, (relative, source_path) in enumerate(source_files.items(), start=1):
        destination_path = destination / relative
        source_size = source_path.stat().st_size
        needs_copy = not destination_path.is_file() or destination_path.stat().st_size != source_size
        if needs_copy and not args.verify_only:
            copy_atomic(source_path, destination_path)
            repaired.append(relative)
        source_hash = sha256(source_path)
        destination_hash = sha256(destination_path) if destination_path.is_file() else None
        verified = source_hash == destination_hash
        if not verified and not args.verify_only:
            copy_atomic(source_path, destination_path)
            repaired.append(relative)
            destination_hash = sha256(destination_path)
            verified = source_hash == destination_hash
        if not verified:
            failures.append(relative)
        entries.append(
            {
                "relative_path": relative,
                "bytes": source_size,
                "sha256": source_hash,
                "verified": verified,
            }
        )
        if index % 100 == 0 or index == len(source_files):
            print(f"Verified {index}/{len(source_files)} files", flush=True)

    extras = sorted(set(destination_files) - set(source_files))
    manifest = {
        "schema_version": "1.0.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_volume": source.name,
        "destination_label": destination.name,
        "source_file_count": len(source_files),
        "source_total_bytes": sum(entry["bytes"] for entry in entries),
        "all_source_files_verified": not failures,
        "repaired_file_count": len(set(repaired)),
        "failures": failures,
        "extra_destination_files_not_removed": extras,
        "files": entries,
    }
    manifest_path = args.manifest or destination / ".scanview-copy-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Verification manifest: {manifest_path}")
    if failures:
        print(f"FAILED: {len(failures)} files do not match", file=sys.stderr)
        return 1
    print("SUCCESS: every source file has a byte-identical destination copy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
