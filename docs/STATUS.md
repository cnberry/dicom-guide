# Status

Last updated: 2026-08-28 08:39 PDT

## Data transfer

- Source found: `/Volumes/PATIENT_DATA`, read-only 1.34 GB UDF DVD-R.
- Destination found: `/Users/chris/Desktop/Mila Scan CD`.
- Finder already held the source directory open and was actively copying before this
  build began; no competing copier was started.
- Latest destination-only observation: 1,891 non-empty files / 215,293,654 bytes.
- Transfer status: **in progress; not yet verified**.
- Verification command is implemented but must wait until Finder releases the source.

## Repository

- Initial local-first React/TypeScript/Cornerstone3D viewer implemented.
- Baseline/follow-up pairing, linked stack position, compatibility explanations, and
  registration safety gate implemented.
- Python DICOM catalog, provenance hashing, pairing candidates, local agent API, and
  JSON Schema implemented.
- Copy/repair/SHA-256 verification utility implemented.
- Patient-data exclusion rules and synthetic-only test policy implemented.
- Research, architecture, plan, roadmap, safety, and status committed to the project.

## Verification

- Python agent tests: 2 passing.
- Copy utility: Python bytecode compilation passing.
- Viewer TypeScript typecheck: passing.
- Viewer production build: passing (Cornerstone codec bundle warnings noted).
- Real patient-file smoke test: deliberately pending copy completion.
- Full source/destination checksum: pending copy completion.

## Known gaps

- Current linked navigation uses normalized stack position, not patient coordinates.
- Window/level, pan/zoom, manual measurements, MPR, and orientation overlays are next.
- Viewer folder import and agent API are separate entry paths in this increment.
- No registration, segmentation, response criteria, or automated medical conclusion.
- Production packaging and Linux smoke test remain pending.
