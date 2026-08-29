#!/usr/bin/env python3
"""Build a self-contained ScanView wheel without modifying the source tree."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("release"),
        help="Directory for the self-contained wheel (default: ./release)",
    )
    args = parser.parse_args()

    repository = Path(__file__).resolve().parents[1]
    viewer_dist = repository / "apps" / "viewer" / "dist"
    agent_source = repository / "packages" / "agent"
    if not (viewer_dist / "index.html").is_file():
        parser.error("viewer bundle is missing; run `pnpm build` first")

    output = args.output_dir.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="scanview-release-") as temporary:
        staged_agent = Path(temporary) / "agent"
        shutil.copytree(
            agent_source,
            staged_agent,
            ignore=shutil.ignore_patterns(
                "__pycache__", ".pytest_cache", "*.pyc", "*.pyo", "*.egg-info"
            ),
        )
        shutil.copytree(viewer_dist, staged_agent / "src" / "scanview_agent" / "ui")
        shutil.copytree(
            repository / "schemas",
            staged_agent / "src" / "scanview_agent" / "schemas",
        )
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "wheel",
                "--no-deps",
                str(staged_agent),
                "--wheel-dir",
                str(output),
            ],
            check=True,
        )


if __name__ == "__main__":
    main()
