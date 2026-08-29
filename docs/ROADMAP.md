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
3. Added an owner-only six-file v1 derivative bundle with exact source/output hashes,
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
4. Added a non-overwriting, self-attested v1 JSON review record that anchors all six
   live registration files and their geometry. Only exploratory shared-coverage overlay/swipe
   can be authorized; subtraction, masks, segmentation, resampled measurements, and
   response conclusions remain locked.
5. Added CLI/server/schema validation, cookie-versus-bearer authorization tests,
   tamper/refusal tests, 3-D local NRRD parsing, and a production-build browser smoke
   across all three planes and four QA modes. At that milestone, real Slicer and
   real-patient QA remained pending and were not claimed.

## Completed in the seventeenth milestone

1. Added a strict v1 reviewed-registration display contract that requires one accepted,
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
4. Made the then-current v1 shared-coverage limit explicit: the six-file bundle had no
   transformed pixel coverage mask, so authorization was reviewer-visual only and
   pixels outside visible overlap remained unauthorized. The v2 contract added in the
   twenty-second milestone now fails v1 closed and enforces sampling support per pixel.
5. Added mandatory OS-enforced network denial for Slicer execution: macOS uses a
   deny-all-network sandbox; supported 64-bit Linux requires `bwrap` private namespaces
   plus seccomp rejection of network socket domains and io_uring. Only local `AF_UNIX`
   IPC is allowed for the private no-TCP Xvfb display. Inherited displays and weaker
   `unshare`-only execution fail closed with no unsandboxed fallback.

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
   synthetic translation was recovered, and the validated historical v1 six-file bundle stayed
   `generated_pending_qa`/`unreviewed` with every display unlock false.
5. Loaded those real-engine NRRDs in the isolated local QA viewer. Axial, coronal,
   sagittal, opacity, swipe, checkerboard, and edge views rendered without browser
   errors or external requests. No decision was submitted, no patient data was used,
   and synthetic inputs/derivatives were moved to recoverable Trash.

## Completed in the twenty-first milestone

1. Added a source-bound clinician consultation board for 2–8 explicitly selected
   neutral native key images. It requires one matching opaque patient context, both
   MR and CT, at least two studies, and a distinct source instance for every item.
2. Added bounded, Unicode-safe person-entered discussion headings and ordered
   move/remove controls. Headings are permanently identified as unreviewed prompts,
   not observations, findings, lesion identities, or clinical conclusions.
3. Added strict CLI assembly/validation and an authenticated exact-origin loopback
   endpoint. Every nested archive, catalog position, guarded source descriptor, and
   DICOM SHA-256 is revalidated locally; hostile ZIPs, source mutation, oversized
   expansion, ambiguous members, and privacy-leaking failures are refused.
4. Added a script-free responsive/printable board plus a strict v1 agent contract and
   privacy-minimized summary. Computed and interpretation arrays remain empty, and no
   chronology, alignment, registration, lesion linkage, diagnosis, comparison, or
   treatment-response authority is created.
5. Verified the production workflow on synthetic MR/CT DICOM: both local pixels
   rendered, the readiness gates activated, the downloaded nine-file board passed all
   integrity flags, browser diagnostics were empty, and server traffic stayed on
   loopback. Synthetic sources and output were moved to recoverable Trash.
6. Promoted “no external DICOM-processing API and no cloud fallback” to a release
   invariant. The rebuilt deterministic offline bundle now verifies the consultation-
   board contract, all 17 then-current schemas, embedded UI, pinned local dependency, and explicit
   `runtime_network_required: false` and
   `external_dicom_processing_api_required: false` assertions before cataloging.

## Completed in the twenty-second milestone

1. Upgraded registration generation to a strict seven-file v2 bundle. The authenticated
   local Slicer process now uses the pinned BRAINSFit transform to resample a constant-one
   moving-grid label map through BRAINSResample with nearest-neighbor interpolation,
   producing a uint8 binary sampling-support NRRD in exact fixed geometry.
2. Added full-payload host validation for raw or gzip NRRD masks, `{0,1}` values,
   nonempty support, exact geometry, recomputed voxel counts, provenance, hashes, and
   owner-only publication. V1 generation/review/display contracts remain historical
   and fail closed rather than silently acquiring v2 authority.
3. Bound the mask into the qualified QA checklist, accepted review, local server, and
   browser display contract. Opacity and swipe now use nearest-neighbor patient-space
   mask sampling, force fixed pixels wherever support is zero, and matte the standalone
   registered pane; no unmasked fallback exists.
4. Kept the evidence meaning narrow: the mask proves only where the pinned resampler had
   moving-image sampling support. It does not prove shared anatomy, tumor, segmentation,
   registration quality, clinical comparability, or treatment response, all of which
   remain outside machine authority or require qualified human review.
