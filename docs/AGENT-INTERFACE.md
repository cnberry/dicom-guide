# Agent interface

ScanView gives local agents a read-only, versioned contract so they do not need to
scrape filenames or guess at DICOM series descriptions. This interface never calls
an external API and never grants source mutation.

## Offline agent distribution

`scripts/build_offline_bundle.py` produces one deterministic, non-overwriting
`scanview-offline-0.4.0.zip` for Python 3.11+ hosts on macOS and Linux. It contains
the UI-embedded ScanView wheel, pinned pure-Python `pydicom` 3.0.2, an exact payload
manifest, hash-locked requirements, and verifier/install/launch entry points. After
extraction, an agent or person can run:

```bash
python3 verify.py
PIP_NO_INDEX=1 sh install.sh
sh launch.sh '/safe/local/DICOM/root' --no-open
```

Installation invokes pip with `--no-index --require-hashes`; every launch rechecks
the bundle and installed versions, UI, schemas, and consultation contract before any
DICOM catalog is built. The launched agent interface is the same loopback bearer-
authorized API documented below. Build-time dependency retrieval is separate from
runtime DICOM processing and contains no patient data. The unsigned hash manifest is
corruption evidence only, not publisher or clinical identity authentication. The
exact v0.4.0 artifact has passed no-index install, runtime, synthetic source-bound SEG,
qualified boundary-review, and reviewed volume-comparison validation, source-tamper
refusal, and loopback launch
on macOS arm64 and Strawberry Linux x86_64; signing/notarization remains pending.

## Local artifacts

`scanview-agent manifest` creates a sensitive JSON catalog containing:

- opaque study, series, frame-of-reference, and instance IDs;
- an opaque patient-context digest used only to prevent cross-patient pairing;
- modality, acquisition date, sequence/protocol descriptors, and image type;
- dimensions, spacing, orientation, slice position, and stack order;
- MR sequence parameters and contrast metadata where present;
- source byte counts and SHA-256 hashes;
- explicit privacy, provenance, limitations, missing context, and review state.

Direct patient-name/ID tags and absolute paths are omitted. The output is still
medical data and explicitly says `deidentified: false`. Catalogs are atomically
written with owner-only permissions and must remain outside Git.

The patient-context digest is derived locally from available patient identity tags;
those raw values are not emitted. The digest remains sensitive and potentially
linkable: it is a pairing safety boundary, not proof of de-identification. If reliable
identity context is unavailable, the fallback is study-scoped so different exams
cannot be joined automatically.

`scanview-agent candidates` creates metadata-based pairing suggestions. It:

- considers only multi-instance MR↔MR or CT↔CT stacks from different exams;
- requires one matching opaque patient context and excludes missing/mismatched ones;
- excludes PR/SR, localizers/scouts, and very short series;
- checks sequence terms, contrast, body part, matrix, orientation, TR/TE/TI/flip,
  and frame-of-reference metadata;
- returns score, reasons, warnings, locked derived operations, and `unreviewed`;
- never sets `auto_approved` to true.

Zero candidates is valid and safer than cross-modality or object-type guessing.

## Measurement evidence packets

The viewer exports manual length, perpendicular bidirectional, and elliptical ROI
drafts. New exports conform to `schemas/scanview-measurements-v3.schema.json`; the
importer and validator continue to accept length-only v1 and length/bidirectional v2
packets. Each accepted record contains:

- a stable tracking ID and `unreviewed` state;
- opaque source series, instance, and optional frame-of-reference IDs;
- two length or four bidirectional/ellipse DICOM patient LPS world points;
- a length, long/short axes and bidimensional product, or ellipse major/minor axes and
  area only when pixel spacing is trustworthy;
- the exact manual tool implementation and explicit limitations.

Annotations without valid geometry or source mapping are excluded rather than
exported as evidence. Imported numeric results must agree with the patient-space
geometry. Agents can validate and summarize a packet without printing its
identifiers, coordinates, or values:

```bash
scanview-agent validate-measurements '/safe/local/scanview-measurements.json'
```

The viewer can reopen a validated packet after the source folder is loaded. It
restores overlays only on a selected series/instance whose opaque IDs match. Loading
a new DICOM folder clears the annotation state, pixel cache, and file registry so
measurements cannot silently carry across imaging sessions.

Service-backed measurement packets use the catalog's `series_*`, `instance_*`, and
`frame_*` opaque IDs directly, so agents can join evidence to manifest records
without filenames or DICOM UIDs. Validators also accept the earlier 16-hex local
folder IDs for backward compatibility.

