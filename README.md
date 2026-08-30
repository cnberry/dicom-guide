# ScanView

![ScanView: a local Codex-first MRI viewer](docs/assets/scanview-codex-mri.png)

ScanView is a simple, local MRI/CT viewer built to work with Codex. Keep the viewer
open beside the conversation, point at an image, and ask questions such as:

> What am I looking at here?

Codex can read the exact series, slice, three-plane position, and active display
tool through ScanView's local API. It can also move the viewer to an exact source
image or patient-space point. DICOM parsing and rendering stay on this computer;
ScanView does not use an external DICOM-processing API.

The current interface intentionally does one job well: explore one MRI or CT series
as a native stack or as linked axial, coronal, and sagittal views. Longitudinal
comparison and rotatable 3D rendering are not part of the current viewer.

ScanView is investigational software, not a medical device. Use it to explore and
prepare questions, then confirm medical interpretation with a qualified clinician.

## Install and run

Requirements: macOS or Linux, Python 3.11+, Node.js 22+, and pnpm 11+.

```bash
git clone https://github.com/cnberry/scan-view.git
cd scan-view
python3 -m venv .venv
pnpm install
pnpm build
.venv/bin/python -m pip install -e 'packages/agent[test]'
.venv/bin/scanview-agent launch '/path/to/DICOM-folder'
```

Open the printed `http://127.0.0.1:8765/` URL in Codex's side panel or any local
Chrome window. The viewer itself needs no login. The launcher also prints a bearer
token for local agent commands; do not put that token in a URL or commit it.

If ScanView is already installed:

```bash
.venv/bin/scanview-agent launch '/path/to/DICOM-folder'
```

Use the repository skills for guided operation:

- `skills/scanview-install` — install, build, launch, and troubleshoot ScanView.
- `skills/scanview-control` — answer questions about the current image and drive the
  viewer through its local API.

## What is here now

- Native MRI/CT stack viewing with window, pan, zoom, and reset.
- Linked three-plane MPR with crosshairs, window, pan, zoom, and reset.
- Reversible color highlights in Single and 3-plane views: people or Codex can brush a bounded
  region in any MPR plane, while the local API reports its exact patient-space path.
  Highlights are explicitly not segmentations or measurements.
- Local folder selection and automatic fit when the panel changes size.
- Exact local viewer state for agents: source series and instance, slice position,
  view mode, render status, selected tool, and DICOM LPS point.
- Agent commands for series/slice selection, native or MPR mode, display-tool
  selection, patient-space navigation, discussion highlights, and reset.
- Local retrieval of privacy-minimized metadata or one exact DICOM instance when an
  agent needs deeper on-device analysis.

The source tree still contains experimental comparison, registration, segmentation,
and evidence code. Those are not presented as the current product. The supported
front door is the focused single-series viewer and its agent-control API.

## Agent API

The complete contract is in [docs/AGENT-API.md](docs/AGENT-API.md). The common loop is:

```bash
export SCANVIEW_AGENT_TOKEN='<token printed by the launcher>'

.venv/bin/python skills/scanview-control/scripts/scanview_control.py state
.venv/bin/python skills/scanview-control/scripts/scanview_control.py series
.venv/bin/python skills/scanview-control/scripts/scanview_control.py show \
  --series-id series_0123456789abcdef0123 \
  --instance-id instance_0123456789abcdef0123 \
  --view mpr --tool crosshairs --lps 12.5 -8.25 43.0
```

The API is loopback-only. Browser display is unauthenticated because the server only
binds to the local machine; agent reads and commands require the launcher's bearer
token. Source DICOM files are read-only.

## Core projects

ScanView is built on established open-source imaging tools:

| Project | Role | Required? |
| --- | --- | --- |
| [Cornerstone3D](https://github.com/cornerstonejs/cornerstone3D) | Browser rendering, DICOM loading, viewports, and interaction tools | Yes |
| [pydicom](https://github.com/pydicom/pydicom) | Local DICOM indexing and metadata access | Yes |
| [dcmjs](https://github.com/dcmjs-org/dcmjs) | DICOM web utilities and local derived-object support | Yes |
| [3D Slicer](https://github.com/Slicer/Slicer) | Optional local registration experiments through BRAINSFit/BRAINSResample | No |
| [React](https://github.com/facebook/react) + [Vite](https://github.com/vitejs/vite) | Viewer application and build | Yes |

The pinned JavaScript versions are in `apps/viewer/package.json`; Python dependencies
are in `packages/agent/pyproject.toml`.

## Develop

```bash
pnpm test
pnpm typecheck
pnpm build
.venv/bin/python -m pytest packages/agent/tests
```

Useful code locations:

- `apps/viewer` — React/Cornerstone3D viewer.
- `packages/agent` — local catalog, server, and command validation.
- `skills` — Codex install and control workflows.
- `schemas` — versioned machine-readable contracts used by experimental modules.

Patient scans, generated findings, tokens, local paths, and screenshots do not belong
in Git. Tests use synthetic data. Licensed under [MIT](LICENSE).
