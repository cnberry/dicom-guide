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
  and `unreviewed` state. Validated JSON can also be pasted locally for agent-driven
  workflows; annotations can be removed from the in-memory session without touching DICOM.
- Per-viewport local key-image export: one ZIP containing a watermarked PNG, exact
  source/presentation provenance, and the visible source-scoped measurement packet.
- One-click local clinician visit-packet export from the two live unified-viewer
  panes, plus the equivalent CLI workflow. Both use the same Python validation gates
  and produce a static side-by-side review page with an agent-verifiable manifest.
- Local agent comparison of explicitly selected, distinct-series measurements;
  a bounded working lesion label and numeric changes remain source-linked and never
  become a response verdict. The same workflow is available in the human viewer.
- Local comparison-review ZIPs bind an exact visit packet to its exact numeric
  comparison and two key images. Script-free printable review history, self-attested
  decisions, amendment requests, and amended comparisons remain separate from DICOM.
- One-click local comparison-review export captures the two exact source slices for
  the current explicit measurement pair, assembles both nested evidence artifacts in
  memory, and downloads the validated seven-file ZIP without a server-side patient file.
- Versioned agent-to-viewer navigation opens exact opaque baseline/follow-up source
  instances through a one-use URL fragment. Targets are checked against the local
  catalog, the fragment is removed immediately, and pairing remains unreviewed.
- Explicit opt-in viewer-state sharing lets a bearer-authorized local agent read the
  current opaque series/instance positions, active tool, link mode, MPR series, and
  evidence counts. It is off by default, memory-only, pixel/PHI-free, and expires
  within 30 seconds without a browser heartbeat.
- Transparent metadata compatibility score and warnings.
- Version-gated local 3D Slicer/BRAINSFit rigid-registration jobs for explicitly
  attested, matching opaque patient-context, same-modality chronological series.
  Patient identity remains unverified. Outputs are source-hashed, published without
  replacement, and locked pending human QA; CT/MR registration and subtraction are
  prohibited.
- Isolated browser-capability human registration QA with native and registered
  side-by-side views,
  axial/coronal/sagittal traversal, opacity, swipe, checkerboard, edge comparison,
  qualitative landmarks, physical-point residual tools, and a separate hash-linked
  self-attested accept/reject JSON record. Acceptance requires quantitative 3-D
  residual evidence. The bearer agent interface cannot fetch QA pixels or approve it;
  this is a capability boundary, not proof a person is present.
- Python catalog with SHA-256 source provenance and opaque logical IDs.
- Bearer-token-protected, loopback-only, source-read-only local API.
- Versioned measurement, key-image, comparison, visit-packet, review-record,
  navigation-intent, viewer-state, rigid-registration, and registration-QA JSON
  Schemas; committed tests use synthetic data only.
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
  --lesion-label 'Target lesion A' \
  --output comparison.json
.venv/bin/scanview-agent validate-comparison comparison.json
.venv/bin/scanview-agent assemble-comparison-review scanview-visit-packet.zip comparison.json \
  --output review-initial.zip
.venv/bin/scanview-agent validate-comparison-review review-initial.zip
.venv/bin/scanview-agent viewer-link manifest.json \
  --baseline-series 'series_…' --baseline-instance 'instance_…' \
  --base-url 'http://127.0.0.1:8765/'
.venv/bin/scanview-agent registration-doctor
.venv/bin/scanview-agent run-rigid-registration '/path/to/copied/DICOM' \
  --fixed-series 'series_…' --moving-series 'series_…' \
  --expected-slicer-sha256 '<trusted 64-hex digest>' \
  --output '/safe/local/registration-job' --attest-series-selection
.venv/bin/scanview-agent validate-registration '/safe/local/registration-job'
.venv/bin/scanview-agent review-registration '/safe/local/registration-job'
.venv/bin/scanview-agent record-registration-review '/safe/local/registration-job' \
  review-request.json --output registration-review.json
.venv/bin/scanview-agent validate-registration-review registration-review.json \
  --registration-bundle '/safe/local/registration-job'
