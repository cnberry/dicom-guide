# Series guide

Use this as a routing aid, not a diagnostic rule. Verify the actual DICOM metadata and
visible image. Vendor names vary, and TR/TE/TI ranges depend on scanner and protocol.

## MRI

| Likely series | What it commonly emphasizes | Important caution |
| --- | --- | --- |
| T1 pre-contrast | Anatomy, fat, marrow, and baseline signal before contrast | Fluid is often dark; brightness alone does not identify tissue |
| T1 post-contrast | Areas of enhancement, vessels, and blood-brain-barrier disruption | Enhancement is nonspecific and must be compared with pre-contrast T1 |
| T2 | Water-rich tissue, fluid, edema, cystic components, and broad lesion extent | CSF is usually bright and can obscure adjacent T2-bright abnormality |
| T2 FLAIR | T2-like abnormalities near suppressed dark CSF; edema and many white-matter lesions | Incomplete suppression, motion, and treatment effects can mimic abnormal signal |
| DWI with ADC | Restricted diffusion; useful in acute ischemia and some highly cellular or purulent processes | Confirm high DWI with low ADC; DWI alone can show T2 shine-through |
| GRE or SWI | Susceptibility from blood products, veins, mineralization, or metal | MRI may not reliably separate calcium from blood products; CT can help |
| Perfusion | Relative blood flow or blood volume, depending on technique | Requires technique-specific processing and careful quality checks |
| Spectroscopy | Metabolite patterns within a selected voxel or region | Sampling and processing matter; it does not replace tissue diagnosis |
| Localizer/scout | Planning later acquisitions | Usually low-resolution and not the primary series for interpretation |
| MPR/reformat | Orthogonal views reconstructed from one 3D acquisition | It is not a separately acquired sequence and inherits source limitations |

Useful MRI metadata clues include `SeriesDescription`, `ProtocolName`, contrast agent
context, `RepetitionTime`, `EchoTime`, `InversionTime`, `FlipAngle`, orientation,
spacing, and whether a series is derived. Do not identify contrast solely from bright
tissue; compare labels and pre/post acquisitions.

## CT

| Likely series | What it commonly emphasizes | Important caution |
| --- | --- | --- |
| Non-contrast CT | Attenuation, acute blood, calcification, bone, mass effect, and fluid spaces | Window and level strongly affect what is visible |
| Contrast-enhanced CT | Enhancement of vessels, organs, and some lesions | Compare with non-contrast imaging when available before calling enhancement |
| Soft-tissue/brain window | Parenchyma and soft-tissue contrast | Bone detail may be clipped |
| Bone window/reconstruction | Cortex, fracture, mineralization, and fine bone detail | Soft-tissue contrast is intentionally reduced |
| Coronal/sagittal reformat | Spatial relationships in another plane | Usually derived from the same acquisition, not an independent scan |
| Scout/topogram | Scan planning | Not a diagnostic cross-sectional series |

For CT, check contrast context, reconstruction kernel, slice thickness, pixel spacing,
image type, and window presets. A window preset changes display, not source values.

## Choosing a series

- Anatomy and location: begin with a high-quality structural series and use MPR when
  its geometry supports it.
- Reported enhancement: compare matched T1 pre- and post-contrast MRI, or matched CT
  acquisitions when present.
- Edema or non-enhancing T2 signal: inspect T2 and FLAIR together.
- Restricted diffusion: inspect DWI and ADC together.
- Blood products or mineralization: inspect GRE/SWI and CT when available.
- Fine boundaries: verify on native acquisition slices, not only MPR.
- Change over time: do not compare measurements until studies are appropriately
  matched, registered, and quality-reviewed.
