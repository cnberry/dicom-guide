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

## Registration engine verification

The local execution foundation requires [3D Slicer 5.12.3 revision
34627](https://github.com/Slicer/Slicer/wiki/Release-Details), the current stable
release documented for macOS and Linux on the research date. Slicer's official
[headless scripting guidance](https://slicer.readthedocs.io/en/latest/developer_guide/script_repository/gui.html)
supports `--no-splash --no-main-window --python-script`; ScanView additionally uses
`--disable-settings`, `--ignore-slicerrc`, and `PYTHONNOUSERSITE=1`, and never
downloads or contacts a processing service. This prevents Slicer settings, its
documented automatic user startup script, or user-site packages from changing the
required version-gated job.

The launcher must match a caller-supplied expected SHA-256 before DICOM staging and
again after execution. This protects against accidental substitution relative to an
independently recorded digest, but it does not authenticate the distributor, macOS
code signature, Linux package, SlicerApp-real process, BRAINSFit binary, or dependent
libraries. End-to-end official-release signature/checksum verification remains a
required packaging milestone. ScanView now requires OS-enforced network isolation for
the child: a macOS deny-all-network sandbox or, on supported 64-bit Linux, `bwrap`
private namespaces plus a seccomp filter denying socket creation, socket pairs, and
io_uring. It refuses weaker `unshare`-only execution and has no unsandboxed fallback.

The runner uses Slicer's official temporary local [DICOM database/import
helpers](https://slicer.readthedocs.io/en/latest/developer_guide/script_repository/dicom.html)
and invokes the bundled [BRAINSFit](https://slicer.readthedocs.io/en/latest/user_guide/modules/brainsfit.html)
module. The initial contract is six-degree-of-freedom rigid registration, center-of-
head initialization, automatic ROI masking with 3 mm dilation, 2% sampling, and
linear interpolation. Histogram matching is disabled: BRAINSFit's own guidance warns
that changing tumors or lesions can make histogram matching problematic. Generated
results still require patient-specific visual and quantitative QA.

The local QA design is adapted from [AAPM TG-132 registration QA
concepts](https://www.aapm.org/pubs/reports/detail.asp?docid=164): verify the exact
patient dataset both qualitatively and quantitatively, traverse the full shared
coverage, use multiple complementary comparison methods, and inspect both the region
of importance and distant stable anatomy. It is not represented as TG-132 compliance,
commissioning, or clinical validation. The display methods follow Slicer's documented
local [Compare Volumes](https://slicer.readthedocs.io/en/latest/user_guide/modules/comparevolumes.html)
and [CheckerBoard](https://slicer.readthedocs.io/en/5.8/user_guide/modules/checkerboardfilter.html)
patterns: native and registered side-by-side views, linked anatomical planes, opacity,
swipe, checkerboard, and edges. Landmark residuals remain location-specific
supplemental evidence. Any spatial authorization must be limited to the exact hashed
transform and shared coverage; it cannot establish lesion identity or response.

No required Slicer executable is installed on the current host, so the wrapper and
bundle have been tested with a synthetic engine double but not yet with a real Slicer
process. This limitation is explicit in status and does not trigger a download or
cloud fallback.

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
