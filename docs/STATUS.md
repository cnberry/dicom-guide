# Status

Last updated: 2026-08-28 09:30 PDT

## Data transfer

- Source found: `/Volumes/PATIENT_DATA`, read-only 1.34 GB UDF DVD-R.
- Destination found: `/Users/chris/Desktop/Mila Scan CD`.
- Finder already held the source directory open and was actively copying before this
  build began; no competing copier was started.
- Finder completed at 10,322 destination files / 1,305,227,159 bytes and released
  the source. Source inventory is 10,321 files; the extra destination file is kept.
- SHA-256 verification/repair pass: **complete, 10,321 / 10,321 byte-identical**.
- Verified source payload: 1,305,221,011 bytes; 0 failures and 0 repairs required.
- One destination-only file was preserved. No destination file was deleted.
- Owner-only verification manifest retained at the destination, outside Git.

## Local catalog

- 2 studies, 65 series, and 10,286 DICOM instances indexed locally.
- Series distribution: 49 MR, 8 CT, 7 PR, and 1 SR.
- The media contains one MRI exam and one CT exam. There is no same-modality
  longitudinal pair, so the matcher correctly returns zero comparison candidates.
- Sample MR and CT objects report JPEG 2000 Lossless transfer syntax. The browser
  bundle includes a local OpenJPEG WebAssembly decoder; production-viewer testing
  of these copied pixels remains an explicit manual check.
- Catalog and candidate files are owner-only, outside Git, and marked sensitive and
  `deidentified: false` despite direct patient name/ID and paths being omitted.

## Repository

- Initial local-first React/TypeScript/Cornerstone3D viewer implemented.
- Baseline/follow-up pairing, linked stack position, compatibility explanations, and
  registration safety gate implemented.
- Window/level, pan, zoom, reset, and in-memory length tools implemented.
- Python DICOM catalog, provenance hashing, pairing candidates, local agent API, and
  JSON Schema implemented.
- Copy/repair/SHA-256 verification utility implemented.
- Patient-data exclusion rules and synthetic-only test policy implemented.
- Research, architecture, plan, roadmap, safety, and status committed to the project.

## Verification

- Python agent tests: 4 passing.
- Viewer tests: 5 passing, including local-only endpoint enforcement.
- Copy utility: Python bytecode compilation passing.
- Viewer TypeScript typecheck: passing.
- Viewer production build: passing (Cornerstone codec bundle warnings noted).
- Synthetic browser smoke test: two canvases render; all five viewer controls activate;
  no console error or external document URL.
- Real patient metadata inventory: complete without logging identifying metadata.
- Full source/destination SHA-256 verification: passing for all 10,321 source files.

## Known gaps

- Current linked navigation uses normalized stack position, not patient coordinates.
- Length measurements are in-memory only; persistence, tracking IDs, bidirectional/ROI
  tools, MPR, and orientation overlays are next.
- Viewer folder import and agent API are separate entry paths in this increment.
- No registration, segmentation, response criteria, or automated medical conclusion.
- Manual production-viewer smoke tests with the copied JPEG 2000 images and Linux
  packaging remain pending.
