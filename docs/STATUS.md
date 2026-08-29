# Status

Last updated: 2026-08-29 06:31 PDT

## Data transfer

- Source found: `/Volumes/PATIENT_DATA`, read-only 1.34 GB UDF DVD-R.
- Destination found: `/Users/chris/Desktop/Mila Scan CD`.
- Finder already held the source directory open and was actively copying before this
  build began; no competing copier was started.
- Finder completed at 10,322 destination files / 1,305,227,159 bytes and released
  the source. Source inventory is 10,321 files; the extra destination file is kept.
- SHA-256 verification/repair pass: **complete, 10,321 / 10,321 byte-identical**.
- Verified source payload: 1,305,221,011 bytes; 0 failures and 0 repairs required.
- One destination-only file was preserved. No destination file was deleted.
- Owner-only verification manifest retained at the destination, outside Git.

## Local catalog

- 2 studies, 65 series, and 10,286 DICOM instances indexed locally.
- Series distribution: 49 MR, 8 CT, 7 PR, and 1 SR.
- The media contains one MRI exam and one CT exam. There is no same-modality
  longitudinal pair, so the matcher correctly returns zero comparison candidates.
- Sample MR and CT objects report JPEG 2000 Lossless transfer syntax. The production
  viewer decoded and rendered both through its bundled OpenJPEG WebAssembly worker.
- The complete copied folder loaded in the production viewer in about five seconds:
  2 studies and all 57 renderable MR/CT series, matching the catalog's 49 MR + 8 CT.
- Catalog and candidate files are owner-only, outside Git, and marked sensitive and
  `deidentified: false` despite direct patient name/ID and paths being omitted.
- A full no-hash reindex derives one matching opaque patient context across both
  studies and all 65 series, with no missing context. Raw PatientID/PatientName values
  remain absent from catalog output. Candidate generation still returns zero because
  the only exams are different modalities.
- The private catalog-hash-bound longitudinal-readiness report validates against its
  v1 schema and reports 53 eligible MR/CT series, 10,286 instances, one opaque patient
  context, zero candidates, and
  `future_distinct_study_same_modality_series`. It contains no paths or pixels, grants
  no derived or clinical permission, and is retained outside Git with mode 0600.
- Privacy-minimized local GSPS inspection found 7 PR states, 6 with annotations (19
  PIXEL polylines and 9 anchor-text objects). The final strict v0.9 parser withholds
  all 7 because their displayed-area far corner uses dimensions plus one rather than
  DICOM's exact `(Columns,Rows)` full-image boundary. No identifiers, annotation text,
  coordinates, pixels, paths, or patient artifact left the Mac or entered Git; native
  MR/CT display remains available.
- The copied media has no DICOM SEG objects: the complete modality inventory is MR,
  CT, PR, and SR only. The v0.10 source-SEG reader was therefore exercised only with
  patient-free synthetic data; no segmentation was inferred from Mila's images.

## Repository

- A strict read-only source-carried DICOM SEG path now catalogs a conservative binary,
  uncompressed, exact-native-grid subset. It performs stable no-follow reads, rehashes
  every referenced MR/CT source, validates per-frame derivation/source references,
  segment/plane dimensions, regular geometry, and aggregate work/memory bounds, then
  reconstructs bounded dense masks in memory. DICOM's optional Spatial Locations
  Preserved attribute may be `YES` or absent only after all exact source and geometry
  guards pass; explicit negative or unknown values fail closed. Catalog v2 reports
  which evidence path applied.
- The browser independently checks catalog privacy and permission constants, physical
  slice ordering, geometry, mask SHA-256, binary values, voxel count, and technical
  native-grid volume before a read-only three-plane display. Browser capability is
  required for mask bytes; authenticated bearer agents may read the explicitly
  sensitive full catalog, while CLI validation output is privacy-minimized. Paint,
  erase, evidence conversion, export, identity, accuracy, diagnosis, response, and
  clinical conclusions are all unavailable.
- A distinct v1 source-SEG boundary-review workflow now lets a qualified person review
  the exact read-only mask on its original images without converting it into ScanView
  manual ROI evidence. The bounded record separates reviewer-defined represented
  tissue and boundary criteria from unverified source label/codes, records ten explicit
  source-specific checks and a fixed self-attestation, and retains creator, algorithm,
  accuracy, source meaning, longitudinal, response, diagnosis, and conclusion locks.
- The browser sends only an opaque exact source reference and reviewer declaration to
  a browser-session-only same-origin loopback route. The server revalidates the guarded
  original SEG and every source image, reconstructs the dense native mask, assembles
  the five-file sensitive ZIP in memory, independently revalidates it, returns
  `no-store`, and persists nothing. Bearer authorization alone is refused. The CLI
  supports owner-only non-overwriting creation and privacy-minimized validation with
  bounded no-follow request reads; tamper, symlink, oversize, incomplete acceptance,
  source mutation, catalog mismatch, and authority escalation fail closed.
- An accepted source-SEG review permits only one-timepoint boundary and technical-
  volume discussion plus structural eligibility for a future pairing review. Current
  comparison assembly deliberately does not consume it, and it computes no change or
  treatment response. The copied Mila media contains no SEG objects, so all new tests
  and browser QA remain patient-free.
- An optional patient-free interoperability gate now uses pinned highdicom 0.28.1 as
  an independent writer and reader. It proved that a standard sparse SEG may list its
  complete 24-image source series at top level while encoding only 11 nonempty frames;
  ScanView accepts that superset while retaining exact per-frame SOP, native-plane,
  source-hash, geometry, and bounds checks. highdicom and NumPy are test-only and are
  absent from the local runtime and offline bundle.
- A second optional patient-free interoperability gate pins NCI/QIICR dcmqi 1.5.6
  revision `60d63dc` as an independent writer and reader. Both converters run inside
  OS-enforced external-network isolation and must reconstruct the same dense mask as
  ScanView and the fixed reference. dcmqi is absent from the runtime and never
  processes Mila data.
- Initial local-first React/TypeScript/Cornerstone3D viewer implemented.
- Baseline/follow-up pairing, linked stack position, compatibility explanations, and
  registration safety gate implemented.
- Window/level, pan, zoom, reset, manual length, perpendicular bidirectional, and
  elliptical ROI tools implemented.
- Geometry-gated single-series MPR implemented with local axial, coronal, and
  sagittal orthographic volume views, wheel navigation, window/level, pan, zoom,
  reset, cache cleanup, and permanent derived/interpolated safety labeling.
- MPR planes now share one physically linked DICOM patient-space crosshair and an
  accessible live LPS coordinate. Minimal interaction mode keeps the planes canonical
  by withholding oblique rotation and slab-thickness controls.
- The same single-series workspace now supports one person-painted binary native-grid
  ROI draft. Paint/erase and export require consistent single-frame per-instance
  matrix, spacing, orientation, regular projected gaps, and no in-plane drift. The
  live value is marked-voxel × native voxel volume and is permanently labeled
  computed, unreviewed, with boundary uncertainty not quantified.
- Browser export creates exactly one DICOM SEG-format mask, v1 source/provenance/
  arithmetic sidecar, and README. An independent read-only agent validator rehashes
  stable source descriptors, checks exact study/series/frame and DICOM references,
  rebuilds the dense binary mask, and recomputes its hash, voxel count, and volume.
  V1 has no acceptance path and locks lesion linkage, percent change, response,
  diagnosis, and clinical conclusions.
- A separate one-timepoint qualified boundary-review workflow now wraps the exact
  source-bound evidence. It records a self-attested reviewer role, acquisition
  suitability, represented tissue, inclusion/exclusion criteria, all-three-plane
  review, eight explicit boundary checks, a fixed attestation, and an accept/revise/
  reject decision. Acceptance permits discussion of that one reviewed boundary and
  future pairing-review eligibility only; identity remains unverified and every
  longitudinal, response, diagnostic, and clinical-conclusion permission stays false.
  The independent agent validator recursively revalidates the nested DICOM SEG and
  live source bytes, checks the static review page and exact record, and fails closed.
- A second reviewed manual ROI volume-comparison workflow now accepts only two exact
  independently accepted boundary-review archives plus a strict qualified pairing
  request. It joins both reviewed series to the live catalog, verifies consistent
  per-instance DICOM dates and strict chronology, recursively reopens both DICOM SEG/
  source chains, and requires explicit same-lesion, same-tissue, comparability,
  registration-consideration, checklist, and attestation gates. A valid acceptance
  exposes transparent reviewed volume arithmetic for discussion only. Any non-accepted,
  malformed, mismatched, or source-changed state withholds every numeric value;
  response, treatment causality, spatial localization, diagnosis, conclusion, and
  sign-off remain false.
- An accepted volume-comparison archive can now launch a dedicated reviewed native-
  boundary workspace. Startup recursively validates both reviews, both DICOM SEG
  masks, and every native source byte, then guards those identities for the process
  lifetime. The browser independently rehashes/recounts both binary masks and shows
  each as a locked overlay on its own exact axial/coronal/sagittal DICOM volume.
  Independent boundary-centroid navigation is the default. Optional normalized-grid
  mirroring is off by default and prominently labeled approximate navigation only;
  registration, cross-scan overlay, subtraction, propagation, spatial change,
  response, diagnosis, causality, conclusion, and sign-off remain unavailable.