## Key-image evidence archives

Each viewport can save a source-traceable local ZIP with exactly three members.
New exports use key-image schema v2; the validator retains v1 compatibility, but
v1 lacks patient/study context and cannot enter a longitudinal visit packet:

- `key-image.png`: the displayed native slice plus visible annotation overlay,
  orientation labels, and a permanent unreviewed/derived/not-for-diagnosis footer;
- `key-image.json`: exact opaque patient/study/series/instance/frame references,
  modality/date, stack location, display role, patient orientation, viewport
  dimensions, window, invert, zoom, pan, implementation versions, limitations, and
  integrity digests;
- `measurements.json`: a v3 packet containing only measurements on that displayed
  source series and instance.

The image and measurement JSON are SHA-256 cross-linked from `key-image.json`.
Agents validate archive composition, size limits, PNG chunks/CRC/dimensions, both
digests, the embedded measurement schema, tracking IDs, and exact source linkage:

```bash
scanview-agent validate-key-image '/safe/local/scanview-key-image.zip'
```

The validator returns only versions, review/artifact state, measurement count,
integrity booleans, and errors; it does not print source identifiers or values. A
valid archive remains sensitive, `unreviewed`, and a display derivative. The native
DICOM is authoritative, and validation is not clinical approval.

The human viewer's rendered MPR planes remain local navigation-only derivatives and
are not part of the key-image contract. The separate manual ROI volume contract below
stores its binary labelmap on the native source grid and binds every source instance;
it does not export an MPR screenshot as evidence. The live MPR panel exposes its
current LPS patient coordinate in accessible UI text so an agent can help a person
navigate, but that transient point is not saved, compared, or promoted to an
observation.

## Source-bound manual ROI volume evidence

ScanView v1 lets a person paint one binary region on one strictly regular native MR
or CT source grid. The browser exports exactly `evidence.json`, `segmentation.dcm`,
and `README.txt`. The sidecar conforms to
`schemas/scanview-lesion-volume-evidence-v1.schema.json`; the DICOM object uses the
Segmentation Storage SOP class, uncompressed Explicit VR Little Endian, one `MANUAL`
segment, and generic abnormal-structure/lesion coding. Those codes are interoperability
labels, not a diagnosis, neoplasm claim, histology, or tumor-component classification.

Validate the draft only against the supplied exact local source directory:

```bash
scanview-agent validate-lesion-volume \
  '/safe/local/scanview-lesion-volume.zip' '/safe/local/DICOM/root'
```

The validator is independent of the browser. It reads the source objects without
following final symlinks, hashes stable file descriptors, requires one study/series/
Frame of Reference and a consistent single-frame native matrix, checks strict
orientation, spacing, positions, gaps, and in-plane drift, resolves all DICOM SEG
source references, decodes the bit-packed binary frames, rebuilds the dense native
mask, and recomputes its hash, foreground count, and voxel-count volume. It rejects
duplicate JSON fields, extra ZIP members, changed/missing sources, reference mismatch,
non-binary or empty masks, and sidecar arithmetic changes.

`valid: true` and `source_validated_pending_review` mean only that these source,
format, geometry, mask, and arithmetic checks passed. They do not validate the painted
boundary, acquisition suitability, represented tissue, lesion identity, clinical
interpretation, or DICOM conformance outside the ScanView v1 profile. V1 has no
acceptance or clinical-approval transition. Its fixed states and locks are:

- `draft_unreviewed`, `unreviewed`, `computed_unreviewed`, and
  `boundary_uncertainty: not_quantified`;
- local source/mask display and a single-source-series computed ROI volume only;
- no longitudinal link, percentage change, response classification, diagnosis, or
  clinical conclusion.

Each export receives a new Tracking UID; matching labels or codes do not establish
that two exports represent the same lesion. Invalid evidence returns no computed
volume and `evidence_use: none`. The ZIP remains sensitive and patient-identifiable
because its DICOM object and pixels retain clinical context even though the JSON uses
opaque IDs.

## Manual ROI boundary-review archives

The browser can wrap the current freshly rehashed manual ROI evidence in a separate
four-member archive: `review.json`, nested `evidence.zip`, script-free `review.html`,
and `README.txt`. The human form records one self-attested qualified role, represented
tissue, inclusion/exclusion criteria, acquisition suitability, a decision, and eight
complete-boundary checks while the source overlay is visible. Reviewer identity and
credentials are explicitly `self_asserted_unverified`.

