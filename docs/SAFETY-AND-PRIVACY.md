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
- The app makes no runtime network request by default.
- DICOM processing never depends on an external API; the CSP blocks external origins.
- The API binds to loopback and requires a random bearer token; the unified browser
  uses a SameSite, HttpOnly session cookie established by a one-time local redirect.
- The one local POST is not an external DICOM-processing dependency. It accepts only
  two derived key-image ZIPs from the exact loopback origin, enforces compressed and
  uncompressed size limits, assembles and recursively validates in memory, returns
  `no-store`, and creates no server-side patient file.
- Paths, patient names/IDs, DICOM headers, and response bodies are absent from logs.
- Patient identity tags are used only in local memory to derive an opaque patient-
  context digest. The raw values are never written to manifests, evidence packets,
  logs, or Git; the digest remains sensitive, potentially linkable, and is not
  de-identification.
- Manifests and derivatives stay outside Git and are treated as sensitive.
- Source delete and overwrite operations do not exist.
- Generated content is `derived` and `unreviewed` until explicitly accepted.
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
