# ScanView Codex workspace

- For requests to inspect or control the running viewer, read and follow
  `skills/scanview-control/SKILL.md` before acting.
- Keep DICOM reading, decoding, geometry, registration, measurement, and derived-data
  processing local. Never add an external processing fallback or upload patient data.
- Treat the source tree, catalog, opaque references, coordinates, and derived artifacts
  as sensitive. Never commit patient files, findings, tokens, paths, or screenshots.
- Keep source observations, computations, tentative interpretations, and clinician
  conclusions explicitly separate. ScanView is investigational and not validated for
  diagnosis.