Agents validate the outer record, nested DICOM SEG evidence, and live source together:

```bash
scanview-agent validate-lesion-volume-review \
  '/safe/local/scanview-lesion-volume-review.zip' '/safe/local/DICOM/root'
```

The independent validator enforces exact archive shape, strict JSON, bounded text,
file hashes, a script/external-resource/event-handler-free static page, exact
source-snapshot equality, and the complete nested source/geometry/mask/arithmetic
validation. `accepted_for_discussion` additionally requires suitable acquisition,
all checklist values, and a non-missing opaque patient context. It permits only
`reviewed_volume_for_discussion` and eligibility as input to the separate pairing
review. It never grants longitudinal linkage, percentage change, response
classification, diagnosis, clinical conclusion, identity authentication, or
medical-record sign-off. Invalid evidence returns no volume and `evidence_use: none`.

The privacy-minimized summary omits reviewer name, organization, tissue definition,
criteria, notes, source IDs, and hashes. The full ZIP remains sensitive and
patient-identifiable and must stay local.

## Reviewed manual ROI volume-comparison archives

This is a second review boundary, not an automatic operation on two accepted masks.
It consumes exactly two independently accepted boundary-review ZIPs plus one strict
`scanview.lesion-volume-comparison-request` record. The exact local root containing
both source series is mandatory:

```bash
scanview-agent assemble-lesion-volume-comparison \
  baseline-boundary-review.zip followup-boundary-review.zip pairing-request.json \
  '/safe/local/DICOM/root' --output reviewed-volume-comparison.zip
scanview-agent validate-lesion-volume-comparison \
  reviewed-volume-comparison.zip '/safe/local/DICOM/root'
```

Both reviews must share one opaque patient context and modality but have distinct
studies, series, evidence IDs, and review IDs. ScanView builds a fresh live catalog,
requires every instance in each reviewed series to share one DICOM date, and requires
baseline before follow-up. Person-entered dates are not request fields. The reviewer
records same-lesion identity, same represented tissue, chronology,
acquisition/boundary comparability, registration consideration, eight explicit review
checks, a decision, and the fixed attestation. Reviewer name, role, and organization
are self-asserted and not authenticated. Accepted review requires confirmed identity,
tissue, and chronology; suitable or suitable-with-limitations comparability; every
check; and a note whenever comparability or registration uncertainty exists.

The output conforms to
`schemas/scanview-lesion-volume-comparison-review-v1.schema.json` and has exactly:

- `comparison.json`;
- `baseline-review.zip` and `followup-review.zip`;
- regenerated script-free `review.html`;
- `README.txt`.

Validation requires exact member shape, strict duplicate-key-free JSON, schema and
cross-field semantics, hash/size anchors, exact regenerated page bytes, both complete
nested review/evidence archives, and every original source byte. The minimized summary
reveals reviewed baseline/follow-up volumes, arithmetic absolute and percentage change,
numeric direction, and elapsed days only for a valid
`accepted_for_volume_change_discussion` record. It omits IDs, hashes, tissue definitions,
reviewer fields, and notes. Any revision, rejection, malformed record, or source change
sets every numeric field to null and `evidence_use: none`.

This contract performs transparent volume arithmetic only. It never authorizes a
spatial overlay, voxelwise localization, biological tumor-burden interpretation,
progression/response classification, treatment causality, diagnosis, clinical
conclusion, or medical-record sign-off. The manual-boundary uncertainty remains
unquantified.

## Clinician consultation-packet archives

When the local catalog has no qualified longitudinal pair, agents and people can
prepare one neutral MRI view and one neutral CT view for source-grounded clinician
discussion. The browser uses consultation key-image v1 sidecars with `view_a` and
`view_b` selection slots—never baseline/follow-up roles—and a permanent neutral
footer. The exact standalone workflow is:

```bash
scanview-agent assemble-consultation-packet '/safe/local/DICOM/root' \
  view-a-key-image.zip view-b-key-image.zip \
  --output scanview-consultation-packet.zip
scanview-agent validate-consultation-packet scanview-consultation-packet.zip
```

