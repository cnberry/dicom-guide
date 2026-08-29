# ScanView Agent

Source-read-only catalog, compatibility scoring, and loopback API for local DICOM
studies.
It excludes direct patient-name/ID tags from its output by design, but its manifests
remain sensitive medical information and are **not de-identified**.

```bash
python -m pip install -e '.[test]'
scanview-agent manifest '/path/to/copied/DICOM' --output manifest.json
scanview-agent candidates manifest.json
scanview-agent serve '/path/to/copied/DICOM'
scanview-agent launch '/path/to/copied/DICOM'
scanview-agent validate-measurements '/path/to/scanview-measurements.json'
scanview-agent validate-key-image '/path/to/scanview-key-image.zip'
scanview-agent assemble-visit-packet baseline-key-image.zip followup-key-image.zip \
  --output scanview-visit-packet.zip
scanview-agent validate-visit-packet scanview-visit-packet.zip
scanview-agent assemble-consultation-packet '/path/to/copied/DICOM' \
  view-a-key-image.zip view-b-key-image.zip --output scanview-consultation-packet.zip
scanview-agent validate-consultation-packet scanview-consultation-packet.zip
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

Use `scripts/build_release.py` from the repository root to produce a self-contained
wheel with the built UI under `scanview_agent/ui` and all versioned contracts under
`scanview_agent/schemas`. A regular agent-only wheel stays lightweight and reads
schemas from the source checkout. `launch` serves an embedded or explicitly supplied `--ui-dist` bundle
and the API from one loopback origin. It establishes an
HttpOnly browser session, while agents continue to use the printed bearer token.
The server has no source-write or delete endpoint. The unified viewer's derivative
POSTs accept exact bounded transports: two timepoint key-image bundles for a visit
packet, one neutral MRI plus one neutral CT key-image bundle for a consultation
packet, or the timepoint bundles plus one normalized comparison for a comparison-
review packet. All recursively assemble and revalidate in memory, return `no-store`,
and create no server-side patient file. Measurement validation returns only validity, schema,
review state, count, and errors; it does not echo source identifiers, coordinates,
or values. Comparison requires explicit tracking IDs from distinct source series and
trusted millimeter results. It emits source-linked numeric change, missing context,
and clinician questions with an empty interpretation list and `unreviewed` state.
An optional working lesion label is normalized and bounded but never treated as proof
of lesion identity. Comparison validation omits that label, IDs, coordinates, and
numeric values from its privacy-minimized summary.
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

`viewer-link` creates a versioned, sensitive local navigation intent from exact
opaque catalog IDs. It verifies series/instance membership, permits only a plain
loopback base origin, and reports that pairing is `not_assessed`. The launcher accepts
the same baseline/follow-up ID options for an initial view. The browser consumes the
fragment atomically, clears it from the address bar, and leaves compatibility and
clinical review gates unchanged. Fragments never reach the HTTP service, and no
navigation state is stored server-side.

The unified viewer also has an explicit **Agent state** opt-in. While enabled, it
publishes a strict, memory-only summary to `POST /v1/viewer-state`; a bearer-authorized
agent reads it with `GET /v1/viewer-state`. The summary contains only opaque catalog
series/instance positions, tool/link state, optional MPR series, and evidence counts.
It contains no pixels, descriptions, dates, measurement values/labels/geometry,
paths, or direct identifiers. The server independently checks catalog membership,
serves it with `no-store`, and expires it after 30 seconds without a heartbeat.
Opt-out revokes that ephemeral publisher so an in-flight older update cannot restore
sharing. This is transient navigation context, not observation or clinical review.

Rigid registration also stays local. `registration-doctor` looks for the required 3D
Slicer 5.12.3 revision 34627 executable but never downloads it and reports its
observed launcher hash without authenticating the distributor.
`run-rigid-registration` requires an explicit human series-selection attestation,
one matching but identity-unverified opaque patient context, original-primary
brain/head MR↔MR or CT↔CT, distinct chronological studies, one conservative sequence
and explicit contrast category, regular per-instance geometry, hashes, and a score
of at least 80. The expected launcher SHA-256 must match before staging and after the
job; a no-data preflight checks the self-reported version/revision and BRAINSFit
availability before source staging. Source bytes are rehashed before private staging;
Slicer/BRAINSFit receives only
local generic paths, and user settings/startup scripts and user-site Python packages
are disabled. OS-enforced network isolation is mandatory: macOS uses a deny-all-network
sandbox; supported 64-bit Linux requires `bwrap` private namespaces plus seccomp denial
of socket creation, socket pairs, and io_uring. The weaker `unshare`-only path is
refused, and there is no unsandboxed fallback. A successful non-overwriting, owner-only directory contains the fixed,
moving, and registered-moving NRRDs, moving-to-fixed text ITK transform, engine report,
and v1 manifest. `validate-registration` rechecks all hashes, required versions,
parameters, parsed output geometry/rigidity, private permissions, source provenance,
and the invariant that the generated bundle stays `generated_pending_qa` and
`unreviewed`.

`review-registration` serves a separate, watermarked, browser-capability QA workspace
from loopback. It shows derived fixed/moving reference and registered volumes in all three planes with
opacity, swipe, checkerboard, edges, landmarks, and physical-point residual tools.
Agents can read only a privacy-minimized status; bearer authentication alone cannot
fetch NRRDs or submit a decision. This is a separate browser capability, not proof a
person is present. A downloaded self-attested JSON record anchors every byte of the unchanged
six-file bundle. A qualified self-attested acceptance requires a trained clinician or
medical physicist, every checklist item, full three-plane/four-mode coverage, three
aligned qualitative landmarks, and at least three spatially distributed 3-D landmark
pairs within the fixed geometry-derived tolerance. It can authorize only exploratory
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

The browser-only reviewed surface exposes only fixed reference and registered-moving
NRRDs and implements opacity/swipe. A bearer agent sees a minimized authorization
summary but cannot fetch these pixels. Rejected, tampered, linked, mismatched, missing,
or non-owner-only review inputs keep the ordinary DICOM viewer available and every
registered pixel locked. Startup hashes plus per-response review/bundle identity and
metadata freshness checks relock the surface if any evidence changes. Shared coverage
is reviewer-identified because the six-file bundle has no pixel-level transformed
coverage mask.
