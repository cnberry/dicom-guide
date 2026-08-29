# Cross-platform DICOM viewer research

Research updated: 2026-08-29. Viewer/standard research used only public project
documentation and repositories. A separate privacy-minimized structural inspection of
the copied media ran locally: no DICOM bytes, identifiers, annotation text, coordinates,
pixels, paths, or derived patient artifact left this computer or entered Git.

## DICOM presentation states used in v0.9

The copied media contains seven Grayscale Softcopy Presentation State objects. A
privacy-minimized local inspection found that all seven use zero rotation, no
horizontal flip, identity presentation LUT, no shutter, one intended full-image SCALE
TO FIT display area, and one linear VOI. Six contain annotations; together they contain 19
PIXEL POLYLINE objects and nine anchor-text objects. The one SR object is an X-Ray
Radiation Dose SR with numeric dose content, not a diagnostic radiology report.

The final strict v0.9 gate withholds all seven states: their displayed-area far corner
uses dimensions-plus-one, while DICOM defines the full image from `(1,1)` through
exactly `(Columns,Rows)`. ScanView records only the aggregate lock reason and continues
to render native MR/CT images; it does not approximate the vendor convention.

The current DICOM Graphic Annotation Module defines PIXEL coordinates relative to the
top-left corner of the top-left pixel as `(0,0)`; the bottom-right corner is
`(Columns,Rows)`. POLYLINE data is ordered as x/y pairs and consecutive points are
connected. This is why ScanView subtracts 0.5 before converting a DICOM corner
coordinate to a Cornerstone image-data index center. See [DICOM PS3.3 C.10.5](https://dicom.nema.org/medical/DICOM/current/output/chtml/part03/sect_C.10.5.html).

The DICOM Displayed Area Module defines the top-left displayed pixel as `(1,1)`, the
bottom-right displayed pixel as a one-based column/row, and an explicit presentation
pixel aspect that may override image spacing. ScanView accepts only exact
`(Columns,Rows)` with a presentation aspect proven equal to the local source display;
vendor dimensions-plus-one, cropping, aspect overrides, and scoped areas fail closed.
See [DICOM PS3.3 C.10.4](https://dicom.nema.org/medical/dicom/current/output/chtml/part03/sect_C.10.4.html).

GSPS defines the grayscale pipeline from stored values through modality, VOI, and
presentation LUTs, and overrides image presentation transforms. ScanView therefore
supports only single-frame monochrome sources whose linear modality transform exactly
matches the GSPS, forces LINEAR VOI and identity-presentation polarity in Cornerstone,
and rejects masks, overlays, subtraction, lookup tables, and source-transform drift.
See [DICOM PS3.4 N.2](https://dicom.nema.org/medical/dicom/2024a/output/chtml/part04/sect_N.2.html)
and [DICOM PS3.3 C.11.8](https://dicom.nema.org/medical/dicom/current/output/chtml/part03/sect_c.11.8.html).

DICOM requires referenced grayscale images to be in the presentation state's study;
ScanView enforces the same-study and one-patient-context relationship and rejects
frame-scoped references until frame navigation is implemented. See
[DICOM PS3.4 N.1](https://dicom.nema.org/medical/dicom/2025e/output/chtml/part04/chapter_N.html)
and [DICOM PS3.3 C.11.11](https://dicom.nema.org/medical/dicom/current/output/chtml/part03/sect_c.11.11.html).

Cornerstone's current stack viewport exposes `worldToCanvas()` for mapping a patient-
space point to the live canvas. ScanView first uses the active image data's
`indexToWorld()` mapping and then `worldToCanvas()`, so the overlay follows camera
zoom and pan. See [Cornerstone IStackViewport](https://www.cornerstonejs.org/docs/api/core/namespaces/types/classes/istackviewport/).

The implementation is intentionally smaller than full GSPS. It does not implement
rotation, flip, crop, shutters, masks, overlays, lookup-table transforms,
displayed-area/VOI scoping, multi-frame references, compound or filled
graphics, bounding-box text, graphic-layer styling, or author authentication. It
uses a fixed high-contrast local style, so it does not claim vendor color/style/layer
fidelity, authenticated creator identity, or assessed clinical meaning. The DICOM
[creator identification macro](https://dicom.nema.org/medical/Dicom/2024b/output/chtml/part03/sect_10.9.3.html)
and [digital-signature profiles](https://dicom.nema.org/medical/dicom/current/output/chtml/part15/sect_c.3.html)
are not verified by this milestone.

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
- `@cornerstonejs/adapters`: 5.8.2
- `dcmjs`: 0.52.0
- `dicom-parser`: 1.8.21
- Vite: 8.2.2
- Vitest: 4.1.11
- pydicom: 3.0.x

`@cornerstonejs/adapters` currently brings deprecated `core-js` 2.6.12 transitively.
It is bundled only at build time and no dependency install script is allowed, but the
pin remains a dependency/license review item before a signed distribution.

## Source-carried DICOM SEG import used in v0.10

DICOM Segmentation is a multi-frame derived image object. Its Image Module defines
binary and fractional segmentations, segment-number semantics, foreground values, and
pixel-data constraints; the Segmentation IOD and functional-group table define the
required shared/per-frame relationships. See [DICOM PS3.3 C.8.20.2](https://dicom.nema.org/medical/dicom/current/output/chtml/part03/sect_C.8.20.2.html),
[PS3.3 A.51](https://dicom.nema.org/medical/dicom/current/output/chtml/part03/sect_A.51.html),
and [PS3.3 A.51.5](https://dicom.nema.org/medical/dicom/current/output/chtml/part03/sect_A.51.5.html).

ScanView v0.10 implements a deliberately narrow reader profile, not a general DICOM
SEG conformance claim. It accepts only uncompressed binary SEG using Explicit or
Implicit VR Little Endian; one referenced MR/CT series; single-frame sources; an exact
regular native matrix/orientation/position/spacing grid; standard segmentation
derivation and source-purpose codes; `SpatialLocationsPreserved=YES`; and coherent
segment/plane dimension indexes. It refuses fractional or compressed objects,
resampling, multiframe sources, inconsistent or missing references, duplicate planes,
tilted/drifting grids, and objects beyond fixed decoded-work and retained-mask limits.

Sparse frames are locally unpacked into a dense source-ordered 0/1 mask. The Python
reader hashes every stable source descriptor and computes voxel count and native-grid
volume; the browser independently checks physical slice order, permissions, hashes,
binary bytes, counts, geometry, and arithmetic before creating a read-only labelmap.
There is no upload or processing API, and ScanView does not modify or emit a new SEG.
The display does not authenticate the creator, validate the algorithm, establish that
a segment is tumor, quantify boundary uncertainty, or authorize diagnosis or response.

The next interoperability gate is an independently produced highdicom/vendor fixture
and comparison in an established viewer such as 3D Slicer or Weasis. Until that passes,
support means only the fixed ScanView profile above.

## Manual ROI DICOM SEG profile

DICOM defines Segmentation objects as pixel classifications derived from referenced
images and permits segmentation sampling that differs from the source
([PS3.3 A.51](https://dicom.nema.org/medical/dicom/current/output/chtml/part03/sect_a.51.html)).
ScanView v1 deliberately chooses a narrower profile: one binary, manually entered
segment on the exact regular native source grid, uncompressed Explicit VR Little
Endian, with sparse SEG frames permitted only when each one resolves to an exact
source SOP class/instance and plane position. The sidecar keeps the complete ordered
source-byte set so an independent local validator can rebuild the dense mask and
recompute volume.

The pinned Cornerstone adapter is post-processed locally before serialization. Its
5.8.2 binary-SEG path omits the per-frame source SOP Class and required derivation/
purpose codes, can associate sparse source UIDs with reversed plane positions, uses
projected spacing as Slice Thickness, and byte-pads sub-byte frames individually.
ScanView repairs those fields from the exact loaded source geometry and repacks the
complete multi-frame bitstream. DICOM requires native multi-frame frames to be
concatenated without per-frame padding, with padding applied only to the complete
Pixel Data value ([PS3.5 8.2](https://dicom.nema.org/medical/dicom/current/output/chtml/part05/sect_8.2.html)).
Slice Thickness remains distinct from projected center-to-center spacing: the former
is preserved in SEG Pixel Measures while volume arithmetic uses the latter. A real-
adapter Part-10 fixture is validated cross-language by pydicom to prevent either
implementation from becoming its own oracle.

DICOM defines `MANUAL` as a user-entered segment and specifies Segment Label, coded
property, Tracking ID, and Tracking UID semantics
([PS3.3 C.8.20.4](https://dicom.nema.org/medical/dicom/current/output/chtml/part03/sect_c.8.20.4.html));
for a binary SEG, a stored value of one means the represented property is present at
that pixel
([PS3.3 C.8.20.2.3](https://dicom.nema.org/medical/dicom/current/output/chtml/part03/sect_c.8.20.2.3.html)).
ScanView uses generic SCT abnormal-structure and lesion concepts from
[CID 7150](https://dicom.nema.org/medical/dicom/current/output/chtml/part16/sect_cid_7150.html)
and [CID 7159](https://dicom.nema.org/medical/dicom/current/output/chtml/part16/sect_cid_7159.html).
They are interoperability coding, not proof of neoplasm, malignancy, histology,
enhancement, tumor component, or diagnosis.

Volume is binary foreground count multiplied by the determinant of the native
source-grid voxel dimensions. Source geometry follows DICOM Pixel Spacing, Image
Position (Patient), and Image Orientation (Patient) semantics
([PS3.3 C.7.6.2](https://dicom.nema.org/medical/dicom/current/output/chtml/part03/sect_c.7.6.2.html)).
Boundary uncertainty, partial-volume effects, acquisition suitability, and represented
tissue are not quantified. V1 exports SEG plus JSON, not a DICOM Structured Report.
A future interoperable numeric path should evaluate a TID 1500 Measurement Report
with a [TID 1411 Volumetric ROI measurement group](https://dicom.nema.org/medical/dicom/current/output/chtml/part16/sect_tid_1411.html),
not silently treat the v1 sidecar as SR.

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
