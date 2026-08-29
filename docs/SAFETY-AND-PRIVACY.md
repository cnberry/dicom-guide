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

- ScanView has no source write/delete operation; copied originals are hashed. This is
  an application boundary, not an operating-system immutable-file flag.
- Loopback DICOM streaming anchors each source to its startup device/inode/size/change
  metadata, opens with no symlink following, copies and hashes one exact-size local
  snapshot before sending headers, and refuses any changed source. The temporary
  snapshot is owner-only, unlinked after rollover, and deleted at request completion.
- The app makes no external runtime network request; unified-workspace traffic stays
  on the loopback origin.
- DICOM processing never depends on an external API; the CSP blocks external origins.
- There is no cloud-processing fallback. A missing codec, parser, package, registration
  engine, or isolation control disables that operation instead of transmitting DICOM,
  derived pixels, headers, catalogs, or evidence to another service.
- The transferable offline bundle contains the embedded ScanView wheel and pinned
  pure-Python `pydicom` wheel. Installation uses `pip --no-index --require-hashes`,
  and every launch verifies manifested payload bytes plus installed versions, UI,
  schemas, and consultation support before cataloging a source. The build step may
  retrieve the pinned dependency, but no patient data is present or processed during
  that retrieval; installation and runtime need no package service. The unsigned
  manifest detects corruption only and does not authenticate the publisher or host
  Python interpreter.
- The API binds to loopback and requires a random bearer token; the unified browser
  uses a SameSite, HttpOnly session cookie established by a one-time local redirect.
- The derivative POSTs are not external DICOM-processing dependencies. They accept
  only exact bounded ZIP transports from the exact loopback origin. Visit input has
  two derived timepoint key-image ZIPs; consultation input has one neutral MR and one
  neutral CT key-image ZIP; review input adds one normalized comparison JSON.
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
- Consult Prep disables viewer-state v1 publication because that contract uses
  baseline/follow-up pane names. Neutral agent evidence travels only in the explicit
  consultation packet, preventing internal UI roles from becoming a chronology claim.
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
- Rigid registration invokes a version-gated local Slicer 5.12.3/BRAINSFit process.
  The release computed revision is 34627; the enforced runtime repository revision is
  `9034c71`. The official macOS package and this host's installed copy were
  independently checksum/signature/Gatekeeper verified as recorded in
  [`SLICER-ENGINE-TRUST.md`](SLICER-ENGINE-TRUST.md). The generic runtime gate still
  requires a caller-supplied launcher SHA-256 and does not claim to authenticate
  arbitrary installations. It requires attested, identity-unverified matching opaque
  patient context; same
  modality and strict chronology; original-primary brain/head images; explicit
  sequence/contrast matching; and consistent per-instance volume geometry. It
  rehashes every source before and after private staging and records exact engine,
  runner, parameters, and output hashes. The caller-supplied expected launcher hash
  must match before DICOM staging and after execution; this is substitution
  protection, not distributor/signature authentication. A no-data preflight verifies
  self-reported version/runtime repository revision and BRAINSFit availability before
  source staging.
  The generated bundle is always pending QA, with overlay, swipe, subtraction, and
  mask propagation locked. User settings, `.slicerrc.py`, and user-site Python
  packages are disabled, and Slicer temporary/cache paths are redirected into the
  private job directory. Proxy, credential, extension-server, and Python-path
  variables are not inherited. The engine is required to run inside OS-enforced
  network isolation: macOS uses a deny-all-network sandbox; supported 64-bit Linux
  requires `bwrap` private namespaces plus seccomp denial of socket creation, socket
  pairs, and io_uring. A weaker `unshare`-only path is refused. Missing isolation
  fails closed; there is no unsandboxed fallback.
  Engine diagnostics exist only inside the deleted private job directory because
  third-party errors could contain patient context; a timeout terminates the process
  group before cleanup.
- Registration QA is an explicit exception for inspecting an otherwise display-locked
  derivative. It runs only in a visibly watermarked, separately cookie-authenticated
  human workflow on loopback. The bearer agent interface receives no NRRD URLs or
  pixels and cannot submit a decision. Possession of the browser capability is not
  proof a person is present. The browser verifies each allowlisted volume's byte count
  and SHA-256 before parsing it locally; the review request contains observations and
  physical landmark points, never volume bytes or filesystem paths.
- A registration-QA decision is a separate sensitive JSON derivative. It never changes
  the pending bundle, anchors all six live files, and must be revalidated against that
  bundle before its display flags are trusted. Reviewer name, role, organization, and
  training are self asserted. Its event hash is tamper evidence, not identity proof or
  a digital signature. Qualified self-attested acceptance is limited to exploratory
  shared-coverage overlay/swipe;
  subtraction, mask propagation, segmentation, resampled-image measurements, and
  response conclusions remain locked.
- Browser downloads cannot establish owner-only Unix permissions. The local
  `import-registration-review` command validates the downloaded bytes against the live
  bundle and creates one non-overwriting `0600`, single-link copy; only that protected
  copy is eligible for reviewed launch.
- Reviewed registration display requires the exact saved owner-only, unlinked accepted
  record and its live six-file bundle at server startup. It rechecks the review, bundle
  directory, and all six evidence-file identities and metadata before each reviewed
  response. The browser session can fetch
  only fixed reference and registered-moving NRRDs; bearer agents receive only a
  minimized authorization summary. Rejected, invalid, linked, missing, mismatched, or
  tampered inputs leave registered pixels inaccessible while ordinary DICOM remains
  usable. Supplying a review suppresses the pending-QA routes.
- The reviewed surface provides opacity and swipe only. Both displayed NRRDs are
  derived; registered moving is resampled; native DICOM remains authoritative. The
  bundle has no pixel-level transformed coverage mask, so shared coverage is identified
  by reviewer inspection and is not machine-enforced. Subtraction, masks, segmentation,
  resampled measurements, exports, and response conclusions are absent.
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
- A clinician consultation packet also inherits the sensitivity of both rendered
  views and may contain burned-in identifiers. V1 permits exactly one MRI plus one CT
  from distinct studies with one matching opaque patient context. It assigns no
  chronological role, lesion relationship, registration, alignment, intensity
  equivalence, comparison, diagnosis, or response authority. The assembler verifies
  exact live catalog positions and rehashes each guarded source DICOM; the resulting
  byte/SHA anchors establish provenance, not patient identity or clinical meaning.
  Its computed and interpretation arrays are fixed empty. A valid packet remains an
  unreviewed question-preparation artifact that must be confirmed in the clinical
  imaging system.
- A clinician consultation board inherits the sensitivity of every included rendered
  view and discussion heading. V1 accepts 2–8 distinct source instances with one
  matching opaque patient context, at least one MRI and one CT, and at least two
  studies. Every source is rejoined to the live guarded catalog and rehashed locally.
  Item order is presentation order only, and person-entered headings are not findings.
  The artifact grants no chronology, registration, alignment, lesion identity,
  comparison, diagnosis, treatment response, or clinical-review authority. Browser
  download permissions are controlled by the host and may not be owner-only; move and
  protect a retained board appropriately. CLI output is non-overwriting and `0600`.
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
- Adjacent MRI and CT exam dates do not make them a longitudinal pair. In Consult
  Prep they remain independent reference views; dates label sources only.
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

Registration QA is a human authority boundary. Agents may inspect its minimized
availability/review-status contract and validate a saved record, but they may not load
QA pixels, satisfy the visual checklist, choose acceptance, or treat self-attested
review as an authenticated clinical sign-off.

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
