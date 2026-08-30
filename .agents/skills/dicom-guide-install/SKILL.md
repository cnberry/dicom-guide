---
name: dicom-guide-install
description: Bootstrap DICOM Guide from its GitHub repository and turn a local folder from an imaging disc, portal download, or copied MRI/CT study into a running session on macOS, Linux, or Windows. Use when a person gives the DICOM Guide repository URL and a scan path; says they have medical scan files but does not know whether they are DICOM; asks to install, update, open, or troubleshoot DICOM Guide; provides a folder path and asks for a tour; or needs the viewer URL. Fetch the repository when needed, detect the platform, preserve the source folder, prefer a verified self-contained release, install the person-facing skills, validate the local service and first rendered series, and begin the guided handoff without requiring separate setup prompts or knowledge of terminals, Python environments, DICOMDIR, extensions, or series names.
---

# Install and open DICOM Guide

Own the setup from folder path to useful first view. Use plain language and keep the
person's scan data local.

## Bootstrap from one remote prompt

Treat this as a complete request, not documentation for the person to translate:

```text
Install DICOM Guide from https://github.com/cnberry/dicom-guide and start a guided tour using /absolute/path/to/DICOM-folder
```

If the task starts outside a DICOM Guide checkout:

1. Fetch the canonical repository into a fresh temporary checkout, using existing
   GitHub access when the repository requires it.
2. Read the root `AGENTS.md` and this skill. Do not ask the person to clone or open
   the repository themselves.
3. Use the system skill-installer workflow when available to install
   `.agents/skills/dicom-guide-install` and `.agents/skills/dicom-guide` for future
   turns. Newly installed skills become selectable on the next turn, but do not stop
   or require a restart before completing the current installation and first tour.
4. Continue through application installation, launch, validation, and the first useful
   explanation in this same task. Remove only a temporary checkout created for this
   bootstrap after it is no longer needed.

If the repository cannot be fetched, report the access problem directly and leave the
scan folder untouched. If already operating in a checkout, skip the fetch.

## Accept the folder they have

- A DICOM folder may be a disc root, a nested export, or files without extensions.
- Do not require `DICOMDIR`; DICOM Guide recursively discovers readable MRI and CT
  objects.
- Do not rename, reorganize, or write into the source folder.
- Keep an untouched copy of the original media when practical.
- Never move patient files into the repository or include their names or paths in Git.

If the person supplied a path, proceed without asking them to identify a file. If the
path is missing, ask only for the top-level folder copied from the disc or download.

## Prefer a self-contained release

1. Detect the operating system and CPU architecture.
2. Select the matching release artifact:
   - `macos-arm64`
   - `macos-x86_64`
   - `linux-x86_64`
   - `windows-x86_64`
3. Download the adjacent `.sha256` file and the release's portable
   `dicom-guide-v<version>-provenance.sigstore.json` bundle. Verify the archive with
   `gh attestation verify`, scoped to `cnberry/dicom-guide` and
   `.github/workflows/release.yml`, then verify the adjacent checksum before extracting
   it. If the local GitHub CLI cannot verify attestations, state that limitation rather
   than describing a checksum as a publisher signature. Do not send the scan folder to
   GitHub or any other service.
4. Install for the current platform.

macOS and Linux packages contain `install.sh` and install to
`/usr/local/lib/dicom-guide/<version>` with `/usr/local/bin/dicom-guide`. Run the
installer normally first. If it explicitly reports that `/usr/local` is not writable,
rerun that exact installer with `sudo`; do not silently choose a hidden home folder.
On macOS, an elevated process may be denied access to an extracted bundle under
`Desktop`, `Documents`, or another privacy-protected folder. If that happens, verify
the archive again, extract it to a fresh owner-only directory under `/private/tmp`,
and rerun the same installer there. Never ask the person to paste an administrator
password into chat.

Windows packages contain `install.ps1` and install per-user to
`%LOCALAPPDATA%\Programs\DICOM Guide`, with a command shim in its `bin` directory.
Run:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

Open a new terminal after a Windows PATH change if needed. Do not use Unix install
instructions on Windows.

The packaged app includes its Python runtime and viewer. It must not require a user
managed virtual environment, Node.js, an account, login, or network connection at
runtime.

## Build locally when a release is unavailable

When operating in a repository checkout, read `$dicom-guide-develop`, build the viewer,
and run `python scripts/build_native_distribution.py`. The build may use a temporary
isolated environment; the resulting installed application must not depend on it.

Do not build against patient data. Use synthetic DICOM for build and smoke tests.

## Launch and prove it works

1. Run `dicom-guide open '<absolute-folder-path>'` in a persistent process.
2. Report the clean loopback URL, normally `http://127.0.0.1:8765/`.
3. Check `GET /v1/health` locally.
4. Open the URL in the Codex side panel or local browser.
5. Run `dicom-guide state` and require `viewer_connected: true` and
   `render_status: ready`.
6. Run `dicom-guide series` and confirm at least one MRI or CT series. If none exists,
   explain what was searched and check nested folders before asking for a different
   source.
7. Hand off immediately with a useful prompt:

```text
$dicom-guide Give me a visual tour of this study. Start by explaining the available series.
```

Do not print session credentials. Installed commands securely discover owner-only
local session state and remove it when the viewer stops.

## Troubleshoot by outcome

- **The command is missing:** verify the documented install directory and PATH; do
  not install a second hidden copy.
- **The port is busy:** identify an existing DICOM Guide process before selecting a
  different loopback port.
- **The catalog is empty:** inspect the chosen path recursively for readable DICOM;
  filenames and extensions are not reliable indicators.
- **The browser loads but no image renders:** confirm the exact clean loopback URL,
  viewer build, series support, browser console, and hard refresh locally.
- **macOS blocks first launch:** explain the current ad-hoc signature and use **Open
  Anyway** in Privacy & Security; never disable Gatekeeper globally.
- **Windows blocks the script:** use the one-process `-ExecutionPolicy Bypass` command
  above; do not weaken the machine-wide execution policy.

End setup answers with the viewer URL, what study/series was found in plain language,
and one `$dicom-guide` prompt. Do not bury success beneath installation mechanics.
