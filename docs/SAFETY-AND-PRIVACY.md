# Medical safety and privacy

## DICOM presentation-state safety

- GSPS objects and their annotation text are sensitive local medical data. The full
  authenticated endpoint contains source text and opaque linkable IDs; it is not a
  de-identified export and must not be copied into logs, Git, issue trackers, or
  external services.
- The parser reads only bounded stable regular files with no-follow semantics and
  binds each supported state to its PR SHA-256 plus hashed exact same-study MR/CT
  catalog objects. Source changes fail closed.
- Support is limited to a documented display subset. ScanView does not silently drop
  unsupported transforms, polarity, frames, aspect, rotation, flip, crop, shutter,
  mask, overlay, LUT, scoping, graphic, or text semantics and then show a misleading
  partial state; the entire state is withheld. Projection is atomic at runtime.
- Orange GSPS geometry/text is read-only source-carried display content. Text may
  contain identifiers or clinical language. ScanView does not authenticate the
  creator/credentials/signature, establish review status or accuracy, or assess the
  text's clinical meaning. It is not a ScanView measurement, finding, diagnosis,
  tumor label, response assessment, or medical-record statement.
- Orange is a high-contrast ScanView rendering of supported source coordinates;
  source color, style, layer behavior, typography, and full GSPS fidelity are not
  claimed. The original image and GSPS object remain authoritative.
- All viewport manipulation and slice navigation, existing measurement overlays,
  measurement draft import/export, evidence captures, consultation/board/volume
  exports, MPR, and live agent-state publication are locked or hidden while any
  source state is active because current provenance contracts do not represent GSPS.
  Clearing restores the native DICOM display without modifying either source object.
- All parsing and rendering is local. There is no external API, cloud fallback,
  telemetry, remote font, or external DICOM-processing request.

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
  neutral CT key-image ZIP; review input adds one normalized comparison JSON; reviewed
  volume-comparison input has two complete boundary-review ZIPs and one strict pairing
  request. The latter is also joined to the current local catalog and source root.
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
- Longitudinal readiness is metadata-only and never turns a candidate into a pairing.
  It requires valid distinct DICOM dates, separate studies, eligible MR↔MR or CT↔CT
  stacks, and one matching opaque patient context. Its agent form omits descriptions,
  pixels, and paths; its human form shows only aggregate readiness and missing gates.
  Both keep selection, registration, spatial comparison, lesion linkage, response,
  treatment effect, diagnosis, and clinical conclusion unauthorized.
- Agent consultation plans are local navigation proposals, not findings or evidence.
  They must bind to the stable content of the exact local catalog, contain 2–8
  distinct exact source instances, share one opaque patient context, span both MR and
  CT and at least two studies, and preserve fixed false permissions. The browser sends
  a bounded strict plan only to its same-origin browser-session endpoint; bearer access
  alone is refused, validation returns `no-store`, and the server persists no plan.
- A valid plan does not authenticate its software author or establish source relevance,
  chronology, alignment, lesion identity, diagnosis, response, treatment effect, or a
  conclusion. The viewer never auto-opens or auto-captures an item. A person must
  choose a pane and source deliberately, inspect the native image, and separately add
  any consultation-board evidence. Plan headings are unreviewed and may be sensitive;
  the contract explicitly marks that they may contain identifiers. Direct DICOM
  identifiers being absent does not make the artifact de-identified. Duplicate JSON
  fields and non-finite constants are refused rather than interpreted ambiguously.
- Bearer-access auditing is optional and local. If configured, covered sensitive GETs
  are not routed until a privacy-minimized event has been durably appended. The event
  contains a fixed operation class, sequence/time, authorization state, and hash-chain
  anchors only. It excludes tokens, URLs/request targets, query strings, opaque IDs,
  paths, status/body/size, DICOM metadata, pixels, masks, measurements, reviewed
  values, and conclusions. The owner-only log refuses symlinks, hard links, concurrent
  writers, broad permissions, corruption, external change, and oversize state. Audit
  failure returns 503 for bearer reads; it never triggers an external service or
  patient-data upload. Browser-session reads are a separate capability and are not
  represented as bearer events.