- Bearer agents receive only a privacy-minimized reviewed-native-display summary.
  The full context and mask bytes require the browser session; reviewer identity,
  organization, source IDs, tissue definitions, criteria, hashes, and masks are not
  exposed to the bearer interface. This adds the 24th strict embedded JSON Schema.
- Validated DICOM patient-orientation labels implemented; labels are withheld rather
  than guessed when Image Orientation (Patient) is missing or malformed.
- Follow-up auto-selection removed; same-exam pairings are explicitly incompatible
  for longitudinal response.
- Catalog and browser imports derive an opaque patient-context digest locally;
  viewer and agent pairing now reject missing or different patient contexts.
- Physical patient-position slice mapping implemented for shared compatible Frames
  of Reference; normalized fallback is labeled approximate.
- Manual length/bidirectional/ellipse drafts now save/reopen with tracking ID, opaque
  series/instance/frame provenance, DICOM patient-space geometry, units gate,
  limitations, and review state.
- Human-readable source evidence table implemented; imported values are rejected when
  they disagree with their geometry.
- Human/agent measurement workspace implemented with strict bounded JSON paste,
  in-memory annotation deletion, explicit baseline/follow-up tracking-ID selection,
  normalized working lesion labels, strict acquisition-date ordering, and numeric
  preview/export that never assigns a response category.
- Comparison schema/builder now accepts an optional bounded label. The local agent
  validator independently checks source separation, type/unit agreement, complete
  metric sets, arithmetic, review state, and an empty interpretation list while its
  summary withholds labels, IDs, coordinates, and values.
- Local comparison-review archives now bind a recursively validated visit packet to
  its exact numeric comparison and visible baseline/follow-up measurements. They
  include both images, a script-free printable page, self-attested checklist events,
  explicit identity-verification limits, and privacy-minimized validation.
- The unified viewer can now create the complete comparison-review archive with one
  button. It restores both panes to the exact source instances named by the explicit
  measurement pair, keeps export disabled if either pane differs, and sends only two
  in-memory key-image archives plus normalized comparison JSON to the exact-origin
  loopback assembler. The server persists no source, intermediate, or output file.
- Agents can now create versioned one-use viewer navigation intents from exact opaque
  manifest series/instances. The CLI and launcher validate catalog membership; the
  browser applies all targets or none, clears the fragment immediately, and visibly
  states that pairing remains unreviewed. URL fragments never reach the local server.
- People can now explicitly opt in to a memory-only local viewer-state bridge for
  bearer-authorized agents. V2 publishes only exact opaque Image A/Image B positions,
  explicit neutral or longitudinal view roles, tool/link state, optional MPR series,
  and evidence counts. A visibly active supported source SEG may add only its opaque
  object/segment/series references and guarded catalog-content hash; no mask bytes,
  source text, label/code, algorithm, volume, accuracy, or interpretation is included.
  Manifest/source-SEG catalog validation, guarded-source invalidation, 30-second
  expiry, visible opt-out, publisher revocation, `no-store`, fixed-false clinical and
  mutation permissions, and default-off behavior are enforced.
- Launch/serve can now opt into an owner-only privacy-minimized bearer-access audit.
  Each covered sensitive bearer GET appends and fsyncs one strict operation-class
  event before routing. Events are sequence/hash chained across validated restarts and
  contain no token, request target, opaque ID, path, response status/body/size, DICOM
  content, pixels, masks, measurements, or reviewed values. Final-symlink, hard-link,
  broad-permission, concurrent-writer, corrupt, externally changed, oversized, or
  unwritable logs fail the bearer read closed with 503. Browser capability reads are
  separate and remain outside this bearer log.
- `verify-agent-audit` independently checks the strict JSONL chain and returns only
  counts, sequence bounds, the last event hash, and fixed privacy declarations. The
  audit proves bearer authorization events only—not response delivery, agent identity,
  a digital signature, medical-record compliance, or OS immutability.
- A version-gated local Slicer 5.12.3 computed revision 34627/runtime repository
  revision `9034c71`/BRAINSFit/BRAINSResample rigid-registration
  executor now accepts only explicitly attested, identity-unverified matching opaque
  patient context; same-modality distinct-study chronology; original-primary
  brain/head images; conservative sequence and explicit contrast matching; regular
  per-instance volume geometry; score ≥80; and SHA-256 provenance. Source bytes are
  rehashed before and after generic private staging; Slicer temp/cache paths stay
  inside that deleted private job space. Slicer must run inside OS-enforced network
  isolation—a macOS deny-all-network sandbox or, on supported 64-bit Linux, `bwrap`
  private namespaces plus seccomp that allows only local `AF_UNIX` IPC and rejects
  network socket domains and io_uring. Linux Slicer runs on private no-TCP Xvfb and
  never inherits the desktop display. There is no weaker `unshare`-only or unsandboxed
  fallback. DICOM is never mutated and ScanView requires no external processing API.
- Successful registration creates an atomic no-replace, owner-only seven-file v2
  derivative directory containing fixed/moving/registered scalar NRRDs, a uint8 binary
  registered-moving sampling-support NRRD in fixed geometry, one finite proper-rigid
  text ITK transform in DICOM patient LPS, an engine report, and a strict manifest.
  The validator decodes every support voxel, permits only `{0,1}`, rejects empty
  support, and recomputes counts. Every source bundle remains
  `generated_pending_qa`/`unreviewed`; review never mutates it.
- An isolated browser-capability registration-QA workspace now provides true LPS
  axial/coronal/sagittal reformats for oblique/permuted NRRDs, derived reference and
  registered views, physical aspect, independent 3-D landmarks, opacity, swipe,
  checkerboard, edges,
  strict browser-recorded full-coverage traversal evidence, and one separate
  hash-bound JSON decision.
  A bearer token alone cannot fetch the NRRDs or submit review. Qualified self-attested
  acceptance requires a trained clinician/medical physicist, three spatially distributed
  landmark pairs within the geometry-derived tolerance, three aligned qualitative
  landmarks, every checklist item, every plane/mode, explicit support-boundary and
  excluded-region review, and no defect. It can authorize
  only exploratory shared-coverage overlay/swipe; all other derivative uses remain
  locked.
- The ordinary local workspace can now consume one accepted, owner-only v2 review only
  with its exact live seven-file bundle. A separate browser-only surface exposes fixed
  reference, registered-moving, and the technical sampling-support NRRDs; verifies
  hashes, binary payload, and geometry; loads bounded files sequentially; creates no
  render state before all three pass; enforces encoded/predecode/decoded and
  render-dimension ceilings; recomputes the complete bundle anchor in the browser; and
  implements opacity/swipe only. The mask uses nearest-neighbor sampling, mattes the
  standalone registered pane at zero, and forces fixed pixels at zero in composites.
  Rejected, stale, tampered, linked, mismatched, missing, non-binary, or unsafe inputs
  fall back to ordinary DICOM with registered pixels locked. Both images are labeled
  derived, registered moving is labeled resampled, native DICOM remains authoritative,
  and the mask is explicitly not anatomy, tumor, segmentation, registration quality,
  or clinical comparability. Browser-downloaded decisions must pass the bounded
  no-symlink `import-registration-review` flow, which seals one non-overwriting
  owner-only record against the live bundle.
- Review and amendment commands always create a new owner-only archive. Event hashes
  bind the actor, checklist, note, source comparison, prior event, and parent archive;
  an amended comparison is rejoined to the visual evidence and reset to `unreviewed`.
- Each native viewport can export one local key-image v2 ZIP with a watermarked PNG,
  exact opaque patient/study/series/instance and presentation provenance, and only
  the v3 measurements visible on that source instance. A privacy-minimized agent
  validator checks archive shape, PNG structure/dimensions, SHA-256 cross-links, and
  source linkage while retaining v1 validation compatibility.
- Two explicitly selected key images can be assembled locally into a sensitive
  clinician visit-packet ZIP. Same-modality, distinct-series, chronological, and
  viewport-role gates are mandatory; the script-free review page says unregistered,
  unreviewed, and no response conclusion, while the agent manifest cross-hashes all
  eight payload files.
- The unified viewer can now create that visit packet directly from the two live
  panes with one button. Both key-image captures remain in browser memory, an
  authenticated exact-origin loopback POST invokes the same Python assembler, and
  the validated ZIP is returned with `no-store` without a server-side patient file.
- The viewer now detects when the loaded catalog has no valid dated, same-modality,
  cross-study longitudinal source pair and switches to **Consult preparation**. The
  two panes become neutral **Image A/Image B** reference views, approximate slice
  linking and lesion-pair arithmetic are disabled, and visit/review exports are
  replaced by a source-verified consultation packet. The existing live viewer-state
  bridge is also disabled because its v1 schema names timepoint roles; agents consume
  the neutral packet instead of receiving misleading baseline/follow-up state.