Assembly requires exactly one MR plus one CT from distinct source studies and one
matching opaque patient context. It independently joins study/series/instance
metadata and stack position/count to the live hashed catalog, opens the guarded
source without following a final symlink, and rehashes the stable DICOM descriptor.
Hashless catalogs, browser-folder sidecars, metadata/position disagreement, changed
sources, same-study, same-modality, cross-patient, malformed, duplicate, encrypted,
oversized, or extra archive content fail closed.

The output contains exactly nine files: `consultation-packet.json`, `review.html`,
`README.txt`, and the neutral three-file evidence bundle under each of `view-a/` and
`view-b/`. The agent record includes source anchors, fixed limitations/missing context/
clinician questions, and mandatory empty `computed_results` and
`candidate_interpretations`. The deterministic script-free review page binds both
source byte counts and SHA-256 digests and visibly states that dates are source labels
only; the views are unregistered, not aligned, not a comparison, not diagnostic, and
not a response conclusion. Validation summaries omit source IDs, hashes, dates,
descriptions, and measurement values.

The unified viewer sends the two neutral in-memory key-image ZIPs to the exact-origin
loopback endpoint and receives the validated packet with `no-store`; the server writes
no patient file. A valid packet is still sensitive, unreviewed derived evidence and
must be checked against the clinical imaging system by a clinician. Live viewer-state
publication is deliberately unavailable in Consult Prep because viewer-state v1 uses
baseline/follow-up fields; an agent must not infer timepoint roles from the internal
pane implementation.

## Clinician consultation-board archives

A consultation board groups 2–8 explicitly selected neutral consultation key images
for a source-grounded discussion. It is assembled locally from repeated label/archive
pairs:

```bash
scanview-agent assemble-consultation-board '/safe/local/DICOM/root' \
  --item 'MRI overview' mr-overview.zip \
  --item 'CT overview' ct-overview.zip \
  --item 'MRI detail for discussion' mr-detail.zip \
  --output scanview-consultation-board.zip
scanview-agent validate-consultation-board scanview-consultation-board.zip
```

Every input must be a complete neutral consultation key-image archive. Assembly
requires one matching opaque patient context, at least one MR and one CT, at least two
distinct studies, and a distinct source instance for every item. Each catalog
study/series/instance position and guarded source descriptor is resolved and rehashed
again. Labels are trimmed, bounded person-entered discussion headings; they are not
observations or findings.

The outer browser transport contains only `board-input.json` and ordered
`item-01.zip` through `item-08.zip` members. The authenticated exact-origin
`POST /v1/consultation-boards` endpoint accepts that strict bounded ZIP, assembles and
revalidates the board in memory, returns `application/zip` with `no-store`, and writes
no patient artifact. Standalone CLI output is non-overwriting and owner-only.

The v1 board record conforms to
`schemas/scanview-clinician-consultation-board-v1.schema.json` and is accompanied by
a script-free `review.html`, instructions, and one exact three-file evidence directory
per item. Its observation order is for
presentation only. `computed_results` and `candidate_interpretations` are fixed empty;
chronology, alignment, registration, lesion identity, diagnosis, comparison, treatment
response, and clinical review are explicitly not established. The privacy-minimized
validator summary omits labels, source IDs, dates, hashes, paths, and pixels.

## Clinician visit-packet archives

Agents can assemble two explicitly ordered key-image archives into one local
communication packet:

```bash
scanview-agent assemble-visit-packet baseline-key-image.zip followup-key-image.zip \
  --output scanview-visit-packet.zip
scanview-agent validate-visit-packet scanview-visit-packet.zip
```

Assembly first validates both complete v2 key-image bundles, then requires one
matching opaque patient context, distinct source studies and series, MR↔MR or CT↔CT,
valid acquisition dates with baseline before follow-up, and matching viewport roles.
It refuses unsafe input instead of producing a partial packet.

The unified viewer invokes this exact assembler from **Save visit packet**. It wraps
the two current in-memory key-image archives as `baseline.zip` and `followup.zip`
inside a bounded transport ZIP and sends it only to its same-origin loopback process.
The response is the validated archive; no intermediate or output patient file is
created by the server.

The output contains exactly nine files: `visit-packet.json`, `review.html`,
`README.txt`, and the three original evidence files under each of `baseline/` and
`followup/`. The v1 manifest records the pairing gate, two full source/presentation
observations, payload SHA-256 digests and byte counts, limitations, missing context,
and clinician questions. `computed_results` and `candidate_interpretations` are
required to be empty.

