# DICOM Guide

![DICOM Guide: a local Codex-first MRI viewer](docs/assets/dicom-guide-codex-mri.png)

**The local MRI and CT viewer your agent can control.**

DICOM Guide keeps the viewer beside your Codex conversation. Ask what is under the
crosshairs, mark an area with a brush, or let the agent move to an exact series,
slice, plane, or patient-space point. DICOM parsing and rendering stay on this
computer; no external processing API is used.

The focused interface explores one MRI or CT series as a native stack or linked
axial, coronal, and sagittal views. It is investigational software, not a medical
device; use it to understand imagery and prepare precise questions for clinicians.

## Install

Download the archive for macOS or Linux from Releases, then:

```bash
tar -xzf dicom-guide-<version>-<platform>.tar.gz
cd dicom-guide-<version>-<platform>
sh install.sh
dicom-guide open '/path/to/DICOM-folder'
```

The installer uses `/usr/local/lib/dicom-guide` and `/usr/local/bin/dicom-guide`.
It will explicitly request a rerun with `sudo` when `/usr/local` is not writable.

The packaged application includes its runtime and web viewer. It needs no Python,
Node.js, virtual environment, account, login, or network connection at runtime.
Open the printed loopback URL in Codex's side panel or any local Chrome window.
Current macOS archives are ad-hoc signed but not Apple-notarized, so the first launch
may require **Open Anyway** in System Settings → Privacy & Security.

Use the bundled Codex skills for guided work:

- `$dicom-guide-install` — install, launch, and troubleshoot.
- `$dicom-guide` — answer questions about the current image and control the viewer.

## Viewer and agent controls

- Native MRI/CT stacks with window, pan, zoom, and automatic fit.
- Linked three-plane MPR with shared crosshairs.
- Reversible color discussion highlights in Single and 3-plane views.
- Exact local state: series, instance, plane, slice, tool, render status, and LPS point.
- API control of navigation, tools, reset, and discussion highlights.
- Local retrieval of minimized metadata or one exact DICOM instance for deeper
  on-device analysis.

The installed command discovers the active session securely, so no token copying is
needed:

```bash
dicom-guide state
dicom-guide series
dicom-guide show \
  --series-id series_0123456789abcdef0123 \
  --instance-id instance_0123456789abcdef0123 \
  --view mpr --tool crosshairs --lps 12.5 -8.25 43.0
```

The complete machine contract is in [docs/AGENT-API.md](docs/AGENT-API.md). The API
binds only to loopback, agent operations require an owner-only session credential,
and source DICOM files are read-only.

## Core projects

| Project | Role | Required? |
| --- | --- | --- |
| [Cornerstone3D](https://github.com/cornerstonejs/cornerstone3D) | Browser rendering, DICOM loading, viewports, and tools | Yes |
| [pydicom](https://github.com/pydicom/pydicom) | Local DICOM indexing and metadata | Yes |
| [dcmjs](https://github.com/dcmjs-org/dcmjs) | DICOM web utilities and derived-object support | Yes |
| [3D Slicer](https://github.com/Slicer/Slicer) | Optional local registration experiments | No |
| [React](https://github.com/facebook/react) + [Vite](https://github.com/vitejs/vite) | Viewer application and build | Yes |

## Develop and distribute

Contributors need Python 3.11+, Node.js 22+, and pnpm 11+.

```bash
pnpm install
pnpm test
pnpm typecheck
pnpm build
python -m pytest packages/agent/tests
python scripts/build_native_distribution.py
```

Tagged releases build self-contained `macos-arm64`, `macos-x86_64`, and
`linux-x86_64` archives in GitHub Actions. The Python namespace is `dicom_guide`;
media types, schema IDs, and artifact types use `dicom-guide` consistently. This is
an intentional breaking rename, so pre-rename artifacts must be recreated or migrated.

Patient scans, generated findings, tokens, local paths, and screenshots do not belong
in Git. Tests use synthetic data. Licensed under [MIT](LICENSE).