- A matching longitudinal-readiness card now shows aggregate MR/CT study and eligible-
  series counts, metadata-candidate count, and the exact missing gate. The Python
  `readiness` command and authenticated loopback endpoint bind the same strict result
  to the canonical catalog hash, cap candidate details at 256 opaque ID pairs, omit
  descriptions/paths/pixels, and leave every selection, derived-use, diagnostic, and
  clinical-conclusion permission false. Candidate generation now also fails closed on
  missing, malformed, or identical DICOM acquisition dates.
- Consultation packet v1 accepts exactly one MR and one CT view from distinct studies
  with one matching opaque patient context. Each neutral key-image sidecar uses a
  `view_a`/`view_b` slot instead of a timepoint role. The loopback assembler checks
  the exact live catalog position and rehashes the guarded DICOM source descriptor,
  then returns a nine-file, script-free, owner-sensitive archive with empty computed
  and interpretation arrays. Its deterministic review page binds both DICOM byte
  counts/SHA-256 values and permanently says reference views only, not a comparison,
  unregistered, unreviewed, not for diagnosis, and no response conclusion.
- Consultation-board v1 extends that neutral workflow to 2–8 explicitly labeled,
  ordered native views with both MR and CT, at least two studies, distinct source
  instances, and one matching opaque patient context. Every nested archive and exact
  guarded DICOM source is revalidated and rehashed locally. Labels remain unreviewed
  person-entered discussion headings; computed results, interpretations, chronology,
  alignment, lesion linkage, diagnosis, comparison, and response authority are absent.
- The viewer collects those labeled captures in memory, shows independent readiness
  gates, permits explicit move/remove/clear, and sends only a strict bounded ZIP to
  authenticated `POST /v1/consultation-boards`. The validated result is returned with
  `no-store`; the server writes no patient artifact. A matching CLI path produces
  non-overwriting owner-only output and a privacy-minimized validation summary.
- Agent consultation-plan v1 provides a strict navigation-only bridge from a software
  agent to the human Consult Prep workspace. A local request names 2–8 ordered exact
  opaque series/instance pairs and bounded discussion headings. Creation and validation
  require distinct instances, one opaque patient context, both MR and CT, at least two
  studies, and a canonical catalog-content digest that excludes only the volatile
  top-level generation time. All other source IDs, hashes, counts, and metadata remain
  bound.
- The viewer accepts a pasted plan only after strict client parsing and live server
  rebuilding through a bounded exact-origin, exact-media-type, browser-session-only
  `POST /v1/agent-consultation-plans/validate`. It then exposes deliberate per-item
  Image A/B navigation and prefills the unreviewed heading. Validation never opens or
  captures a source, bearer-only access is refused, no plan is persisted, and agent
  identity, relevance, chronology, registration, lesion, response, treatment effect,
  diagnosis, and clinical-conclusion authority remain false.
- The same consultation contract is available through strict non-overwriting CLI
  assembly/validation and `POST /v1/consultation-packets`. All nested input and output
  ZIP members, JSON keys, digests, source metadata, positions, modalities, study and
  patient-context gates are validated locally; the server persists no artifact.
- Versioned measurement, key-image, consultation-key-image, consultation-packet,
  numeric-comparison, visit-packet,
  comparison-review, navigation-intent, viewer-state, longitudinal-readiness,
  agent-consultation-plan, source-bound GSPS presentation-state,
  rigid-registration,
  registration-QA, reviewed-registration-display, source-bound manual ROI volume,
  manual boundary-review, reviewed manual ROI volume-comparison, reviewed native-
  boundary display, and agent-access-audit event
  JSON Schemas plus local validation are implemented. Same-series pairs, unknown units,
  mismatched measurement types, and mismatched visual/numeric evidence are refused; no
  response label is emitted.
- Unified `scanview-agent launch` path implemented: one loopback process serves the
  bundled UI, manifest, pairing candidates, and protected native DICOM instances.
  Every instance route is bound to its startup file identity/change metadata and
  optional catalog SHA-256, refuses final-component symlinks or later changes, and
  hashes an exact ephemeral local snapshot before sending patient bytes.
- The staged release builder embeds the viewer, workers, and local codecs into a
  UI-embedded wheel together with all 31 contracts without breaking lightweight
  agent-only builds. A deterministic offline builder now combines it with pinned
  pure-Python `pydicom` 3.0.2, exact hashes, no-index installation, and per-launch
  runtime checks. The package, private-display/network boundary, and real official
  checksum-verified Slicer synthetic runs pass on Strawberry Linux; ScanView
  signing/notarization remains pending.
- Browser sessions use a one-time local redirect and SameSite, HttpOnly cookie;
  service-backed measurement IDs join directly to the agent manifest while legacy
  folder-import drafts remain supported.
- Python DICOM catalog, provenance hashing, pairing candidates, local agent API, and
  JSON Schema implemented.
- Copy/repair/SHA-256 verification utility implemented.
- Patient-data exclusion rules and synthetic-only test policy implemented.
- Research, architecture, plan, roadmap, safety, and status committed to the project.

## Verification

- v0.14.0 source-SEG boundary-review milestone: passing on macOS arm64. The full
  Python suite reports 262 tests; the viewer reports 141 tests across 29 files;
  TypeScript typecheck, production build, Python bytecode compilation, diff hygiene,
  and all 32 Draft 2020-12 schemas pass. Adversarial coverage rejects incomplete
  acceptance, malformed/oversize/symlink/FIFO request input, interrupted-output
  cleanup, archive/mask/source tamper, catalog/source mutation, bearer POST, cross-
  origin POST, wrong media type, non-overwrite, and every authority escalation
  represented by the fixed permission locks.
- Patient-free production-browser QA used one generated 24-source/11-frame binary SEG.
  The native stack plus axial/coronal/sagittal MPR rendered four canvases; the source-
  authority warning and distinct qualified-review form remained visible. A revision-
  requested record traversed the real loopback POST and downloaded a 7,339-byte ZIP.
  CLI revalidation confirmed the exact original SEG/mask/source chain and five archive
  members; the static report omitted the source-carried label and retained creator,
  longitudinal, and response locks. The temporary fixture and download were moved to
  Trash; Mila data was not used.
- Offline runtime bundle v0.14.0: passing on macOS arm64. The retained owner-only
  5,555,555-byte ZIP has nine fixed-timestamp members and SHA-256
  `6ac7e02e53887089f6e54f496d7f578936ff4388be5923cf376eba800a38a729`.
  It contains the 3,157,956-byte ScanView wheel (SHA-256
  `78f9a6a5399e87e914ece316c3cd31ef37809bd003a9f13fb30606a7de6eaae4`),
  11 UI/worker/codec files (10,302,292 uncompressed bytes), all 32 schemas (307,629
  bytes), and pinned pydicom 3.0.2. The wheel and final ZIP were each built twice
  byte-identically.
- A fresh exact-artifact extraction verified and installed with `PIP_NO_INDEX=1`,
  reported version 0.14.0, embedded UI, 32 schemas, and both runtime-network and
  external-DICOM-processing-API requirements false. The packaged CLI created and
  validated an owner-only source-SEG review, refused overwrite, and the packaged
  loopback route refused bearer creation with 403 while accepting the browser-session
  same-origin request with 200 `application/zip` and `no-store`; the returned archive
  independently validated against the patient-free live source. dcmqi, highdicom, and
  NumPy were absent.
- Strawberry Linux v0.14 commissioning is pending: `strawberry.local` still resolves
  and answers on SSH, but the configured credentials were refused again on 2026-08-29.
  No password, host configuration, remote state, software, or patient data was changed
  or transferred. The exact v0.11 Linux gate remains passing.
- v0.13.0 viewer-state v2/source-SEG milestone: passing on macOS arm64. The full
  Python suite reports 259 tests; the viewer reports 136 tests across 28 files;
  TypeScript typecheck, production build, Python bytecode compilation, diff hygiene,
  and all 31 Draft 2020-12 schemas pass. Adversarial coverage rejects role/workspace,
  source-SEG object/segment/series/hash, active-MPR, privacy, permission, catalog, and
  changed-source mismatches.
- Patient-free production-browser QA used one generated sparse 24-source/
  11-frame SEG. Consult Prep exposed neutral `reference`/`reference` roles; the native
  stack plus axial/coronal/sagittal read-only MPR produced four canvases. After explicit
  opt-in, the bearer response carried only the allowed opaque SEG reference and
  guarded catalog hash with all safety locks; label, source text, mask hash/bytes,
  technical volume, and interpretation were absent. Opt-out immediately returned
  `not_shared`.
- Offline runtime bundle v0.13.0: passing on macOS arm64. The retained owner-only
  5,540,314-byte ZIP has nine fixed-timestamp members and SHA-256
  `76f3f3bd921dcde675c8487575c1b9d2bea74316e64877af1c22361cedb63780`.
  It contains the 3,143,044-byte ScanView wheel (SHA-256
  `987b88372edacc6e234c77dbbc01ca3cc0428b88518c539fcc93c8cba3e1ce0d`),
  11 UI/worker/codec files (10,291,372 uncompressed bytes), all 31 schemas (293,469
  bytes), and pinned pydicom 3.0.2. A second independent build was byte-identical.
  A fresh exact-artifact extraction installed with `PIP_NO_INDEX=1`, reported version
  0.13.0, embedded UI, 31 schemas, and both runtime-network and external-DICOM-
  processing-API requirements false; dcmqi, highdicom, and NumPy were absent.
