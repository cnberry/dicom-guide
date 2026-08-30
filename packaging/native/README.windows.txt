DICOM Guide @VERSION@

Open PowerShell in this extracted folder and run:

    powershell -ExecutionPolicy Bypass -File .\install.ps1

The installer uses the standard per-user application directory:

    %LOCALAPPDATA%\Programs\DICOM Guide

It adds the application's bin directory to your user PATH. Open a new terminal,
then open the top-level folder copied from your imaging disc or portal download:

    dicom-guide open 'C:\path\to\DICOM-folder'

All DICOM parsing and display remain on this computer. No Python, Node.js,
virtual environment, account, or external processing API is required.

The current Windows build is not code-signed. If Windows shows an Unknown Publisher
warning, verify the adjacent .sha256 file against the downloaded archive and proceed
only when the package came from the official DICOM Guide release.
