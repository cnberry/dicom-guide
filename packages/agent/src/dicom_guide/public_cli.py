from __future__ import annotations

import sys


VERSION = "0.16.0"
HELP = """DICOM Guide — open medical scan files and explore them with your agent

Have a folder copied from an imaging disc or portal download? Open the top-level
folder. DICOM Guide finds MRI and CT files beneath it even when they have no extension.

Usage:
  dicom-guide open DICOM_FOLDER [options]
  dicom-guide state
  dicom-guide series
  dicom-guide show [options]
  dicom-guide highlight add|remove|clear [options]
  dicom-guide metadata --instance-id ID
  dicom-guide fetch-instance --instance-id ID --output PATH

Run `dicom-guide <command> --help` for command details.
All DICOM processing stays on this computer.

In Codex, try:
  $dicom-guide Give me a visual tour of this study. Start with the series list.
"""


def main() -> None:
    if len(sys.argv) == 1 or sys.argv[1] in {"-h", "--help"}:
        print(HELP, end="")
        return
    if sys.argv[1] == "--version":
        print(f"DICOM Guide {VERSION}")
        return
    from .cli import main as full_main

    full_main()


if __name__ == "__main__":
    main()