5. Re-ran the official authenticated macOS Slicer engine on private synthetic equal- and
   partial-field MR pairs. Both v2 bundles validated, the known translation was recovered,
   and the partial-field mask produced a nontrivial 65,536/69,632 support boundary. The
   pending-QA browser loaded four allowlisted local NRRDs and exercised the technical
   boundary in three planes plus four mask-gated comparison modes; the reviewed browser
   loaded its three allowlisted NRRDs for mask-gated opacity/swipe. Both had empty
   browser diagnostics and loopback-only page resources.
6. Verified the patient-free offline runtime on Strawberry Ubuntu 26.04 x86_64/Python
   3.14.4: no-index installation, embedded UI, all 20 schemas, local DICOM catalog/server,
   bubblewrap network namespaces plus the then-current no-socket seccomp probe, and
   atomic no-replace publication passed. Strawberry did not yet have the pinned Slicer
   engine at that milestone; the twenty-third milestone closes that execution gate.

## Completed in the twenty-third milestone

1. Pinned the immutable official Slicer 5.12.3 Linux amd64 bitstream, byte count, and
   published SHA-512. Strawberry's owner-only download matched all three, and a
   pre-extraction audit found one safe package root across 10,572 members and 385 links.
2. Installed the package owner-only on Strawberry Ubuntu 26.04 x86_64, recorded exact
   launcher/BRAINSFit/BRAINSResample hashes and ELF build IDs, and installed only the
   documented Ubuntu/Qt dependencies plus bubblewrap and private Xvfb support. Slicer's
   Linux process supplies no independent publisher signature, so trust remains
   explicitly official-source/checksum verified rather than signature verified.
3. Added a fail-closed headless Linux display path. ScanView refuses inherited displays,
   launches private Xvfb with TCP disabled inside bubblewrap's separate
   network namespace, permits only local `AF_UNIX` IPC in seccomp, and rejects network
   socket domains and io_uring. A live probe allowed `AF_UNIX` and denied `AF_INET`
   with `EPERM`; no X11 TCP listener remained.
4. Rebuilt the deterministic offline release with this production path. The owner-only
   5,340,464-byte ZIP has SHA-256
   `e6ca632f031268eed9139b2a70899c534f4f8a77cf75f3bf08ead86108c47c81`,
   verified, and installed on Strawberry with `PIP_NO_INDEX=1`, `--no-index`, and
   required hashes.
5. Ran normal real-engine equal- and partial-field synthetic MR registrations. Both
   owner-only seven-file v2 bundles validated, sources stayed byte-identical, every
   display use remained locked, and computed/interpretation arrays stayed empty. The
   transforms recovered -2.008290 mm and -1.998159 mm x translation; support was
   65,536/65,536 and 65,536/69,632 (94.117647%), matching the macOS oracles.
6. Used no Mila data on Strawberry and no external DICOM-processing API. The detailed
   human and machine-readable Linux provenance records are committed with the repo.

## Completed in the twenty-fourth milestone

1. Added one in-memory person-painted binary ROI shared across local axial, coronal,
   and sagittal views. Paint/erase, brush size, clearing, voxel count, and arithmetic
   mL display are available only for one strict single-frame native MR/CT grid.
2. Added a three-member source-bound evidence export: an uncompressed DICOM
   SEG-format object, a v1 JSON sidecar, and local instructions. Each export has one
   `MANUAL` segment, generic abnormal-structure/lesion coding, a new Tracking UID,
   ordered source-byte anchors, mask hash, and permanently unreviewed safety locks.
3. Added an independent `validate-lesion-volume` agent command. It reopens stable
   local source descriptors, rehashes every source, checks one exact study/series/
   Frame of Reference and strict native geometry, resolves DICOM SEG references,
   decodes sparse bit-packed frames, rebuilds the dense mask, and recomputes marked
   voxels and volume without an external API.
4. Added fail-closed archive, strict-JSON, size, source-change, geometry, DICOM
   reference, binary-mask, and arithmetic validation. `valid: true` is explicitly
   limited to source/format/geometry/mask/arithmetic checks; v1 has no approval state.
5. Exercised the production browser workflow with a synthetic three-slice MR series:
   one painted plane produced 64 voxels and 0.048 mL. A stricter release audit then
   found pinned-adapter omissions in source references, derivation semantics, sparse
   plane association, Slice Thickness, and sub-byte multi-frame packing. ScanView now
   repairs each item from exact loaded source geometry and has a real-adapter regression.
6. Added the 21st embedded JSON Schema and bundled the pinned local Cornerstone
   adapter/dcmjs runtime. The viewer retains no external processing or telemetry path;
   the offline installer and runtime remain package-index-free.
