#!/usr/bin/env python3
"""Fail closed unless the installed offline DICOM Guide runtime is complete."""

from __future__ import annotations

import json
from importlib.metadata import version
from importlib.resources import files

from dicom_guide.cli import _viewer_dist
from dicom_guide.agent_access_audit import ARTIFACT_TYPE as AGENT_AUDIT_ARTIFACT_TYPE
from dicom_guide.agent_consultation_plans import ARTIFACT_TYPE as AGENT_PLAN_ARTIFACT_TYPE
from dicom_guide.consultation_boards import ARTIFACT_TYPE as BOARD_ARTIFACT_TYPE
from dicom_guide.consultation_packets import ARTIFACT_TYPE
from dicom_guide.lesion_volume_reviews import ARTIFACT_TYPE as ROI_REVIEW_ARTIFACT_TYPE
from dicom_guide.lesion_volume_comparisons import ARTIFACT_TYPE as ROI_COMPARISON_ARTIFACT_TYPE
from dicom_guide.lesion_volume_display import DISPLAY_ARTIFACT_TYPE as NATIVE_DISPLAY_ARTIFACT_TYPE
from dicom_guide.longitudinal_readiness import ARTIFACT_TYPE as READINESS_ARTIFACT_TYPE
from dicom_guide.presentation_states import ARTIFACT_TYPE as PRESENTATION_STATE_ARTIFACT_TYPE
from dicom_guide.source_segmentations import ARTIFACT_TYPE as SOURCE_SEGMENTATION_ARTIFACT_TYPE
from dicom_guide.source_segmentation_reviews import ARTIFACT_TYPE as SOURCE_SEGMENTATION_REVIEW_ARTIFACT_TYPE
from dicom_guide.viewer_state import SCHEMA_VERSION as VIEWER_STATE_SCHEMA_VERSION


def main() -> None:
    if version("dicom-guide") != "0.16.0" or version("pydicom") != "3.0.2":
        raise SystemExit("installed DICOM Guide runtime versions are invalid")
    if ARTIFACT_TYPE != "clinician_consultation_packet":
        raise SystemExit("installed DICOM Guide consultation contract is unavailable")
    if BOARD_ARTIFACT_TYPE != "clinician_consultation_board":
        raise SystemExit(
            "installed DICOM Guide consultation-board contract is unavailable"
        )
    if ROI_REVIEW_ARTIFACT_TYPE != "dicom-guide.lesion-volume-review":
        raise SystemExit("installed DICOM Guide manual ROI review contract is unavailable")
    if ROI_COMPARISON_ARTIFACT_TYPE != "dicom-guide.lesion-volume-comparison-review":
        raise SystemExit("installed DICOM Guide manual ROI comparison contract is unavailable")
    if NATIVE_DISPLAY_ARTIFACT_TYPE != "lesion_volume_native_boundary_display_context":
        raise SystemExit("installed DICOM Guide native-boundary display contract is unavailable")
    if AGENT_AUDIT_ARTIFACT_TYPE != "dicom-guide.agent-access-audit-event":
        raise SystemExit("installed DICOM Guide agent access audit contract is unavailable")
    if READINESS_ARTIFACT_TYPE != "dicom-guide.longitudinal-readiness":
        raise SystemExit("installed DICOM Guide longitudinal readiness contract is unavailable")
    if AGENT_PLAN_ARTIFACT_TYPE != "dicom-guide.agent-consultation-plan":
        raise SystemExit("installed DICOM Guide agent consultation-plan contract is unavailable")
    if PRESENTATION_STATE_ARTIFACT_TYPE != "dicom-guide.presentation-state-catalog":
        raise SystemExit("installed DICOM Guide presentation-state contract is unavailable")
    if SOURCE_SEGMENTATION_ARTIFACT_TYPE != "dicom-guide.source-segmentation-catalog":
        raise SystemExit("installed DICOM Guide source-segmentation contract is unavailable")
    if SOURCE_SEGMENTATION_REVIEW_ARTIFACT_TYPE != "dicom-guide.source-segmentation-review":
        raise SystemExit("installed DICOM Guide source-SEG review contract is unavailable")
    if VIEWER_STATE_SCHEMA_VERSION != "2.0.0":
        raise SystemExit("installed DICOM Guide viewer-state contract is unavailable")
    if not _viewer_dist(None).joinpath("index.html").is_file():
        raise SystemExit("installed DICOM Guide UI is unavailable")
    schemas = list(files("dicom_guide").joinpath("schemas").iterdir())
    schema_count = len([path for path in schemas if path.name.endswith(".json")])
    if schema_count != 32:
        raise SystemExit("installed DICOM Guide schemas are incomplete")
    print(
        json.dumps(
            {
                "valid": True,
                "dicom_guide": "0.16.0",
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
