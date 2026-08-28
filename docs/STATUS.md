# Status

Last updated: 2026-08-28 10:58 PDT

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
- Sample MR and CT objects report JPEG 2000 Lossless transfer syntax. The production
  viewer decoded and rendered both through its bundled OpenJPEG WebAssembly worker.
- The complete copied folder loaded in the production viewer in about five seconds:
  2 studies and all 57 renderable MR/CT series, matching the catalog's 49 MR + 8 CT.
- Catalog and candidate files are owner-only, outside Git, and marked sensitive and
  `deidentified: false` despite direct patient name/ID and paths being omitted.

## Repository

- Initial local-first React/TypeScript/Cornerstone3D viewer implemented.
- Baseline/follow-up pairing, linked stack position, compatibility explanations, and
  registration safety gate implemented.
- Window/level, pan, zoom, reset, manual length, perpendicular bidirectional, and
  elliptical ROI tools implemented.
- Validated DICOM patient-orientation labels implemented; labels are withheld rather
  than guessed when Image Orientation (Patient) is missing or malformed.
- Follow-up auto-selection removed; same-exam pairings are explicitly incompatible
  for longitudinal response.
- Physical patient-position slice mapping implemented for shared compatible Frames
  of Reference; normalized fallback is labeled approximate.
- Manual length/bidirectional/ellipse drafts now save/reopen with tracking ID, opaque
  series/instance/frame provenance, DICOM patient-space geometry, units gate,
  limitations, and review state.
- Human-readable source evidence table implemented; imported values are rejected when
  they disagree with their geometry.
- Versioned measurement/comparison JSON Schemas, local validation, and explicit
  numeric-only agent comparison implemented. Same-series pairs, unknown units, and
  mismatched measurement types are refused; no response label is emitted.
- Unified `scanview-agent launch` path implemented: one loopback process serves the
  bundled UI, manifest, pairing candidates, and protected native DICOM instances.
- The staged release builder embeds the viewer, workers, and local codecs into a
  self-contained wheel without breaking lightweight agent-only builds;
  signing/notarization and Linux execution remain pending.
- Browser sessions use a one-time local redirect and SameSite, HttpOnly cookie;
  service-backed measurement IDs join directly to the agent manifest while legacy
  folder-import drafts remain supported.
- Python DICOM catalog, provenance hashing, pairing candidates, local agent API, and
  JSON Schema implemented.
- Copy/repair/SHA-256 verification utility implemented.
- Patient-data exclusion rules and synthetic-only test policy implemented.
- Research, architecture, plan, roadmap, safety, and status committed to the project.

## Verification

- Python agent tests: 14 passing, including v3 JSON Schema conformance and elliptical
  ROI geometry/area comparison checks.
- Viewer tests: 23 passing, including local-only endpoint enforcement, pairing safety,
  physical-position mapping, and measurement provenance/import validation.
- Copy utility: Python bytecode compilation passing.
- Viewer TypeScript typecheck: passing.
- Viewer production build: passing (Cornerstone codec bundle warnings noted).
- Self-contained staged Python wheel build: passing; the 2.7 MB wheel contains the viewer
  entry point plus all 11 built UI/worker/codec files (9.7 MB uncompressed), and an
  isolated installation resolves its embedded UI without the source checkout.
- Synthetic browser smoke test: two canvases render; all five viewer controls activate.
- Real-data production smoke test: copied JPEG 2000 MRI and CT pixels render in two
  1162×1200 canvases; the full folder produces 57 pixel series; local server logs show
  only bundled UI/worker/OpenJPEG assets.
- Measurement round-trip smoke test: a temporary real-image manual length exported,
  passed the agent validator, and restored after viewer/source reopen. Temporary test
  DICOM copies and the test measurement packet were then removed.
- Bidirectional round-trip smoke test: a synthetic native MR stack produced a
  37.7 × 25.1 mm overlay and 946.2 mm² table result; its v2 packet passed local agent
  validation and restored after a complete page/source reopen with no browser errors.
  The test files were moved to Trash after verification.
- Unified synthetic smoke test: the browser established a private local session,
  discovered the catalog without a folder picker, streamed native DICOM pixels,
  exported a valid bidirectional packet, and produced series/instance IDs that joined
  directly to the manifest.
- Elliptical ROI round-trip smoke test: a synthetic axial MR stack displayed R/L/A/P
  orientation labels, produced a 61.7 × 55.1 mm ellipse and 2668.4 mm² area, exported
  a locally valid v3 packet, and restored the overlay after a complete page reopen.
  The session requested only loopback UI/worker/instance resources; synthetic artifacts
  and the exported draft were moved to Trash.
- Unified complete-copy smoke test: 2 studies, all 57 renderable MR/CT series, and
  10,286 instances loaded from the local service. A 62-slice native stack rendered
  through the bundled OpenJPEG WebAssembly decoder with no browser errors or external
  requests.
- Real patient metadata inventory: complete without logging identifying metadata.
- Full source/destination SHA-256 verification: passing for all 10,321 source files.

## Known gaps

- Different-frame longitudinal exams still use approximate normalized linking until
  a reviewed registration exists; patient-position linking is only enabled for a
  shared compatible frame.
- Measurement table editing, key-image export, and MPR remain. Elliptical ROI is a 2D
  manual draft, not segmentation or volume measurement.
- Signed/notarized macOS/Linux release packaging remains pending; the self-contained
  wheel and source checkout launcher are working and verified on macOS.
- No registration, segmentation, response criteria, or automated medical conclusion.
- Linux packaging/smoke testing remains pending.