Validation recursively validates both key-image bundles, source linkage, every file
digest/count, the longitudinal gates, and the exact script-free human-review
template. Its summary omits source identifiers, descriptions, dates, measurements,
and paths. A valid packet remains sensitive and unreviewed; it is not registration,
same-lesion confirmation, clinical interpretation, or sign-off.

## Numeric comparison drafts

Agents can compute a deliberately limited measurement comparison locally:

```bash
scanview-agent compare-measurements baseline.json followup.json \
  --baseline-id 'bidirectional:baseline-id' \
  --followup-id 'bidirectional:followup-id' \
  --lesion-label 'Target lesion A' \
  --output comparison.json
scanview-agent validate-comparison comparison.json
```

The command requires two valid packets, explicit tracking IDs, matching measurement
types, trusted millimeter values, and distinct source series. Its output conforms to
`schemas/scanview-measurement-comparison-v1.schema.json` and contains source-linked
baseline/follow-up values, absolute and percentage changes, limitations, missing
context, and questions for a clinician. `candidate_interpretations` is deliberately
empty. The command does not establish same-lesion identity, scan compatibility, or
the response criteria needed for a medical conclusion. Elliptical ROI comparisons
report only major/minor diameter and mathematical 2D ellipse-area change; they do not
establish tumor segmentation, volume, burden, or response.

The unified viewer exposes the same strict path without filesystem automation: an
agent may paste a bounded versioned measurement packet, select the two tracking IDs,
enter a working lesion label, preview the arithmetic, and export the v1 comparison.
Deletion affects only a hydrated annotation in the current memory session. The local
validator reports validity, schema/review state, measurement type, metric count, and
whether a label exists; it never echoes the label, IDs, coordinates, or values.

## Local comparison review and amendment

Agents can bind the visual and numeric derivatives into one human-readable artifact:

```bash
scanview-agent assemble-comparison-review visit-packet.zip comparison.json \
  --output review-initial.zip
scanview-agent validate-comparison-review review-initial.zip
```

Assembly recursively validates both inputs, then joins each comparison observation
to exactly one visible measurement in the corresponding baseline/follow-up key image.
Source series, instance, tracking ID, type, units, and metric values must all agree.
The output contains exactly seven files: a v1 review record, the normalized comparison,
the complete visit packet, both copied key-image PNGs, `review.html`, and `README.txt`.

The unified viewer provides the same workflow from **Save review packet**. It first
maps the selected measurement pair to exact source-instance indexes and restores
both panes to those slices. Export remains disabled if either pane moves away. The
browser then sends one bounded transport containing only `baseline.zip`,
`followup.zip`, and `comparison.json` to the same-origin loopback assembler. The
server creates the nested visit packet and final review archive in memory, returns
the validated seven-file ZIP, and persists no patient artifact.

Human decisions are appended to a new archive, never written into the comparison:

```bash
scanview-agent record-comparison-review review-initial.zip \
  --output review-reviewed.zip \
  --reviewer-name 'Reviewer name' --reviewer-role 'Clinical role' \
  --decision accepted_for_discussion \
  --same-lesion confirmed --acquisition-suitability suitable \
  --measurement-placement accepted --response-criteria uncertain \
  --note 'Person-entered review note.' --attest
```

`accepted_for_discussion` requires confirmed same-lesion identity, suitable acquisition,
and accepted measurement placement. Other supported decisions are
`amendment_requested` and `rejected`. All identity fields are explicitly
`self_asserted_unverified`; `--attest` acknowledges that ScanView has not authenticated
the person or their credentials. This is not a digital signature or medical-record
sign-off.

`amend-comparison-review` accepts a newly validated comparison, rechecks the full join,
creates another non-overwriting archive, appends a `comparison_amended` event, anchors
the prior archive digest inside the event hash, and resets the review state to
`unreviewed`. Keep ancestor archives: the current archive records their hashes but
cannot independently prove that a missing ancestor existed. The validator reports
only status, event count/type, modality, parent-link presence, and integrity booleans;
it withholds reviewer identity, notes, lesion label, opaque IDs, and numeric values.

## Exact local viewer navigation

An agent can turn exact manifest references into a human-viewer handoff without using
filenames, raw DICOM UIDs, or an external service:

```bash
scanview-agent viewer-link manifest.json \
  --baseline-series 'series_…' --baseline-instance 'instance_…' \
  --followup-series 'series_…' --followup-instance 'instance_…' \
  --base-url 'http://127.0.0.1:8765/'
```

