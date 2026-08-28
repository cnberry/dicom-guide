# Roadmap and next steps

## Immediate

1. Let the active Finder copy finish; do not run another source reader meanwhile.
2. Run `scripts/copy_and_verify.py` and retain the manifest with the local copy.
3. Smoke-test at least one copied MRI and CT series in the Cornerstone viewer without
   printing or committing patient metadata.
4. Add window/level, pan, zoom, reset, orientation labels, and length/ROI tools.
5. Replace normalized stack index linking with patient-position synchronization.
6. Serve instance bytes and static UI from one loopback process for a consistent
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
