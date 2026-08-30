# DICOM Guide

![A person using DICOM Guide while a friendly agent points out regions on three scan views](docs/assets/dicom-guide-guided-tour.png)

**You have medical scan files. DICOM Guide helps you open them, see what matters,
and ask better questions.**

DICOM is the standard hospitals and imaging centers use to store and exchange MRI,
CT, and many other scans. A scan folder may contain hundreds of oddly named
files—sometimes without extensions—plus a `DICOMDIR` index. Do not rename or sort
them. Point DICOM Guide at the folder you received, and it will find the images.

DICOM Guide is a small local viewer built to be driven by a Codex agent. The agent
can inventory the study, choose a useful series, move through exact slices, point to
anatomy with colored highlights, and explain what a sequence commonly helps experts
assess. The scan pixels and metadata stay on your computer.

## Start with the folder you have

Open this repository in Codex and ask:

```text
$dicom-guide-install Install DICOM Guide and give me a tour using /path/to/DICOM-folder
```

The install skill chooses the correct macOS, Linux, or Windows package, starts the
local viewer, and opens it beside the conversation. If you want the skills available
from any Codex task first, ask:

```text
$skill-installer Install the DICOM Guide skills from https://github.com/cnberry/scan-view/tree/main/.agents/skills
```

Then try one of these:

```text
$dicom-guide What does the series I am looking at mean?
$dicom-guide What is the green highlighted area?
$dicom-guide Highlight the pons in this view using green.
$dicom-guide Give me a visual tour of this study. Explain one view at a time.
$dicom-guide Take me on a visual tour of this radiology report: <paste report text>
$dicom-guide Which series would best help an expert assess the finding in my report?
```

You do not need to know which files are images, what “T2 FLAIR” means, or which
plane to open. That orientation is part of the guide’s job.

## What a guided session does

1. Finds MRI and CT studies beneath the folder without changing the source files.
2. Explains the available series in plain language before choosing one.
3. Opens the most useful series and walks through anatomy or report findings visually.
4. Keeps visible observations, DICOM metadata, anatomical inference, and report text
   distinct so the explanation does not sound more certain than the evidence.
5. Offers reputable sources and a focused next question after medical explanations.

The viewer supports native image stacks and linked axial, coronal, and sagittal
views, plus reversible discussion highlights. It is designed for guided exploration
and preparing precise questions—not validated diagnosis, segmentation, or
longitudinal measurement.

## Local by design

- DICOM parsing, rendering, metadata inspection, and agent control are local.
- The service binds only to loopback and source DICOM files are read-only.
- No account, login, Python environment, Node.js install, or external processing API
  is required by a packaged application.
- When the agent looks up a general medical source, it must use generic terms and
  never send scan pixels, metadata, names, report text, or patient-specific details.

The viewer needs the DICOM source files. It ignores unrelated CD viewer programs and
documents, though keeping an untouched copy of the complete original folder is wise.

## Install without Codex

Download the package for your computer from Releases.

**macOS or Linux**

```bash
tar -xzf dicom-guide-<version>-<platform>.tar.gz
cd dicom-guide-<version>-<platform>
sh install.sh
dicom-guide open '/path/to/DICOM-folder'
```

This installs under `/usr/local/lib/dicom-guide` with the command at
`/usr/local/bin/dicom-guide`. The installer asks you to rerun with `sudo` only when
`/usr/local` requires it. macOS packages are currently ad-hoc signed rather than
Apple-notarized, so the first launch may require **Open Anyway** in Privacy & Security.

**Windows**

Extract `dicom-guide-<version>-windows-x86_64.zip`, open PowerShell in the extracted
folder, and run:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
dicom-guide open 'C:\path\to\DICOM-folder'
```

The Windows installer uses the standard per-user application directory at
`%LOCALAPPDATA%\Programs\DICOM Guide` and adds its `bin` folder to the user `PATH`.
Open a new terminal if the command is not immediately visible.

## Agent interface

The supported command surface securely discovers the active local session:

```bash
dicom-guide state
dicom-guide series
dicom-guide show --series-id SERIES_ID --instance-id INSTANCE_ID --view native --reset
dicom-guide highlight add --color green --image-normalized 0.46 0.46
```

The complete state and control contract is in [docs/AGENT-API.md](docs/AGENT-API.md).
Repository-scoped workflows live in [.agents/skills](.agents/skills):

- `$dicom-guide-install` — turn a folder path into a running local session.
- `$dicom-guide` — explain and control the current imagery.
- `$dicom-guide-develop` — set up the repository, make a change, test it, and prepare
  an upstream contribution with synthetic data.

## Built on

| Project | Role |
| --- | --- |
| [Cornerstone3D](https://github.com/cornerstonejs/cornerstone3D) | DICOM loading, rendering, viewports, and tools |
| [pydicom](https://github.com/pydicom/pydicom) | Local DICOM indexing and metadata |
| [dcmjs](https://github.com/dcmjs-org/dcmjs) | DICOM utilities and derived-object support |
| [3D Slicer](https://github.com/Slicer/Slicer) | Optional local registration research; not required by the viewer |
| [React](https://github.com/facebook/react) + [Vite](https://github.com/vitejs/vite) | Viewer application and build |

## Develop with Codex

Start with an outcome instead of setup instructions:

```text
$dicom-guide-develop Set up this repository, run its checks, and tell me the smallest useful first contribution.
$dicom-guide-develop Fix <problem>, verify it on every affected platform, and prepare a PR.
$dicom-guide-develop Build a release for this computer and smoke-test it with synthetic DICOM.
```

Patient scans, local paths, tokens, reports, findings, and screenshots do not belong
in Git. Development and tests use synthetic data. Licensed under [MIT](LICENSE).
