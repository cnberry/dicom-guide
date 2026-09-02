from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from dicom_guide.folder_picker import FolderPickerUnavailable, choose_local_folder


def completed(
    command: list[str], *, returncode: int = 0, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(command, returncode, stdout, stderr)


def test_macos_picker_returns_selected_directory_without_a_shell() -> None:
    commands: list[list[str]] = []

    def run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return completed(command, stdout="/private/tmp/synthetic-study/\n")

    selected = choose_local_folder(platform_name="darwin", run=run)

    assert selected == Path("/private/tmp/synthetic-study")
    assert commands[0][0] == "/usr/bin/osascript"
    assert commands[0][1] == "-e"


def test_macos_picker_treats_user_cancellation_as_no_selection() -> None:
    def run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        return completed(command, returncode=1, stderr="execution error: User canceled. (-128)")

    assert choose_local_folder(platform_name="darwin", run=run) is None


def test_windows_picker_uses_sta_powershell_and_distinguishes_cancellation() -> None:
    commands: list[list[str]] = []

    def run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return completed(command, returncode=2)

    selected = choose_local_folder(
        platform_name="win32",
        run=run,
        find_executable=lambda name: "C:/Windows/powershell.exe"
        if name == "powershell.exe"
        else None,
    )

    assert selected is None
    assert commands[0][:3] == ["C:/Windows/powershell.exe", "-NoProfile", "-STA"]


def test_linux_picker_uses_available_native_dialog() -> None:
    commands: list[list[str]] = []

    def run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return completed(command, stdout="/tmp/synthetic-study\n")

    selected = choose_local_folder(
        platform_name="linux",
        run=run,
        find_executable=lambda name: "/usr/bin/zenity" if name == "zenity" else None,
    )

    assert selected == Path("/tmp/synthetic-study")
    assert commands == [
        [
            "/usr/bin/zenity",
            "--file-selection",
            "--directory",
            "--title=Choose a local DICOM folder",
        ]
    ]


def test_picker_reports_platform_failures_without_leaking_stderr() -> None:
    def run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        return completed(command, returncode=7, stderr="sensitive local failure details")

    with pytest.raises(FolderPickerUnavailable, match="could not be opened") as error:
        choose_local_folder(platform_name="darwin", run=run)

    assert "sensitive" not in str(error.value)
