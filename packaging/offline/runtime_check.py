#!/usr/bin/env python3
"""Fail closed unless the installed offline ScanView runtime is complete."""

from __future__ import annotations

import json
from importlib.metadata import version
from importlib.resources import files

from scanview_agent.cli import _viewer_dist
from scanview_agent.agent_access_audit import ARTIFACT_TYPE as AGENT_AUDIT_ARTIFACT_TYPE
from scanview_agent.agent_consultation_plans import ARTIFACT_TYPE as AGENT_PLAN_ARTIFACT_TYPE
from scanview_agent.consultation_boards import ARTIFACT_TYPE as BOARD_ARTIFACT_TYPE
from scanview_agent.consultation_packets import ARTIFACT_TYPE
from scanview_agent.lesion_volume_reviews import ARTIFACT_TYPE as ROI_REVIEW_ARTIFACT_TYPE
from scanview_agent.lesion_volume_comparisons import ARTIFACT_TYPE as ROI_COMPARISON_ARTIFACT_TYPE
from scanview_agent.lesion_volume_display import DISPLAY_ARTIFACT_TYPE as NATIVE_DISPLAY_ARTIFACT_TYPE
from scanview_agent.longitudinal_readiness import ARTIFACT_TYPE as READINESS_ARTIFACT_TYPE
from scanview_agent.presentation_states import ARTIFACT_TYPE as PRESENTATION_STATE_ARTIFACT_TYPE
from scanview_agent.source_segmentations import ARTIFACT_TYPE as SOURCE_SEGMENTATION_ARTIFACT_TYPE
from scanview_agent.viewer_state import SCHEMA_VERSION as VIEWER_STATE_SCHEMA_VERSION


def main() -> None:
    if version("scanview-agent") != "0.13.0" or version("pydicom") != "3.0.2":
        raise SystemExit("installed ScanView runtime versions are invalid")
    if ARTIFACT_TYPE != "clinician_consultation_packet":
        raise SystemExit("installed ScanView consultation contract is unavailable")
    if BOARD_ARTIFACT_TYPE != "clinician_consultation_board":
        raise SystemExit(
            "installed ScanView consultation-board contract is unavailable"
        )
    if ROI_REVIEW_ARTIFACT_TYPE != "scanview.lesion-volume-review":
        raise SystemExit("installed ScanView manual ROI review contract is unavailable")
    if ROI_COMPARISON_ARTIFACT_TYPE != "scanview.lesion-volume-comparison-review":
        raise SystemExit("installed ScanView manual ROI comparison contract is unavailable")
    if NATIVE_DISPLAY_ARTIFACT_TYPE != "lesion_volume_native_boundary_display_context":
        raise SystemExit("installed ScanView native-boundary display contract is unavailable")
    if AGENT_AUDIT_ARTIFACT_TYPE != "scanview.agent-access-audit-event":
        raise SystemExit("installed ScanView agent access audit contract is unavailable")
    if READINESS_ARTIFACT_TYPE != "scanview.longitudinal-readiness":
        raise SystemExit("installed ScanView longitudinal readiness contract is unavailable")
    if AGENT_PLAN_ARTIFACT_TYPE != "scanview.agent-consultation-plan":
        raise SystemExit("installed ScanView agent consultation-plan contract is unavailable")
    if PRESENTATION_STATE_ARTIFACT_TYPE != "scanview.presentation-state-catalog":
        raise SystemExit("installed ScanView presentation-state contract is unavailable")
    if SOURCE_SEGMENTATION_ARTIFACT_TYPE != "scanview.source-segmentation-catalog":
        raise SystemExit("installed ScanView source-segmentation contract is unavailable")
    if VIEWER_STATE_SCHEMA_VERSION != "2.0.0":
        raise SystemExit("installed ScanView viewer-state contract is unavailable")
    if not _viewer_dist(None).joinpath("index.html").is_file():
        raise SystemExit("installed ScanView UI is unavailable")
    schemas = list(files("scanview_agent").joinpath("schemas").iterdir())
    schema_count = len([path for path in schemas if path.name.endswith(".json")])
    if schema_count != 31:
        raise SystemExit("installed ScanView schemas are incomplete")
    print(
        json.dumps(
            {
                "valid": True,
                "scanview_agent": "0.13.0",
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