The JSON result conforms to
`schemas/scanview-navigation-intent-v1.schema.json`. It is explicitly `local_only`,
`sensitive`, and `pairing_status: not_assessed`. Generation requires each exact
instance to belong to its named renderable MR/CT series, distinct baseline/follow-up
series, complete paired follow-up fields, and—when supplied—a plain loopback HTTP
origin with no credentials, query, or pre-existing fragment.

The same four source options can be passed to `scanview-agent launch`. The fragment
contract is `#scanview-v1?baseline_series=…&baseline_instance=…` with an optional
complete follow-up pair. The browser accepts only those four singleton fields within
320 characters, resolves all targets against the fetched loopback catalog, and
applies all or none. It then removes the fragment from the visible URL without a
request. Because fragments are not part of HTTP requests, they do not enter the
server access log or create server-side navigation state.

Navigation changes only the selected native series and stack indexes. It does not
approve compatibility, prove chronology or same-lesion identity, accept registration,
hydrate measurements, or generate a conclusion. Existing compatibility and evidence
export gates run normally after navigation.

## Opt-in live viewer state

An agent can inspect what the unified viewer is currently showing without scraping
the UI. The person must first choose **Agent state: off** so it becomes **Agent state:
on**. Sharing is otherwise absent—not merely empty.

```bash
curl --fail --silent \
  -H 'Authorization: Bearer <token printed by scanview-agent>' \
  http://127.0.0.1:8765/v1/viewer-state
```

Keep that token out of shared scripts, shell history, screenshots, and logs. The v1
response is defined by `schemas/scanview-viewer-state-v1.schema.json`. When available,
`state` contains exactly:

- opaque baseline and optional follow-up series/instance IDs with exact one-based
  stack position/count;
- active tool and explicit `unpaired`, `independent`, `patient_position`, or
  `approximate_index` slice-link state;
- an optional opaque MPR series ID;
- measurement count and whether an in-memory comparison draft is present;
- `unreviewed` status and fixed local-only/no-pixels/no-direct-identifiers/no-persistence
  declarations.

It excludes pixels, rendered images, descriptions, dates, modality/anatomy labels,
measurement values/labels/geometry, LPS coordinates, source paths, DICOM UIDs, and
direct identifiers. Resolve opaque IDs through the separately authorized manifest
only when the task requires it; do not print sensitive catalog metadata by default.
Every position/count/reference is independently checked against the current local
manifest before publication becomes visible.

The browser heartbeats every 10 seconds. The server keeps one latest state only in
memory and returns its receipt time, age, and remaining lifetime with `no-store`.
It becomes unavailable after 30 seconds without a heartbeat. Opt-out clears the state
and revokes the tab's ephemeral publisher ID, so an older in-flight heartbeat cannot
restore it; a later opt-in uses a new ID. Page close also attempts immediate cleanup.
Multiple tabs are last-valid-publication-wins, and a tab can clear only its own current
publication.

This endpoint reports transient UI/navigation context. It is not a source-image
observation, pairing approval, registration result, measurement validation, clinical
review, diagnosis, or response conclusion. Agents needing evidentiary output must use
the source-linked measurement/key-image/review contracts.

## Local rigid-registration jobs

Agents can request one bounded local registration derivative after a person chooses
and attests the exact fixed-earlier and moving-later series. These are registration
roles, not an assertion about the clinical treatment baseline or nadir:

```bash
scanview-agent registration-doctor
scanview-agent run-rigid-registration '/safe/local/DICOM/root' \
  --fixed-series 'series_…' --moving-series 'series_…' \
  --expected-slicer-sha256 '<trusted 64-hex digest>' \
  --output '/safe/local/registration-job' --attest-series-selection
scanview-agent validate-registration '/safe/local/registration-job'
scanview-agent review-registration '/safe/local/registration-job'
scanview-agent validate-registration-review registration-review.json \
  --registration-bundle '/safe/local/registration-job'
```

