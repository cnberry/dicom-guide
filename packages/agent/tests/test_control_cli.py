from __future__ import annotations

from dicom_guide.control_cli import navigation_command


def test_navigation_targets_the_ready_viewer_and_preserves_current_marks() -> None:
    command = navigation_command(
        {"viewer_id": "viewer_0123456789abcdef0123"},
        series_id="series_0123456789abcdef0123",
        instance_id="instance_0123456789abcdef0123",
        view="mpr",
        tool="crosshairs",
        patient_point_lps_mm=[1.25, -2.5, 3.75],
        reset_view=True,
    )

    assert command["target_viewer_id"] == "viewer_0123456789abcdef0123"
    assert command["discussion_marks_patch"] == {"add": []}
    assert command["patient_point_lps_mm"] == [1.25, -2.5, 3.75]
    assert command["command_id"].startswith("control_")
