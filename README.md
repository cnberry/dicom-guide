# ScanView

ScanView is a local-first, cross-platform DICOM workspace for reviewing MRI and
CT studies over time. It is being built for two audiences at once:

- people who need to see, compare, measure, and discuss scans with clinicians;
- software agents that need a structured, source-traceable, read-only interface.

The current MVP reads copied DICOM files locally, groups them into studies and
series, renders native pixels with Cornerstone3D, and presents two series side by
side. It suggests pair compatibility with visible reasons but never approves a
pair or issues a medical conclusion.

All DICOM processing is local by design. ScanView has no cloud-processing fallback:
if a required local decoder, registration engine, or runtime dependency is missing,
the operation fails closed without uploading images or metadata. The only runtime
HTTP traffic is authenticated loopback communication between the local viewer and
the local ScanView process.

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
- Source-bound manual ROI volume evidence drafts: paint or erase one binary region on
  a strictly regular native MR/CT grid, export a DICOM SEG-format mask plus a versioned
  JSON sidecar, and independently rehash the supplied sources and recompute voxel count
  and volume locally. Every result remains computed, unreviewed, with boundary
  uncertainty not quantified and all longitudinal/diagnostic conclusions locked.
- Separate manual-boundary review archives: a self-attested qualified clinician or
  medical physicist can record represented tissue, inclusion/exclusion criteria,
  acquisition suitability, and a complete three-plane checklist while the mask is
  visible. The four-file archive embeds the exact DICOM SEG evidence and a printable
  page; independent validation reopens both the nested evidence and original source
  bytes. Acceptance means discussion-only and still cannot link scans or compute response.
- Reviewed manual ROI volume comparisons: two separately accepted boundary-review
  archives can be joined only after an explicit qualified pairing review confirms the
  same lesion, same represented tissue, DICOM chronology, acquisition/boundary
  comparability, and registration need. The five-file archive recursively revalidates
  both DICOM SEG objects and every original source byte before exposing transparent
  volume arithmetic. It never classifies response, attributes change to treatment,
  localizes voxelwise change, diagnoses, or signs a medical record.
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
- Automatic **Consult preparation workspace** when the loaded catalog has no valid
  dated same-modality longitudinal source pair. It uses neutral Image A/Image B roles,
  disables approximate linking and lesion-pair arithmetic, and never presents MRI+CT
  as a response pair. Live viewer-state v1 is disabled in this mode because it uses
  timepoint field names; agents use the neutral consultation packet instead.
- One-click and CLI local consultation packets for exactly one MRI plus one CT from
  distinct studies with one matching opaque patient context. Exact catalog positions
  and stable DICOM bytes are reverified and hashed; the static packet contains no
  comparison, registration, computed result, interpretation, diagnosis, or response
  conclusion.
- A source-bound consultation board can collect 2–8 explicitly labeled native MRI/CT
  reference views for a clinical conversation. Labels are person-entered discussion
  headings, not findings; every source is reverified locally and the board makes no
  chronology, alignment, lesion, diagnosis, comparison, or response claim.
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
- Version-gated local 3D Slicer/BRAINSFit/BRAINSResample rigid-registration jobs for explicitly
  attested, matching opaque patient-context, same-modality chronological series.
  Patient identity remains unverified. Outputs are source-hashed, published without
  replacement, and locked pending human QA; CT/MR registration and subtraction are
  prohibited.
- Isolated browser-capability human registration QA with fixed/moving reference,
  registered side-by-side, and technical sampling-support boundary views,
  axial/coronal/sagittal traversal, opacity, swipe, checkerboard, edge comparison,
  qualitative landmarks, physical-point residual tools, and a separate hash-linked
  self-attested accept/reject JSON record. Acceptance requires quantitative 3-D
  residual evidence. The bearer agent interface cannot fetch QA pixels or approve it;
  this is a capability boundary, not proof a person is present.
- Live-bundle-validated accepted reviews can open a separate exploratory comparison
  surface with only opacity and swipe. Both inputs are visibly derived, registered
  moving is resampled, and a hash-verified binary mask suppresses registered-moving
  pixels without transformed moving-image sampling support. The mask is technical
  support evidence—not anatomy, tumor, segmentation, registration quality, or a
  clinical conclusion—and native DICOM remains authoritative.