7. Passed the release-grade cross-language gate with actual dcmjs Part-10 bytes: the
   strict Python validator rejoined a sparse first/last-slice SEG to three exact source
   files, recovered 2 voxels and 4.0 mm³ / 0.004 mL, and rejected a one-byte source
   change with all computed values withheld. The deterministic versioned v0.2.0 offline
   ZIP then verified, installed with no package index, launched its loopback UI/catalog,
   and repeated the exact validation and tamper refusal on macOS arm64 and Strawberry
   Ubuntu x86_64/Python 3.14.4. No Mila data left the local computer.

## Completed in the twenty-fifth milestone

1. Added a separate four-file manual ROI boundary-review archive without mutating or
   upgrading the source v1 evidence. It embeds the exact evidence ZIP, one strict v1
   review record, a script-free printable page, and local instructions.
2. Added a qualified-role human form beside the live three-plane mask. It records
   represented tissue, inclusion/exclusion criteria, acquisition suitability, eight
   full-boundary checks, a decision, note, and fixed self-attestation; identity and
   credentials remain explicitly unverified.
3. Made `accepted_for_discussion` fail closed unless acquisition is suitable, every
   checklist item is true, all canonical planes are recorded, required definitions are
   present, and the source has one locally derived opaque patient context. Acceptance
   authorizes only single-timepoint discussion and future pairing-review input.
4. Added independent `validate-lesion-volume-review` validation. It enforces exact
   archive shape, strict JSON/text, file hashes, static-page safety and record equality,
   source-snapshot equality, then recursively reopens the DICOM SEG evidence and every
   original DICOM source descriptor before reporting its privacy-minimized state.
5. Kept longitudinal linkage, percentage change, response classification, diagnosis,
   clinical conclusion, identity authentication, and medical-record sign-off false for
   every review decision. Invalid or source-changed evidence withholds the volume and
   sets evidence use to `none`.
6. Found and fixed a production MPR race: editable labelmap derivation now waits for
   the bounded source-volume load so every image-plane metadata record exists. A local
   synthetic browser run rendered all three planes, painted 454 voxels / 0.908 mL,
   exercised the complete accepted-review form, and produced no browser errors.
7. The exact browser-produced archive passed the independent validator against all 12
   synthetic source objects. Changing one source byte failed nonzero and removed all
   volume and future-pairing authority. The v0.3.0 offline release embeds 22 schemas;
   macOS and Strawberry Linux package gates are recorded in Status.

## Completed in the twenty-sixth milestone

1. Added a separate five-file reviewed manual ROI volume-comparison archive. It embeds
   two unchanged accepted boundary-review ZIPs, one strict pairing record, a regenerated
   script-free review page, and local instructions without mutating either ancestor.
2. Added the qualified pairing form to the ordinary same-modality longitudinal viewer.
   Export requires both exact reviewed source series in the live panes and explicit
   same-lesion, same-tissue, chronology, acquisition/boundary comparability,
   registration-consideration, eight-check, decision, and fixed-attestation records.
   The form is absent from neutral MRI+CT Consult Prep.
3. Added recursive agent assembly and validation. Both nested review/evidence archives,
   DICOM SEG bytes, every original source byte, live catalog membership, per-instance
   DICOM date consistency, strict chronology, static page, hashes, and archive shape are
   rechecked locally. The server transport persists no patient file.
4. Limited valid accepted output to reviewed baseline/follow-up volumes, arithmetic
   absolute/percentage change, numeric direction, and elapsed days for discussion.
   Reviewer identity remains self-asserted; boundary uncertainty remains unquantified;
   spatial localization, response classification, treatment causality, diagnosis,
   clinical conclusion, and medical-record sign-off remain false.
5. Made rejection, revision, malformed input, mismatched patient/modality/chronology,
   incomplete pairing gates, extra members, numeric/page tampering, and any source-byte
   change fail closed with every numeric field null and `evidence_use: none`. Browser
   preview also refuses duplicate, unexpected, or oversized expanded ZIP members.
6. Production browser QA used two synthetic MR studies only. It verified exact source-
   pane gating, 0.002250 mL to 0.003000 mL arithmetic, complete acceptance gates, local
   five-file download, independent validation, empty browser diagnostics, and one-byte
   source-tamper refusal. No Mila data left the computer.
7. Added the 23rd embedded JSON Schema and advanced the deterministic offline bundle to
   v0.4.0. Exact macOS and Strawberry Linux package evidence is recorded in Status.
8. Added the 24th JSON Schema and reviewed native-boundary display. One accepted
   manual-volume comparison can reopen both exact, rehashed DICOM SEG masks in
   independent native tri-planar workspaces. The masks are read-only; normalized
   navigation is off by default; registration, cross-scan overlay, subtraction,
   spatial change, and response assessment remain locked.
9. Added the 25th JSON Schema and an optional privacy-minimized bearer-access audit.
   Owner-only JSONL events are application-appended, fsynced, restart-validated, and
   hash-chained without tokens, targets, identifiers, paths, payload facts, pixels,
   masks, measurements, or medical values. Covered bearer reads fail closed if the
   configured audit cannot append; the chain is not agent identity authentication.

