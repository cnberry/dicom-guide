# Roadmap and next steps

## Completed in the first milestone

1. Preserved the Finder transfer and verified all 10,321 source files byte-for-byte
   without modifying the disc or deleting destination extras.
2. Cataloged the local copy into opaque, hashed study/series/instance records without
   committing patient data.
3. Built local MRI/CT rendering, two-up comparison, compatibility explanations,
   window/level, pan, zoom, reset, and in-memory length tools.
4. Built the loopback-only, token-protected, read-only agent interface.
5. Confirmed the current media contains one MRI exam and one CT exam, and therefore
   no valid same-modality longitudinal comparison candidate.

## Completed in the second milestone

1. Loaded the complete copied folder and rendered real JPEG 2000 MRI and CT pixels
   using only bundled browser workers/codecs.
2. Removed arbitrary follow-up selection and reject same-exam series as a
   longitudinal response pair.
3. Added patient-position slice linking when DICOM frames/orientations permit it;
   all other linked navigation is visibly approximate.
4. Added versioned, source-traceable manual length export, local validation, and
   save/reopen overlay restoration.

## Completed in the third milestone

1. Added perpendicular bidirectional measurements with long axis, short axis, and
   bidimensional product in trusted physical units.
2. Added a human-readable evidence table with opaque source provenance, tracking IDs,
   and persistent `unreviewed` labeling.
3. Added v2 measurement packets, geometry/result consistency checks, local validation,
   and bidirectional save/reopen restoration.
4. Added a local agent comparison command that requires explicit tracking IDs from
   distinct series and emits numeric change, limitations, missing context, and no
   response interpretation.
5. Unified the bundled UI, privacy-minimized manifest, protected native instances,
   and agent API behind one loopback launcher. Service-backed evidence IDs now join
   directly to manifest records.

## Completed in the fourth milestone

1. Added DICOM patient-orientation labels derived locally from validated Image
   Orientation (Patient) geometry; invalid geometry produces no labels.
2. Added manual elliptical ROI overlays with major/minor diameters and 2D ellipse area
   in trusted patient-space units.
3. Added v3 source-linked measurement packets, v1/v2 import compatibility, ROI
   geometry/result validation, save/reopen restoration, and numeric-only agent
   comparison.
4. Verified the full ROI export/validate/reopen path with a synthetic local DICOM
   stack and no external runtime request.

## Completed in the fifth milestone

1. Added per-viewport local key-image ZIP export with a watermarked PNG, exact
   opaque source/presentation provenance, and a source-scoped v3 measurement packet.
2. Added local SHA-256 cross-links plus strict agent validation of archive contents,
   PNG structure/dimensions, measurement integrity, and exact source-instance match.
3. Added a versioned JSON Schema for the key-image evidence contract using opaque
   source IDs and no source paths or DICOM UIDs.
4. Verified the production browser export and agent validation round-trip on a
   synthetic native MR stack with an ROI, no browser errors, and no external calls.

## Completed in the sixth milestone

1. Added local clinician visit-packet assembly from two explicitly selected,
   validated key-image archives with no external service or patient-data mutation.
2. Added hard gates for one matching opaque patient context, distinct source studies
   and series, MR↔MR or CT↔CT, valid chronological acquisition dates, and correct
   baseline/follow-up display roles.
3. Added a versioned agent schema, SHA-256/byte-count manifest, nested evidence
   validation, static-template validation, and privacy-minimized CLI summary.
4. Added a script-free responsive/printable review page with both images, dates,
   sequences, source slices, clinician questions/checklist, and permanent safety
   labeling; numeric results and candidate interpretations remain empty.
5. Verified assemble/validate and human rendering end to end with synthetic MR key
   images, no scripts or external links, and only loopback page/PNG requests.
6. Added locally derived opaque patient context to both catalog paths, blocked
   cross-patient viewer/agent suggestions, and verified the complete copied dataset
   resolves to one context without emitting raw identifiers.

## Completed in the seventh milestone

1. Added one-click clinician visit-packet export from the two live viewer panes while
   retaining the Python assembler as the sole authoritative longitudinal gate.
2. Added a bounded two-member ZIP transport and authenticated exact-origin loopback
   POST that assembles and recursively validates the result entirely in memory.
3. Refactored each viewport to expose its current source-linked key-image archive
   without forcing a separate download; the existing individual export remains.
4. Added transport, safety-gate, same-origin, and successful HTTP round-trip tests.
5. Verified the production viewer end to end on two synthetic dated MR studies: the
   downloaded nine-file packet passed every local integrity check and the service
   created no patient-data output file.

## Immediate

1. Import a future same-modality MRI follow-up and have a person confirm the intended
   baseline/follow-up sequences.
2. Repeat production packaging and real-codec smoke tests on Linux without exposing
   metadata or screenshots.
3. Define explicit clinician identity, attestation, amendment, and sign-off states
   around the implemented unreviewed visit packet.
4. Produce signed/notarized macOS/Linux release artifacts and add agent/viewer deep
   links around the self-contained Python wheel.
5. Add measurement-table editing and MPR.

## Next milestone

1. Add Orthanc as an optional DICOMweb archive and pin/test its local configuration.
2. Prototype an OHIF longitudinal ScanView mode instead of forking OHIF.
3. Add explicit compatibility/QA badges to the local clinician visit packet,
   followed by a reviewed sign-off workflow.
4. Add append-only audit records for access, comparison drafts, and review decisions.
5. Package and smoke-test on macOS Apple Silicon and Linux x86_64.

## Registration milestone

1. Wrap Slicer/BRAINSFit rigid same-subject brain registration.
2. Persist transform provenance and source hashes in a derivative manifest.
3. Build per-case QA with overlay, checkerboard, edge view, and accept/reject state.
4. Unlock derived display only after explicit acceptance; never overwrite originals.

## Decisions needed with clinicians

- Mila's diagnosis/pathology and which pediatric or adult response criteria apply.
- Which MRI sequence is the intended longitudinal primary series.
- Preferred baseline, nadir/best-response convention, and confirmation timing.
- Tumor component definitions and measurement/segmentation method.
- What evidence packet format is most useful in neurosurgery/neuro-oncology visits.