- The exact packaged macOS gate created and validated an owner-only synthetic source-
  SEG catalog, returned 401/200 plus `no-store` for catalog authorization, refused
  bearer mask access with 403, published exact viewer-state v2 SEG context without
  clinical/mask fields, returned `source_changed` after guarded-source mutation, and
  then refused the source-SEG catalog with 409. The server bound only to loopback.
- Strawberry Linux v0.13 commissioning is pending: `strawberry.local` still resolves
  and answers on SSH, but the configured credentials were refused again on 2026-08-29.
  No password, host configuration, or remote state was changed; no v0.13 software or
  patient data was transferred. The exact v0.11 Linux gate remains passing.
- v0.12.0 independent dcmqi interoperability milestone: passing on macOS arm64. The
  full Python suite reports 258 tests; the viewer reports 135 tests across 28 files;
  TypeScript typecheck, production build, Python bytecode compilation, diff hygiene,
  and all 30 Draft 2020-12 schemas pass. A patient-free gate pinned dcmqi 1.5.6
  revision `60d63dc` and pydicom 3.0.2, proved external access was denied by macOS
  `sandbox-exec`, independently wrote and read a sparse 24-source/11-frame binary
  SEG, and required dcmqi, ScanView, and the fixed reference to reconstruct the same
  98,304 bytes, 3,083 foreground voxels, 3.946240 mL, and SHA-256
  `81946112b1311f1ee9ff4fe1d61f86d36ce82d076122b39b9d4e7a8e46cf82bb`.
- Patient-free production-browser QA opened the dcmqi-created object with one
  supported SEG, zero locked objects, 24 source slices, 11 mapped frames, and one
  segment. It rendered the read-only boundary in axial, coronal, and sagittal MPR
  planes with linked crosshairs, exposed no edit/evidence/export path, and reported
  no browser warnings or errors.
- Offline runtime bundle v0.12.0: passing on macOS arm64. The retained owner-only
  5,535,669-byte ZIP has nine fixed-timestamp members and SHA-256
  `71712961f15de19aea17a48d315099fde60b5f564458ef29c062f8fc6c4fa614`.
  It contains the 3,138,673-byte ScanView wheel (SHA-256
  `532ac041f940689eca554a206b34df76d7989a45ffd302724a9d1796889ac3dd`),
  11 UI/worker/codec files (10,289,454 uncompressed bytes), all 30 schemas (284,332
  bytes), and pinned pydicom 3.0.2. A second independent build was byte-identical.
  A fresh exact-artifact extraction installed with `PIP_NO_INDEX=1`, reported
  version 0.12.0, embedded UI, 30 schemas, and both runtime-network and external-
  DICOM-processing-API requirements false; dcmqi, highdicom, and NumPy were absent.
- The exact packaged macOS gate created and validated an owner-only dcmqi source-SEG
  catalog, then returned 401 for an unauthenticated catalog, 200 plus `no-store` for
  an authenticated catalog, 403 for bearer mask access, 200 for browser-session
  access to the exact 98,304-byte mask/hash/count, and 409 after a source mutation.
  The server bound only to `127.0.0.1`.
- Strawberry Linux v0.12 commissioning is pending: `strawberry.local` resolves and
  answers on SSH, but the configured `~/.ssh/id_ed25519` public key was refused on
  2026-08-29. No password, host configuration, or remote state was changed; no v0.12
  software or patient data was transferred. The exact v0.11 Linux gate remains
  passing, but the new Linux bubblewrap dcmqi path is not yet claimed as tested.
- v0.11.0 independent highdicom interoperability milestone: passing. The full Python
  suite reports 255 tests; the viewer reports 135 tests across 28 files; TypeScript
  typecheck, production build, Python bytecode compilation, diff hygiene, and all 29
  Draft 2020-12 schemas pass. A socket-denied, patient-free gate pinned highdicom
  0.28.1, NumPy 2.5.2, and pydicom 3.0.2, independently generated and read a sparse
  24-source/11-frame binary SEG, and required highdicom and ScanView to reconstruct
  the same 98,304 bytes, 3,083 foreground voxels, 3.946240 mL, and SHA-256
  `81946112b1311f1ee9ff4fe1d61f86d36ce82d076122b39b9d4e7a8e46cf82bb`.
  No patient data entered this gate, and it added no runtime processing service or API.
- Patient-free production-browser QA opened the independently generated object with
  one supported SEG, zero locked objects, 24 source slices, 11 mapped frames, and one
  segment. It rendered a locked overlay on exactly three axial/coronal/sagittal MPR
  canvases alongside the native stack, exposed no edit/evidence/export path, and
  reported no browser warnings or errors.
- Offline runtime bundle v0.11.0: passing on macOS arm64 and Strawberry Linux x86_64.
  The retained owner-only 5,532,095-byte ZIP has nine fixed-timestamp members and
  SHA-256 `4fb920ce93ab1459eb3953644162121a02539ba82e7de5881bbc0fc35b345aaf`.
  It contains the 3,135,113-byte ScanView wheel (SHA-256
  `f652f5b17c2152b754c2917be3dc0764be2ebf1c8d7075fd0d01c49b202e9f62`),
  11 UI/worker/codec files (10,289,183 uncompressed bytes), all 29 schemas (271,110
  bytes), and pinned `pydicom` 3.0.2. A second independent build was byte-identical.
  Fresh exact-artifact extractions installed with `PIP_NO_INDEX=1`, reported version
  0.11.0, the embedded UI and 29 schemas, and both runtime-network and external-DICOM-
  processing-API requirements false. highdicom and NumPy were absent from each exact
  installed runtime.
- Exact packaged macOS and Strawberry gates created and validated owner-only source-
  SEG catalogs, then returned 401 for an unauthenticated catalog, 200 plus `no-store`
  for an authenticated catalog, 403 for bearer mask access, 200 for browser-session
  access with the exact mask arithmetic/hash, and 409 after a source mutation.
  Strawberry listened only on loopback with no server-owned established external
  socket. Its separate disposable highdicom environment reproduced the independent
  oracle result. Only the exact software ZIP and patient-free synthetic data went to
  Strawberry; its entire test tree was deleted, and no Mila data left this computer.
- v0.10.0 strict source-carried DICOM SEG milestone: passing. The full Python suite
  reports 254 tests; the viewer reports 135 tests across 28 files; TypeScript
  typecheck, production build, Python bytecode compilation, diff hygiene, and all 29
  Draft 2020-12 schemas pass. Coverage includes stable source-byte guards, exact
  single-series native geometry, sparse binary decoding, multi-frame dimensions,
  standard derivation/purpose codes, explicit spatial preservation, duplicate/drift/
  mismatch refusal, aggregate decoded-work and retained-mask limits, source-change
  locks, owner-only CLI round-trip, authenticated/no-store catalog, browser-only mask,
  strict browser parsing/order/hash/count/arithmetic, and atomic read-only opening.
- Patient-free production-browser QA loaded one supported sparse SEG with one 3,083-
  voxel segment and 3.946240 mL technical native-grid volume, rendered its overlay on
  exactly three axial/coronal/sagittal canvases with linked crosshairs, and reported no
  browser errors or warnings. Paint, erase, measurement/evidence conversion, export,
  diagnosis, response, and clinical conclusions were absent. No patient SEG exists on
  the copied media and no Mila segmentation was displayed or inferred.
- Offline runtime bundle v0.10.0: passing on macOS arm64 and Strawberry Linux x86_64.
  The retained owner-only 5,531,237-byte ZIP has nine fixed-timestamp members and
  SHA-256 `715b161a4a55493b19d3b8895d97d1c8fd4644bf798c5617398d140ceacd503f`.
  It contains the 3,134,567-byte ScanView wheel (SHA-256
  `2237df3813bc21683c2a4a49111aa78637489cc7bd626ad4e4ba0974e11a30f4`),
  11 UI/worker/codec files (10,289,232 uncompressed bytes), all 29 schemas (271,110
  bytes), and pinned `pydicom` 3.0.2. A second independent build was byte-identical.
  Fresh extractions installed with `PIP_NO_INDEX=1`, reported version 0.10.0,
  `schema_count: 29`, `runtime_network_required: false`, and
  `external_dicom_processing_api_required: false`, then created and independently
  validated an owner-only patient-free source-SEG catalog on both platforms.
- Exact packaged macOS and Strawberry gates returned 401 without authority, 200 plus
  `Cache-Control: no-store` with bearer authority, 403 for bearer mask access, and 200
  for browser-session mask access with the exact 98,304-byte dense binary mask and
  matching SHA-256. Both returned 409 after mutating the disposable synthetic SEG.
  Strawberry listened only on loopback and had no server-owned established external
  socket. Only the exact ZIP and 25 patient-free synthetic DICOM files went to
  Strawberry; its entire temporary runtime/test tree was deleted afterward, and no
  Mila data left this computer.
