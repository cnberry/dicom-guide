# Cross-platform DICOM viewer research

Research date: 2026-08-28. Only public project documentation and repositories were
reviewed; no patient data was used.

## Recommendation

Use a layered stack instead of inventing medical-image decoding and geometry:

| Project | Role | Why it fits | Constraint |
|---|---|---|---|
| [OHIF Viewer](https://github.com/OHIF/Viewers) | Primary long-term UI | MIT, web-based, macOS/Linux browsers, DICOMweb, measurements, segmentation, fusion, MPR, and a longitudinal mode | Robust local use normally benefits from a DICOMweb archive |
| [Cornerstone3D](https://www.cornerstonejs.org/docs/getting-started/overview/) | MVP renderer/toolkit | MIT, local DICOM P10, compressed codecs, stack/volume rendering, synchronizers, physical-space tools | Provides rendering, not registration algorithms |
| [Orthanc](https://orthanc.uclouvain.be/book/plugins/dicomweb.html) | Local archive/API | DICOM/DICOMweb plus a complete REST boundary suitable for agents and OHIF | GPL licensing review; no Docker is installed on this host |
| [3D Slicer](https://slicer.readthedocs.io/en/latest/user_guide/modules/comparevolumes.html) | Registration/segmentation engine | Cross-platform, BSD-style, DICOM, scripted CLI/Python, comparison layouts, BRAINSFit | Research software; generated results require case-specific QA |
| [Weasis](https://github.com/nroduit/Weasis) | Independent validation viewer | macOS/Linux, imports DICOMDIR/CD, comparison layouts, geometry warnings, DICOM SEG | Less direct agent integration and no longitudinal registration engine |
| [MITK](https://github.com/MITK/MITK) | Native analysis alternative | BSD-3-Clause, ITK/VTK, macOS/Linux, registration and segmentation | Heavier C++ customization path |
| [VolView](https://github.com/Kitware/VolView) | Architecture/reference | Apache-2.0, browser DICOM/3D/segmentation; VolView Insight demonstrates Python AI pipelines | Less oncology workflow depth than OHIF |

OHIF is explicitly a complex-imaging application framework, built on Cornerstone3D,
and supports DICOMweb archives. Its extension/mode model and longitudinal workflow
align well with tracked measurements over time. Orthanc supplies QIDO-RS, WADO-RS,
STOW-RS, and WADO-URI through its official plugin. These become the phase-two
interoperability foundation.

## Selected version pins for the MVP

- `@cornerstonejs/core`, `tools`, and `dicom-image-loader`: 5.8.2
- `dicom-parser`: 1.8.21
- Vite: 8.2.2
- Vitest: 4.1.11
- pydicom: 3.0.x

## Longitudinal comparison findings

- Native side-by-side review is the safest first view.
- Series candidates must show compatibility reasons and remain unapproved.
- Link using DICOM patient coordinates or an accepted transform, not equal slice
  numbers; normalized position is only an approximate fallback.
- Rigid registration is a derivative. Store fixed/moving source references,
  transform direction, algorithm/version/parameters, interpolation, and QA state.
- [AAPM TG-132](https://www.aapm.org/pubs/reports/detail.asp?docid=164) supports
  patient-specific visual and quantitative registration verification.
- CT/MRI intensities are not subtractable. Longitudinal MRI subtraction requires
  compatible sequences, registration, bias correction/intensity normalization,
  and explicit research labeling.
- Measurements need source frame, patient-space geometry, units, method, author,
  timestamp, stable tracking ID, and review state.
- Use DICOM SEG for masks and DICOM SR TID 1500 for interoperable measurements.

## Clinical response boundaries

The app must not apply one generic “tumor response” percentage. Adult RANO and the
different pediatric RAPNO criteria depend on diagnosis, age, treatment, clinical
status, steroids, baseline/nadir choice, new lesions, and confirmation timing.
Until a clinician selects and completes an appropriate criteria module, ScanView
shows source-backed measurements and missing inputs—not a response verdict.

Useful primary references:

- [DICOMweb standard overview](https://www.dicomstandard.org/using/dicomweb/)
- [DICOM Spatial Registration](https://dicom.nema.org/medical/dicom/current/output/html/part03.html)
- [DICOM confidentiality profiles](https://dicom.nema.org/medical/dicom/current/output/html/part15.html)
- [RANO 2.0 primary paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC10860967/)
- [Pediatric brain tumor imaging white paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC10466217/)
- [FDA clinical decision support boundary](https://www.fda.gov/medical-devices/digital-health-center-excellence/step-6-software-function-intended-provide-clinical-decision-support)
