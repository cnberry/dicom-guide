---
name: scanview-install
description: Install, build, launch, update, or troubleshoot the local ScanView MRI/CT viewer on macOS or Linux. Use when a person asks to set up ScanView, open a local DICOM folder, find the viewer URL, verify prerequisites, rebuild the web viewer, or diagnose a local launch problem.
---

# Install ScanView

Work inside the ScanView repository. Keep any DICOM folder outside Git.

## Verify prerequisites

Require Python 3.11+, Node.js 22+, and pnpm 11+. Check with:

```bash
python3 --version
node --version
pnpm --version
```

## Install

```bash
python3 -m venv .venv
pnpm install
pnpm build
.venv/bin/python -m pip install -e 'packages/agent[test]'
```

Reuse an existing `.venv` and `node_modules` when healthy. Do not delete user data to
repair an install.

## Launch

```bash
.venv/bin/scanview-agent launch '/absolute/path/to/DICOM-folder'
```

Report the printed clean loopback URL, normally `http://127.0.0.1:8765/`. The browser
needs no login. Treat the printed agent token as a secret; do not put it in a URL,
shell history, documentation, or Git.

If port 8765 is busy, identify the existing ScanView process before choosing another
port. After launch, check `/v1/health`, open the viewer, and confirm that at least one
MRI or CT series renders.

## Troubleshoot

- Missing viewer bundle: run `pnpm build`.
- Missing Python command: rerun the editable package install in `.venv`.
- Empty catalog: confirm the chosen directory contains readable DICOM Part 10 files.
- External Chrome does not render: use the clean loopback URL, rebuild, then hard
  refresh; never add cloud fallbacks or remote processing.

Run `pnpm typecheck`, `pnpm test`, and the Python tests after changing installation
or launch code.
