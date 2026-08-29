# ScanView Agent

Source-read-only catalog, compatibility scoring, and loopback API for local DICOM
studies.
It excludes direct patient-name/ID tags from its output by design, but its manifests
remain sensitive medical information and are **not de-identified**.

```bash
python -m pip install -e '.[test]'
scanview-agent manifest '/path/to/copied/DICOM' --output manifest.json
scanview-agent candidates manifest.json
scanview-agent readiness manifest.json --output longitudinal-readiness.json
scanview-agent create-consultation-plan manifest.json consultation-request.json \
  --output agent-consultation-plan.json
scanview-agent validate-consultation-plan manifest.json agent-consultation-plan.json
scanview-agent presentation-states '/path/to/copied/DICOM' \
  --output '/safe/private/presentation-states.json'
scanview-agent validate-presentation-states '/path/to/copied/DICOM' \
  '/safe/private/presentation-states.json'
scanview-agent source-segmentations '/path/to/copied/DICOM' \
  --output '/safe/private/source-segmentations.json'
scanview-agent validate-source-segmentations '/path/to/copied/DICOM' \
  '/safe/private/source-segmentations.json'
scanview-agent create-source-segmentation-review '/path/to/copied/DICOM' \
  source-seg-review-request.json --output source-seg-review.zip
scanview-agent validate-source-segmentation-review source-seg-review.zip \
  '/path/to/copied/DICOM'
scanview-agent serve '/path/to/copied/DICOM'
scanview-agent launch '/path/to/copied/DICOM'
scanview-agent launch '/path/to/copied/DICOM' \
  --lesion-volume-comparison '/path/to/reviewed-volume-comparison.zip'
scanview-agent launch '/path/to/copied/DICOM' \
  --agent-audit-log '/safe/private/scanview-agent-access.jsonl'
scanview-agent verify-agent-audit '/safe/private/scanview-agent-access.jsonl'
scanview-agent validate-measurements '/path/to/scanview-measurements.json'
scanview-agent validate-key-image '/path/to/scanview-key-image.zip'
scanview-agent validate-lesion-volume \
  '/path/to/scanview-lesion-volume.zip' '/path/to/copied/DICOM'
scanview-agent validate-lesion-volume-review \
  '/path/to/scanview-lesion-volume-review.zip' '/path/to/copied/DICOM'
scanview-agent assemble-lesion-volume-comparison \
  baseline-boundary-review.zip followup-boundary-review.zip pairing-request.json \
  '/path/to/copied/DICOM' --output reviewed-volume-comparison.zip
scanview-agent validate-lesion-volume-comparison \
  reviewed-volume-comparison.zip '/path/to/copied/DICOM'
scanview-agent assemble-visit-packet baseline-key-image.zip followup-key-image.zip \
  --output scanview-visit-packet.zip
scanview-agent validate-visit-packet scanview-visit-packet.zip
scanview-agent assemble-consultation-packet '/path/to/copied/DICOM' \
  view-a-key-image.zip view-b-key-image.zip --output scanview-consultation-packet.zip
scanview-agent validate-consultation-packet scanview-consultation-packet.zip
scanview-agent assemble-consultation-board '/path/to/copied/DICOM' \
  --item 'MRI overview' mr-key-image.zip \
  --item 'CT overview' ct-key-image.zip \
  --output scanview-consultation-board.zip
scanview-agent validate-consultation-board scanview-consultation-board.zip
scanview-agent compare-measurements baseline.json followup.json \
  --baseline-id 'bidirectional:baseline-id' \
  --followup-id 'bidirectional:followup-id' \
  --lesion-label 'Target lesion A' \
  --output comparison.json
scanview-agent validate-comparison comparison.json
scanview-agent assemble-comparison-review scanview-visit-packet.zip comparison.json \
  --output review-initial.zip
scanview-agent validate-comparison-review review-initial.zip
scanview-agent viewer-link manifest.json \
  --baseline-series 'series_…' --baseline-instance 'instance_…' \
  --base-url 'http://127.0.0.1:8765/'
scanview-agent registration-doctor
scanview-agent run-rigid-registration '/path/to/copied/DICOM' \
  --fixed-series 'series_…' --moving-series 'series_…' \
  --expected-slicer-sha256 '<trusted 64-hex digest>' \
  --output '/safe/local/registration-job' --attest-series-selection
scanview-agent validate-registration '/safe/local/registration-job'
scanview-agent review-registration '/safe/local/registration-job'
scanview-agent record-registration-review '/safe/local/registration-job' \
  review-request.json --output registration-review.json
scanview-agent import-registration-review '/safe/local/registration-job' \
  ~/Downloads/scanview-registration-review.json \
  --output '/safe/local/registration-review.json'
scanview-agent validate-registration-review registration-review.json \
  --registration-bundle '/safe/local/registration-job'
```

