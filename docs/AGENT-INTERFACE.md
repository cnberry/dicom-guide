# Agent interface

ScanView gives local agents a read-only, versioned contract so they do not need to
scrape filenames or guess at DICOM series descriptions. This interface never calls
an external API and never grants source mutation.

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

The human viewer's MPR planes are local navigation-only derivatives and are not part
of the key-image or agent evidence contract. Agents should continue to reference
native source instances until a versioned derived-image provenance contract exists.
The live MPR panel exposes its current LPS patient coordinate in accessible UI text so
an agent can help a person navigate, but that transient point is not saved, compared,
or promoted to an observation.

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
an atomic no-replace publication. The required local 3D Slicer 5.12.3 revision 34627
launcher must match a caller-supplied SHA-256 before data staging and after execution.
Before staging, a no-data process checks the self-reported version/revision and
BRAINSFit availability. Those checks are provenance—not distributor or code-signature
authentication. Neither ScanView command calls an external API. Slicer
settings, `.slicerrc.py`, user-site Python packages, proxy/credential variables, and
extension-server configuration are excluded from the private job environment.

The v1 bundle contains exactly six owner-only files: fixed, moving, and
registered-moving NRRDs; a moving-to-fixed text ITK transform in DICOM patient LPS;
an engine report; and
`registration.json`. The manifest binds every source instance and output by hash,
the executable and runner hashes, exact rigid parameters, transform direction,
privacy state, limitations, and QA checklist. Validation summaries omit source IDs,
dates, paths, and engine diagnostics. The Python validator—not JSON Schema alone—also
enforces cross-field semantics, parses the NRRD payloads and transform, requires fixed
and registered geometry to match, and rejects non-owner-only or linked files.

Generation is not acceptance. The registration bundle remains
`generated_pending_qa`/`unreviewed` forever; review never mutates it.
`review-registration` mounts a visibly watermarked browser-capability human preview
with native and registered views, three-plane traversal, four comparison modes,
landmarks, and physical-point residual tools. A bearer token can read only
`GET /v1/registration-qa`, a privacy-minimized status. Preview context, allowlisted
NRRD bytes, and decision POST
require the distinct HttpOnly browser session; the bearer agent interface cannot
approve registration. Possession of the separate browser capability is not proof a
person is present.

The downloaded v1 review JSON anchors all six live bundle members, the source manifest
and transform, fixed/registered geometry, reviewer-entered checks, landmark
observations, quantitative residuals when recorded, and an event hash. Reviewer
identity/training are self asserted and the hash is not a signature. Acceptance
requires a self-attested trained clinician or medical physicist, every checklist item,
full three-plane/four-mode coverage, at least three aligned qualitative landmarks, no
material defect, and at least three spatially distributed 3-D landmark pairs within
the fixed geometry-derived tolerance. That acceptance can set only `overlay` and
`swipe` true for exploratory display within the exact shared coverage.
Subtraction, mask propagation, segmentation, resampled-image measurements, and
response conclusions remain false. If quantitative QA is unavailable, only a
non-accepting record can be created and it carries a permanent
spatial-error-not-quantified label.
Agents must validate the record with its live bundle before relying on display flags;
standalone validation deliberately reports source integrity as false. The ordinary
viewer does not yet consume an accepted record.

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
GET /v1/registration-qa/files/{fixed.nrrd|moving.nrrd|registered-moving.nrrd}
GET /v1/instances/{opaque_id}
POST /v1/viewer-state
POST /v1/visit-packets
POST /v1/comparison-reviews
POST /v1/registration-reviews
```

There is no source write, overwrite, or delete endpoint. The viewer-state POST is a
memory-only session publication/clear route: exact loopback Origin, private browser
session, exact media type, 16 KiB limit, strict fields, catalog validation, publisher
revocation, and a 30-second TTL apply. The other two POSTs are stateless derivative
responses with exact ZIP allowlists. Visit input contains `baseline.zip` and
`followup.zip`; review input adds only `comparison.json`. Both return
`application/zip` with `no-store`. Non-health
agent requests require `Authorization: Bearer <token>`. QA preview files and QA review
submission reject bearer-only authorization and require the human browser cookie.
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

Ordinary-viewer consumption of accepted registration QA, segmentation and volume-
measurement types, and signed evidence packets remain future explicit derivative
workflows. Each must preserve the implemented registration and QA source hashes,
algorithm/tool version, parameters, outputs, limitations, and review state. Native
DICOM files remain read-only. No ordinary registration-derived display will unlock
until an accepted record is revalidated against its exact live bundle; that future
integration may unlock exploratory overlay/swipe only.