## Completed in the twenty-seventh milestone

1. Added a strict v1 longitudinal-readiness artifact bound to the canonical SHA-256
   of the exact local catalog. It reports aggregate MR/CT study, eligible-series,
   valid-date, opaque patient-context, and metadata-candidate gates without source
   descriptions, paths, pixels, direct identifiers, or an assertion of de-identification.
2. Added matching human readiness logic and a visible Consult Prep card. The current
   MRI+CT shape states that a future same-patient MR or CT exam is required and that
   consultation reference views do not form a longitudinal pair.
3. Tightened all agent candidate suggestions to require valid, distinct DICOM dates
   in addition to same modality, distinct study, and one matching opaque patient
   context. Every candidate remains unreviewed and never authorizes selection,
   registration, lesion linkage, response, diagnosis, or a clinical conclusion.
4. Added owner-only CLI output, authenticated `GET /v1/longitudinal-readiness`, strict
   schema validation, a fixed privacy-minimized audit operation, bounded candidate
   reporting, and adversarial Python/TypeScript coverage for missing dates,
   cross-patient studies, localizers, malformed catalogs, and candidate truncation.
5. Generated and schema-validated Mila's private local readiness report: 2 studies,
   65 series, 53 eligible MR/CT series, 10,286 DICOM instances, one opaque patient
   context, zero candidates, and the explicit missing requirement for a future
   distinct same-modality study. The report remains outside Git with mode 0600.
6. Released deterministic offline bundle v0.7.0 and passed exact-artifact macOS arm64
   and Strawberry Linux x86_64 no-index install, runtime, readiness, authorization,
   audit-resume/privacy, and tamper-refusal gates using synthetic DICOM only.

## Completed in the twenty-eighth milestone

1. Added a strict v1 agent consultation-plan artifact for 2–8 ordered exact native
   MRI/CT sources and bounded discussion headings. Construction and independent
   validation rejoin every instance to one local catalog, require distinct instances,
   one opaque patient context, both modalities, and at least two studies.
2. Bound plans to a canonical content digest that excludes only the catalog's volatile
   top-level generation time. A fresh unchanged local launch can therefore accept a
   separately generated plan while any changed source identity, hash, count, metadata,
   opaque patient context, or other catalog content fails closed.
3. Added owner-only CLI creation/validation and a bounded, exact-origin, exact-media-
   type, browser-session-only validation endpoint. Bearer-only access is refused, the
   endpoint returns a privacy-minimized `no-store` summary, and no plan is persisted.
   Duplicate JSON fields and non-finite constants are refused.
4. Added a Consult Prep handoff panel that makes the software agent's unverified and
   every heading's unreviewed state visible. A person deliberately chooses Image A or
   Image B for each exact source. Navigation prefills the heading but never auto-opens
   on validation or adds a consultation-board capture.
5. Kept every non-navigation permission false: source mutation, automatic capture,
   chronology, registration, lesion linkage, response, treatment effect, diagnosis,
   and clinical conclusion. A validated plan is never represented as relevance,
   author identity, evidence acceptance, or medical advice.
   The privacy contract explicitly says discussion headings may contain identifiers.
6. Added the 27th embedded JSON Schema plus adversarial Python, HTTP, TypeScript, and
   synthetic production-browser coverage. Browser testing caught and corrected the
   catalog generation-time binding before release packaging.
7. Released deterministic offline bundle v0.8.0 and passed exact-artifact macOS arm64
   and Strawberry Linux x86_64 no-index install, 27-schema runtime, CLI plan,
   browser-session authorization, bearer refusal, and minimized-summary gates using
   synthetic DICOM only.

## Completed in the twenty-ninth milestone

1. Inspected the copied media's non-image DICOM objects locally without emitting
   patient identifiers, paths, pixels, annotation text, or coordinates. The seven PR
   objects are Grayscale Softcopy Presentation States; the single SR is an X-Ray
   Radiation Dose SR, not a diagnostic narrative report.
2. Added a strict source-bound GSPS catalog and 28th JSON Schema. Each PR is read with
   no-follow/stable-descriptor guards, bounded to 16 MiB, rehashed, rejoined through
   opaque catalog IDs to exact MR/CT instances, and rebuilt byte-for-byte during
   validation. Malformed or source-changed inputs fail closed.
3. Restricted display to hashed same-study, single-frame monochrome sources whose
   linear modality transform matches the GSPS, with unrotated/unflipped geometry,
   LINEAR VOI, identity presentation LUT/polarity, no shutter/mask/overlay/subtraction,
   exact full-image SCALE TO FIT and matching aspect, plus explicit PIXEL POLYLINE/
   anchor-text annotations. Frame scopes, dimensions-plus-one, crops, lookup tables,
   unsupported graphics/text, invalid layers/SOP classes, unsafe controls, and
   out-of-image points are withheld as a whole.
