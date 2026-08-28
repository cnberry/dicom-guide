# Medical safety and privacy

## Intended posture

ScanView is a local research and communication tool. It may organize source-backed
facts, compute measurements, suggest comparable series, and draft questions. It
must not independently diagnose, recommend treatment, or state that a tumor has
responded/progressed. A qualified clinician must review images, measurements,
registration quality, clinical context, and any candidate interpretation.

Software that interprets medical images may fall under medical-device regulation;
making the reasoning inspectable does not automatically remove that issue. Any
future distribution for clinical decisions requires intended-use, risk, validation,
quality-system, and regulatory review.

## Data handling

- Originals are immutable and hashed.
- The app makes no external runtime network request; unified-workspace traffic stays
  on the loopback origin.
- DICOM processing never depends on an external API; the CSP blocks external origins.
- The API binds to loopback and requires a random bearer token; the unified browser
  uses a SameSite, HttpOnly session cookie established by a one-time local redirect.
- The derivative POSTs are not external DICOM-processing dependencies. They accept
  only exact bounded ZIP transports from the exact loopback origin. Visit input has
  two derived key-image ZIPs; review input adds one normalized comparison JSON.
  Compressed and uncompressed size limits, duplicate/extra/encrypted-member refusal,
  recursive in-memory validation, and `no-store` responses apply. No server-side
  patient file is created.
- Live agent inspection is explicitly off by default. If a person opts in, the
  browser publishes at most 16 KiB of exact allowlisted JSON to the same-origin
  loopback process: opaque current series/instance positions, tool/link state,
  optional MPR series, and evidence counts. It never sends pixels, descriptive
  metadata, dates, paths, measurement values/labels/geometry, or direct identifiers.
  The server validates every reference against the local catalog, stores only the
  latest state in memory, returns `no-store`, and requires the bearer token to read
  it. Opt-out clears and revokes the ephemeral publisher; absent heartbeats expire
  within 30 seconds. Opaque IDs remain sensitive and potentially linkable.
- Paths, patient names/IDs, DICOM headers, and response bodies are absent from logs.
- Agent viewer links contain only opaque local catalog IDs in a bounded URL fragment.
  Fragments are not transmitted in HTTP, are removed immediately on receipt, and
  are applied only after exact local series/instance membership checks. They remain
  sensitive and potentially linkable if copied, saved, or captured before use.
- Patient identity tags are used only in local memory to derive an opaque patient-
  context digest. The raw values are never written to manifests, evidence packets,
  logs, or Git; the digest remains sensitive, potentially linkable, and is not
  de-identification.
- Manifests and derivatives stay outside Git and are treated as sensitive.
- Source delete and overwrite operations do not exist.
- Generated content is `derived` and `unreviewed` until explicitly accepted.
- Rigid registration invokes a version-gated local Slicer/BRAINSFit process. It
  requires attested, identity-unverified matching opaque patient context; same
  modality and strict chronology; original-primary brain/head images; explicit
  sequence/contrast matching; and consistent per-instance volume geometry. It
  rehashes every source before and after private staging and records exact engine,
  runner, parameters, and output hashes. The caller-supplied expected launcher hash
  must match before DICOM staging and after execution; this is substitution
  protection, not distributor/signature authentication. A no-data preflight verifies
  self-reported version/revision and BRAINSFit availability before source staging.
  The generated bundle is always pending QA, with overlay, swipe, subtraction, and
  mask propagation locked. User settings, `.slicerrc.py`, and user-site Python
  packages are disabled, and Slicer temporary/cache paths are redirected into the
  private job directory. Proxy, credential, extension-server, and Python-path
  variables are not inherited. ScanView requests no external API but, without an OS
  network sandbox, does not claim to observe every action of a third-party binary.
  Engine diagnostics exist only inside the deleted private job directory because
  third-party errors could contain patient context; a timeout terminates the process
  group before cleanup.
- A key-image ZIP remains sensitive medical data. Its PNG can contain burned-in
  identifiers or recognizable anatomy inherited from the displayed pixels, so it
  requires the same sharing safeguards as the original DICOM even though its JSON
  uses opaque IDs and omits direct names and paths.
- A clinician visit packet inherits the sensitivity of both key images. Its local
  assembler requires one matching opaque patient context and refuses cross-modality,
  same-study/series, non-chronological, or mislabeled input. The packet is side-by-side
  only, not registered, and contains empty numeric
  result and interpretation arrays. Successful integrity validation is not clinical
  review or sign-off.