Use `scripts/build_release.py` from the repository root to produce an installable
wheel with the built UI under `scanview_agent/ui` and all versioned contracts under
`scanview_agent/schemas`. A regular agent-only wheel stays lightweight and reads
schemas from the source checkout. `launch` serves an embedded or explicitly supplied `--ui-dist` bundle
and the API from one loopback origin. Any local browser can open the printed clean URL
without a login or session cookie, while agents continue to use the printed bearer
token for control commands. The focused viewer also exposes a memory-only control
bridge: bearer agents issue exact catalog-validated navigation/display commands, and
the same-origin browser reports the resulting rendered state. Codex should use the repository
workflow in `skills/scanview-control/SKILL.md`; it authorizes no source mutation,
measurement, diagnosis, response classification, or external DICOM processing.
For offline transfer and installation on macOS or Linux, run
`scripts/build_offline_bundle.py`. Its non-overwriting ZIP includes the embedded-asset
wheel, pinned pure-Python `pydicom` 3.0.2, hash-locked local requirements, and
verifier/install/launch scripts. The installer invokes pip only with `--no-index` and
`--require-hashes`, and every launch checks the bundle and installed runtime before
indexing DICOM. Python 3.11+ remains a prerequisite. The exact v0.8.0 bundle has passed
offline install, runtime checks, consultation-plan generation/validation, browser and
bearer authorization gates, and loopback launch on both macOS arm64 and Strawberry
Linux x86_64. The v0.9.0 GSPS bundle passed the same exact-artifact gate. The v0.10.0
source-SEG bundle also passed fresh no-index install, 29-schema runtime, strict CLI,
authorization, browser-only mask, hash/length, source-change, and loopback-only gates
on macOS arm64 and Strawberry Linux x86_64. Its second build was byte-identical; no
external DICOM-processing API or runtime network was required.
The v0.11 interoperability gate additionally generates a patient-free sparse binary
SEG with highdicom 0.28.1, independently reconstructs its dense mask through
highdicom's source-instance API, and requires ScanView to produce identical bytes,
hash, count, and volume. highdicom and NumPy are optional test dependencies only and
are not included in the offline runtime.
V0.12 adds a second independent writer/reader gate with NCI/QIICR dcmqi 1.5.6
revision `60d63dc`. Both converters run inside OS-enforced external-network isolation,
and the exact dcmqi, ScanView, and reference dense masks must agree. dcmqi is an
optional test dependency only and is not included in the offline runtime.
V0.13 adds viewer-state v2: neutral Image A/Image B roles work in Consult Prep, while
longitudinal workspaces explicitly declare baseline/followup. A visibly active source
SEG may contribute only its opaque object/segment/series references and guarded
catalog hash; mask bytes, source text, labels, algorithms, volume, and interpretation
remain outside the live state. All navigation, mutation, mask-read, diagnostic,
response, and clinical permissions are fixed false.
V0.14 adds a separate source-SEG boundary-review archive. The browser sends only an
opaque exact source reference and reviewer declaration to the same-origin loopback
service. The service revalidates the guarded original SEG and every referenced source,
reconstructs the native mask, assembles and independently validates the sensitive ZIP
in memory, and persists nothing. CLI creation and validation use the same contract.
Acceptance permits one-timepoint discussion and future pairing review only; it does
not verify source labels, codes, creator, algorithm, accuracy, or meaning and cannot
authorize lesion linkage, change, response, diagnosis, or a conclusion.
The deterministic owner-only v0.14.0 ZIP was built twice byte-identically. A fresh
macOS arm64 no-index install passed the 32-schema runtime, packaged source-SEG
catalog/review creation and validation, owner-only/non-overwrite behavior, bearer POST
refusal, browser-session same-origin assembly, `no-store`, and independent validation
of the returned five-file ZIP. The runtime contains neither dcmqi, highdicom, nor
NumPy and requires no runtime network or external DICOM API. Patient-free production-
browser QA passed; current Strawberry commissioning is pending SSH authentication and
no patient data was transferred.