- Python catalog with SHA-256 source provenance and opaque logical IDs.
- Bearer-token-protected, loopback-only, source-read-only local API.
- Versioned measurement, key-image, manual ROI volume, manual ROI review, manual ROI
  volume-comparison review, consultation-key-image, consultation-packet, comparison, visit-packet, review-record,
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

To create an installable wheel with the UI and contracts embedded, without modifying
the source tree:

```bash
pnpm build
.venv/bin/python scripts/build_release.py --output-dir release
```

The release builder stages the viewer, workers, codecs, and all versioned JSON Schemas
inside the wheel. A regular agent-only wheel remains lightweight and can still run `manifest`,
`candidates`, and `serve`; pass `--ui-dist` to `launch` when using that form.

For a transferable macOS/Linux package whose installation and runtime require no
package index or external DICOM-processing API:

```bash
pnpm build
.venv/bin/python scripts/build_offline_bundle.py --output-dir release
unzip release/scanview-offline-0.4.0.zip
cd scanview-offline-0.4.0
python3 verify.py
PIP_NO_INDEX=1 sh install.sh
sh launch.sh '/absolute/path/to/copied/DICOM'
```

The offline builder packages the embedded-asset ScanView wheel plus pinned pure-Python
`pydicom` 3.0.2, a hash-locked requirements file, a standard-library verifier, and
local install/launch checks. The installer uses `--no-index` and `--require-hashes`;
every launch rechecks the extracted payload, installed versions, UI, schemas, and
consultation contract before indexing DICOM. Python 3.11+ remains a prerequisite.
Building the bundle may download the pinned dependency unless `--pydicom-wheel` is
supplied, but installation, viewing, indexing, comparison, and evidence generation
are offline. The integrity manifest is corruption evidence, not publisher signing or
clinical authentication. Output is non-overwriting.

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
.venv/bin/scanview-agent validate-lesion-volume \
  '/path/to/scanview-lesion-volume.zip' '/path/to/copied/DICOM'
.venv/bin/scanview-agent validate-lesion-volume-review \
  '/path/to/scanview-lesion-volume-review.zip' '/path/to/copied/DICOM'
.venv/bin/scanview-agent assemble-lesion-volume-comparison \
  baseline-boundary-review.zip followup-boundary-review.zip pairing-request.json \
  '/path/to/copied/DICOM' --output reviewed-volume-comparison.zip
.venv/bin/scanview-agent validate-lesion-volume-comparison \
  reviewed-volume-comparison.zip '/path/to/copied/DICOM'
.venv/bin/scanview-agent assemble-visit-packet baseline-key-image.zip followup-key-image.zip \
  --output scanview-visit-packet.zip
.venv/bin/scanview-agent validate-visit-packet scanview-visit-packet.zip
.venv/bin/scanview-agent assemble-consultation-packet '/path/to/copied/DICOM' \
  view-a-key-image.zip view-b-key-image.zip --output scanview-consultation-packet.zip
.venv/bin/scanview-agent validate-consultation-packet scanview-consultation-packet.zip
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
.venv/bin/scanview-agent import-registration-review '/safe/local/registration-job' \
  ~/Downloads/scanview-registration-review.json \
  --output '/safe/local/registration-review.json'
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
- `GET /v1/reviewed-registration/display` (accepted-review browser session only)
- `GET /v1/reviewed-registration/files/{fixed.nrrd|registered-moving.nrrd|registered-moving-coverage.nrrd}`
  (accepted-review browser session only)
- `GET /v1/instances/{opaque_id}`
- `POST /v1/viewer-state` (same-origin browser publication/clear; memory only)
- `POST /v1/visit-packets` (same-origin browser session; in-memory derivative only)
- `POST /v1/consultation-packets` (same-origin browser session; in-memory derivative only)
- `POST /v1/comparison-reviews` (same-origin browser session; in-memory derivative only)
- `POST /v1/lesion-volume-comparisons` (same-origin browser session; recursive source
  validation; in-memory derivative only)
- `POST /v1/registration-reviews` (same-origin human browser; one in-memory JSON response)