The executor requires one matching opaque patient context (identity unverified),
distinct studies and series, identical MR or CT modality, strict chronology,
original-primary brain/head images, a conservatively matched sequence family, one
explicit contrast category, consistent per-instance classic-image geometry, at least
five slices/10 mm coverage, source SHA-256 values, and a compatibility score of 80 or
higher. It rehashes the source before and after staging, never mutates DICOM, and uses
an atomic no-replace publication. The required local 3D Slicer 5.12.3 computed
revision 34627/runtime repository revision `9034c71`
launcher must match a caller-supplied SHA-256 before data staging and after execution.
Before staging, a no-data process checks the self-reported version/runtime repository
revision and BRAINSFit/BRAINSResample availability. Those checks are provenance—not distributor or code-signature
authentication. Platform-specific package evidence and the Linux no-signature limit are
documented in [`SLICER-ENGINE-TRUST.md`](SLICER-ENGINE-TRUST.md). Neither ScanView command calls
an external API. Slicer
settings, `.slicerrc.py`, user-site Python packages, proxy/credential variables, and
extension-server configuration are excluded from the private job environment. The
engine process must also run with OS-enforced network isolation: macOS uses a
deny-all-network sandbox; supported 64-bit Linux requires `bwrap` private namespaces
plus seccomp that permits only local `AF_UNIX` IPC and rejects network socket domains
and io_uring. Linux Slicer receives a private Xvfb display with TCP listening disabled
and never inherits the desktop display. A weaker `unshare`-only setup is refused.
Missing isolation fails closed and there is no unsandboxed fallback.

The v2 bundle contains exactly seven owner-only files: fixed, moving, and
registered-moving NRRDs; a binary registered-moving sampling-support NRRD in fixed
geometry; a moving-to-fixed text ITK transform in DICOM patient LPS; an engine report;
and `registration.json`. The manifest binds every source instance and output by hash,
the executable and runner hashes, exact rigid parameters, transform direction,
privacy state, support-mask derivation/counts, limitations, and QA checklist. Validation summaries omit source IDs,
dates, paths, and engine diagnostics. The Python validator—not JSON Schema alone—also
enforces cross-field semantics, parses the NRRD payloads and transform, requires fixed,
registered, and mask geometry to match, decodes the full uint8 binary mask, rejects
empty support, and rejects non-owner-only or linked files. Six-file v1 evidence is
historical and cannot authorize the v2 mask-gated display.

Generation is not acceptance. The registration bundle remains
`generated_pending_qa`/`unreviewed` forever; review never mutates it.
`review-registration` mounts a visibly watermarked browser-capability human preview
with derived fixed/moving reference, registered, and technical sampling-support
boundary views, three-plane traversal, four
comparison modes, landmarks, and physical-point residual tools. A bearer token can read only
`GET /v1/registration-qa`, a privacy-minimized status. Preview context, allowlisted
NRRD bytes, and decision POST
require the distinct HttpOnly browser session; the bearer agent interface cannot
approve registration. Possession of the separate browser capability is not proof a
person is present.

The downloaded v2 review JSON anchors all seven live bundle members, the source manifest
and transform, fixed/registered/mask geometry, exact mask semantics and counts,
reviewer-entered checks, landmark
observations, quantitative residuals when recorded, and an event hash. Reviewer
identity/training are self asserted and the hash is not a signature. Acceptance
requires a self-attested trained clinician or medical physicist, every checklist item,
full three-plane/four-mode coverage, at least three aligned qualitative landmarks, no
material defect, explicit review of the technical support boundary/excluded region,
and at least three spatially distributed 3-D landmark pairs within
the fixed geometry-derived tolerance. That acceptance can set only `overlay` and
`swipe` true for exploratory display where the technical sampling-support mask is one
and shared anatomy was reviewer-attested.
Subtraction, mask propagation, segmentation, resampled-image measurements, and
response conclusions remain false. If quantitative QA is unavailable, only a
non-accepting record can be created and it carries a permanent
spatial-error-not-quantified label.
Agents must validate the record with its live bundle before relying on display flags;
standalone validation deliberately reports source integrity as false. Because a
browser cannot guarantee Unix file modes, first validate and import the download into
one owner-only, non-overwriting local copy:

```bash
scanview-agent import-registration-review '/safe/local/registration-job' \
  ~/Downloads/scanview-registration-review.json \
  --output '/safe/local/registration-review.json'
```

The ordinary viewer consumes an accepted record only when launched with that imported
owner-only record and its exact live bundle:

```bash
scanview-agent launch '/safe/local/DICOM/root' \
  --registration-bundle '/safe/local/registration-job' \
  --registration-review '/safe/local/registration-review.json'
```