The deterministic owner-only v0.13.0 ZIP was built twice byte-identically. A fresh
macOS arm64 no-index install passed the
31-schema runtime and exact packaged source-SEG/viewer-state v2 authorization,
forbidden-field, revocation, and changed-source gates. The runtime contains neither
dcmqi, highdicom, nor NumPy and requires no runtime network or external DICOM API.
Current Strawberry commissioning is pending SSH authentication; the exact v0.11
Linux gate remains passing and no patient data was transferred.
The earlier source-bound boundary-review, reviewed volume-comparison, and reviewed
native-boundary display gates remain covered by the full regression suite and v0.5.0
cross-platform package evidence;
publisher signing remains pending.
The server has no source-write or delete endpoint. The unified viewer's derivative
POSTs accept exact bounded transports: two timepoint key-image bundles for a visit
packet, one neutral MRI plus one neutral CT key-image bundle for a consultation
packet, or the timepoint bundles plus one normalized comparison for a comparison-
review packet. The reviewed volume-comparison route accepts exactly two complete
boundary-review ZIPs plus one strict pairing request and revalidates them against the
live source root. All recursively assemble and revalidate in memory, return `no-store`,
and create no server-side patient file. Measurement validation returns only validity, schema,
review state, count, and errors; it does not echo source identifiers, coordinates,
or values. Comparison requires explicit tracking IDs from distinct source series and
trusted millimeter results. It emits source-linked numeric change, missing context,
and clinician questions with an empty interpretation list and `unreviewed` state.
An optional working lesion label is normalized and bounded but never treated as proof
of lesion identity. Comparison validation omits that label, IDs, coordinates, and
numeric values from its privacy-minimized summary.
`readiness` and `GET /v1/longitudinal-readiness` produce the same metadata-only,
catalog-hash-bound follow-up gate. The report counts eligible MR/CT studies and series,
requires valid distinct dates and one matching opaque patient context, caps reported
candidate pairs, excludes descriptions/pixels/paths, and leaves all clinical and
derived-use permissions false.

`presentation-states` builds an owner-only, source-bound GSPS display catalog entirely
locally and always hashes the PR plus every referenced MR/CT instance. The strict
subset requires same-study/same-patient, single-frame monochrome sources, a linear
modality transform equivalent to the source renderer, LINEAR VOI, identity presentation
LUT/polarity, exact full-image displayed area with matching aspect, and bounded PIXEL
POLYLINE/anchor text. Masks, overlays, subtraction, lookup tables, frame scoping,
transform/aspect drift, invalid geometry/text, or missing hashes withhold the whole
state. `validate-presentation-states` rehashes local sources and emits only aggregate
counts; it omits IDs, text, geometry, and window values.

Authenticated `GET /v1/presentation-states` is a sensitive read-only extraction for
local agents and the human viewer. It returns `no-store` and can be audited as
`presentation_states_read`; it contains opaque IDs and source text that may contain
identifiers or clinical language. Creator identity is not authenticated, source-text
clinical meaning is `not_assessed`, and ScanView interpretation, editing, measurement,
diagnosis, response, and conclusion permissions are false. No external API is called.

`source-segmentations` creates an owner-only catalog for a deliberately narrow local
DICOM SEG profile. It requires uncompressed binary frames, one exact regular single-
frame MR/CT source grid, exact per-frame source references, supported segment/plane
dimensions, strict geometry, and catalog-wide decode/mask budgets. DICOM defines
Spatial Locations Preserved as optional: `YES` or absence is accepted only after all
native geometry is independently proven exact; `NO`, `REORIENTED_ONLY`, or any other
value is refused. The v2 catalog reports which evidence path applied.
`validate-source-segmentations` rehashes every source and returns only aggregate counts.
Full DICOM conformance, creator identity, algorithm identity or accuracy, boundary
accuracy, tissue meaning, diagnosis, and response are not asserted.
The top-level Common Instance Reference may list the complete guarded source series
when empty SEG planes are omitted; every encoded frame must still resolve through that
set and its exact source plane.
The sensitive catalog and dense mask bytes are available on the loopback service
without browser login; bearer catalog reads can be audited as
`source_segmentations_read`. The browser rehashes/recounts the mask and aligns slice slabs
by independently derived physical source order before read-only MPR display. No
external API is called.