All endpoints except health require authentication. The unified browser uses a
same-origin HttpOnly session cookie instead of exposing the printed bearer token to
application JavaScript. QA preview pixels and review submission specifically require
that browser session; a bearer-authorized agent can read only the minimized QA status.
All POSTs additionally require the exact local origin and bounded route-specific
content. The viewer-state route accepts at most 16 KiB of strict JSON and keeps only
the latest 30-second publication in memory. Visit-packet
input contains only the two timepoint key-image archives. Consultation input contains
only two neutral MR/CT key-image archives. Comparison-review input
contains those same two archives plus the current normalized comparison JSON; the
server builds the nested visit packet and review archive entirely in memory. Lesion-
volume-comparison input contains only two complete boundary-review ZIPs and one
strict pairing request; the server joins them to the current source catalog and
recursively revalidates their nested DICOM SEG and original DICOM bytes in memory.
Every route returns `no-store` and creates no server-side file. There is no source mutation
or deletion endpoint.
The server refuses non-loopback bind addresses. This loopback interface is part of
the offline local application, not an external processing API.

## Generate a rigid registration pending QA

ScanView can run one rigid moving-later-to-fixed-earlier job through a locally
installed 3D Slicer 5.12.3 computed revision 34627 (runtime repository revision
`9034c71`) and its bundled BRAINSFit and BRAINSResample modules. Earlier
and later are registration roles; neither establishes a clinical treatment baseline
or nadir. ScanView never downloads an engine, sends DICOM to an API, or falls back to
a cloud service. Check the host first:

```bash
.venv/bin/scanview-agent registration-doctor
```

On Linux the doctor also requires `bwrap`, `xvfb-run`, and Xauthority support in
addition to Slicer's documented Ubuntu runtime libraries. ScanView creates its own
private no-TCP display; an existing `DISPLAY` does not satisfy or bypass that gate.

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
It writes an owner-only seven-file v2 directory: fixed, moving, and registered-moving
NRRD volumes; a binary registered-moving sampling-support NRRD in fixed geometry; one
text ITK rigid transform in DICOM patient LPS coordinates; the engine report; and
`registration.json`. Existing outputs and source files are never overwritten.
Slicer settings, the user startup script, and user-site Python packages are disabled
for the job so local customizations cannot silently change the version-gated workflow.
The process also runs inside a required OS network boundary: macOS uses a deny-all-
network sandbox, while supported 64-bit Linux requires `bwrap` private namespaces plus
a seccomp filter that permits only local `AF_UNIX` IPC and rejects network socket
domains and io_uring. Linux Slicer receives a private Xvfb display with TCP listening
disabled; inherited displays, weaker `unshare`-only execution, and unsandboxed fallback
are refused.

The expected SHA-256 must match before any DICOM is staged and is checked again after
execution. A no-data preflight first verifies the self-reported Slicer version,
runtime repository revision, and both BRAINSFit and BRAINSResample availability.
`registration-doctor` can
show the observed launcher hash, but ScanView does not authenticate the distributor
or code signature; obtain and record the expected digest through a trusted
software-installation process. Platform-specific package and installed-copy evidence,
including the Linux checksum-versus-signature limitation, is recorded in
[`docs/SLICER-ENGINE-TRUST.md`](docs/SLICER-ENGINE-TRUST.md). ScanView strips proxy,
credential, extension-server, and Python-path variables; the OS sandbox prevents the
registration process from reaching external or host network services.

Every generated bundle is `generated_pending_qa` and `unreviewed`; the registration
directory itself is never mutated by review. Validate integrity locally with
`validate-registration`. Validation parses the scalar NRRDs, requires registered and
coverage-mask geometry to match the fixed volume, decodes every mask voxel as uint8
`0` or `1`, rejects empty support, recomputes support counts, verifies a finite proper
rigid transform, checks all hashes and owner-only permissions, and still does not
establish registration quality.

For one valid pending bundle, open the isolated local human QA workspace:

```bash
.venv/bin/scanview-agent review-registration '/safe/local/registration-job'
```

It visibly watermarks the resampled preview, keeps fixed and moving derived reference
volumes available alongside registered moving,
requires full traversal in all three patient-space planes and four comparison modes,
explicit review of the technical support boundary and excluded region, and can
download one separate self-attested JSON decision. A qualified self-attested
acceptance can authorize only exploratory shared-coverage overlay and swipe; it
requires quantitative 3-D landmark error within the fixed geometry-derived tolerance.
Subtraction, mask propagation, segmentation, measurements on the resampled image, and
response conclusions remain locked. Reviewer identity and training are not
authenticated, and event hashes are not digital signatures. A browser download is not
accepted directly because its Unix permissions are outside browser control. Run
`import-registration-review` with the live bundle to validate the exact record and
create one non-overwriting owner-only copy, then use `validate-registration-review`
with the live bundle to recheck the full seven-file source anchor.

