# ScanView

ScanView is a local-first, cross-platform DICOM workspace for reviewing MRI and
CT studies over time. It is being built for two audiences at once:

- people who need to see, compare, measure, and discuss scans with clinicians;
- software agents that need a structured, source-traceable, read-only interface.

The current MVP reads copied DICOM files locally, groups them into studies and
series, renders native pixels with Cornerstone3D, and presents two series side by
side. It suggests pair compatibility with visible reasons but never approves a
pair or issues a medical conclusion.

The first local catalog contains 2 studies, 65 series, and 10,286 DICOM instances.
They represent one MRI exam and one CT exam, so there is not yet a valid
same-modality longitudinal pair for measuring chemotherapy response. ScanView
returns zero candidates instead of treating CT and MRI as interchangeable.

> **Important:** ScanView is investigational software, not a medical device and
> not validated for diagnosis. Imaging findings and treatment-response judgments
> require qualified clinician review.

## Current capabilities

- Local folder import; no upload, analytics, fonts, or telemetry.
- One loopback launcher for the bundled UI, privacy-minimized catalog, protected
  native DICOM bytes, and agent endpoints.
- No external processing API: decoding, metadata, and comparisons stay on-device.
- Extension-independent DICOM Part 10 parsing.
- MRI/CT stack rendering through Cornerstone3D's maintained codecs.
- Geometry-gated, single-series axial/coronal/sagittal MPR built locally from native
  source slices, with physically linked patient-space crosshairs, visible LPS
  coordinates, window/level, pan, zoom, wheel navigation, and reset.
- Window/level, pan, zoom, reset, DICOM patient-orientation labels, and manual
  length/bidirectional/elliptical ROI measurement tools.
- Follow-up is never guessed; same-exam series are rejected as longitudinal pairs.
- Longitudinal suggestions require one matching opaque patient-context digest; raw
  patient identifiers are read only to derive it locally and are never emitted.
- Patient-position slice linking for shared compatible DICOM frames, with an explicitly
  approximate normalized fallback everywhere else.
- Human-readable measurement table plus versioned draft export/reopen with opaque
  series/instance references, patient-space geometry, tracking IDs, limitations,
  and `unreviewed` state.
- Per-viewport local key-image export: one ZIP containing a watermarked PNG, exact
  source/presentation provenance, and the visible source-scoped measurement packet.
- One-click local clinician visit-packet export from the two live unified-viewer
  panes, plus the equivalent CLI workflow. Both use the same Python validation gates
  and produce a static side-by-side review page with an agent-verifiable manifest.
- Local agent comparison of explicitly selected, distinct-series measurements;
  numeric changes remain source-linked and never become a response verdict.
- Transparent metadata compatibility score and warnings.
- Registration-gated derived comparisons; CT/MR subtraction is prohibited.
- Python catalog with SHA-256 source provenance and opaque logical IDs.
- Bearer-token-protected, loopback-only, source-read-only local API.
- Versioned measurement, key-image, comparison, and visit-packet JSON Schemas;
  committed tests use synthetic data only.
- Resumable copy/repair and byte-for-byte verification utility.

## Launch the unified local workspace

Requirements: Python 3.11+, plus Node.js 22+ and pnpm 11+ for the initial build.

```bash
python3 -m venv .venv
pnpm install
pnpm build
.venv/bin/python -m pip install -e 'packages/agent[test]'
.venv/bin/scanview-agent launch '/Users/chris/Desktop/Mila Scan CD'
```

The launcher indexes the selected directory, binds only to loopback, opens the local
viewer, and serves the same opaque manifest and native instances to people and
agents. A one-time URL establishes an HttpOnly local browser session and then
redirects to a clean URL. DICOM bytes never leave this computer.

To create a self-contained installable wheel without modifying the source tree:

```bash
pnpm build
.venv/bin/python scripts/build_release.py --output-dir release
```

The release builder stages the viewer, workers, and codecs inside the wheel. A
regular agent-only wheel remains lightweight and can still run `manifest`,
`candidates`, and `serve`; pass `--ui-dist` to `launch` when using that form.

## Run the folder-picker viewer

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

For a built production bundle, Node is not required at runtime:

```bash
pnpm build
python3 scripts/run_viewer.py
```

## Run the agent catalog/API

Requirements: Python 3.11+.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e 'packages/agent[test]'
.venv/bin/scanview-agent manifest '/path/to/copied/DICOM' --output /safe/local/manifest.json
.venv/bin/scanview-agent serve '/path/to/copied/DICOM'
.venv/bin/scanview-agent launch '/path/to/copied/DICOM'
.venv/bin/scanview-agent validate-measurements '/path/to/scanview-measurements.json'
.venv/bin/scanview-agent validate-key-image '/path/to/scanview-key-image.zip'
.venv/bin/scanview-agent assemble-visit-packet baseline-key-image.zip followup-key-image.zip \
  --output scanview-visit-packet.zip
.venv/bin/scanview-agent validate-visit-packet scanview-visit-packet.zip
.venv/bin/scanview-agent compare-measurements baseline.json followup.json \
  --baseline-id 'bidirectional:baseline-id' \
  --followup-id 'bidirectional:followup-id' \
  --output comparison.json