```

The server exposes:

- `GET /v1/health` (no token required)
- `GET /v1/manifest`
- `GET /v1/viewer-state` (opt-in, expiring browser session state)
- `GET /v1/comparison-candidates`
- `GET /v1/registration-qa` (privacy-minimized agent status)
- `GET /v1/registration-qa/preview` (separate browser session capability only)
- `GET /v1/registration-qa/files/{allowlisted_nrrd}` (separate browser session capability only)
- `GET /v1/instances/{opaque_id}`
- `POST /v1/viewer-state` (same-origin browser publication/clear; memory only)
- `POST /v1/visit-packets` (same-origin browser session; in-memory derivative only)
- `POST /v1/comparison-reviews` (same-origin browser session; in-memory derivative only)
- `POST /v1/registration-reviews` (same-origin human browser; one in-memory JSON response)

All endpoints except health require authentication. The unified browser uses a
same-origin HttpOnly session cookie instead of exposing the printed bearer token to
application JavaScript. QA preview pixels and review submission specifically require
that browser session; a bearer-authorized agent can read only the minimized QA status.
All POSTs additionally require the exact local origin and bounded route-specific
content. The viewer-state route accepts at most 16 KiB of strict JSON and keeps only
the latest 30-second publication in memory. Visit-packet
input contains only the two derived key-image archives. Comparison-review input
contains those same two archives plus the current normalized comparison JSON; the
server builds the nested visit packet and review archive entirely in memory. Every
route returns `no-store` and creates no server-side file. There is no source mutation
or deletion endpoint.
The server refuses non-loopback bind addresses. This loopback interface is part of
the offline local application, not an external processing API.

## Generate a rigid registration pending QA

ScanView can run one rigid moving-later-to-fixed-earlier job through a locally
installed 3D Slicer 5.12.3 revision 34627 and its bundled BRAINSFit module. Earlier
and later are registration roles; neither establishes a clinical treatment baseline
or nadir. ScanView never downloads an engine, sends DICOM to an API, or falls back to
a cloud service. Check the host first:

```bash
.venv/bin/scanview-agent registration-doctor
```

Then choose the two exact catalog series IDs and explicitly attest that selection:

```bash
.venv/bin/scanview-agent run-rigid-registration \
  '/Users/chris/Desktop/Mila Scan CD' \
  --fixed-series 'series_…' --moving-series 'series_…' \
  --slicer '/Applications/Slicer.app' \
  --expected-slicer-sha256 '<trusted 64-hex digest>' \
  --output '/safe/local/mila-registration-001' \
  --attest-series-selection
```

The command rehashes every source instance, stages private generic filenames, and
accepts only original-primary brain/head MR↔MR or CT↔CT series from one matching
opaque patient context, distinct strictly ordered studies, one conservative sequence
family, one explicit contrast category, regular per-instance volume geometry, and a
compatibility score of at least 80. Matching context does not verify patient identity.
It writes an owner-only six-file directory: three NRRD volumes, one text ITK rigid
transform in DICOM patient LPS coordinates, the engine report, and
`registration.json`. Existing outputs and source files are never overwritten.
Slicer settings, the user startup script, and user-site Python packages are disabled
for the job so local customizations cannot silently change the version-gated workflow.

The expected SHA-256 must match before any DICOM is staged and is checked again after
execution. A no-data preflight first verifies the self-reported Slicer version,
revision, and BRAINSFit availability. `registration-doctor` can show the observed
launcher hash, but ScanView does not authenticate the distributor or code signature;
obtain and record the expected
digest through a trusted software-installation process. ScanView strips proxy,
credential, extension-server, and Python-path variables and requests no external API,
but it cannot prove that an arbitrary third-party executable made no network access.

Every generated bundle is `generated_pending_qa` and `unreviewed`; the registration
directory itself is never mutated by review. Validate integrity locally with
`validate-registration`. Validation parses the scalar NRRDs, requires registered
geometry to match the fixed volume, verifies a finite proper rigid transform, checks
all hashes and owner-only permissions, and still does not establish registration
quality.

For one valid pending bundle, open the isolated local human QA workspace:

```bash
.venv/bin/scanview-agent review-registration '/safe/local/registration-job'
```

It visibly watermarks the resampled preview, keeps both native volumes available,
requires full traversal in all three patient-space planes and four comparison modes,
and can download one separate self-attested JSON decision. A qualified self-attested
acceptance can authorize only exploratory shared-coverage overlay and swipe; it
requires quantitative 3-D landmark error within the fixed geometry-derived tolerance.
Subtraction, mask propagation, segmentation, measurements on the resampled image, and
response conclusions remain locked. Reviewer identity and training are not
authenticated, event hashes are not digital signatures, and the ordinary
viewer does not yet consume an accepted record. Use `validate-registration-review`
with the live bundle to recheck the full six-file source anchor before trusting its
display flags.

The currently copied CD contains one MRI exam and one CT
exam, so it cannot produce a valid registration pair. A future same-modality
follow-up and the required local Slicer installation are required for a real run.

## Open exact sources for an agent-assisted conversation

Create a bounded navigation intent from IDs already present in a local manifest:

```bash
.venv/bin/scanview-agent viewer-link manifest.json \
  --baseline-series 'series_…' --baseline-instance 'instance_…' \
  --followup-series 'series_…' --followup-instance 'instance_…' \
  --base-url 'http://127.0.0.1:8765/' \
  --output viewer-link.json
```

The command verifies both instances belong to their requested renderable MR/CT
series and refuses non-loopback, credential-bearing, query-bearing, or malformed base
URLs. Open the returned `url` only in an already authenticated local workspace. To
start the workspace at those sources, pass the same four ID options directly to
`scanview-agent launch`.

The viewer consumes `#scanview-v1?...` at startup or on a same-tab fragment change,
validates every field again against the fetched local catalog, applies all requested
targets or none, and removes the fragment with `history.replaceState`. URL fragments
are never sent to the HTTP server. Opaque IDs remain sensitive and potentially
linkable; this navigation is not pair approval, registration, review, or a medical
conclusion.

