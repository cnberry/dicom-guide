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

## Completed in the fourth milestone

1. Added DICOM patient-orientation labels derived locally from validated Image
   Orientation (Patient) geometry; invalid geometry produces no labels.
2. Added manual elliptical ROI overlays with major/minor diameters and 2D ellipse area
   in trusted patient-space units.
3. Added v3 source-linked measurement packets, v1/v2 import compatibility, ROI
   geometry/result validation, save/reopen restoration, and numeric-only agent
   comparison.
4. Verified the full ROI export/validate/reopen path with a synthetic local DICOM
   stack and no external runtime request.

## Completed in the fifth milestone

1. Added per-viewport local key-image ZIP export with a watermarked PNG, exact
   opaque source/presentation provenance, and a source-scoped v3 measurement packet.
2. Added local SHA-256 cross-links plus strict agent validation of archive contents,
   PNG structure/dimensions, measurement integrity, and exact source-instance match.
3. Added a versioned JSON Schema for the key-image evidence contract using opaque
   source IDs and no source paths or DICOM UIDs.
4. Verified the production browser export and agent validation round-trip on a
   synthetic native MR stack with an ROI, no browser errors, and no external calls.

## Completed in the sixth milestone

1. Added local clinician visit-packet assembly from two explicitly selected,
   validated key-image archives with no external service or patient-data mutation.
2. Added hard gates for one matching opaque patient context, distinct source studies
   and series, MR↔MR or CT↔CT, valid chronological acquisition dates, and correct
   baseline/follow-up display roles.
3. Added a versioned agent schema, SHA-256/byte-count manifest, nested evidence
   validation, static-template validation, and privacy-minimized CLI summary.
4. Added a script-free responsive/printable review page with both images, dates,
   sequences, source slices, clinician questions/checklist, and permanent safety
   labeling; numeric results and candidate interpretations remain empty.
5. Verified assemble/validate and human rendering end to end with synthetic MR key
   images, no scripts or external links, and only loopback page/PNG requests.
6. Added locally derived opaque patient context to both catalog paths, blocked
   cross-patient viewer/agent suggestions, and verified the complete copied dataset
   resolves to one context without emitting raw identifiers.

## Completed in the seventh milestone

1. Added one-click clinician visit-packet export from the two live viewer panes while
   retaining the Python assembler as the sole authoritative longitudinal gate.
2. Added a bounded two-member ZIP transport and authenticated exact-origin loopback
   POST that assembles and recursively validates the result entirely in memory.
3. Refactored each viewport to expose its current source-linked key-image archive
   without forcing a separate download; the existing individual export remains.
4. Added transport, safety-gate, same-origin, and successful HTTP round-trip tests.
5. Verified the production viewer end to end on two synthetic dated MR studies: the
   downloaded nine-file packet passed every local integrity check and the service
   created no patient-data output file.

## Completed in the eighth milestone

1. Added a strict local MPR eligibility gate for MR/CT source count, Frame of
   Reference, matrix, pixel spacing, orthonormal orientation, patient positions, and
   regular projected slice spacing.
2. Added Cornerstone streaming-volume construction and axial, coronal, and sagittal
   orthographic viewports with wheel navigation, window/level, pan, zoom, and reset.
3. Added visible derived/interpolated/not-registered/not-for-diagnosis labeling and
   kept measurement/key-image evidence export on authoritative native source panes.
4. Verified synthetic three-plane rendering, controls, cleanup, and reopen using
   only loopback source instances and bundled assets.
5. Verified a 62-slice copied JPEG 2000 MR series through the bundled OpenJPEG codec
   without retaining a patient screenshot or creating a derivative file.

## Completed in the ninth milestone

1. Added physically linked crosshairs that move one DICOM patient-space point across
   the axial, coronal, and sagittal planes of a single local source volume.
2. Added an accessible live LPS coordinate display with explicit axis semantics for
   people and browser-operating agents.
3. Used Cornerstone minimal mode to suppress oblique rotation and slab-thickness
   controls while retaining point jumps, line translation, and canonical planes.
4. Verified point movement, tool switching, reset, cleanup, reopen, three-plane SVG
   rendering, and loopback-only requests with a synthetic 24-slice volume.
5. Repeated movement and reset against a copied 62-slice JPEG 2000 MR series through
   bundled OpenJPEG without retaining or displaying a patient screenshot.

## Completed in the tenth milestone

1. Added a human/agent measurement workspace that can strictly validate bounded
   pasted JSON without an operating-system file picker or external API.
2. Added session-only annotation deletion using stable tracking-ID mapping; source
   DICOM and previously exported drafts remain unchanged.
3. Added explicit baseline/follow-up measurement selection, a normalized working
   lesion label, and local numeric preview/export with no response category.