- v0.9.0 source-bound GSPS milestone: passing. The full Python suite reports 242
  tests; the viewer reports 131 tests across 27 files; TypeScript typecheck,
  production build, Python bytecode compilation, diff hygiene, and all 28 Draft
  2020-12 schemas pass. GSPS coverage proves exact hashed same-study/patient sources,
  source-equivalent linear modality transforms, LINEAR VOI/polarity, exact full-image
  aspect, frame/mask/overlay/LUT/shutter/crop/scoping refusal, bounded geometry/text,
  semantic-authority locks, owner-only CLI round-trip, authenticated/no-store/audited
  endpoint behavior, source-change 409, strict browser parsing, pixel-corner mapping,
  atomic projection, and complete manipulation/evidence locking while active.
- Offline runtime bundle v0.9.0: passing on macOS arm64 and Strawberry Linux x86_64.
  The retained owner-only 5,510,395-byte ZIP has nine fixed-timestamp files and
  SHA-256 `d0ba563e5e8a0d41cac52b2da6f700a5ff22183b411af642f46012182c0dd1ae`.
  It contains the 3,114,039-byte ScanView wheel (SHA-256
  `59d1e28e9a76c4a5f4474b1807cf5fde33e0399f63fbfe1e466dfad60272ee6a`),
  11 UI/worker/codec files (10,262,098 uncompressed bytes), all 28 schemas (258,131
  bytes), and pinned `pydicom` 3.0.2. A second independent build was byte-identical.
  Fresh extractions installed with `PIP_NO_INDEX=1`, reported version 0.9.0,
  `schema_count: 28`, `runtime_network_required: false`, and
  `external_dicom_processing_api_required: false`, then created and independently
  validated an owner-only one-state patient-free GSPS catalog on both platforms.
- Exact packaged macOS and Strawberry loopback gates returned 401 without authority,
  200 plus `Cache-Control: no-store` with bearer authority, and 409 after mutating the
  disposable synthetic PR metadata. The optional two-event audit validated without
  patient content, tokens, paths, or request targets; each listener was loopback-only
  and the Strawberry server had no established external socket. Packaged-browser QA
  deliberately opened exact synthetic CT slice 2/3, displayed one polyline and one
  text object, locked both panes/tools/measurements/evidence/MPR/agent state, and
  restored native controls after Clear. Only the exact ZIP and four patient-free
  synthetic DICOM files went to Strawberry; 1,344 temporary test/runtime files were
  deleted afterward, and no Mila data left this computer.

- v0.8.0 agent consultation-plan milestone: passing. The full Python suite reports
  221 tests; the viewer reports 125 tests across 26 files; TypeScript typecheck,
  production build, Python bytecode compilation, diff hygiene, and all 27 Draft
  2020-12 schemas pass. Plan-specific coverage proves strict request/plan shape,
  owner-only output, stable catalog-content binding across a changed generation time,
  refusal of any other catalog change, exact instance ownership, one patient context,
  both MR and CT, distinct instances/studies, item-count and heading bounds, fixed
  false permissions, privacy-minimized summaries, exact-origin/media/size/session
  endpoint gates, duplicate-field/non-finite-number refusal, explicit free-text
  identifier risk, and browser-folder/server refusal. Production browser QA of the
  exact packaged UI validated two synthetic proposals, deliberately opened the exact
  MRI source at slice 2/3, prefilled its unreviewed heading, left the consultation
  board at 0/8 with no captures, and reported no browser errors.
- Offline runtime bundle v0.8.0: passing on macOS arm64 and Strawberry Linux x86_64.
  The retained owner-only 5,489,490-byte ZIP has nine fixed-timestamp members and
  SHA-256 `9a20a957db8d9a96fe69ac4289bdb230ecb91b39b609634791eb6546f27ba91f`.
  It contains the 3,093,470-byte ScanView wheel (SHA-256
  `2754a7803ebdb1ace33255bf736221ae5eded47556486a35ce21bafff32d351f`),
  11 UI/worker/codec files (10,235,734 uncompressed bytes), all 27 schemas (246,404
  bytes), and pinned `pydicom` 3.0.2. An independent second build was byte-identical.
  Fresh extractions installed strictly from included wheels with package-index access
  disabled and reported the embedded UI, all schemas, and both runtime-network and
  external-DICOM-processing-API requirements false. On both platforms the packaged
  CLI created and validated a two-item MR/CT navigation plan with mode-0600 outputs.
  The Strawberry loopback gate refused bearer-only plan submission with 403 and
  accepted the same plan through its browser session with 200 and a minimized summary.
  Only six synthetic DICOM files, a patient-free request, and the patient-free ZIP
  went to Strawberry; its staging tree was deleted, and no Mila data left this computer.
- v0.7.0 longitudinal-readiness milestone: passing. The full Python suite reports 210
  tests; the viewer reports 121 tests across 25 files; TypeScript typecheck,
  production build, Python bytecode compilation, diff hygiene, and all 26 Draft
  2020-12 schemas pass. Readiness coverage proves strict catalog shape and canonical
  hash binding, current MRI+CT refusal, valid same-patient MR candidates, invalid/date-
  missing/same-date/cross-patient/localizer refusal, fixed permission locks, bounded
  256-pair reporting, owner-only CLI output, authenticated/no-store endpoint behavior,
  and privacy-minimized bearer auditing. Production browser QA of the packaged UI
  shows the current page title/version, zero-candidate card, future same-modality
  requirement, explicit MR+CT consultation-reference limitation, and locked comparison.
- Offline runtime bundle v0.7.0: passing on macOS arm64 and Strawberry Linux x86_64.
  The retained owner-only 5,479,756-byte ZIP has nine fixed-timestamp members and
  SHA-256 `4aa77dfe6f0d4b057d0b6f4b71054a12eb787735611b18bce1add7e68621e1cc`.
  It contains the 3,084,032-byte ScanView wheel (SHA-256
  `dd320993afa639ec3f65c8d2d8d883989734026cb885ccde68d2640050de4395`),
  11 UI/worker/codec files (10,222,044 uncompressed bytes), all 26 schemas (240,034
  bytes), and pinned `pydicom` 3.0.2. An independent second build was byte-identical.
  Fresh extractions installed strictly from included wheels with package-index access
  disabled and reported the embedded UI, all schemas, and both runtime-network and
  external-DICOM-processing-API requirements false. On both platforms a synthetic
  two-date MR fixture produced one unreviewed metadata candidate while a synthetic
  MR+CT fixture produced zero and the future-same-modality requirement. Loopback
  unauthenticated readiness returned 401 and bearer readiness returned 200; mode-0600
  audit chains resumed across restart and contained no token, route, opaque ID, path,
  or DICOM marker. Deliberate chain tampering failed verification and startup without
  a traceback. Only 12 synthetic DICOM files and the patient-free ZIP went to
  Strawberry; its staging tree was deleted, and no Mila data left this computer.
- v0.6.0 privacy-minimized agent-access audit milestone: passing. The full Python
  suite reports 203 tests; the viewer reports 118 tests across 24 files; TypeScript
  typecheck, production build, Python bytecode compilation, diff hygiene, and all 25
  Draft 2020-12 schemas pass. Audit-specific coverage proves strict canonical events,
  append/resume hash chaining, independent privacy-minimized verification, owner-only
  creation, exclusive-writer locking, and refusal of tampering, partial events,
  symlinks, hard links, broad permissions, concurrent writers, external modification,
  and unsafe CLI startup. Browser-session reads create no bearer events. Authorized
  bearer reads fail closed with HTTP 503 if the configured audit becomes unavailable.
- Offline runtime bundle v0.6.0: passing on macOS arm64 and Strawberry Linux x86_64.
  The retained owner-only 5,471,647-byte ZIP has nine fixed-timestamp members and
  SHA-256 `a19a3944825249d2a56295f2f9eb4fd7067e96a478f1c42d714764779b2248d4`.
  It contains the 3,076,211-byte ScanView wheel (SHA-256
  `b0502d48776190214c634aef30f79986d8af29b19160fd2da763ccdd131e1b05`),
  11 UI/worker/codec files (10,217,834 uncompressed bytes), all 25 schemas (231,279
  bytes), and pinned `pydicom` 3.0.2. An independent second build was byte-identical.
  Fresh extractions on macOS and Strawberry Ubuntu / Python 3.14.4 verified and
  installed strictly from the included wheels with package-index access disabled,
  then reported the embedded UI, all 25 schemas, and both
  `runtime_network_required: false` and
  `external_dicom_processing_api_required: false`. On both platforms the packaged
  launcher indexed the same six-instance synthetic MR fixture; unauthenticated reads
  returned 401, browser reads succeeded without audit events, and six covered bearer
  operation classes appended a valid mode-0600 chain with no token, request target,
  opaque ID, path, DICOM marker, pixels, masks, measurements, or reviewed value.
  Restart continued the existing chain. A deliberately truncated copy failed both
  verification and server startup without a traceback. Only the patient-free fixture
  went to Strawberry; its staging tree was deleted, and no Mila data left this computer.
