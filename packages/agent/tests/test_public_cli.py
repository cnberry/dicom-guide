from __future__ import annotations

import sys

from dicom_guide import public_cli


def test_public_help_is_focused(capsys, monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["dicom-guide", "--help"])
    public_cli.main()
    output = capsys.readouterr().out
    assert "dicom-guide open DICOM_FOLDER" in output
    assert "dicom-guide state" in output
    assert "run-rigid-registration" not in output


def test_public_version(capsys, monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["dicom-guide", "--version"])
    public_cli.main()
    assert capsys.readouterr().out == "DICOM Guide 0.15.0\n"