4. Extended the v1 comparison schema and Python builder for optional bounded labels,
   then added a privacy-minimized validator that rechecks arithmetic, metric sets,
   sources, review state, and the empty-interpretation invariant.
5. Verified a two-study synthetic MR workflow end to end: strict paste, overlay
   hydration, 20→16 mm selection, −4 mm/−20% preview, schema/agent validation,
   deletion, and loopback-only resource access.

## Completed in the eleventh milestone

1. Added a local seven-file comparison-review ZIP that recursively validates and
   embeds the visit packet, normalized numeric comparison, both key images, a static
   printable review page, and a v1 review record.
2. Added exact visible-evidence joins: baseline/follow-up tracking ID, series,
   instance, measurement type, unit, and every metric value must agree before a
   review artifact can be assembled.
3. Added explicit self-attested human review choices for same-lesion identity,
   acquisition suitability, measurement placement, and response-criteria context;
   identity and credentials remain visibly unverified.
4. Added non-overwriting amendment and review commands. Event hashes bind actor,
   checklist, note, source comparison, prior event, and parent archive; an amended
   comparison always resets review state to `unreviewed`.
5. Added privacy-minimized validation, a v1 JSON Schema, 6 end-to-end tests, and
   browser QA of the script-free human page using synthetic evidence and only local
   image requests.

## Completed in the twelfth milestone

1. Added one-click comparison-review export from the live unified viewer using the
   current explicit measurement pair and its two exact source instances.
2. Added deterministic source-instance lookup and automatic pane restoration; export
   stays disabled when either displayed slice does not match the selected evidence.
3. Added a same-origin, authenticated, bounded three-member transport and local
   `/v1/comparison-reviews` route that builds the nested visit packet and final
   seven-file review ZIP entirely in memory with `no-store`.
4. Added service, source-index, transport-integrity, same-origin, and HTTP round-trip
   tests plus production-browser QA of the complete local synthetic workflow.

## Completed in the thirteenth milestone

1. Added a versioned `viewer-link` agent command that validates exact opaque
   series/instance membership and emits a bounded local-only navigation intent.
2. Added optional exact baseline/follow-up targets to `launch`, including direct
   authenticated startup at the requested native source slices.
3. Added a strict one-use browser fragment parser with a four-field allowlist,
   all-or-none local catalog resolution, immediate URL cleanup, and unchanged
   compatibility/review gates.
4. Moved stack-index ownership to the parent viewer so exact agent selections survive
   renderer initialization while ordinary human series selection still opens at the
   explicit midpoint.
5. Added a v1 JSON Schema, Python/TypeScript safety tests, and production-browser QA
   proving exact slice application, malformed-target refusal, clean URLs, and no
   fragment or opaque navigation references in HTTP logs.

## Completed in the fourteenth milestone

1. Added a visible **Agent state** control that is off by default and available only
   in the authenticated unified local workspace.
2. Added strict browser publication of opaque current pane positions, active tool,
   link state, optional MPR series, and evidence counts—never pixels, descriptions,
   dates, measurement values/labels/geometry, paths, or direct identifiers.
3. Added bearer-authenticated `GET /v1/viewer-state`, exact-origin bounded publication,
   independent local-catalog validation, `no-store`, and a 30-second memory-only TTL.
4. Made opt-out race-safe by revoking each ephemeral publisher ID before a later
   opt-in; stale in-flight updates cannot silently restore sharing.
5. Added a versioned response schema plus server, validation, privacy, transport,
   expiry, and browser-publisher tests.

## Completed in the fifteenth milestone

1. Added a version-gated local 3D Slicer 5.12.3 computed revision 34627/runtime
   repository revision `9034c71`/BRAINSFit rigid-
   registration executor for explicitly attested same-opaque-context (identity
   unverified), same-modality chronological pairs.
2. Added pre/post-staging source SHA-256 checks, generic private DICOM staging,
   bounded headless execution, non-persisted diagnostics, a source-read-only
   application boundary, and non-overwriting output publication.
3. Added an owner-only six-file derivative bundle with exact source/output hashes,
   parsed NRRD/fixed-space geometry, a finite proper-rigid text ITK transform,
   transform direction, binary/runner provenance, exact parameters, limitations,
   empty computation/interpretation arrays, and no external API requested by ScanView.
4. Added a strict pending-QA state that keeps overlay, swipe, subtraction, and mask
   propagation locked; this milestone deliberately provides no acceptance command.
5. Added doctor/run/validate CLI commands, a v1 JSON Schema, and synthetic failure,
   process-group timeout, permission, transform/volume parsing, tamper, privacy,
   hard-pairing-gate, and output-integrity tests.