## Share the current view with a local agent

In the unified workspace, choose **Agent state: off** to opt in. The button visibly
changes to **Agent state: on**. A bearer-authorized local agent can then read the
short-lived state:

```bash
curl --fail --silent \
  -H 'Authorization: Bearer <token printed by the launcher>' \
  http://127.0.0.1:8765/v1/viewer-state
```

Do not put the bearer token in shared scripts, shell history, screenshots, or logs.
The response conforms to `schemas/scanview-viewer-state-v1.schema.json`. It contains
opaque local series/instance IDs and stack positions, tool/link state, an optional
opaque MPR series ID, measurement count, and whether a comparison draft exists. It
never contains pixels, descriptions, dates, measurement values/geometry/labels,
paths, or direct patient identifiers. Every posted field is checked against the
local manifest. Turning sharing off clears and revokes that tab's ephemeral publisher;
closing the page also clears it, and missed cleanup still expires within 30 seconds.
This state is navigation context, not an imaging observation, pairing decision,
clinical review, or medical conclusion.

## Save and reopen a measurement draft

Choose **Length**, **Bidirectional**, or **Ellipse ROI**, draw a manual measurement, then choose
**Export measurement draft**. The local JSON file is sensitive derived medical
data. It contains opaque source references and DICOM patient-space geometry, but no
direct patient name/ID or source path. To reopen it, load the source DICOM folder,
select the matching series, and choose **Open measurement draft**. Matching overlays
and table rows are restored locally and remain `unreviewed`.

For agent-operated sessions, choose **Paste measurement JSON**, paste the same
versioned draft, and validate it in the browser. Input is capped at 2 MB and follows
the identical strict parser. The measurement table can delete a hydrated annotation
from memory; it never alters the imported packet on disk or the source DICOM.

After selecting an eligible, strictly chronological baseline/follow-up pair, enter a
working lesion label and explicitly choose one measurement from each source series. **Build numeric preview**
shows only the baseline value, follow-up value, arithmetic difference, and percentage
change. Exported comparison JSON remains `unreviewed` and has an empty
`candidate_interpretations` array.

`compare-measurements` requires explicit baseline and follow-up tracking IDs from
different source series. It refuses unknown physical units, mismatched tool types,
and geometry/result disagreements. Its output contains deltas, limitations, missing
clinical context, and questions—not a treatment-response category. An ellipse is a
2D area draft only; it is not tumor segmentation, volume, or a response verdict.
`validate-comparison` rechecks source linkage, metric completeness, units, arithmetic,
label bounds, review state, and the empty-interpretation invariant without printing
the label, source IDs, coordinates, or numeric values.

## Create a local comparison-review packet

Bind the exact visual visit packet to the exact numeric comparison before asking a
person to review it. In the unified viewer, build an explicit numeric preview from
one baseline and one follow-up measurement. ScanView moves both panes to the exact
source instances. **Save review packet** becomes available only while those exact
slices remain displayed; it captures the two key images and downloads the complete
validated archive through the same-origin loopback process. No source or intermediate
patient file is written by the server.

The equivalent standalone CLI workflow is:

```bash
.venv/bin/scanview-agent assemble-comparison-review \
  scanview-visit-packet.zip comparison.json --output review-initial.zip

.venv/bin/scanview-agent record-comparison-review review-initial.zip \
  --output review-requested-amendment.zip \
  --reviewer-name 'Reviewer name' --reviewer-role 'Clinical role' \
  --decision amendment_requested \
  --same-lesion uncertain --acquisition-suitability suitable \
  --measurement-placement revision_needed --response-criteria uncertain \
  --note 'Clarify the intended tumor component.' --attest

.venv/bin/scanview-agent amend-comparison-review \
  review-requested-amendment.zip amended-comparison.json \
  --output review-amended.zip \
  --actor-name 'Coordinator name' --actor-role 'Care coordinator' \
  --reason 'Applied the requested working-label clarification.' --attest

.venv/bin/scanview-agent validate-comparison-review review-amended.zip
```

Every output is a new owner-only ZIP; an existing output is never overwritten. Keep
ancestor archives so `parent_archive_sha256` can be checked. The archive recursively
validates the visit packet and comparison, requires each selected tracking ID/value
to join the visible key-image measurement exactly, embeds both images, and provides a
script-free printable `review.html`. Events are hash chained and amendments reset the
state to `unreviewed`.

Names, roles, organizations, checklist choices, and notes are person-entered and
self-attested. ScanView does not authenticate credentials or create a digital
signature. Even `accepted_for_discussion` is not a diagnosis, treatment recommendation,
medical-record sign-off, or automated response category; the embedded arithmetic
comparison remains `unreviewed`. Privacy-minimized validation does not echo reviewer
identity, notes, lesion labels, identifiers, or numeric values.

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

In the unified local workspace, choose a dated matching-opaque-context MR↔MR or CT↔CT pair,
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