The server creates one strict `reviewed_registration_display_context` only after full
bundle/review validation, then rechecks review, bundle-directory, and all seven evidence-
file identities and metadata before every reviewed response. The browser session can fetch exactly `fixed.nrrd`,
`registered-moving.nrrd`, and `registered-moving-coverage.nrrd`; the bearer interface receives only a privacy-minimized
authorization summary. The context binds review/event/bundle/manifest/transform/file
hashes, source roles/dates, identical geometry, and self-attested reviewer role/training
without name or organization. Only opacity and swipe are implemented. Native moving,
subtraction, lesion-mask propagation, segmentation, resampled-image measurements, exports, and response
conclusions are unavailable. The fixed NRRD is a derived reference representation and
registered moving is resampled; neither replaces native DICOM. The separate technical
mask is independently hash/geometry/binary validated before render, sampled with
nearest-neighbor semantics, and forces the fixed pixel wherever support is zero. It
does not identify anatomy, tumor, segmentation, registration quality, or clinical
comparability; shared anatomy remains reviewer-attested.

Rejected, tampered, linked, mismatched, missing, malformed, or non-owner-only review
inputs keep registered context and pixels unavailable while ordinary DICOM remains
usable. Supplying `--registration-review` also suppresses the pending-QA routes so the
reviewed launch cannot silently reopen review authority.

## Source-read-only HTTP surface

Start the local service:

```bash
scanview-agent serve '/safe/local/DICOM/root'
```

Or launch the bundled human and agent workspace on the same origin:

```bash
scanview-agent launch '/safe/local/DICOM/root'
```

It binds only to `127.0.0.1`, prints a random bearer token, and exposes:

```text
GET /v1/health
GET /v1/manifest
GET /v1/viewer-state
GET /v1/comparison-candidates
GET /v1/registration-qa
GET /v1/registration-qa/preview
GET /v1/registration-qa/files/{fixed.nrrd|moving.nrrd|registered-moving.nrrd|registered-moving-coverage.nrrd}
GET /v1/reviewed-registration/display
GET /v1/reviewed-registration/files/{fixed.nrrd|registered-moving.nrrd|registered-moving-coverage.nrrd}
GET /v1/instances/{opaque_id}
POST /v1/viewer-state
POST /v1/visit-packets
POST /v1/consultation-packets
POST /v1/comparison-reviews
POST /v1/registration-reviews
```

There is no source write, overwrite, or delete endpoint. The viewer-state POST is a
memory-only session publication/clear route: exact loopback Origin, private browser
session, exact media type, 16 KiB limit, strict fields, catalog validation, publisher
revocation, and a 30-second TTL apply. The three evidence POSTs are stateless derivative
responses with exact ZIP allowlists. Visit input contains `baseline.zip` and
`followup.zip`; consultation input contains `view-a.zip` and `view-b.zip`; review
input adds only `comparison.json`. All return
`application/zip` with `no-store`. Non-health
agent requests require `Authorization: Bearer <token>`. QA preview and reviewed-display
files plus QA review submission reject bearer-only authorization and require the human
browser cookie. Reviewed routes exist only for one startup-validated accepted review;
the server rechecks the review, bundle directory, and all seven evidence-file identities
and metadata before each reviewed context or file response.
The browser receives a
SameSite, HttpOnly session cookie after a one-time loopback redirect; the token is
not exposed to viewer JavaScript or retained in the visible URL.

## Required agent output shape

Agents should produce a separate draft document with:

```json
{
  "schema_version": "1.0.0",
  "review_status": "unreviewed",
  "observations": [],
  "computed_results": [],
  "candidate_interpretations": [],
  "limitations": [],
  "missing_context": [],
  "questions_for_clinician": []
}
```

Every observation or computation must reference source series/instances and, where
relevant, measurement IDs. Any future candidate interpretation must cite those
observations, state the selected clinical criteria, and remain tentative. The
current comparison command never emits one. If required context is missing, return
it in `missing_context`; do not synthesize a diagnosis or response category.

## Future write boundary

The ordinary viewer now consumes an accepted registration QA record only through the
implemented live-bundle-validated opacity/swipe surface. Manual native-grid binary ROI
export exists only as the unreviewed single-series evidence profile above. SEG import,
DICOM SR, component-specific or semi-automatic tumor segmentation, reviewed volume
types, longitudinal lesion linkage, transformed lesion masks, and signed evidence
packets remain future explicit derivative workflows. Each must preserve the
implemented registration and QA source hashes, algorithm/tool version, parameters,
outputs, limitations, and review state. Native DICOM files remain read-only;
subtraction, propagation, resampled measurements, and response conclusions remain
locked.