## Completed in the sixteenth milestone

1. Added an isolated, browser-capability registration-QA workspace that never exposes
   NRRDs to bearer-authorized agents and never loads the ordinary measurement or
   evidence-export viewer. The capability boundary does not prove human presence.
2. Added derived fixed/moving reference and registered-moving views with axial, coronal, and
   sagittal traversal, orientation labels, independent windows, opacity, swipe,
   checkerboard, edge comparison, qualitative landmark review, and physical-point
   residual tools—all computed locally.
3. Added strict accept/reject semantics: acceptance requires a self-attested trained
   clinician or medical physicist, every checklist item, full three-plane/four-mode
   coverage, at least three aligned qualitative landmarks, no material defect, and at
   least three spatially distributed 3-D landmark pairs within the fixed
   geometry-derived tolerance.
4. Added a non-overwriting, self-attested JSON review record that anchors all six live
   registration files and their geometry. Only exploratory shared-coverage overlay/swipe
   can be authorized; subtraction, masks, segmentation, resampled measurements, and
   response conclusions remain locked.
5. Added CLI/server/schema validation, cookie-versus-bearer authorization tests,
   tamper/refusal tests, 3-D local NRRD parsing, and a production-build browser smoke
   across all three planes and four QA modes. At that milestone, real Slicer and
   real-patient QA remained pending and were not claimed.

## Completed in the seventeenth milestone

1. Added a strict reviewed-registration display contract that requires one accepted,
   owner-only, unlinked review and its exact live six-file bundle. It binds review,
   event, bundle, manifest, transform, file, and geometry hashes while omitting reviewer
   name and organization.
2. Added `serve`/`launch --registration-review` plumbing, a browser-only reviewed
   context, same-descriptor file streaming, bearer-minimized status, and refusal of
   rejected, tampered, mismatched, missing, linked, malformed, or unsafe inputs.
   Reviewed mode suppresses pending-QA routes rather than reopening review authority.
3. Added a separate human display with patient-space axial/coronal/sagittal traversal,
   exact fixed/registered geometry checks, capped sequential loading, and only opacity
   and swipe. It identifies both NRRDs as derived, registered moving as resampled, and
   native DICOM as authoritative.
4. Made the shared-coverage limit explicit: the six-file bundle has no transformed
   pixel coverage mask, so authorization is reviewer-visual only and pixels outside
   visible overlap remain unauthorized.
5. Added mandatory OS-enforced network denial for Slicer execution: macOS uses a
   deny-all-network sandbox; supported 64-bit Linux requires `bwrap` private namespaces
   plus seccomp denial of socket creation, socket pairs, and io_uring. Weaker
   `unshare`-only execution fails closed with no unsandboxed fallback.

## Completed in the eighteenth milestone

1. Added dataset-aware Consult Prep mode for catalogs such as the current MRI+CT
   copy that contain no valid dated same-modality longitudinal source pair. Visible
   roles become Image A/Image B and no response pairing is suggested.
2. Disabled approximate cross-exam slice linking, longitudinal lesion-pair arithmetic,
   visit-packet export, and comparison-review export in that mode. Only optional
   verified shared-patient-position linking can activate. Viewer-state v1 publication
   is also disabled because its fields use longitudinal pane roles.
3. Added neutral consultation key-image v1 and clinician consultation-packet v1
   contracts. V1 requires exactly one MR plus one CT from distinct studies with one
   matching opaque patient context and explicitly asserts no chronology, alignment,
   lesion relationship, comparison, or response authority.
4. Bound every selected image to its exact live catalog position and stable guarded
   DICOM descriptor, rehashing the bytes during assembly. The static nine-file packet
   includes source byte/SHA anchors, fixed questions/limitations, empty computed and
   interpretation arrays, and no script or external resource.
5. Added non-overwriting CLI assembly/validation, bounded in-memory same-origin
   loopback export, strict schemas, hostile archive/JSON/source-tamper tests, and a
   real-copy visual smoke test with no retained patient derivative.

## Completed in the nineteenth milestone

1. Added a deterministic, non-overwriting offline runtime ZIP builder for macOS and
   Linux. It accepts only pinned `py3-none-any` wheels and packages the embedded UI,
   workers, codecs, 16 contracts, and `pydicom` 3.0.2 without patient data.
2. Added an exact eight-payload SHA-256 manifest, two-wheel hash-locked requirements,
   strict standard-library verifier, `pip --no-index --require-hashes` installer, and
   loopback launcher. Every launch also probes installed versions, embedded UI,
   schema count, and the neutral consultation contract before cataloging DICOM.