- An audit event means only that the random bearer capability authorized a covered
  request. It does not prove which person, software agent, model, or process held the
  token, and it does not prove response delivery. The SHA-256 chain is tamper evidence,
  not a signature, medical-record audit, or OS immutable/append-only property. A
  privileged local user can still alter or delete the file; independent verification
  should run after the service releases its exclusive lock.
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
- A manual ROI volume evidence ZIP is a sensitive, patient-identifiable derivative.
  The browser keeps one person-painted binary labelmap on the native source grid and
  emits a DICOM SEG-format object plus an opaque-ID sidecar. The independent local
  validator rehashes stable source descriptors and recomputes selected format,
  geometry, mask, voxel-count, and arithmetic checks. `valid: true` is limited to
  those checks; it is not boundary accuracy, acquisition suitability, lesion identity,
  tumor classification, clinical validation, or DICOM conformance certification.
  V1 stays `draft_unreviewed`, has no acceptance transition, and cannot unlock a
  longitudinal link, percentage change, response classification, diagnosis, or
  clinical conclusion.
- A manual ROI boundary review is a separate sensitive four-file archive and never
  mutates or upgrades the v1 source evidence. A qualified role is self-asserted, not
  authenticated. Acceptance requires suitable acquisition, the complete eight-item
  boundary checklist, all three planes, represented tissue and inclusion/exclusion
  criteria, and an opaque patient context. It means acceptable for discussion only.
  Independent validation reopens the nested evidence and live DICOM sources; any
  source, mask, snapshot, file, HTML-safety, or permission change fails closed. Even
  a valid accepted review cannot link timepoints, compute change, classify response,
  diagnose, or create a clinical conclusion.
- A reviewed manual ROI volume comparison is a separate sensitive five-file archive.
  It cannot be created from masks alone: each timepoint must already have a complete
  accepted boundary review, and a person must separately attest same-lesion identity,
  same represented tissue, chronology, acquisition/boundary comparability,
  registration consideration, and eight pairing-review checks. The server derives
  consistent per-series dates from the live local catalog and recursively revalidates
  both nested DICOM SEG/source chains. Accepted output exposes transparent reviewed
  volume arithmetic only. Boundary uncertainty remains unquantified; spatial overlay,
  voxelwise localization, response/progression classification, treatment causality,
  diagnosis, clinical conclusion, and medical-record sign-off remain false. Any
  rejection, revision, malformed input, or changed source withholds all numeric values.
- Reviewed native-boundary display is a separate startup mode and creates no new
  patient artifact. It recursively validates that accepted five-file comparison,
  both nested reviews, both DICOM SEG masks, and every source byte before holding two
  exact binary masks in memory. Agents receive only a privacy-minimized status;
  context and mask bytes require the HttpOnly browser session. The browser independently
  rehashes, recounts, and verifies binary masks before render. Each mask is displayed
  only on its own native grid, is locked against editing/export, and opens at its own
  centroid. Normalized-grid mirroring is off by default and is explicitly not
  anatomical correspondence. No registration, overlay, subtraction, propagation,
  spatial change, treatment response, diagnosis, or conclusion is available. Source
  or comparison mutation locks this surface while ordinary native DICOM remains usable.
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
  self-reported version/runtime repository revision and BRAINSFit/BRAINSResample
  availability before source staging.
  The generated bundle is always pending QA, with overlay, swipe, subtraction, and
  mask propagation locked. User settings, `.slicerrc.py`, and user-site Python
  packages are disabled, and Slicer temporary/cache paths are redirected into the
  private job directory. Proxy, credential, extension-server, and Python-path
  variables are not inherited. The engine is required to run inside OS-enforced
  network isolation: macOS uses a deny-all-network sandbox; supported 64-bit Linux
  requires `bwrap` private namespaces plus seccomp that permits only local `AF_UNIX`
  IPC and rejects network socket domains and io_uring. Linux Slicer uses a private
  Xvfb display with TCP listening disabled and never inherits the desktop display.
  A weaker `unshare`-only path is refused. Missing isolation fails closed; there is no
  unsandboxed fallback.
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
  the pending bundle, anchors all seven live files plus exact support-mask semantics and
  counts, and must be revalidated against that
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
  record and its live seven-file v2 bundle at server startup. It rechecks the review,
  bundle directory, and all seven evidence-file identities and metadata before each
  reviewed response. The browser session can fetch
  only fixed reference, registered-moving, and the separate technical sampling-support
  NRRDs; bearer agents receive only a
  minimized authorization summary. Rejected, invalid, linked, missing, mismatched, or
  tampered inputs leave registered pixels inaccessible while ordinary DICOM remains
  usable. Supplying a review suppresses the pending-QA routes.