- v0.5.0 reviewed native-boundary milestone: passing. The full Python suite reports
  197 tests; the viewer reports 118 tests across 24 files; TypeScript typecheck,
  production build, diff hygiene, and all 24 Draft 2020-12 schemas pass. Adversarial
  coverage includes recursive accepted-comparison/review/SEG/source validation,
  bearer refusal for context and masks, exact browser capability, source/comparison
  mutation locks, strict context arithmetic/chronology/source ordering, and mask
  byte/hash/binary/foreground-count checks.
- Production browser QA with synthetic MR only: passing. The local production bundle
  rendered six canvases across two native tri-planar workspaces with no load banner or
  browser warning/error. Link mode was false by default; the independent mask centroids
  resolved to `14.3% · 0.0% · 33.3%` and `21.4% · 0.0% · 50.0%`. The page stated
  “Two accepted boundaries, two native spaces” and “Not registered. No spatial
  correspondence.” Read-only overlays were visible and normalized linking was
  separately verified as navigation only.
- Offline runtime bundle v0.5.0: passing on macOS arm64 and Strawberry Linux x86_64.
  The 5,466,019-byte owner-only ZIP has nine fixed-timestamp members and SHA-256
  `60b867598f7b64c05c8e17084a7301eefcd046c102e5718afe58c302f85c41ac`.
  It contains the 3,070,976-byte ScanView wheel (SHA-256
  `7405bef078a7fea763af23f7cc9b3ab7e9b7b9e29035aaa5bab63fc96989e12f`),
  11 UI/worker/codec files (10,217,834 uncompressed bytes), all 24 schemas (229,332
  bytes), and pinned `pydicom` 3.0.2. A second build from those exact two wheels was
  byte-identical. Fresh extractions on macOS and Strawberry Ubuntu / Python 3.14.4
  verified and installed with package-index access disabled, passed the 24-schema
  runtime gate and recursive comparison validator, launched the embedded UI/service,
  kept bearer agents out of context/masks, and returned both browser-session masks
  with exact byte counts, SHA-256 values, binary values, and foreground counts.
  Runtime and external DICOM-processing API requirements were both false. Only a
  six-instance synthetic fixture went to Strawberry; no Mila data left this computer.

- Python agent tests: 203 passing, including cross-patient and legacy-context
  rejection, visit-packet safety/integrity, key-image archive integrity, v3 JSON
  Schema conformance, ROI comparison checks, exact review joins, review event chains,
  non-overwriting amendments, privacy summaries, comparison-review transport and
  same-origin HTTP enforcement, local navigation membership/base-origin refusal,
  owner-only intent output, exact viewer-state catalog validation, same-origin/auth
  enforcement, expiry/revocation, static presentation integrity, registration hard
  gates, source immutability, pending-QA locks, child-process-group timeout, engine
  failure privacy, private permissions, parsed NRRD/transform integrity, fixed-space
  geometry, derivative tamper detection, strict registration-QA role/training,
  full-traversal, tolerance, 3-D landmark, source-anchor, standalone-lock, strict-JSON,
  atomic publication, browser-token separation, idempotent retry, volume-FD checks,
  mandatory OS-level registration network denial, no-sandbox refusal, strict accepted-
  review/bundle binding, bounded owner-only review import, same-size review-read and
  startup-validation race refusal, stale-evidence relocking,
  native-DICOM path-swap/in-place-change refusal, full raw/gzip uint8 support-mask
  decoding, non-binary/empty/wrong-grid/missing/extra/tampered/legacy-v1 refusal,
  seven-file review/display anchoring, mask mutation relocking, Linux namespace plus
  AF_UNIX-only seccomp enforcement, private no-TCP display gating, staged-runner hash
  binding, checksum-versus-signature trust claims, minimized agent summaries,
  reviewed-route capability separation,
  same-descriptor reviewed-volume streaming, consultation MR/CT/patient/study gates,
  live source hash/position binding, hostile nested/final ZIP refusal, strict JSON,
  output permissions/no-overwrite, presentation/source-anchor tamper detection, and
  consultation endpoint auth/origin/media enforcement; consultation-board patient/
  modality/study/instance gates, Unicode label safety, aggregate decoded-size limits,
  source-anchor tamper detection, live-source mutation refusal, privacy-minimized
  failures, authenticated exact-origin transport, owner-only/non-overwriting CLI
  output, and deterministic presentation; source-bound manual ROI evidence plus
  qualified boundary-review shape, recursive source/evidence binding, exact static
  record presentation, permission locks, malformed-input fail-closed behavior, and
  privacy-minimized summaries; two-review manual ROI volume-comparison shape,
  live-catalog chronology, nested source/evidence recursion, human pairing gates,
  arithmetic/page/source tamper refusal, exact in-memory endpoint transport, and
  privacy-minimized withholding; privacy-minimized bearer audit event/schema/hash-
  chain validation, secure append/resume, exclusive-writer and file-shape gates,
  fail-closed server integration, and concise CLI refusal; deterministic offline-
  bundle shape, pure-wheel gates, payload tamper/extra-file refusal, and non-overwrite.
- Viewer tests: 118 passing, including patient-context and local-only enforcement,
  pairing safety, physical-position mapping, key-image cross-linking, and measurement
  validation, the exact two-file visit-packet transport and relative same-origin
  endpoint contract, exact neutral two-view consultation transport/sidecar,
  cross-modality dataset-mode gates, consultation-board order/label/count/size and
  exact same-origin service transport, exact three-file comparison-review transport
  and source-slice lookup, strict one-use navigation parsing and atomic source
  resolution, and
  complete/regular MPR geometry gating, privacy-minimized viewer-state construction,
  source refusal, link-state labeling, same-origin publication/clear transport,
  oblique/permuted/RAS patient-space NRRD reformats, physical aspect, through-plane
  landmark mapping, bounded gzip decoding, strict v2 QA context and four-file
  transport, fail-closed probing, binary-mask boundary/matte/composite enforcement,
  strict reviewed-display v2 context validation, local SHA-256 image/mask and complete-bundle
  anchor checks, binary-mask raw/gzip decoding, all-three-plane nearest-neighbor mask
  sampling, mask-zero opacity/swipe leakage refusal and standalone matte behavior,
  chronology/source-separation refusal, encoded/predecode/decoded and render-dimension
  caps, ordinary-viewer state retention across mode switches, and rejected/malformed/
  legacy reviewed-context refusal; source-bound manual ROI evidence generation and
  the complete one-timepoint boundary-review decision/attestation workflow; reviewed
  volume-comparison preview, exact three-member transport, human acceptance gates,
  limitation-note requirement, same-origin endpoint, and local download behavior.
- All 25 JSON Schemas pass Draft 2020-12 validation; v1 registration/review/display
  schemas remain as historical contracts while generation and display require v2.
- Python source and utility bytecode compilation: passing.
- Viewer TypeScript typecheck: passing.
- Viewer production build: passing (Cornerstone codec bundle warnings noted).
- UI-embedded staged Python wheel build: passing; the 3,056,523-byte v0.4.0 wheel contains
  the registration host/runner/review/display module, viewer-state server module,
  source-bound manual ROI, boundary-review, and reviewed volume-comparison validators,
  viewer entry point, all 11 built UI/worker/codec files (10,187,057 bytes
  uncompressed), and all 23 JSON Schemas (216,361 bytes). A fresh isolated
  installation resolved its embedded UI and schemas
  without the source checkout.
- Offline runtime bundle v0.4.0 build plus macOS arm64 and Strawberry Linux x86_64 smoke tests:
  passing. The deterministic 5,451,088-byte ZIP contains nine fixed-timestamp members:
  `bundle.json` plus eight hash-manifested payloads, including the 3,056,523-byte
  embedded ScanView wheel and
  pinned 2,376,822-byte `pydicom` 3.0.2 wheel. A fresh extraction verified, installed
  with `PIP_NO_INDEX=1`, `--no-index`, and `--require-hashes`, then rechecked both
  versions, the embedded UI, all 23 schemas, the consultation, manual ROI review, and
  reviewed volume-comparison contracts, and explicit
  `runtime_network_required: false` and
  `external_dicom_processing_api_required: false` runtime assertions. A second build
  from the same wheels was byte-identical. The retained ZIP SHA-256 is
  `32c173f31a5efa098b1c295bea14557669419f07b3e922b519654ac6aa37a948`; the embedded
  wheel SHA-256 is
  `4ccd10d44561c9c1bcc2bd984dbfddc0ac6db9d035898c8d204ddffcb301dd1e`. Its packaged
  launcher indexed two synthetic MR studies / 6 instances and served its manifest over
  loopback. The exact final ZIP also verified and installed offline on Strawberry
  Ubuntu 26.04 x86_64 / Python 3.14.4, reported all 23 schemas with both network/API
  requirements false, validated the browser-created 0.002250→0.003000 mL reviewed
  comparison, and failed closed after one exact source byte was changed with all
  values withheld. No Mila data was sent. The remote synthetic staging directory was
  removed after the gate.
  The current patient-free v0.4.0 ZIP, prior v0.3.0/v0.2.0 ZIPs, and historical
  v0.1.0 ZIP are retained in the ignored local `release/` directory.