3. Added deterministic-shape, tamper, extra-file, unsafe/platform-wheel, and
   non-overwrite tests. A fresh macOS arm64 extraction installed entirely from the
   bundle with `PIP_NO_INDEX=1`, then the packaged launcher indexed and served one
   synthetic MR instance over loopback. No Linux runtime exists on this host, so Linux
   execution remains pending rather than inferred from the pure-Python wheel tags.
4. Kept trust claims narrow: the bundle requires host Python 3.11+, its build may fetch
   pinned dependencies, and its manifest is corruption evidence—not code signing,
   host-interpreter attestation, clinical validation, or medical-record identity.

## Completed in the twentieth milestone

1. Downloaded the official 3D Slicer 5.12.3 macOS amd64 DMG, matched its published
   SHA-512, verified DMG integrity and stapled notarization, and authenticated the
   mounted and installed app with Gatekeeper plus deep strict code-signature checks.
   The Developer ID is Kitware team `W38PE5Y733`; exact non-PHI evidence is committed
   in a human and machine-readable trust record.
2. Installed the x86_64 app under Rosetta 2 at `/Users/chris/Applications/Slicer.app`,
   recorded the launcher and BRAINSFit SHA-256 values, and confirmed the signed local
   copy remained unchanged after installation.
3. Corrected the engine gate: `34627` is Slicer's computed release revision, while
   the real runtime reports repository revision `9034c71`. The prior mismatch failed
   closed before source staging; doctor output, runtime checks, tests, schema, and
   agent documentation now name both values explicitly.
4. Ran the normal ScanView registration command on two private synthetic 16-slice MR
   studies through the real official Slicer/BRAINSFit process under mandatory macOS
   deny-all-network isolation. All 32 source hashes remained identical, the known
   synthetic translation was recovered, and the validated six-file bundle stayed
   `generated_pending_qa`/`unreviewed` with every display unlock false.
5. Loaded those real-engine NRRDs in the isolated local QA viewer. Axial, coronal,
   sagittal, opacity, swipe, checkerboard, and edge views rendered without browser
   errors or external requests. No decision was submitted, no patient data was used,
   and synthetic inputs/derivatives were moved to recoverable Trash.

## Immediate

1. Use the consultation packet only to prepare questions with Mila's clinicians;
   confirm the correct MRI and CT source views in the clinical imaging system and do
   not treat the packet as a diagnosis or treatment-response analysis.
2. Import a future same-modality MRI follow-up, have a person confirm the intended
   earlier/later sequences and clinical roles, run the required engine on that pair,
   and complete qualified visual/quantitative QA.
3. Protect the authenticated local Slicer installation and keep using the recorded
   launcher hash; reauthenticate any replacement before a future patient-specific job.
4. Repeat engine, production packaging, and real-codec smoke tests on Linux without
   exposing metadata or screenshots.
5. Produce signed/notarized macOS/Linux release artifacts around the verified offline
   bundle, and evaluate whether to include a separately authenticated interpreter.
6. Design optional authenticated signature integration for clinical organizations;
   never relabel the current self-attested hash chain as identity verification.
7. Design an append-only, privacy-minimized local audit for bearer access to live
   viewer state without recording patient content or putting tokens in logs.
8. Add an explicit transformed moving-coverage mask to a future registration bundle so
   reviewed display can enforce shared coverage pixel by pixel rather than visually.

## Next milestone

1. Add Orthanc as an optional DICOMweb archive and pin/test its local configuration.
2. Prototype an OHIF longitudinal ScanView mode instead of forking OHIF.
3. Add explicit compatibility/QA badges to the local clinician visit packet and
   comparison-review page.
4. Extend append-only audit records from review decisions to local evidence access.
5. Smoke-test the same offline artifact on Linux x86_64, then add platform signing and
   notarization without weakening local-only runtime behavior.
6. Prototype a source-bound 2–8 image consultation evidence board with explicit
   clinician-selected labels, while retaining the no-comparison/no-interpretation
   default and exact DICOM provenance.

## Registration milestone

1. Repeat the completed macOS real-Slicer verification on Linux, including distributor
   signature/checksum verification for the complete engine bundle and mandatory
   namespace/seccomp execution.
2. Perform the implemented QA workflow on a valid real same-modality pair with a
   qualified reviewer and a predeclared clinically appropriate landmark tolerance.
3. Verify the implemented accepted-record display on a real reviewed bundle; never
   overwrite originals and never unlock subtraction or masks.

## Decisions needed with clinicians

- Mila's diagnosis/pathology and which pediatric or adult response criteria apply.
- Which MRI sequence is the intended longitudinal primary series.
- Preferred baseline, nadir/best-response convention, and confirmation timing.
- Tumor component definitions and measurement/segmentation method.
- What evidence packet format is most useful in neurosurgery/neuro-oncology visits.