After saving a valid accepted review, launch the ordinary local workspace with both
exact inputs to enable the strictly limited exploratory comparison:

```bash
.venv/bin/scanview-agent launch '/safe/local/DICOM/root' \
  --registration-bundle '/safe/local/registration-job' \
  --registration-review '/safe/local/registration-review.json'
```

The server revalidates the saved owner-only review against the live seven-file v2 bundle at
startup and checks the review, bundle directory, and all seven evidence-file identities
and metadata again before every context or pixel access. Rejected,
tampered, linked, mismatched, or missing inputs leave ordinary DICOM available but all
registered pixels locked. The accepted surface implements only opacity and swipe;
subtraction, lesion-mask propagation, segmentation, measurements, exports, and response
conclusions are absent. Before any reviewed pixels render, the browser independently
hashes and validates fixed, registered-moving, and the binary support mask; it then
uses nearest-neighbor mask sampling and shows fixed pixels wherever support is zero.
Shared anatomy and registration acceptability remain reviewer judgments. Legacy
six-file v1 bundles and reviews fail closed and must be regenerated and reviewed under
v2 before this display can open.

The currently copied CD contains one MRI exam and one CT exam, so it cannot produce a
valid registration pair. The authenticated local Slicer installation has completed a
real-engine synthetic MR registration, but a future same-modality follow-up and
qualified case-specific review are still required for a Mila-specific run.

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

The MPR workspace can also hold one person-painted binary region on the native source
grid. Paint/erase and export remain disabled unless every source object is single-frame
and agrees on matrix, pixel spacing, orientation, regular projected slice spacing, and
absence of in-plane drift. The live voxel count × source-grid voxel volume is labeled
**computed, unreviewed; boundary uncertainty not quantified**.

Choose **Export DICOM SEG evidence** to download exactly `segmentation.dcm`,
`evidence.json`, and `README.txt`. The DICOM object uses generic abnormal-structure/
lesion coding for interoperability; it does not assert tumor, neoplasm, histology, or
tissue type. Validate the bundle against the exact local source directory:

```bash
.venv/bin/scanview-agent validate-lesion-volume \
  '/safe/local/scanview-lesion-volume.zip' '/safe/local/DICOM/root'
```

`valid: true` means only that ScanView matched source bytes, checked its narrow v1
DICOM SEG-format profile and native geometry, and recomputed the mask hash, voxel
count, and arithmetic volume. V1 has no acceptance or clinical-approval mechanism and
cannot link lesions, compute longitudinal change, classify response, diagnose, or
produce a clinical conclusion. The ZIP remains sensitive and patient-identifiable.

While the painted mask is visible in MPR, open **Qualified boundary review record**.
This form is only for a clinician or medical physicist who has inspected the complete
boundary on the original source images. It records the represented tissue,
inclusion/exclusion criteria, acquisition suitability, all-three-plane and artifact
checks, a decision, and the fixed self-attestation. **Accepted for discussion** requires
every checklist item, suitable acquisition, and a locally derived opaque patient
context. Reviewer identity and credentials remain self-asserted and unverified.

The downloaded review archive contains exactly `review.json`, `evidence.zip`,
`review.html`, and `README.txt`. Validate it independently against the exact source:

```bash
.venv/bin/scanview-agent validate-lesion-volume-review \
  '/safe/local/scanview-lesion-volume-review.zip' '/safe/local/DICOM/root'
```

Validation reopens the nested DICOM SEG evidence, rehashes every source object, checks
the review/page/file bindings, and withholds the volume if anything changed. Even an
accepted record authorizes only one-timepoint boundary and volume discussion; lesion
linkage, longitudinal change, percentage change, response classification, diagnosis,
and clinical conclusions remain false until the separate pairing review below—and
response/diagnostic conclusions remain false even after that review.

## Pair two accepted manual ROI boundaries

This path is available only for two same-modality scans from the same opaque patient
context and different studies/series, with exact DICOM dates establishing baseline
before follow-up. Load both accepted boundary-review ZIPs in the unified viewer while
their exact source series are visible. A qualified reviewer must explicitly record:

- same-lesion and same-represented-tissue judgments;
- acquisition and boundary comparability;
- chronology and whether spatial registration is separately needed;
- all eight source/boundary/pairing checklist items and the fixed self-attestation.

