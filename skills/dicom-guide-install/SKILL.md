---
name: dicom-guide-install
description: Install, build, launch, update, or troubleshoot the local DICOM Guide MRI/CT viewer on macOS or Linux. Use when a person asks to set up DICOM Guide, open a local DICOM folder, find the viewer URL, verify a release, build from source, or diagnose a local launch problem.
---

# Install DICOM Guide

Keep every DICOM folder outside Git. Prefer a packaged release: it needs no Python,
Node.js, environment, account, or external processing API.

## Install a release

```bash
tar -xzf dicom-guide-<version>-<platform>.tar.gz
cd dicom-guide-<version>-<platform>
sh install.sh
```

Install to `/usr/local/lib/dicom-guide` and expose `/usr/local/bin/dicom-guide`.
If `/usr/local` is not writable, rerun the exact installer with `sudo`; never silently
fall back to a hidden home-directory runtime.

Launch with:

```bash
dicom-guide open '/absolute/path/to/DICOM-folder'
```

Report the printed clean loopback URL, normally `http://127.0.0.1:8765/`. Session
credentials are stored owner-only for the installed agent commands and removed when
the viewer stops; never print or commit them.

## Build from source

Contributors need Python 3.11+, Node.js 22+, and pnpm 11+. Build the web viewer, then
run `python scripts/build_native_distribution.py`. The build uses a temporary isolated
Python environment; the resulting application does not depend on it.

If port 8765 is busy, identify the existing DICOM Guide process before choosing another
port. After launch, check `/v1/health`, open the viewer, and confirm that at least one
MRI or CT series renders.

## Troubleshoot

- Missing viewer bundle: run `pnpm build`.
- Command missing after install: verify `/usr/local/bin` is on PATH and the symlink
  targets the installed version under `/usr/local/lib/dicom-guide`.
- Empty catalog: confirm the chosen directory contains readable DICOM Part 10 files.
- External Chrome does not render: use the clean loopback URL, rebuild, then hard
  refresh; never add cloud fallbacks or remote processing.

Run `pnpm typecheck`, `pnpm test`, and the Python tests after changing installation
or launch code.
