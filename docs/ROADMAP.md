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

## Immediate

1. Import a future same-modality MRI follow-up and have a person confirm the intended
   baseline/follow-up sequences.
2. Smoke-test copied JPEG 2000 MRI and CT pixels in the production viewer on this
   computer, then repeat on Linux without exposing metadata or screenshots.
3. Persist source-referenced length/ROI measurements with tracking IDs; add
   orientation labels and annotation export.
4. Replace normalized stack index linking with patient-position synchronization.
5. Serve instance bytes and static UI from one loopback process for a consistent
   macOS/Linux launcher and agent/viewer deep links.

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
