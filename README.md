# ScanView

ScanView is a local-first, cross-platform DICOM workspace for reviewing MRI and
CT studies over time. It is being built for two audiences at once:

- people who need to see, compare, measure, and discuss scans with clinicians;
- software agents that need a structured, source-traceable, read-only interface.

The current MVP reads copied DICOM files locally, groups them into studies and
series, renders native pixels with Cornerstone3D, and presents two series side by
side. It suggests pair compatibility with visible reasons but never approves a
pair or issues a medical conclusion.

> **Important:** ScanView is investigational software, not a medical device and
> not validated for diagnosis. Imaging findings and treatment-response judgments
> require qualified clinician review.

## Current capabilities

- Local folder import; no upload, analytics, fonts, or telemetry.
- No external processing API: decoding, metadata, and comparisons stay on-device.
- Extension-independent DICOM Part 10 parsing.
- MRI/CT stack rendering through Cornerstone3D's maintained codecs.
- Baseline/follow-up selection and linked normalized slice navigation.
- Transparent metadata compatibility score and warnings.
- Registration-gated derived comparisons; CT/MR subtraction is prohibited.
- Python catalog with SHA-256 source provenance and opaque logical IDs.
- Bearer-token-protected, loopback-only, read-only agent API.
- Versioned JSON manifest schema and synthetic-only tests.
- Resumable copy/repair and byte-for-byte verification utility.

## Run the viewer

Requirements: Node.js 22+ and pnpm 11+.

```bash
pnpm install
pnpm dev
```

Open `http://127.0.0.1:4173`, choose the copied DICOM directory, then select a
baseline and follow-up series. Pixels remain in the browser process.

After dependencies are installed and the application is built, runtime operation
is offline. Cornerstone codecs and WebAssembly assets are served from the local
bundle; research-document links are references only and are never contacted by the
application. A restrictive Content Security Policy blocks external runtime access.

## Run the agent catalog/API

Requirements: Python 3.11+.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e 'packages/agent[test]'
.venv/bin/scanview-agent manifest '/path/to/copied/DICOM' --output /safe/local/manifest.json
.venv/bin/scanview-agent serve '/path/to/copied/DICOM'
```

The server exposes:

- `GET /v1/health` (no token required)
- `GET /v1/manifest`
- `GET /v1/comparison-candidates`
- `GET /v1/instances/{opaque_id}`

All endpoints except health require the bearer token printed at startup. There is
no mutation or deletion endpoint. The server refuses non-loopback bind addresses.

## Preserve and verify removable media

Do not run a second copier while Finder is still copying. Once the active transfer
has stopped, this utility resumes missing/size-mismatched files, re-copies any hash
mismatch, and produces a SHA-256 manifest beside the local copy:

```bash
python3 scripts/copy_and_verify.py \
  '/Volumes/PATIENT_DATA' \
  '/Users/chris/Desktop/Mila Scan CD'
```

It never deletes destination extras and never writes to the source.

## Project record

- [Architecture](docs/ARCHITECTURE.md)
- [Viewer research](docs/RESEARCH.md)
- [Plan and acceptance criteria](docs/PLAN.md)
- [Current status](docs/STATUS.md)
- [Roadmap / next steps](docs/ROADMAP.md)
- [Medical safety and privacy](docs/SAFETY-AND-PRIVACY.md)

Patient files, catalogs, derived images, annotations, screenshots, and audit logs
must remain outside Git. See [data/README.md](data/README.md).
