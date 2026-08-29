# Status

Last updated: 2026-08-28 18:02 PDT

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

## Repository

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
  bearer-authorized agents. It publishes only exact opaque pane positions, tool/link
  state, optional MPR series, and evidence counts; catalog validation, 30-second
  expiry, visible opt-out, publisher revocation, `no-store`, and default-off behavior
  are enforced. It contains no pixels, descriptions, dates, measurement content,
  paths, or direct identifiers.
- A version-gated local Slicer 5.12.3 revision 34627/BRAINSFit rigid-registration
  executor now accepts only explicitly attested, identity-unverified matching opaque
  patient context; same-modality distinct-study chronology; original-primary
  brain/head images; conservative sequence and explicit contrast matching; regular
  per-instance volume geometry; score ≥80; and SHA-256 provenance. Source bytes are
  rehashed before and after generic private staging; Slicer temp/cache paths stay
  inside that deleted private job space. Slicer must run inside OS-enforced network
  isolation—a macOS deny-all-network sandbox or, on supported 64-bit Linux, `bwrap`
  private namespaces plus seccomp denial of socket creation, socket pairs, and
  io_uring—with no weaker `unshare`-only or unsandboxed fallback. DICOM is never
  mutated and ScanView requires no external processing API.
- Successful registration creates an atomic no-replace, owner-only six-file
  derivative directory containing fixed/moving/registered scalar NRRDs, one finite
  proper-rigid text ITK transform in DICOM patient LPS, an engine report, and a strict
  v1 manifest. Every source bundle remains `generated_pending_qa`/`unreviewed`; review
  never mutates it.
- An isolated browser-capability registration-QA workspace now provides true LPS
  axial/coronal/sagittal reformats for oblique/permuted NRRDs, derived reference and
  registered views, physical aspect, independent 3-D landmarks, opacity, swipe,
  checkerboard, edges,
  strict browser-recorded full-coverage traversal evidence, and one separate
  hash-bound JSON decision.
  A bearer token alone cannot fetch the NRRDs or submit review. Qualified self-attested
  acceptance requires a trained clinician/medical physicist, three spatially distributed
  landmark pairs within the geometry-derived tolerance, three aligned qualitative
  landmarks, every checklist item, every plane/mode, and no defect. It can authorize
  only exploratory shared-coverage overlay/swipe; all other derivative uses remain
  locked.
- The ordinary local workspace can now consume one accepted, owner-only review only
  with its exact live six-file bundle. A separate browser-only surface exposes only
  fixed reference and registered-moving NRRDs, verifies hashes and geometry, loads
  bounded files sequentially, enforces encoded/predecode/decoded and render-dimension
  ceilings, recomputes the complete bundle anchor in the browser, and implements
  opacity/swipe only. Rejected, stale, tampered, linked, mismatched, missing, or unsafe
  inputs fall back to ordinary DICOM with registered pixels locked. Both images are
  labeled derived, registered moving is labeled resampled, native DICOM remains
  authoritative, and shared coverage is explicitly reviewer-visual because the bundle
  has no machine overlap mask. Browser-downloaded decisions must pass the bounded
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
- Consultation packet v1 accepts exactly one MR and one CT view from distinct studies
  with one matching opaque patient context. Each neutral key-image sidecar uses a
  `view_a`/`view_b` slot instead of a timepoint role. The loopback assembler checks
  the exact live catalog position and rehashes the guarded DICOM source descriptor,
  then returns a nine-file, script-free, owner-sensitive archive with empty computed
  and interpretation arrays. Its deterministic review page binds both DICOM byte
  counts/SHA-256 values and permanently says reference views only, not a comparison,
  unregistered, unreviewed, not for diagnosis, and no response conclusion.
- The same consultation contract is available through strict non-overwriting CLI
  assembly/validation and `POST /v1/consultation-packets`. All nested input and output
  ZIP members, JSON keys, digests, source metadata, positions, modalities, study and
  patient-context gates are validated locally; the server persists no artifact.
- Versioned measurement, key-image, consultation-key-image, consultation-packet,
  numeric-comparison, visit-packet,
  comparison-review, navigation-intent, viewer-state, rigid-registration,
  registration-QA, and reviewed-registration-display JSON Schemas plus local validation
  are implemented. Same-series pairs, unknown units, mismatched measurement types, and
  mismatched visual/numeric evidence are refused; no response label is emitted.
- Unified `scanview-agent launch` path implemented: one loopback process serves the
  bundled UI, manifest, pairing candidates, and protected native DICOM instances.
  Every instance route is bound to its startup file identity/change metadata and
  optional catalog SHA-256, refuses final-component symlinks or later changes, and
  hashes an exact ephemeral local snapshot before sending patient bytes.
- The staged release builder embeds the viewer, workers, and local codecs into a
  self-contained wheel together with all 16 contracts without breaking lightweight
  agent-only builds;
  signing/notarization and Linux execution remain pending.
- Browser sessions use a one-time local redirect and SameSite, HttpOnly cookie;
  service-backed measurement IDs join directly to the agent manifest while legacy
  folder-import drafts remain supported.
- Python DICOM catalog, provenance hashing, pairing candidates, local agent API, and
  JSON Schema implemented.