- Registration execution test: synthetic version-gated-engine success and failure
  paths pass, including required expected-launcher hash, strict engine report, parsed
  scalar NRRDs/fixed-space geometry, finite proper-rigid transform, owner-only modes,
  atomic no-replace publication, no partial output, private deleted diagnostics,
  process-group timeout, no-data engine preflight, restricted environment,
  source-change refusal, and v2 Schema plus semantic validation.
  The official 3D Slicer 5.12.3 macOS amd64 DMG was downloaded from Slicer, matched its
  published SHA-512, passed `hdiutil verify`, and carried a valid stapled notarization
  ticket. Gatekeeper and deep strict code-signature checks accepted the mounted and
  installed app as Kitware Developer ID team `W38PE5Y733`. The launcher and BRAINSFit
  hashes, release/runtime revision distinction, and precise trust limits are recorded
  in `docs/SLICER-ENGINE-TRUST.md` and a machine-readable packaging record.
  `registration-doctor` now finds the installed engine, BRAINSFit, BRAINSResample, and mandatory
  macOS network sandbox and reports ready with no external API required.
- Real-engine synthetic registration v2 test: normal ScanView commands processed two
  pairs of private synthetic 16-slice MR studies through the authenticated official
  Slicer/BRAINSFit/BRAINSResample process inside the macOS deny-all-network sandbox.
  All source byte counts and SHA-256 values remained identical. Both seven-file
  owner-only outputs independently passed schema and semantic validation, remained
  `generated_pending_qa`/`unreviewed`, exposed no computation or interpretation, and
  kept every derivative use locked. Known +2 mm displacements yielded approximately
  -2.008 mm and -1.998 mm moving-to-fixed translation with near-identity rotation.
  The equal-field mask contained 65,536/65,536 supported voxels; a deliberately wider
  fixed field contained 65,536/69,632 (94.117647%), providing a real nontrivial boundary
  and transform-direction oracle. No patient data was used.
- Registration-QA v2 production-build smoke test: the real-engine synthetic
  partial-coverage bundle opened through the distinct browser session and strict live
  backend context. The browser sequentially fetched fixed, moving, registered-moving,
  and sampling-support NRRDs from the four allowlisted loopback routes, accepted all
  hashes/headers/geometry, and created no render state until all four passed. Opacity,
  swipe, checkerboard, edges, and the technical boundary view rendered; the boundary
  view was exercised in axial, coronal, and sagittal planes before its attestation
  checkbox enabled. Accessible copy described mask-zero suppression and explicitly
  denied anatomy, tumor, segmentation, registration-quality, or comparability meaning.
  The browser diagnostic log was empty, page assets were loopback-only, the review
  stayed unapproved, and no decision was submitted.
- Reviewed-registration v2 production-build smoke test: a saved synthetic
  commissioning-only accepted review and its exact real-engine partial-coverage bundle
  opened the separate exploratory surface automatically. Fixed, registered-moving,
  support-mask, and composite data validated before render; axial, coronal, sagittal,
  opacity, and swipe all exposed mask-gated accessible labels and sampling-support-only
  warnings. The browser console was empty, and server requests were limited to loopback
  UI/context plus the three allowlisted NRRDs. Synthetic fixtures and review evidence
  were moved to recoverable Trash.
- Strawberry Linux runtime and engine test: the patient-free v0.2.0 offline ZIP verified and
  installed with `PIP_NO_INDEX=1`, `--no-index`, and required hashes on Ubuntu 26.04
  x86_64/Python 3.14.4. It resolved the embedded UI and all 21 schemas, indexed a
  three-instance synthetic MR series with direct identifiers excluded, and returned HTTP
  200 for embedded UI and bearer-authorized manifest over loopback. The official Slicer
  5.12.3 Linux amd64 archive matched its immutable bitstream size and published SHA-512;
  all 10,572 members and 385 links passed safe-root preflight before owner-only install.
  Slicer's documented Linux release process supplies no independent package signature,
  so the
  evidence is explicitly checksum/source verified. Bubblewrap 0.11.1 private namespaces,
  private Xvfb with TCP disabled inside bubblewrap, and seccomp allowing only `AF_UNIX`
  completed no-data preflight and both real-engine synthetic registrations. A live probe denied `AF_INET`
  socket creation with `EPERM`, no X11 TCP listener remained, Linux `renameat2` atomic
  publication succeeded once and refused overwrite, and no Mila data was transferred.
- Source-bound ROI cross-language release gate: the real pinned Cornerstone/dcmjs
  adapter serialized a sparse first/last-slice binary SEG Part-10 object. ScanView
  repaired the adapter's missing SOP Class/derivation/purpose references, reversed
  frame-position association, source Slice Thickness, and forbidden per-frame bit
  padding before serialization. The independent packaged Python validator matched
  all three exact synthetic source byte hashes, recovered 2 marked voxels and exactly
  4.0 mm³ / 0.004 mL, and kept every clinical/longitudinal lock false. The exact same
  artifact passed on macOS and Strawberry; changing one source byte failed nonzero,
  withheld all computed volume fields, and set evidence use to `none`. No Mila data
  was transferred to Strawberry.
- Manual-boundary-review production gate: a patient-free 12-slice, 64×64 synthetic
  MR series loaded through the production launcher and rendered all three MPR planes.
  Browser paint produced 454 native-grid voxels / 0.908 mL. The complete qualified
  form kept export locked until reviewer fields, accepted/suitable decisions, all
  eight checks, and the fixed attestation were present. Its exact four-member review
  archive passed the independent source-recursive validator on macOS and Strawberry,
  reported self-asserted/unverified identity and future pairing-review eligibility,
  and kept longitudinal link, percent change, response classification, diagnosis,
  and clinical conclusion false. Appending one byte to the exact synthetic source
  caused nonzero refusal, withheld the volume, and set evidence use to `none` on both
  platforms. The corrected MPR startup produced no browser errors, and no Mila data
  was transferred to Strawberry.
- Synthetic browser smoke test: two canvases render; all five viewer controls activate.
- Real-data production smoke test: copied JPEG 2000 MRI and CT pixels render in two
  1162×1200 canvases; the full folder produces 57 pixel series; local server logs show
  only bundled UI/worker/OpenJPEG assets.
- Measurement round-trip smoke test: a temporary real-image manual length exported,
  passed the agent validator, and restored after viewer/source reopen. Temporary test
  DICOM copies and the test measurement packet were then removed.
- Bidirectional round-trip smoke test: a synthetic native MR stack produced a
  37.7 × 25.1 mm overlay and 946.2 mm² table result; its v2 packet passed local agent
  validation and restored after a complete page/source reopen with no browser errors.
  The test files were moved to Trash after verification.
- Unified synthetic smoke test: the browser established a private local session,
  discovered the catalog without a folder picker, streamed native DICOM pixels,
  exported a valid bidirectional packet, and produced series/instance IDs that joined
  directly to the manifest.
- Elliptical ROI round-trip smoke test: a synthetic axial MR stack displayed R/L/A/P
  orientation labels, produced a 61.7 × 55.1 mm ellipse and 2668.4 mm² area, exported
  a locally valid v3 packet, and restored the overlay after a complete page reopen.
  The session requested only loopback UI/worker/instance resources; synthetic artifacts
  and the exported draft were moved to Trash.
- Key-image browser smoke test: a synthetic native ROI exported as a 151 KB ZIP whose
  1162×1296 PNG visibly retained the ellipse, patient-orientation labels, and permanent
  unreviewed footer. The local agent verified both SHA-256 links, PNG structure and
  dimensions, embedded v3 measurement, and exact source-instance linkage. The browser
  reported no errors or non-loopback requests; all synthetic artifacts were moved to
  Trash after inspection.
- Key-image v2 production smoke test: the unified viewer indexed and rendered the
  synthetic native MR stack, then exported a 127 KB archive. The agent and v2 JSON
  Schema accepted it; opaque study, series, and patient-context fields joined exactly
  to the local catalog without exposing their values, and only loopback resources were
  requested. The exported archive was moved to Trash after verification.
- Clinician visit-packet smoke test: two synthetic dated key-image v2 MR archives with
  one matching opaque patient context and distinct studies assembled and independently
  revalidated through the CLI. The responsive static review page showed
  both images, dates, sequence labels, source slices, questions, checklist, and notes
  area with prominent unreviewed/no-diagnosis/no-response warnings. It contained no
  scripts or external links and requested only the page and two PNGs from loopback;
  the synthetic archive and images were moved to Trash after inspection.
- One-click visit-packet production smoke test: two synthetic dated MR studies
  rendered in the live unified viewer, scored as plausibly comparable, and exported
  from the two displayed source slices through `POST /v1/visit-packets`. The 337 KB
  archive contained exactly nine files and passed file, nested-component, and static-
  presentation validation with a 73-day interval and no computed result or response
  conclusion. The server log contained only opaque local resource paths and one
  successful loopback POST. The synthetic studies and export were moved to Trash.