4. Added owner-only CLI creation/validation, bearer-audited authenticated
   `GET /v1/presentation-states`, `no-store` responses, process-lifetime source guards,
   and privacy-minimized validation summaries that omit text, IDs, geometry, and VOI
   values. The full catalog remains sensitive and local.
5. Added a strict same-origin browser parser that independently checks the fixed
   permission/privacy contract, exact local source membership, counts, dimensions,
   exact displayed area, VOI arithmetic, text controls, and coordinate bounds before
   resolving controls.
6. Added deliberate Image A/B navigation and a high-contrast read-only source overlay.
   DICOM corner coordinates are converted to image-index centers before Cornerstone
   `worldToCanvas`; projection is atomic, and all viewport/slice manipulation,
   measurement display/import/export, volume/evidence flows, MPR, and live agent-state
   publication are locked while any source state is active because their schemas do
   not encode GSPS provenance.
7. Added a patient-free CT+GSPS generator and synthetic CLI/browser checks. The exact
   annotated slice rendered one polyline and one text object with no browser errors;
   clearing removed the overlay and restored native controls. The copied media's seven
   states correctly remain locked because their far displayed-area corner uses a
   dimensions-plus-one vendor convention outside the strict DICOM full-image rule.
   The deterministic exact v0.9.0 artifact then passed macOS arm64 and Strawberry
   Linux x86_64 no-index install, 28-schema runtime, synthetic CLI, authenticated/
   audited/no-store/409 endpoint, loopback-only listener, strict packaged-browser
   display/clear, and no-external-processing gates. No Mila data went to Strawberry.

## Completed in the thirtieth milestone

1. Added a strict local source-carried DICOM SEG catalog and the 29th embedded JSON
   Schema. Stable no-follow reads bind every SEG and referenced MR/CT source byte;
   malformed or changed inputs fail closed.
2. Limited import to uncompressed binary SEG on one exact regular native grid with
   single-frame sources, explicit per-frame source references, preserved spatial
   locations, standard derivation/purpose codes, and coherent multi-frame dimensions.
3. Rebuilt sparse frames into bounded in-memory dense masks, independently rechecked
   ordering, hashes, binary values, voxel counts, and technical native-grid volumes in
   the browser, and left all originals unchanged.
4. Added a browser-session-only mask route and an explicitly sensitive authenticated
   catalog route. Bearer agents may read catalog provenance, segment text, geometry,
   and technical volume, but never mask bytes; validation summaries remain minimized,
   and every external-processing and clinical permission remains false.
5. Added a read-only three-plane Cornerstone display with linked crosshairs. It has no
   paint, erase, measurement conversion, export, diagnosis, treatment-response, or
   clinical-conclusion path and cannot be recorded in schemas that lack SEG provenance.
6. Added adversarial Python/TypeScript/HTTP coverage and a sparse patient-free DICOM
   SEG generator. Full DICOM conformance and independent vendor/highdicom fixture
   interoperability remain explicit future gates.

## Completed in the thirty-first milestone

1. Added a pinned optional highdicom 0.28.1/NumPy 2.5.2 interoperability gate that
   creates only patient-free DICOM in a deleted temporary directory. Neither package
   enters the ScanView runtime or receives Mila data.
2. Independently generated a 24-plane uncompressed binary SEG with 13 empty planes
   omitted. highdicom enumerates the complete 24-image source series in Common Instance
   Reference while encoding 11 per-frame derivation/source mappings.
3. Corrected the backend and browser assumption that top-level source-reference count
   cannot exceed frame count. Every encoded frame must still resolve through the exact
   top-level set, SOP class/instance, native position, and guarded local series.
4. Required highdicom's public source-instance reconstruction and ScanView to produce
   identical 98,304-byte dense masks, SHA-256, 3,083-voxel count, and 3.946240 mL
   technical native-grid arithmetic.
5. Passed production-browser QA with the independently generated object: one supported
   SEG, three visible locked planes, no edit/evidence/export controls, and no browser
   warnings or errors.
6. Kept full conformance, vendor/clinical-system interoperability, creator/algorithm/
   boundary accuracy, tissue identity, diagnosis, and response authority out of scope.
7. Built the deterministic owner-only v0.11.0 offline ZIP twice byte-identically and
   passed fresh no-index exact-artifact gates on macOS arm64 and Strawberry Linux
   x86_64. Both runtimes excluded highdicom/NumPy, required no external DICOM API,
   and reproduced the strict catalog/authentication/mask/source-change behavior.

## Completed in the thirty-second milestone

1. Added a second independent patient-free SEG interoperability gate with exact
   NCI/QIICR dcmqi 1.5.6 revision `60d63dc` and pydicom 3.0.2. dcmqi is an optional
   test dependency only and never enters the ScanView runtime or processes Mila data.