- A comparison-review ZIP inherits the sensitivity of its visit packet plus any
  person-entered reviewer identity and note. It never calls an external API. Exact
  visible-measurement joins prevent an unrelated comparison from being presented
  beside the key images, and every derivative is owner-only and non-overwriting.
  Viewer export is additionally gated on both live panes displaying the exact source
  instances referenced by the selected measurement pair.

## De-identification warning

DICOM identifiers may exist in standard tags, private tags, structured reports,
graphics/overlays, filenames, burned-in pixels, or recognizable facial anatomy.
Excluding PatientName/PatientID from an API response is privacy minimization, not
de-identification. Never upload scan pixels or manifests to a model/service unless
Mila has knowingly authorized that specific data flow and appropriate safeguards
are established.

## Comparison hazards

- Filesystem order is not chronology; use acquisition metadata.
- Series descriptions are hints, not proof of compatible sequences.
- Pre/post contrast, acquisition parameters, plane, coverage, artifact, and scanner
  differences can invalidate comparisons.
- MRI intensity has no universal absolute scale across exams.
- CT and MRI intensities must never be subtracted.
- Registration can create plausible but wrong alignment; tumor, edema, surgery, and
  ventricles may change anatomy. Every clinical-looking overlay needs case QA.
- MPR reslices interpolate a single source volume. Missing or irregular geometry
  disables MPR, and a valid render still does not make the reslice a native image,
  registration result, segmentation, diagnosis, or response assessment.
- MPR crosshairs link one patient-space point only within that source volume. The
  visible LPS coordinate is a navigation aid, not a lesion finding or a transform
  between exams; oblique rotation and slab-thickness controls remain withheld.
- Deformable registration and propagated masks are research-only until validated.
- Pseudoprogression, treatment effect, steroid change, and clinical status cannot be
  resolved from a simple size difference.
- A manual ellipse is a 2D geometric approximation. Its area is not a tumor mask,
  tumor volume, total burden, or response classification; sequence and tumor component
  still require clinician confirmation.

## Agent output contract

Agent output must keep these separate and source-linked:

- `observations`: facts visible in identified source images/metadata;
- `computed_results`: measurements with method/version/provenance;
- `candidate_interpretations`: explicitly tentative, criteria-bound statements;
- `limitations` and `missing_context`;
- `questions_for_clinician`;
- `review_status`.

Free-text conclusions without source image/series and measurement references are
not acceptable evidence.

The current `compare-measurements` command goes further: it always leaves
`candidate_interpretations` empty. It reports only source-linked numeric differences,
requires distinct source series and trusted physical units, and lists the clinical
context still needed before anyone applies response criteria.

The browser pairing editor uses the same constraints and requires strictly ordered
acquisition dates, a human-selected measurement at each timepoint, and a bounded
working label. The label is not proof of
same-lesion identity. Deletion is session-only, pasted JSON uses the strict measurement
validator and a 2 MB cap, and comparison validation rejects arithmetic tampering or
any non-empty interpretation list while withholding labels, identifiers, and values.

An exact navigation intent is not a pairing decision. It can select native sources
for discussion, but it cannot approve compatibility, unlock registered display,
load measurement evidence, or change any review state. A malformed or partially
resolvable intent is rejected as a whole and the ordinary local default view is used.

Live viewer state is not an observation, even when its opaque references are exact.
It says what the interface is showing and which tool is selected; it does not prove
that a lesion exists, that two series are comparable, that measurements are correct,
or that a person reviewed the images.

The comparison-review workflow keeps the arithmetic comparison immutable and
`unreviewed`. A review decision is a separate self-attested event with explicit
same-lesion, acquisition-suitability, measurement-placement, and response-criteria
checklist values. `accepted_for_discussion` is deliberately not named “signed,”
“verified,” or “clinically validated.” ScanView does not authenticate the entered
identity or credentials.

Event hashes cover the note, checklist, actor fields, source-comparison digest, prior
event digest, and parent-archive digest. This catches accidental or partial edits; it
is not a digital signature and does not stop someone from rebuilding every hash.
Amendments create a new archive and reset review to `unreviewed`; ancestor archives
must be retained to verify the recorded parent hashes. Privacy-minimized summaries
do not print reviewer identity, notes, lesion labels, identifiers, or measurements.
