# Plan and acceptance criteria

## Goal

Create a cross-platform local DICOM visualizer that helps Mila and her clinicians
review MRI/CT studies over time, while giving software agents a structured,
traceable interface. Preserve original data and never turn an unreviewed algorithmic
result into a medical conclusion.

## Work phases

### Phase 0 — preserve the source

- Finish the existing single Finder transfer from `PATIENT_DATA`.
- Inventory source and destination after Finder releases the disc.
- Run byte-for-byte SHA-256 verification and repair missing/mismatched files.
- Keep the verification manifest with the local copy, never in Git.

### Phase 1 — local comparison MVP (current)

- Local folder import and DICOM stack rendering.
- Study/series inventory and timeline metadata.
- Manual baseline/follow-up selection.
- Native side-by-side view with approximate linked position.
- Transparent compatibility suggestion with reasons/warnings.
- Read-only catalog/API and versioned agent JSON contract.
- Explicit safety, privacy, and provenance UI.
- Source-linked manual length and bidirectional evidence with a human-readable table.
- Validated DICOM patient-orientation labels and source-linked 2D elliptical ROI
  evidence.
- Geometry-gated single-series local MPR with three orthographic patient-axis planes
  and explicit interpolated-derivative labeling.
- Physically linked, visible LPS crosshairs within one MPR volume, with canonical
  planes protected from oblique rotation and slab-thickness manipulation.
- Source-linked local key-image archives with display provenance, permanent review
  labeling, measurement evidence, and agent-verifiable integrity.
- Local clinician visit-packet assembly with hard longitudinal gates, a static
  side-by-side human review page, and a versioned agent-verifiable file manifest.
- One-click visit-packet export from the two live viewer panes through a bounded,
  authenticated same-origin loopback request; assembly and validation remain local
  and in memory.
- Explicit, numeric-only local measurement comparison for agents.
- Human/agent measurement workspace with strict pasted-JSON import, session-only
  deletion, explicit labeled lesion pairing, local numeric preview/export, and a
  privacy-minimized comparison validator.
- Local comparison-review archives with exact visual/numeric evidence joins,
  script-free human presentation, self-attested checklist decisions, non-overwriting
  amendment history, and privacy-minimized integrity validation.
- One-click comparison-review export from the current explicit pair and its two exact
  live source slices through a bounded same-origin request; nested assembly and
  validation remain local, in memory, and source-read-only.
- Versioned agent-to-human navigation from exact opaque catalog series/instances via
  a one-use local fragment, with atomic catalog resolution, immediate URL cleanup,
  and no effect on pairing or review state.
- Same-origin loopback launcher for the UI, catalog, and protected native instances.

### Phase 2 — robust local archive and tools

- Orthanc/DICOMweb import with localhost-only configuration.
- OHIF longitudinal mode or ScanView mode extension.
- Explicit clinician review/sign-off workflow built around the implemented key-image,
  measurement, and visit-packet contracts.

### Phase 3 — reviewed derivatives

- Slicer/BRAINSFit rigid registration jobs.
- Registration QA: opacity, checkerboard, edges, landmarks, accept/reject audit.
- Accepted overlay/swipe and mask propagation gates.
- DICOM SEG/SR import/export and separate derivative store.
- Manual/semi-automatic component-specific tumor segmentation.

### Research only

- Intensity-normalized longitudinal MRI subtraction.
- Deformable registration around tumor/resection anatomy.
- AI lesion proposals, automated matching, radiomics, response prediction.

## Acceptance criteria

1. **Source immutability:** cataloging/viewing does not change a source SHA-256;
   every derivative eventually resolves to exact source instances and hashes.
2. **Pairing transparency:** no candidate is auto-approved; results include score,
   warnings, reasons, and `review_status`; missing or different opaque patient
   contexts cannot produce a longitudinal candidate.
3. **Geometry honesty:** approximate index synchronization is labeled; clinical-looking
   overlay requires patient-space geometry or an accepted registration transform.
4. **Registration gating:** reject/accept state is explicit and auditable; rejected or
   unreviewed transforms cannot unlock overlay/subtraction/mask propagation.
5. **Measurement provenance:** geometry, source frames, units, method/version, author,
   timestamp, and tracking ID survive save/reopen.
6. **No false response label:** missing diagnosis/age, selected criteria, clinical
   status, steroids, treatment dates, baseline/nadir, or confirmation yields missing
   fields—not a response category.
7. **Agent safety:** default interface is read-only; source delete does not exist;
   outputs are versioned and separate observation/computation/interpretation/limits.
8. **Privacy:** loopback only, no analytics/outbound runtime calls, PHI excluded from
   logs; header removal is never represented as de-identification.
9. **Offline core:** all DICOM decoding, metadata indexing, comparison, registration,
   segmentation, and evidence generation must remain usable without an external API.
10. **Communication:** exported evidence shows dates, sequence/contrast,
   native/derived state, registration QA, measurement method, sources, limitations,
   and an unreviewed watermark until sign-off.
11. **Review trust:** local review records separate person-entered decisions from
   immutable observations/computations, identify self-asserted credentials as
   unverified, bind every event and parent derivative by hash, and never represent
   that chain as a digital signature or medical-record authentication.
