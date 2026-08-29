#!/usr/bin/env python3
"""Fail closed unless the installed offline ScanView runtime is complete."""

from __future__ import annotations

import json
from importlib.metadata import version
from importlib.resources import files

from scanview_agent.cli import _viewer_dist
from scanview_agent.consultation_boards import ARTIFACT_TYPE as BOARD_ARTIFACT_TYPE
from scanview_agent.consultation_packets import ARTIFACT_TYPE


def main() -> None:
    if version("scanview-agent") != "0.2.0" or version("pydicom") != "3.0.2":
        raise SystemExit("installed ScanView runtime versions are invalid")
    if ARTIFACT_TYPE != "clinician_consultation_packet":
        raise SystemExit("installed ScanView consultation contract is unavailable")
    if BOARD_ARTIFACT_TYPE != "clinician_consultation_board":
        raise SystemExit(
            "installed ScanView consultation-board contract is unavailable"
        )
    if not _viewer_dist(None).joinpath("index.html").is_file():
        raise SystemExit("installed ScanView UI is unavailable")
    schemas = list(files("scanview_agent").joinpath("schemas").iterdir())
    schema_count = len([path for path in schemas if path.name.endswith(".json")])
    if schema_count != 21:
        raise SystemExit("installed ScanView schemas are incomplete")
    print(
        json.dumps(
            {
                "valid": True,
                "scanview_agent": "0.2.0",
                "pydicom": "3.0.2",
                "embedded_ui": True,
                "schema_count": schema_count,
                "runtime_network_required": False,
                "external_dicom_processing_api_required": False,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