- MPR production smoke test: a synthetic 24-slice MR volume visibly rendered the
  expected three-dimensional structure in axial, coronal, and sagittal planes; all
  controls activated and close/reopen cleaned up without errors. The copied study
  then exposed 42 geometry-eligible series, and a 62-slice MR volume reached all
  three stable planes through only the bundled OpenJPEG WebAssembly decoder and
  opaque loopback instance routes. No copied-study screenshot or derivative was
  retained; the synthetic source was moved to Trash.
- Linked-crosshair production smoke test: the same synthetic volume visibly showed
  colored crosshairs in all three planes; axial and coronal clicks changed one shared
  accessible LPS point, reset returned to the exact volume center, and close/reopen
  rebuilt without failure. A copied 62-slice JPEG 2000 MR then exposed 12 SVG lines
  and 3 center markers; point movement and reset succeeded through bundled OpenJPEG
  and only opaque loopback routes. No copied-study screenshot or derivative was
  created or retained; the synthetic source was moved to recoverable Trash.
- Explicit-pairing production smoke test: two synthetic dated same-patient MR studies
  scored as plausibly comparable. A bounded pasted v3 packet restored 20 mm and 16 mm
  source measurements, and the human-selected “Target lesion A” pair previewed −4 mm
  and −20% with no interpretation. The downloaded v1 JSON passed both JSON Schema and
  the privacy-minimized agent validator; session deletion removed one annotation and
  cleared the preview while leaving DICOM unchanged. Only bundled UI/worker and opaque
  loopback instance routes were requested. The final rebuilt bundle repeated the
  preview and then blocked a deliberately reversed baseline/follow-up selection with
  no stale preview. All synthetic inputs and output were moved to recoverable Trash.
- Comparison-review browser smoke test: a synthetic accepted-for-discussion archive
  recursively validated its visit/comparison sources, displayed both local key
  images, all three bidirectional arithmetic rows, the unreviewed safety statement,
  and two complete review-history events in one semantic script-free page. The only
  successful requests were `review.html` and its two local PNGs; the synthetic
  archives and extracted page were moved to recoverable Trash.
- One-click comparison-review production smoke test: two synthetic dated same-patient
  MR studies and a validated pasted measurement packet produced a 20→16 mm explicit
  pair. The viewer automatically restored source slices 2/6 and 5/6, enabled export,
  and sent one successful local `POST /v1/comparison-reviews`. The downloaded 569 KB
  seven-file archive passed recursive agent validation and its script-free page
  visibly showed both measurement overlays, −4 mm/−20% arithmetic, and prominent
  unreviewed/self-attested warnings. Server logs contained only bundled local assets,
  opaque instance routes, and that one POST; all synthetic artifacts were moved to
  recoverable Trash.
- Agent-navigation production smoke test: the local `viewer-link` command and the
  authenticated launcher targeted synthetic baseline slice 2/6 and follow-up slice
  5/6 by exact opaque IDs. Both rendered at those positions after initialization, the
  browser immediately reduced the address to `/`, and the UI kept pairing visibly
  unreviewed. The same intent also applied without reload in an already-open tab; a
  deliberately misowned same-tab intent was rejected without changing either pane.
  Server logs contained only `/`, bundled assets, the manifest,
  and opaque instance routes—never the fragment or navigation IDs. Temporary intent
  and manifest files were moved to recoverable Trash.
- Opt-in viewer-state production smoke test: the synthetic unified workspace returned
  `not_shared` before consent, visibly enabled sharing, and exposed exact opaque
  baseline/follow-up positions plus `zoom` and `patient_position` after UI changes.
  The response contained fixed no-pixels/no-direct-identifiers/no-persistence flags
  and no descriptions, dates, measurement values, geometry, or paths. Opt-out
  immediately returned to `not_shared`; browser diagnostics had no errors, and server
  logs contained only loopback assets, opaque instance routes, and payload-free
  viewer-state request lines.
- Unified complete-copy smoke test: 2 studies, all 57 renderable MR/CT series, and
  10,286 instances loaded from the local service. A 62-slice native stack rendered
  through the bundled OpenJPEG WebAssembly decoder with no browser errors or external
  requests.
- Consultation-board production smoke test: two same-context synthetic MR/CT studies
  rendered in neutral Image A/Image B panes. Explicit headings were captured in
  memory, all four readiness gates activated, and one local
  `POST /v1/consultation-boards` returned a 90,640-byte nine-file ZIP. Independent
  agent validation reported file, nested-component, source-anchor, and deterministic-
  presentation integrity true, with both comparison/response authorization flags
  false and `external_api_required: false`. The static page had no script or external
  URL; browser diagnostics were empty and server logs contained only loopback assets,
  opaque instance reads, and the single POST. The browser-created file demonstrated
  host-controlled `0644` download mode, so the UI now instructs users to move/protect
  retained sensitive boards; the synthetic DICOM and board were moved to recoverable
  Trash.
- Reviewed volume-comparison production smoke test: two synthetic same-patient MR
  studies rendered as exact baseline/follow-up source panes. The browser loaded both
  accepted boundary-review ZIPs, displayed 0.002250 and 0.003000 mL with catalog dates,
  kept export disabled until every qualified pairing gate and attestation was complete,
  and downloaded the exact five-file archive through one local POST. Independent
  validation reported +0.000750 mL / +33.333% over 31 days for discussion only; moving
  either source pane relocked export, and a one-byte source change failed nonzero with
  every value withheld. Browser diagnostics were empty. All inputs were synthetic.
- Real-copy Consult Prep smoke test: the same catalog automatically opened the
  neutral consultation workspace, showed Image A/Image B instead of timepoint roles,
  kept approximate linking disabled, hid longitudinal lesion pairing and response
  export controls, and enabled the consultation-packet action only after one MRI and
  one CT from distinct studies were explicitly selected. Both native stacks rendered
  through bundled local assets, browser diagnostics were empty, and no screenshot or
  patient derivative was created or retained.
- Hardened native-route real-copy smoke test: a fresh private catalog found the same
  2 studies and 10,286 instances; one authenticated opaque instance request returned
  HTTP 200, and both the streamed body and `X-Content-SHA256` matched the exact local
  source bytes. The request log exposed only the redacted instance route.
- Real patient metadata inventory: complete without logging identifying metadata.
- Full source/destination SHA-256 verification: passing for all 10,321 source files.

## Known gaps

- Source-carried SEG support is intentionally a narrow ScanView profile, not full DICOM
  conformance. Fractional/compressed SEG, multiframe sources, resampling, non-native or
  irregular grids, and unsupported reference/dimension forms are refused. The pinned
  highdicom sparse-reference and dcmqi writer/reader gates now pass on macOS; the
  dcmqi Linux gate, real vendor-produced fixtures, broader interoperability, and
  comparison with a clinical imaging system remain.
  A displayed mask, label, code, creator, algorithm, count, or technical volume is not
  a reviewed tumor segmentation, clinical conclusion, or treatment-response result.
- Different-frame longitudinal exams still use approximate normalized linking until
  a reviewed registration exists; patient-position linking is only enabled for a
  shared compatible frame.
- The current MRI+CT consultation packet and multi-view board are source-bound
  conversation aids only. Neither establishes chronology, aligns anatomy, matches a
  lesion, compares intensity, assesses tumor response, authenticates reviewer
  identity, or replaces review in the clinical imaging system.
- Clinical-organization identity authentication, digital signatures, and medical-
  record sign-off remain. The current review chain is self-attested and explicitly
  unverified. Elliptical ROI is a 2D manual draft. A source-bound binary ROI can now
  receive a separate qualified, self-attested boundary-review record for one-timepoint
  discussion, and two accepted records can enter a separate reviewed arithmetic-
  volume pairing. This is still not authenticated clinical sign-off, a proven tumor
  segmentation, spatial boundary-change evidence, a response classification, or a
  clinically validated tumor-volume comparison.
- The optional bearer audit identifies only possession of the process token and fixed
  operation class. It cannot authenticate which person, model, agent, or process made
  a request; privileged host users can still replace or delete the file. Organization-
  authenticated identity and signed medical-record audit integration remain future work.
- Signed/notarized macOS/Linux release packaging remains pending. The wheel, offline
  bundle, and source-checkout launcher are working and verified on macOS; the earlier
  exact v0.11 bundle passes on Strawberry Ubuntu 26.04 x86_64, while current v0.13
  commissioning awaits restored SSH authentication. It still requires host Python
  3.11+ and is not yet signed.
- Registration generation, local QA, accepted-review opacity/swipe display, an
  authenticated official macOS engine, an official-source/checksum-verified Linux
  engine, real-engine synthetic execution on both platforms, and mandatory pixel-level
  moving sampling-support gating now exist. A real same-modality patient run, qualified
  real-case decision, and signed ScanView release remain pending. Sampling support is
  not shared-anatomy or registration-quality evidence, and there is still no tumor segmentation, response
  criteria, reviewed component-specific tumor segmentation, or automated medical
  conclusion.
