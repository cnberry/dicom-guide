from __future__ import annotations

import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path


class FolderPickerUnavailable(RuntimeError):
    """Raised when the platform cannot provide a native directory chooser."""


RunCommand = Callable[..., subprocess.CompletedProcess[str]]
FindExecutable = Callable[[str], str | None]


def _run_picker(
    command: list[str],
    *,
    run: RunCommand,
    cancellation_codes: set[int],
    cancellation_markers: tuple[str, ...] = (),
) -> Path | None:
    try:
        result = run(
            command,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as error:
        raise FolderPickerUnavailable(
            "The native folder chooser could not be opened."
        ) from error
    if result.returncode != 0:
        stderr = result.stderr.strip()
        if result.returncode in cancellation_codes or any(
            marker in stderr for marker in cancellation_markers
        ):
            return None
        raise FolderPickerUnavailable("The native folder chooser could not be opened.")
    selected = result.stdout.strip()
    return Path(selected) if selected else None


def choose_local_folder(
    *,
    platform_name: str = sys.platform,
    run: RunCommand = subprocess.run,
    find_executable: FindExecutable = shutil.which,
) -> Path | None:
    """Open the platform folder chooser without exposing a path to the browser."""

    if platform_name == "darwin":
        return _run_picker(
            [
                "/usr/bin/osascript",
                "-e",
                (
                    'POSIX path of (choose folder with prompt '
                    '"Choose a local DICOM folder")'
                ),
            ],
            run=run,
            cancellation_codes=set(),
            cancellation_markers=("(-128)", "User canceled"),
        )

    if platform_name == "win32":
        executable = find_executable("powershell.exe") or find_executable("powershell")
        if executable is None:
            raise FolderPickerUnavailable(
                "Windows PowerShell is required for the native folder chooser."
            )
        script = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "$dialog = New-Object System.Windows.Forms.FolderBrowserDialog; "
            "$dialog.Description = 'Choose a local DICOM folder'; "
            "$dialog.ShowNewFolderButton = $false; "
            "if ($dialog.ShowDialog() -eq "
            "[System.Windows.Forms.DialogResult]::OK) { "
            "[Console]::Out.Write($dialog.SelectedPath); exit 0 }; exit 2"
        )
        return _run_picker(
            [executable, "-NoProfile", "-STA", "-Command", script],
            run=run,
            cancellation_codes={2},
        )

    if platform_name.startswith("linux"):
        zenity = find_executable("zenity")
        if zenity is not None:
            return _run_picker(
                [
                    zenity,
                    "--file-selection",
                    "--directory",
                    "--title=Choose a local DICOM folder",
                ],
                run=run,
                cancellation_codes={1},
            )
        kdialog = find_executable("kdialog")
        if kdialog is not None:
            return _run_picker(
                [
                    kdialog,
                    "--getexistingdirectory",
                    ".",
                    "--title",
                    "Choose a local DICOM folder",
                ],
                run=run,
                cancellation_codes={1},
            )
        raise FolderPickerUnavailable(
            "Install zenity or kdialog to use the native folder chooser."
        )

    raise FolderPickerUnavailable(
        "This operating system does not provide a supported native folder chooser."
    )