The server—not the browser preview—is authoritative. It derives dates from the live
catalog, checks that every instance in each series has one consistent date, recursively
validates both four-file boundary reviews and their nested DICOM SEG evidence, and
rehashes every source object. The returned archive contains exactly
`comparison.json`, `baseline-review.zip`, `followup-review.zip`, `review.html`, and
`README.txt`. It is created in memory and downloaded without a patient file being
persisted by the server.

The equivalent non-overwriting CLI workflow is:

```bash
scanview-agent assemble-lesion-volume-comparison \
  baseline-boundary-review.zip followup-boundary-review.zip pairing-request.json \
  '/safe/local/DICOM/root' --output reviewed-volume-comparison.zip
scanview-agent validate-lesion-volume-comparison \
  reviewed-volume-comparison.zip '/safe/local/DICOM/root'
```

Only an `accepted_for_volume_change_discussion` decision with every required gate can
expose baseline volume, follow-up volume, absolute change, percentage change, numeric
direction, and elapsed days. Revision, rejection, malformed input, or any source-byte
change returns no numeric values and `evidence_use: none`. Even a valid accepted record
does not authorize spatial overlay, voxelwise localization, biological tumor-burden
interpretation, progression/response classification, treatment causality, diagnosis,
clinical conclusion, or medical-record sign-off. Boundary uncertainty remains
unquantified and reviewer identity/credentials remain self-asserted and unverified.

## Prepare a neutral MRI/CT consultation packet

The current copied media contains one MRI exam and one CT exam, not a valid
longitudinal response pair. ScanView therefore opens **Consult preparation workspace**
and labels the panes **Image A** and **Image B**. Choose one MRI series and one CT
series from the distinct studies, place the desired native source image in each pane,
and choose **Save consultation packet**. Approximate slice linking and cross-view
lesion measurement pairing remain unavailable; dates label source exams only.

The unified viewer creates neutral, source-scoped key images in memory and sends them
only to the exact-origin loopback assembler. The endpoint rechecks the matching
opaque patient context, distinct studies, modalities, exact catalog membership,
instance order/count, metadata, source size, and SHA-256 read from the stable guarded
DICOM descriptors. It returns the validated ZIP with `no-store` and writes no source,
intermediate, or output patient file.

The equivalent non-overwriting local CLI workflow is:

```bash
.venv/bin/scanview-agent assemble-consultation-packet \
  '/Users/chris/Desktop/Mila Scan CD' \
  view-a-key-image.zip view-b-key-image.zip \
  --output scanview-consultation-packet.zip
.venv/bin/scanview-agent validate-consultation-packet \
  scanview-consultation-packet.zip
```

The nine-file packet includes both neutral key images and measurements, a strict
agent JSON record, instructions, and a script-free printable `review.html`. Source
byte counts and SHA-256 anchors are visible in the deterministic page. The packet
permanently states that the views are unregistered, unaligned, unreviewed, not a
comparison, not for diagnosis, and not a response conclusion; computed results and
candidate interpretations are fixed empty. Treat it as sensitive question-preparation
evidence and confirm both source images in the clinician's imaging system.

### Build a multi-view consultation board

In **Consult preparation workspace**, enter a short discussion heading and add the
current Image A or Image B. Repeat for 2–8 distinct native source instances. A valid
board must contain at least one MRI view, at least one CT view, and views from at least
two studies. Choose **Save discussion board** when those gates are visible as ready.
The captured key-image ZIPs remain in browser memory until export or clearing.

The same workflow is available entirely locally from the CLI:

```bash
.venv/bin/scanview-agent assemble-consultation-board \
  '/Users/chris/Desktop/Mila Scan CD' \
  --item 'MRI overview' mr-overview-key-image.zip \
  --item 'CT overview' ct-overview-key-image.zip \
  --item 'MRI detail for discussion' mr-detail-key-image.zip \
  --output scanview-consultation-board.zip
.venv/bin/scanview-agent validate-consultation-board \
  scanview-consultation-board.zip
```

The assembler revalidates every nested neutral key image and exact live DICOM source.
The headings are unreviewed person-entered organizational text, not clinical findings.
The script-free board is a discussion aid only: item order supplies no chronology,
and the artifact supplies no registration, alignment, lesion linkage, diagnosis,
comparison, response assessment, or medical conclusion.
Browser download permissions are host-controlled and may be broader than owner-only;
move the sensitive ZIP into an appropriately protected local folder before retaining
or sharing it. CLI-created boards are written non-overwriting with owner-only mode.

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