- The reviewed surface provides opacity and swipe only. Both displayed image NRRDs are
  derived; registered moving is resampled; native DICOM remains authoritative. The
  browser must hash and validate the fixed-grid uint8 binary support mask before it
  creates render state, samples it with nearest-neighbor semantics, mattes the standalone
  registered pane at zero, and uses the fixed pixel at zero in every composite. Missing,
  changed, non-binary, empty, or geometry-mismatched masks lock the surface with no
  unmasked fallback. This mask is moving-image sampling support, not anatomy, tumor,
  lesion segmentation, registration quality, or clinical comparability. Subtraction,
  lesion-mask propagation, segmentation, resampled measurements, exports, and response
  conclusions are absent.
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
- A manual binary ROI volume is marked-source-grid arithmetic, not a tumor volume.
  Boundary placement, partial-volume effects, included/excluded tissue, acquisition
  protocol, motion, treatment effect, and lesion identity remain unreviewed. Matching
  labels, codes, or Tracking IDs across exports do not establish the same lesion, and
  v1 deliberately performs no longitudinal arithmetic.
- A separate accepted boundary review can document what a self-attested qualified
  reviewer intended to include at one timepoint. It does not make the software or
  volume clinically validated, authenticate that person, prove the represented tissue,
  or establish the same target on a later scan.
- The implemented reviewed volume-comparison artifact validates two exact accepted
  records and requires a new explicit cross-timepoint linkage review. Its numerical
  difference may still reflect boundary choices, acquisition/contrast, motion,
  partial-volume effects, edema, necrosis, resection cavity, treatment effect, or
  other non-tumor-burden factors. It is not a response criterion or causal conclusion.
- Seeing both accepted boundaries at once does not create correspondence between
  their native coordinate systems. Different centroids, matrices, slice spacing,
  coverage, orientation, positioning, and acquisition state can make matching
  fractional grid locations anatomically unrelated. The display therefore provides
  no cross-scan overlay or voxelwise difference and cannot show “where the tumor
  changed.”

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

The lesion-volume validator may report explicitly named `computed_unreviewed_*`
values only after exact-source and arithmetic validation. Agents must describe that
state as “source/format/arithmetic checks passed; clinical review pending,” never as a
finding, tumor measurement, clinical validation, or conclusion. Invalid evidence has
`evidence_use: none` and no computed values. Validation is read-only and cannot approve
or change the artifact.

The lesion-volume-review validator may repeat the nested
`computed_unreviewed_volume_ml` only after both layers and the live sources validate.
Agents must pair it with `identity_verification: self_asserted_unverified` and
`evidence_use: single_timepoint_reviewed_for_discussion_only`. They must not shorten
that state to “clinically reviewed,” “approved tumor volume,” or “response evidence.”

The lesion-volume-comparison validator may report reviewed baseline/follow-up volumes,
arithmetic absolute/percentage change, numeric direction, and elapsed days only when
both complete review/evidence/source chains validate and the explicit pairing decision
is `accepted_for_volume_change_discussion`. Agents must preserve the phrases
“reviewed manual volume arithmetic” and “for discussion only,” plus
`identity_verification: self_asserted_unverified`. They must not call it tumor response,
progression, regression, treatment effect, tumor burden, spatial change, clinical
validation, or sign-off. Every invalid/non-accepted state has `evidence_use: none` and
null numeric fields.

The native-boundary display summary has the same discussion-only arithmetic authority
and no pixel authority for bearer agents. Agents must preserve `registered: false`,
`spatial_overlay: false`, `voxelwise_change_localization: false`, and
`response_classification: false`. “Both reviewed boundaries are available in their
independent native spaces” is acceptable; “the overlay shows response” is impossible
in this mode.

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