2. Ran dcmqi's writer and reader inside macOS `sandbox-exec` deny-all-network
   isolation, with a separate blocked-network probe before DICOM conversion. The
   Linux path requires bubblewrap with a private network namespace and fails closed
   when that isolation is unavailable.
3. Independently generated and read a 24-source/11-frame sparse binary SEG, then
   required the dcmqi round trip, fixed reference mask, and ScanView import to agree
   on all 98,304 bytes, 3,083 marked voxels, 3.946240 mL, and SHA-256
   `81946112b1311f1ee9ff4fe1d61f86d36ce82d076122b39b9d4e7a8e46cf82bb`.
4. Corrected the earlier assumption that Spatial Locations Preserved must be present.
   The current DICOM General Reference module defines it as optional. ScanView now
   accepts `YES` or absence only after all exact source identity and native-geometry
   guards pass, records the evidence path in source-SEG catalog v2, and refuses
   explicit `NO`, `REORIENTED_ONLY`, or any other value.
5. Passed patient-free production-browser QA with the dcmqi object: one supported SEG,
   zero locked objects, 24 source slices, 11 mapped frames, one 3,083-voxel segment,
   and visible read-only overlays in all three linked MPR planes without browser
   warnings or errors.
6. Built the owner-only v0.12.0 offline ZIP twice byte-identically. A fresh macOS arm64
   no-index install passed the 30-schema runtime, strict packaged CLI, loopback
   authorization, browser-only exact mask, and changed-source gates; the runtime
   contains neither dcmqi, highdicom, nor NumPy and requires no external processing API.
7. Strawberry Linux v0.12 commissioning remains pending because the configured SSH
   public key was refused on 2026-08-29. No patient data was transferred; the earlier
   exact v0.11 Linux gate remains passing.

## Completed in the thirty-third milestone

1. Replaced the timepoint-named viewer-state v1 publication path with v2 neutral
   Image A/Image B targets plus strict workspace and view-role declarations. Consult
   Prep now shares `reference`/`reference` navigation context without implying
   chronology; longitudinal review retains explicit `baseline`/`followup` roles.
2. Added an optional active source-SEG display reference containing only the exact
   opaque object, segment, and referenced-series IDs plus guarded source-SEG catalog
   content SHA-256. Mask bytes/hash, source text, segment label/codes, algorithm,
   technical volume, accuracy claims, and interpretation are never published.
3. Required the server to join that reference to one supported segment in the exact
   guarded source-SEG v2 catalog and active MPR series. Changed SEG or referenced
   source bytes now fail publication or clear an available state as `source_changed`.
4. Added fixed-false navigation-from-state, mutation, mask-read, SEG-interpretation,
   diagnosis, response, and clinical-conclusion permissions plus explicit sensitive-
   reference/hash privacy declarations. Off-by-default consent, same-origin bounded
   publication, bearer-only reading, `no-store`, publisher revocation, and 30-second
   memory TTL remain unchanged.
5. Added adversarial Python, TypeScript, schema, and integrated synthetic source-SEG
   server tests. Production-browser QA rendered the native stack plus three read-only
   MPR canvases, published only the allowed opaque SEG reference, proved forbidden
   clinical/mask fields absent, and immediately revoked the state on opt-out.
6. Bumped the local-only offline distribution to v0.13.0 with 31 embedded schemas.
   Exact artifact hashes and platform commissioning evidence are recorded in
   `docs/STATUS.md`; no patient data enters release or interoperability testing.

## Completed in the thirty-fourth milestone

1. Added a distinct v1 source DICOM SEG boundary-review archive instead of converting
   source content into ScanView manual ROI evidence. The record binds the exact
   catalog, original SEG, source series, reconstructed mask, source metadata, and
   technical arithmetic while retaining explicit source-authority locks.
2. Added a read-only MPR review form with a qualified role, self-asserted identity,
   acquisition suitability, reviewer-defined represented tissue and boundary rules,
   ten source-specific checklist items, fixed attestation, and accept/revise/reject
   decision. Acceptance requires suitable acquisition and every check.
3. Added a browser-session-only same-origin loopback assembler. The browser sends no
   DICOM or mask; the server reopens guarded local sources, builds and independently
   validates the five-file sensitive ZIP entirely in memory, returns `no-store`, and
   persists nothing. Bearer authorization alone cannot manufacture the human review.
4. Added local CLI creation and privacy-minimized agent validation. Stable bounded
   no-follow reads, owner-only non-overwriting output, strict JSON/ZIP/member limits,
   exact static-page regeneration, recursive live-source validation, and tamper/source-
   change refusal fail closed.
5. Kept source labels/codes, creator, algorithm, accuracy, and clinical meaning
   unauthenticated, unverified, or not assessed. Even acceptance permits only
   one-timepoint boundary/technical-volume discussion and future pairing-review
   eligibility; current comparison assembly does not consume the artifact and every
   longitudinal, change, response, diagnostic, and clinical-conclusion permission is
   false.
