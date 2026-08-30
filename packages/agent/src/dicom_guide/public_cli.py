from __future__ import annotations

import sys


VERSION = "0.15.0"
HELP = """DICOM Guide — the local MRI and CT viewer your agent can control

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
