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
- Source-linked local key-image archives with display provenance, permanent review
  labeling, measurement evidence, and agent-verifiable integrity.
- Local clinician visit-packet assembly with hard longitudinal gates, a static
  side-by-side human review page, and a versioned agent-verifiable file manifest.
- Explicit, numeric-only local measurement comparison for agents.
- Same-origin loopback launcher for the UI, catalog, and protected native instances.

### Phase 2 — robust local archive and tools

- Orthanc/DICOMweb import with localhost-only configuration.
- OHIF longitudinal mode or ScanView mode extension.
- Physical-coordinate linked crosshair and MPR.
- Direct viewer visit-packet assembly and explicit clinician review/sign-off workflow
  built around the implemented key-image, measurement, and visit-packet contracts.

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