6. Bumped the local-only offline distribution to v0.14.0 with 32 embedded schemas.
   Exact artifact hashes and platform commissioning evidence are recorded in
   `docs/STATUS.md`; no patient data enters release or browser testing.

## Completed in the thirty-fifth milestone

1. Replaced the default multi-panel workspace with a focused **In-depth review**
   surface containing one series selector, one native DICOM viewport, and only
   Window, Pan, Zoom, Reset, slice navigation, and a three-plane entry point.
2. Added a minimal MPR presentation with axial, coronal, and sagittal panes,
   crosshairs, Window, Pan, Zoom, Reset, and Close. Manual ROI, source-SEG review,
   export, and attestation forms remain implemented but do not appear in this mode.
3. Added a separate disabled **Compare over time** mode. Its visible lock states that
   alignment and measurement checks must be built first; the previous approximate
   two-pane surface is not presented as a finished response-comparison workflow.
4. Kept local folder import and authenticated loopback catalog loading, while
   skipping hidden GSPS/SEG catalog work in the focused surface. No external DICOM
   processing API or upload path was added.
5. Passed TypeScript typecheck, all 141 viewer tests in 29 files, production build,
   and production-browser QA with the existing local copied-scan service: one native
   pane, a 324-slice MR selection, three rendered MPR planes, clean close, and zero
   legacy workspace panels.

## Completed in the thirty-sixth milestone

1. Split **In-depth review** into an independently scrolling image workspace on the
   left and a persistent agent-chat workspace on the right. The image side now shows
   either one native pane or three vertically stacked MPR panes, never both at once.
2. Added a versioned local image-context contract containing the exact opaque series
   and source-instance IDs, stack position/count, view mode, modality/date, and the
   pointer or MPR crosshair in DICOM LPS millimeters. MPR context resolves its nearest
   exact native source plane; screenshots, pixels, and source text are absent. The
   friendly series description remains a local display label only.
3. Added the persistent chat shell and an honest **Connector next** state. Its
   composer is disabled until an authenticated, explicitly consented connector is
   implemented; this milestone makes no OpenAI request and adds no DICOM upload or
   external processing path.
4. Kept native pointer context live while moving across the image, kept MPR crosshair
   context live while navigating the reconstructed volume, and cleared stale context
   on series, slice, mode, catalog, and folder changes.
5. Passed TypeScript typecheck, all 143 viewer tests in 30 files, production build,
   and production-browser QA against the existing local copied-scan service. QA
   confirmed the split, precise native pointer context, three vertical MPR panes,
   exact MPR source resolution, and independent left scrolling with chat fixed.

## Completed in the thirty-seventh milestone

1. Removed embedded chat and converted **In-depth review** into a compact Codex side-
   panel visualization surface with explicit Single/3-plane switches and no duplicate
   conversation UI.
2. Replaced transient native hover context with a visible pinned patient-space point.
   Added agent-addressable MPR point/tool/reset control and precise applied-render
   observations, including the nearest exact native source slice.
3. Added a bounded memory-only `/v1/viewer-control` bridge. Bearer agents can issue
   catalog-validated navigation/display commands; only the HttpOnly same-origin
   browser session can publish applied observations. Mutation, measurement, diagnosis,
   response, and clinical-conclusion authority remain fixed false.
4. Added the repo-owned `scanview-control` Codex skill, strict loopback client, API
   reference, skill metadata, and root agent routing. It can inspect state/catalog,
   control native/MPR display, read minimized metadata, and deliberately retrieve one
   exact DICOM object for local-only analysis.
5. Passed 144 viewer tests, TypeScript typecheck, production build, the full Python
   suite, focused control/auth tests, skill validation, and production-browser E2E.
   A real local skill command changed the 57-series copied-scan viewer to MPR and
   received the matching `ready` revision with exact patient coordinates.

## Immediate

1. Use **In-depth review** for one series at a time. Treat the three-plane view as a
   local reconstruction for navigation and confirm medical interpretations with the
   clinical imaging system and a qualified clinician.
2. Use the `scanview-control` skill for exact local state and visualization control.
   Add new analysis operations only as narrow, tested local tools; never upload DICOM,
   pixels, screenshots, source text, coordinates, or credentials.
3. Specify the measurement-grade **Compare over time** protocol before enabling its
   UI: exact timepoints, comparable sequence/tissue definitions, DICOM calibration,
   alignment state, repeatability/uncertainty, review responsibility, and explicit
   rules for when arithmetic must remain hidden.
4. Use manual ROI volume evidence and reviewed volume comparisons only as source-bound
   discussion artifacts. Even an accepted two-timepoint pairing is arithmetic—not a
   response category, treatment-effect conclusion, diagnosis, or clinical sign-off.
5. Use consultation packets or boards only to prepare questions with Mila's
   clinicians; confirm every MRI/CT source view in the clinical imaging system and do
   not treat either artifact as a diagnosis or treatment-response analysis.
