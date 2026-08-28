# Agent interface

ScanView gives local agents a read-only, versioned contract so they do not need to
scrape filenames or guess at DICOM series descriptions. This interface never calls
an external API and never grants source mutation.

## Local artifacts

`scanview-agent manifest` creates a sensitive JSON catalog containing:

- opaque study, series, frame-of-reference, and instance IDs;
- modality, acquisition date, sequence/protocol descriptors, and image type;
- dimensions, spacing, orientation, slice position, and stack order;
- MR sequence parameters and contrast metadata where present;
- source byte counts and SHA-256 hashes;
- explicit privacy, provenance, limitations, missing context, and review state.

Direct patient-name/ID tags and absolute paths are omitted. The output is still
medical data and explicitly says `deidentified: false`. Catalogs are atomically
written with owner-only permissions and must remain outside Git.

`scanview-agent candidates` creates metadata-based pairing suggestions. It:

- considers only multi-instance MR↔MR or CT↔CT stacks from different exams;
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

Each viewport can save a source-traceable local ZIP with exactly three members:

- `key-image.png`: the displayed native slice plus visible annotation overlay,
  orientation labels, and a permanent unreviewed/derived/not-for-diagnosis footer;
- `key-image.json`: exact opaque series/instance/frame references, modality/date,
  stack location, display role, patient orientation, viewport dimensions, window,
  invert, zoom, pan, implementation versions, limitations, and integrity digests;
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

## Numeric comparison drafts

Agents can compute a deliberately limited measurement comparison locally:

```bash
scanview-agent compare-measurements baseline.json followup.json \
  --baseline-id 'bidirectional:baseline-id' \
  --followup-id 'bidirectional:followup-id' \
  --output comparison.json
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

## Read-only HTTP surface

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
GET /v1/comparison-candidates
GET /v1/instances/{opaque_id}
```

There is no source write, overwrite, or delete endpoint. Non-health agent requests
require `Authorization: Bearer <token>`. The browser receives a SameSite, HttpOnly
session cookie after a one-time loopback redirect; the token is not exposed to
viewer JavaScript or retained in the visible URL.

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

Registration, segmentation/volume measurement types, and signed evidence
packets will be explicit, idempotent derivative jobs in a separate store. Each will
record source hashes, algorithm/tool version, parameters, outputs, limitations, and
review status. Native DICOM files remain read-only, and no registration-derived
display will unlock until its required QA state is accepted.
