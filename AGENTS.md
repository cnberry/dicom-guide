# DICOM Guide Codex workspace

DICOM Guide exists for people who may know only that they have a folder from an
imaging center and need help understanding it.

- Treat `Install DICOM Guide from https://github.com/cnberry/dicom-guide and start a
  guided tour using <folder>` as a complete bootstrap request. Fetch the repository
  when needed, read `.agents/skills/dicom-guide-install/SKILL.md`, install the app and
  person-facing skills, open the supplied folder, and begin the tour in the same task.
  Do not require a separate clone, `$skill-installer` prompt, or restart first.
- If a request involves installing, opening, or troubleshooting a scan folder, read
  and follow `.agents/skills/dicom-guide-install/SKILL.md`.
- If a request involves inspecting, explaining, highlighting, or controlling a
  running viewer, read and follow `.agents/skills/dicom-guide/SKILL.md`.
- If a request involves changing this repository, read and follow
  `.agents/skills/dicom-guide-develop/SKILL.md`.
- Never expect the person to identify a DICOM file, series, sequence, plane, or slice.
  Inventory and explain those choices as part of the work.
- Keep DICOM reading, decoding, geometry, measurement, and derived-data processing
  local. Never add an external processing fallback or upload patient data.
- Treat source files, metadata, coordinates, reports, screenshots, and generated
  artifacts as sensitive. Never commit them; tests use synthetic data.
- Keep direct image observations, DICOM metadata, anatomical inference, supplied
  report text, and clinical conclusions explicitly separate.
