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

The local execution foundation requires [3D Slicer 5.12.3 computed revision
34627](https://github.com/Slicer/Slicer/wiki/Release-Details), whose full Git commit is
`9034c71a8fce68ab312458b3d7d16f610562263d` and whose running application reports
`slicer.app.repositoryRevision` as `9034c71`. This distinction is now explicit in the
doctor output and runner gate. Slicer's official
[headless scripting guidance](https://slicer.readthedocs.io/en/latest/developer_guide/script_repository/gui.html)
supports `--no-splash --no-main-window --python-script`; ScanView additionally uses
`--disable-settings`, `--ignore-slicerrc`, and `PYTHONNOUSERSITE=1`, and never
downloads or contacts a processing service. This prevents Slicer settings, its
documented automatic user startup script, or user-site packages from changing the
required version-gated job.

The launcher must match a caller-supplied expected SHA-256 before DICOM staging and
again after execution. This protects against accidental substitution relative to an
independently recorded digest, but the generic runtime check does not authenticate the
distributor, code signature, SlicerApp-real process, BRAINSFit/BRAINSResample binaries, or dependent
libraries. For this macOS host, the official 447,327,067-byte DMG's published SHA-512
matched exactly; DMG integrity/stapled notarization, Gatekeeper assessment, deep strict
app signature, Kitware team identity, launcher hash, and BRAINSFit/BRAINSResample hashes were verified
before installation. Exact evidence and its limitations are recorded in
[`SLICER-ENGINE-TRUST.md`](SLICER-ENGINE-TRUST.md). The official Linux package is now
verified on Strawberry by immutable bitstream, byte count, and published SHA-512, but
Slicer's documented Linux release process provides no independent package signature.
ScanView requires OS-enforced network isolation for the child: a macOS deny-all-network
sandbox or, on supported 64-bit Linux, `bwrap` private namespaces plus seccomp that
allows only local `AF_UNIX` IPC and rejects network socket domains and io_uring. Linux
uses private Xvfb with TCP disabled. ScanView refuses inherited displays, weaker
`unshare`-only execution, and unsandboxed fallback.

The runner uses Slicer's official temporary local [DICOM database/import
helpers](https://slicer.readthedocs.io/en/latest/developer_guide/script_repository/dicom.html)
and invokes the bundled [BRAINSFit](https://slicer.readthedocs.io/en/latest/user_guide/modules/brainsfit.html)
module. The initial contract is six-degree-of-freedom rigid registration, center-of-
head initialization, automatic ROI masking with 3 mm dilation, 2% sampling, and
linear interpolation. Histogram matching is disabled: BRAINSFit's own guidance warns
that changing tumors or lesions can make histogram matching problematic. Generated
results still require patient-specific visual and quantitative QA.

The v2 engine also requires the bundled BRAINSResample module. It creates a constant-one
uint8 image on the native moving grid and resamples that technical domain through the
same BRAINSFit transform onto the fixed reference grid with nearest-neighbor sampling
and outside value zero. The host then decodes the complete result, requires only `0`
and `1`, rejects empty support, and records recomputed counts. This establishes where
the pinned local resampler found moving-image sampling support; it does not establish
shared anatomy, tumor extent, segmentation, registration quality, or clinical
comparability. Browser reformatting keeps the mask nearest-neighbor and never expands
its boundary through smoothing.

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

The authenticated official macOS engine is installed locally and passed the no-data
preflight plus real synthetic same-modality MR registrations through
Slicer/BRAINSFit/BRAINSResample under the mandatory deny-all-network sandbox. Source
bytes remained unchanged, the expected approximately -2 mm translation was recovered,
and a mismatched-field-of-view case produced exactly 65,536 supported voxels out of
69,632 fixed-grid voxels. The seven-file v2 bundle validated with all derivative-use
flags locked; a separately synthetic accepted review then exercised local mask-gated
opacity/swipe in all three planes with no browser errors or non-loopback requests. No
patient data was used. Strawberry independently passed the offline Ubuntu 26.04 x86_64
runtime, loopback UI/catalog, bubblewrap private namespaces, AF_UNIX-only seccomp,
private no-TCP Xvfb, Linux atomic no-replace publication, and the real official Slicer
5.12.3 equal-/partial-field registrations. Both Linux masks and transforms matched the
macOS synthetic oracles and sources stayed unchanged. Real same-modality patient QA
remains pending; it has no cloud fallback.

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