6. Treat any agent consultation plan as a local navigation suggestion only. Inspect
   each native source before adding it to a board, and keep prompts free of unnecessary
   direct identifiers because plan headings are sensitive and not de-identified.
7. Treat GSPS text/geometry as unverified source display content. Confirm its meaning
   and authorship in the clinical imaging system; do not copy it into measurements or
   evidence until the evidence contract explicitly records GSPS provenance.
8. Treat source-carried SEG labels, codes, creator/algorithm fields, masks, and
   technical volume as unverified local display content. Confirm the object and its
   meaning in the clinical imaging system before any clinical use.
9. Import a future same-modality MRI follow-up, have a person confirm the intended
   earlier/later sequences and clinical roles, run the required engine on that pair,
   and complete qualified visual/quantitative QA.
10. Protect the authenticated local Slicer installation and keep using the recorded
   launcher hash; reauthenticate any replacement before a future patient-specific job.
11. Protect the checksum-verified Strawberry Slicer installation and recorded launcher
   hash; repeat authentication and synthetic commissioning after any replacement.
12. Produce signed/notarized macOS/Linux ScanView release artifacts around the verified
   offline bundle, and evaluate whether to include a separately authenticated interpreter.
13. Design optional authenticated signature integration for clinical organizations;
   never relabel the current self-attested hash chain as identity verification.
14. Have a qualified reviewer test the v2 mask-boundary checklist and accepted display
   on a clinically appropriate same-modality case before any patient-specific reliance.

## Next milestone

1. Harden and commission the Codex control skill on macOS and Strawberry Linux. Add
   narrow local pixel/geometry inspection operations, source-change invalidation, and
   repeatable browser-command tests without expanding clinical authority or adding an
   external DICOM-processing dependency.
2. Design and implement the locked shell for **Compare over time** around the Phase 2
   measurement state machine in `docs/PLAN.md`. Begin with exact source/timepoint
   pairing and calibrated same-method observations; add uncertainty/repeatability and
   explicit alignment/review states before exposing absolute or percent change. Do
   not enable response classification or use Mila's current MRI+CT as a time pair.
3. Implement a distinct source-SEG longitudinal volume-pairing review artifact for
   two independently accepted source-SEG review ZIPs. Keep manual/source evidence
   lineages non-interchangeable; recursively revalidate both original SEG objects,
   masks, source images, and exact chronology; require a separate qualified pairing
   attestation; expose arithmetic only after acceptance; and keep response,
   causality, registration, spatial change, diagnosis, conclusion, and sign-off
   locked. Add schema, privacy-minimized summary, CLI, browser-session-only local
   assembler, viewer form, adversarial tests, patient-free browser QA, and complete
   offline-package gates. See the current handoff in `docs/STATUS.md`.
4. Test source-SEG v2 against a real vendor-produced or clinical-system-exported
   patient-free fixture in addition to highdicom and dcmqi, while retaining the
   conservative fail-closed profile.
5. Restore authenticated Strawberry access and rerun the exact v0.14 source-SEG review,
   viewer-state, dcmqi, no-index-package, and loopback endpoint gates under Linux
   bubblewrap.
6. Import a future same-modality Mila follow-up and complete explicit series pairing,
   separately reviewed ROI boundaries, same-lesion/tissue confirmation, and qualified
   pairing review. Keep the current MRI+CT media out of this longitudinal path.
7. Add platform signing and notarization without weakening local-only runtime behavior.
8. Add Orthanc as an optional localhost-only DICOMweb archive and pin/test its local
   configuration.
9. Prototype an OHIF longitudinal ScanView mode instead of forking OHIF.

## Viewer backlog

1. Add a local rotatable 3D volume for one explicitly selected geometry-qualified
   series after the basic viewer and Codex control boundary are stable. Link it to the same
   patient-space point as MPR, bound its work, label it derived, and keep native/MPR
   geometry authoritative for measurement. Do not combine series in 3D until a
   reviewed registration makes that relationship explicit.

## Registration milestone

1. Perform the implemented QA workflow on a valid real same-modality pair with a
   qualified reviewer and a predeclared clinically appropriate landmark tolerance.
2. Verify the implemented accepted-record display on a real reviewed bundle; never
   overwrite originals and never unlock subtraction, segmentation, or mask propagation.
3. Re-run both platform commissioning cases after any engine, sandbox, Xvfb, or
   packaging dependency changes; never infer Linux publisher signing from a checksum.

## Decisions needed with clinicians

- Mila's diagnosis/pathology and which pediatric or adult response criteria apply.
- Which MRI sequence is the intended longitudinal primary series.
- Preferred baseline, nadir/best-response convention, and confirmation timing.
- Tumor component definitions and measurement/segmentation method.
- What evidence packet format is most useful in neurosurgery/neuro-oncology visits.
