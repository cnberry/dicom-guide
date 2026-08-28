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

## Read-only HTTP surface

Start the local service:

```bash
scanview-agent serve '/safe/local/DICOM/root'
```

It binds only to `127.0.0.1`, prints a random bearer token, and exposes:

```text
GET /v1/health
GET /v1/manifest
GET /v1/comparison-candidates
GET /v1/instances/{opaque_id}
```

There is no source write, overwrite, or delete endpoint. Non-health requests require
`Authorization: Bearer <token>`.

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
relevant, measurement IDs. Candidate interpretations must cite those observations,
state the selected clinical criteria, and remain tentative. If required context is
missing, return it in `missing_context`; do not synthesize a diagnosis or response
category.

## Future write boundary

Registration, segmentation, measurements, and evidence packets will be explicit,
idempotent derivative jobs in a separate store. Each will record source hashes,
algorithm/tool version, parameters, outputs, limitations, and review status. Native
DICOM files will remain read-only, and no derived display will unlock until its
required QA state is accepted.