- Copy/repair/SHA-256 verification utility implemented.
- Patient-data exclusion rules and synthetic-only test policy implemented.
- Research, architecture, plan, roadmap, safety, and status committed to the project.

## Verification

- Python agent tests: 128 passing, including cross-patient and legacy-context
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
  native-DICOM path-swap/in-place-change refusal, Linux namespace/seccomp no-socket
  enforcement, minimized agent summaries, reviewed-route capability separation,
  same-descriptor reviewed-volume streaming, consultation MR/CT/patient/study gates,
  live source hash/position binding, hostile nested/final ZIP refusal, strict JSON,
  output permissions/no-overwrite, presentation/source-anchor tamper detection, and
  consultation endpoint auth/origin/media enforcement.
- Viewer tests: 80 passing, including patient-context and local-only enforcement,
  pairing safety, physical-position mapping, key-image cross-linking, and measurement
  validation, the exact two-file visit-packet transport and relative same-origin
  endpoint contract, exact neutral two-view consultation transport/sidecar and
  cross-modality dataset-mode gates, exact three-file comparison-review transport and source-slice
  lookup, strict one-use navigation parsing and atomic source resolution, and
  complete/regular MPR geometry gating, privacy-minimized viewer-state construction,
  source refusal, link-state labeling, same-origin publication/clear transport,
  oblique/permuted/RAS patient-space NRRD reformats, physical aspect, through-plane
  landmark mapping, bounded gzip decoding, strict QA context, fail-closed probing,
  strict reviewed-display context validation, local SHA-256 volume and complete-bundle
  anchor checks, chronology/source-separation refusal, encoded/predecode/decoded and
  render-dimension caps, ordinary-viewer state retention across mode switches, and
  rejected/malformed reviewed-context refusal.
- All 16 JSON Schemas pass Draft 2020-12 validation.
- Python source and utility bytecode compilation: passing.
- Viewer TypeScript typecheck: passing.
- Viewer production build: passing (Cornerstone codec bundle warnings noted).
- Self-contained staged Python wheel build: passing; the 2,909,473-byte wheel contains the
  registration host/runner/review/display module, viewer-state server module, viewer
  entry point, all 11 built UI/worker/codec files (9,882,460 bytes uncompressed), and
  all 16 JSON Schemas (122,332 bytes). A fresh isolated installation resolved its
  embedded UI and schemas without the source checkout; temporary release, installation,
  and installer-log artifacts were moved to recoverable Trash.
- Registration execution test: synthetic version-gated-engine success and failure
  paths pass, including required expected-launcher hash, strict engine report, parsed
  scalar NRRDs/fixed-space geometry, finite proper-rigid transform, owner-only modes,
  atomic no-replace publication, no partial output, private deleted diagnostics,
  process-group timeout, no-data engine preflight, restricted environment,
  source-change refusal, and v1 Schema plus semantic validation.
  `registration-doctor` confirms the required macOS network sandbox is available but
  reports that the real required Slicer executable is not installed on this host, so a
  real-engine registration has not been claimed. A real Linux sandbox execution and
  binary-distributor authentication remain pending.
- Registration-QA production-build smoke test: the distinct browser bootstrap/session
  capability opened the isolated workspace while bearer-only access remained denied in
  server tests. Five patient-space canvases rendered with correct sagittal A/P/S/I
  orientation, the derived moving reference pane stayed explicitly approximate, all
  three plane buttons and four QA modes activated, untrained acceptance remained
  disabled, trained role selection alone did not enable submission, no external
  resources were present, and the browser console reported no errors. Synthetic
  fixtures were moved to Trash.
- Reviewed-registration production-build smoke test: a saved synthetic accepted review
  and its exact live bundle opened the separate exploratory surface automatically.
  Fixed, registered-moving, and composite canvases rendered; axial, coronal, sagittal,
  opacity, swipe, ordinary-DICOM exit, and reviewed-mode re-entry all worked. The
  one-time session token was removed from the URL, the browser reported no errors, and
  server requests were limited to loopback UI, context, manifest, and the two allowlisted
  NRRDs. Synthetic fixtures and the isolated wheel-install test were moved to
  recoverable Trash.
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

- Different-frame longitudinal exams still use approximate normalized linking until
  a reviewed registration exists; patient-position linking is only enabled for a
  shared compatible frame.
- The current MRI+CT consultation packet is a source-bound conversation aid only. It
  does not establish chronology, align anatomy, match a lesion, compare intensity,
  assess tumor response, authenticate reviewer identity, or replace review in the
  clinical imaging system.
- Clinical-organization identity authentication, digital signatures, and medical-
  record sign-off remain. The current review chain is self-attested and explicitly
  unverified. Elliptical ROI is a 2D manual draft, not segmentation or volume
  measurement.
- Bearer reads of live viewer state do not yet have an append-only access audit.
  Any future audit must exclude tokens, payloads, and patient content.
- Signed/notarized macOS/Linux release packaging remains pending; the self-contained
  wheel and source checkout launcher are working and verified on macOS.
- Registration generation, local QA, and accepted-review opacity/swipe display exist,
  but there is no installed required engine, trusted full-engine signature/checksum
  verification, real same-modality patient run, or qualified real-case decision. There
  is still no machine-enforced coverage mask, segmentation, response criteria, or
  automated medical conclusion.
- Linux packaging/smoke testing remains pending.