Run the optional independent interoperability gate from the repository root in a
disposable environment:

```bash
python3 -m venv /private/tmp/scanview-highdicom-interop
/private/tmp/scanview-highdicom-interop/bin/python -m pip install \
  -e './packages/agent[interop]'
/private/tmp/scanview-highdicom-interop/bin/python \
  scripts/verify_highdicom_source_segmentation.py
```

Dependency installation may contact a package index, but the gate itself disables
socket connections before generating or reading DICOM. It uses synthetic data only,
creates everything under a deleted temporary directory, and adds no runtime network
or external processing API.

Run the independent dcmqi writer/reader gate separately:

```bash
python3 -m venv /private/tmp/scanview-dcmqi-interop
/private/tmp/scanview-dcmqi-interop/bin/python -m pip install \
  -e './packages/agent[dcmqi-interop]'
/private/tmp/scanview-dcmqi-interop/bin/python \
  scripts/verify_dcmqi_source_segmentation.py
```

The dcmqi executables are pinned exactly and run inside macOS `sandbox-exec` or a
Linux bubblewrap private network namespace. The gate fails closed when that isolation
is unavailable. It generates and deletes patient-free data only; dcmqi never processes
Mila data and never enters the ScanView runtime or offline bundle.

`create-consultation-plan` accepts a strict local request containing 2–8 exact opaque
series/instance pairs and bounded discussion headings. It rejoins every item to the
supplied catalog, requires one opaque patient context, both MR and CT, distinct
instances, and at least two studies, and binds the result to a canonical catalog-
content SHA-256 that excludes only the catalog's volatile top-level generation time.
`validate-consultation-plan` independently rebuilds that plan from the exact catalog.
Both artifacts remain sensitive and `deidentified: false`.

The unified viewer validates a pasted plan through same-origin
`POST /v1/agent-consultation-plans/validate` before exposing deliberate “Open in
Image A/B” controls. The endpoint is exact-origin, exact-media-type, bounded, local,
and `no-store`. A valid plan authorizes exact
native-source navigation only. Agent identity is unverified, headings are unreviewed,
and automatic opening/capture, source mutation, chronology, registration, lesion
linkage, response, treatment effect, diagnosis, and clinical conclusion remain false.
Visit-packet assembly also stays local. It accepts only validated key-image v2
archives with one matching opaque patient context, distinct dated studies/series,
explicit ordering, and one modality. It creates a static review page plus an
integrity-linked agent manifest and does not perform lesion matching, registration,
response scoring, or interpretation.
Consultation-packet assembly is a separate neutral contract. It requires the local
DICOM root so each selected view can be joined to a hashed live catalog and exact
guarded source descriptor. Exactly one MR and one CT from distinct studies with one
matching opaque patient context are accepted. The final packet uses `view_a`/`view_b`,
not timepoint roles, binds source byte/SHA anchors into a static page, keeps computed
and interpretation arrays empty, and asserts no chronology, alignment, lesion match,
comparison, diagnosis, or response authority.
A consultation board extends that neutral workflow to 2–8 distinct source instances
from at least two studies, including at least one MRI and one CT. Every item is
revalidated against the guarded live catalog and rehashed source bytes. Person-entered
labels remain discussion headings only. The board has empty computation and
interpretation arrays and grants no chronology, alignment, lesion identity,
comparison, diagnosis, or treatment-response authority.
Comparison-review assembly recursively validates both artifacts and requires the
selected measurements, source instances, units, and numeric values to match the
visible key-image evidence exactly. It creates an owner-only ZIP with both images, a
script-free printable page, and a hash-chained event record. `record-comparison-review`
adds a self-attested decision to a new output archive;
`amend-comparison-review` binds an amended comparison, records the parent archive
digest, and resets review state. Neither command overwrites an existing archive.
Reviewer identity is not authenticated or digitally signed, and privacy-minimized
validation never echoes names, roles, notes, labels, IDs, or values.
The viewer invokes the same assembly path only when its current panes show the exact
source instances named by the selected baseline/follow-up measurements.

