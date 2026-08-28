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

## Immediate

1. Import a future same-modality MRI follow-up and have a person confirm the intended
   baseline/follow-up sequences.
2. Repeat production packaging and real-codec smoke tests on Linux without exposing
   metadata or screenshots.
3. Add ROI measurements, orientation labels, and key-image export using the existing
   evidence packet contract.
4. Produce signed/notarized macOS/Linux release artifacts and add agent/viewer deep
   links around the self-contained Python wheel.
5. Define the clinician-reviewed evidence packet and sign-off workflow.

## Next milestone

1. Add Orthanc as an optional DICOMweb archive and pin/test its local configuration.
2. Prototype an OHIF longitudinal ScanView mode instead of forking OHIF.
3. Implement evidence packets: native key images, exact sequences/dates, compatibility
   and QA badges, measurements, limitations, questions, and clinician sign-off.
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