```

The server exposes:

- `GET /v1/health` (no token required)
- `GET /v1/manifest`
- `GET /v1/comparison-candidates`
- `GET /v1/instances/{opaque_id}`
- `POST /v1/visit-packets` (same-origin browser session; in-memory derivative only)

All endpoints except health require the bearer token printed at startup. The unified
browser uses a same-origin HttpOnly session cookie instead of exposing that token to
application JavaScript. The visit-packet POST additionally requires the exact local
origin and accepts a bounded ZIP containing only the two derived key-image archives;
it returns the validated result from memory and creates no server-side file. There is
no source mutation or deletion endpoint. The server refuses non-loopback bind
addresses. This loopback interface is part of the offline local application, not an
external processing API.

## Save and reopen a measurement draft

Choose **Length**, **Bidirectional**, or **Ellipse ROI**, draw a manual measurement, then choose
**Export measurement draft**. The local JSON file is sensitive derived medical
data. It contains opaque source references and DICOM patient-space geometry, but no
direct patient name/ID or source path. To reopen it, load the source DICOM folder,
select the matching series, and choose **Open measurement draft**. Matching overlays
and table rows are restored locally and remain `unreviewed`.

`compare-measurements` requires explicit baseline and follow-up tracking IDs from
different source series. It refuses unknown physical units, mismatched tool types,
and geometry/result disagreements. Its output contains deltas, limitations, missing
clinical context, and questions—not a treatment-response category. An ellipse is a
2D area draft only; it is not tumor segmentation, volume, or a response verdict.

## Save and validate a key image

After a native image renders, choose **Save key image** in that viewport. ScanView
creates one local ZIP containing `key-image.png`, `key-image.json`, and
`measurements.json`. The PNG includes the visible overlays, R/L/A/P labels when
available, and a permanent **unreviewed derived display key image—not for
diagnosis** footer. Key-image v2 sidecars record the opaque patient/study/series and
exact source instance, stack position, display settings, implementation versions,
limitations, and SHA-256
digests that bind the image to its source-scoped measurement evidence.

Validate an archive locally without printing identifiers or measurement values:

```bash
.venv/bin/scanview-agent validate-key-image '/safe/local/scanview-key-image.zip'
```

The ZIP is sensitive derived medical data, not a de-identified or diagnostic
artifact. Keep the original DICOM as the authority and share the archive only with
the same safeguards used for the scans.

## Inspect one source series with MPR

Choose **Open MPR** beside a native viewport. ScanView enables it only when at least
three MR/CT slices have a stable Frame of Reference, validated orientation, positive
matrix/pixel spacing, finite patient positions, and sufficiently regular projected
slice spacing. Axial, coronal, and sagittal patient-axis views are reconstructed in
memory with the bundled Cornerstone volume renderer; wheel navigation and display
controls remain local.

**Linked crosshairs** is the default MPR tool. Click or drag in any plane to move one
shared DICOM patient-space point through all three views. The current LPS coordinate
is displayed in millimetres (`+X` left, `+Y` posterior, `+Z` head). Minimal mode
keeps the planes canonical: oblique rotation and slab-thickness controls are not
exposed.

MPR planes are interpolated display derivatives. They are not registration,
segmentation, tumor response, or diagnosis, and original DICOM remains authoritative.
The shared point links only the three planes reconstructed from that one source series;
it does not align baseline and follow-up exams.
Evidence export stays on the native source panes until derived-image provenance is
implemented.

## Assemble a clinician visit packet

In the unified local workspace, choose a dated same-patient MR↔MR or CT↔CT pair,
place the desired source slice in each pane, then choose **Save visit packet**. The
viewer captures both displayed panes in memory and sends only those two derived
key-image bundles to the same-origin loopback assembler. The returned ZIP downloads
directly; neither the input bundles nor the visit packet is written by the server.

The standalone local CLI uses the same assembler and validation rules:

```bash
.venv/bin/scanview-agent assemble-visit-packet \
  baseline-key-image.zip followup-key-image.zip \
  --output scanview-visit-packet.zip
.venv/bin/scanview-agent validate-visit-packet scanview-visit-packet.zip
```

The assembler refuses invalid inputs, mismatched patient contexts, repeated source
studies/series, CT↔MRI, missing or non-chronological dates, and viewport-role
mismatches. The output contains both complete evidence bundles, a versioned
`visit-packet.json`, instructions, and a
script-free `review.html` for side-by-side viewing or printing. Extract the whole ZIP
before opening the review page. It states that the images are unregistered and
unreviewed, generates no numeric comparison or response conclusion, and keeps the
questions that require clinician review visible.

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
- [Agent interface](docs/AGENT-INTERFACE.md)
- [Viewer research](docs/RESEARCH.md)
- [Plan and acceptance criteria](docs/PLAN.md)
- [Current status](docs/STATUS.md)
- [Roadmap / next steps](docs/ROADMAP.md)
- [Medical safety and privacy](docs/SAFETY-AND-PRIVACY.md)

Patient files, catalogs, derived images, annotations, screenshots, and audit logs
must remain outside Git. See [data/README.md](data/README.md).