`validate-lesion-volume` validates one source-bound manual ROI volume evidence draft.
It accepts a three-member ZIP and the exact local DICOM root, rehashes and matches every
source instance, enforces one regular single-frame native MR/CT grid, checks the
ScanView v1 subset of the DICOM SEG-format references and binary mask, and independently
recomputes the dense mask hash, marked voxel count, and volume. Its summary exposes
only explicitly named `computed_unreviewed_*` values. `source_validated_pending_review`
means byte/format/geometry/arithmetic checks passed; it is not boundary review, DICOM
conformance certification, clinical validation, diagnosis, or treatment-response
authority. The command is read-only and cannot approve or unlock an artifact.

`validate-lesion-volume-review` validates a separate four-member one-timepoint
boundary-review archive against the exact local DICOM root. It recursively revalidates
the nested source-bound evidence and DICOM SEG, verifies the script-free review page
and exact visible record, and enforces the fixed review decision and permission locks.
An accepted record can permit discussion of that reviewed boundary and eligibility
for the separate pairing review only. Reviewer identity is always self-asserted and
unverified; longitudinal linkage, percent change, response classification, diagnosis,
and clinical conclusion remain false. Invalid or changed source evidence withholds
the volume and fails closed with `evidence_use: none`.

`assemble-lesion-volume-comparison` is the separate cross-timepoint pairing-review
transition. It accepts exactly two complete `accepted_for_discussion` boundary-review
ZIPs, one strict pairing request, and the exact local DICOM root. It requires one
matching opaque patient context and modality, distinct studies/series/reviews/evidence,
and live catalog dates that establish baseline before follow-up. Every source instance
in each reviewed series must agree on that date. The request records self-attested
qualified role, same-lesion and same-tissue judgments, chronology,
acquisition/boundary comparability, registration consideration, eight checklist
values, notes, decision, and the fixed attestation.

An `accepted_for_volume_change_discussion` decision fails closed until all pairing
gates are complete. The five-member output contains `comparison.json`, both exact
review ZIPs, a regenerated script-free `review.html`, and `README.txt`.
`validate-lesion-volume-comparison` recursively reopens both reviews, their DICOM SEG
evidence, and every live source object, then checks hashes, strict JSON/schema/archive
shape, chronology, and exact page bytes. Only a valid accepted record exposes reviewed
baseline/follow-up volumes, arithmetic absolute/percentage change, numeric direction,
and elapsed days in its privacy-minimized summary. Rejection, revision, malformed
input, or any source change returns null numeric values and `evidence_use: none`.
Spatial overlay, voxelwise localization, response classification, treatment causality,
diagnosis, clinical conclusion, identity authentication, and medical-record sign-off
remain false in every state; boundary uncertainty remains unquantified.

`viewer-link` creates a versioned, sensitive local navigation intent from exact
opaque catalog IDs. It verifies series/instance membership, permits only a plain
loopback base origin, and reports that pairing is `not_assessed`. The launcher accepts
the same baseline/follow-up ID options for an initial view. The browser consumes the
fragment atomically, clears it from the address bar, and leaves compatibility and
clinical review gates unchanged. Fragments never reach the HTTP service, and no
navigation state is stored server-side.

The unified viewer also has an explicit **Agent state** opt-in. While enabled, it
publishes a strict, memory-only summary to `POST /v1/viewer-state`; a bearer-authorized
agent reads it with `GET /v1/viewer-state`. V2 contains only opaque Image A/Image B
positions, explicit neutral or longitudinal roles, tool/link state, optional MPR
series, and evidence counts. If a supported source SEG is visibly open it may also
contain only that object's opaque segment/series references and guarded catalog hash.
It contains no pixels, SEG mask, source text, labels/codes, algorithms, volume, dates,
measurement values/labels/geometry, paths, direct identifiers, or interpretation.
The server independently checks manifest and source-SEG catalog membership, serves
the state with `no-store`, expires it after 30 seconds without a heartbeat, and
clears it when guarded source input changes. Opt-out revokes that ephemeral publisher
so an in-flight older update cannot restore sharing. This is transient navigation
context, not observation, mask access, clinical review, diagnosis, or response.

Rigid registration also stays local. `registration-doctor` looks for the required 3D
Slicer 5.12.3 computed revision 34627/runtime repository revision `9034c71`
executable but never downloads it and reports its
observed launcher hash without authenticating the distributor.
`run-rigid-registration` requires an explicit human series-selection attestation,
one matching but identity-unverified opaque patient context, original-primary
brain/head MR↔MR or CT↔CT, distinct chronological studies, one conservative sequence
and explicit contrast category, regular per-instance geometry, hashes, and a score
of at least 80. The expected launcher SHA-256 must match before staging and after the
job; a no-data preflight checks the self-reported version/runtime repository revision
and BRAINSFit/BRAINSResample availability before source staging. Source bytes are
rehashed before private staging; Slicer and those two local modules receive only
local generic paths, and user settings/startup scripts and user-site Python packages
are disabled. OS-enforced network isolation is mandatory: macOS uses a deny-all-network
sandbox; supported 64-bit Linux requires `bwrap` private namespaces plus seccomp that
permits only local `AF_UNIX` IPC and rejects network socket domains and io_uring. Linux
Slicer runs on private Xvfb with TCP listening disabled; inherited displays, weaker
`unshare`-only execution, and unsandboxed fallback are refused. A successful non-overwriting, owner-only
v2 directory contains fixed, moving, registered-moving, and binary registered-moving
sampling-support NRRDs; a moving-to-fixed text ITK transform; an engine report; and a
manifest. `validate-registration` rechecks all hashes, required versions and both local
modules, parameters, parsed output geometry/rigidity, the complete uint8 `{0,1}` mask
payload and recomputed support counts, private permissions, source provenance, and the
invariant that the generated bundle stays `generated_pending_qa` and `unreviewed`.

`review-registration` serves a separate, watermarked, local-browser QA workspace
from loopback. It shows derived fixed/moving reference, registered, and technical
sampling-support boundary views in all three planes with
opacity, swipe, checkerboard, edges, landmarks, and physical-point residual tools.
The clean loopback URL can fetch the allowlisted NRRDs; decision submission still
requires the exact local Origin. This browser context is not proof a person is present.
A downloaded self-attested JSON record anchors every byte of the unchanged
seven-file bundle. A qualified self-attested acceptance requires a trained clinician or
medical physicist, every checklist item, full three-plane/four-mode coverage, three
aligned qualitative landmarks, and at least three spatially distributed 3-D landmark
pairs within the fixed geometry-derived tolerance, plus explicit review of the
technical sampling-support boundary and excluded region. It can authorize only exploratory
shared-coverage overlay/swipe; all other derivative uses stay false.
`validate-registration-review` must be given the live bundle to establish source
integrity. No command authenticates the reviewer or turns an event hash into a
signature.

A browser cannot guarantee the owner-only Unix mode required for display authorization.
Validate and import the downloaded bytes into a non-overwriting owner-only copy first:

```bash
scanview-agent import-registration-review '/safe/local/registration-job' \
  ~/Downloads/scanview-registration-review.json \
  --output '/safe/local/registration-review.json'
```

An accepted imported record can be consumed only with its exact live bundle:

```bash
scanview-agent launch '/safe/local/DICOM/root' \
  --registration-bundle '/safe/local/registration-job' \
  --registration-review '/safe/local/registration-review.json'
```

The local reviewed surface exposes fixed reference, registered-moving, and the
separate technical sampling-support NRRD and implements opacity/swipe. It verifies all
three files before rendering, samples the mask with nearest-neighbor semantics, and
uses the fixed pixel wherever support is zero. Rejected, tampered, linked,
mismatched, missing, non-binary, or non-owner-only inputs keep the ordinary DICOM
viewer available and every registered pixel locked. Startup hashes plus per-response
review/bundle identity and metadata freshness checks relock the surface if any
evidence changes. The mask is not anatomy, tumor, lesion segmentation, registration
quality, or proof of clinical comparability; shared anatomy remains reviewer-attested.
