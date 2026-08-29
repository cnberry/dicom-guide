# Plan and acceptance criteria

## Goal

Create a cross-platform local DICOM visualizer that helps Mila and her clinicians
review MRI/CT studies over time, while giving software agents a structured,
traceable interface. Preserve original data and never turn an unreviewed algorithmic
result into a medical conclusion.

## Work phases

### Phase 0 — preserve the source

- Finish the existing single Finder transfer from `PATIENT_DATA`.
- Inventory source and destination after Finder releases the disc.
- Run byte-for-byte SHA-256 verification and repair missing/mismatched files.
- Keep the verification manifest with the local copy, never in Git.

### Phase 1 — local comparison MVP (current)

- Local folder import and DICOM stack rendering.
- Study/series inventory and timeline metadata.
- Manual baseline/follow-up selection.
- Native side-by-side view with approximate linked position.
- Transparent compatibility suggestion with reasons/warnings.
- Read-only catalog/API and versioned agent JSON contract.
- Explicit safety, privacy, and provenance UI.
- Source-linked manual length and bidirectional evidence with a human-readable table.
- Validated DICOM patient-orientation labels and source-linked 2D elliptical ROI
  evidence.
- Geometry-gated single-series local MPR with three orthographic patient-axis planes
  and explicit interpolated-derivative labeling.
- Strictly geometry-gated, source-bound manual binary ROI volume evidence on one
  native MR/CT series, with a DICOM SEG-format export, versioned sidecar, exact source
  rehashing, independent mask/volume recomputation, and no clinical-approval or
  longitudinal authority.
- Separate source-revalidated manual ROI boundary-review archives with a qualified-role
  human form, represented-tissue and inclusion/exclusion definitions, suitable-
  acquisition and complete three-plane gates, a script-free printable page, and an
  independent privacy-minimized validator. Acceptance is self-attested and for
  discussion only; it cannot establish a cross-timepoint link or response.
- Separate reviewed manual ROI volume-comparison archives that accept only two exact
  independently accepted boundary reviews plus a qualified pairing request. Live
  catalog chronology, both nested DICOM SEG/source chains, same patient context,
  modality, distinct studies/series, same lesion/tissue, comparability, registration
  consideration, and checklist gates are enforced before discussion-only arithmetic.
  Response, causality, spatial localization, diagnosis, and clinical conclusion stay locked.
- Display-only reopening of one accepted volume-comparison archive as two independent
  native tri-planar workspaces with exact, rehashed, read-only binary boundaries.
  Each scan centers on its own mask; optional normalized-grid navigation is off by
  default and never grants registration, correspondence, overlay, subtraction,
  propagation, spatial-change localization, or response authority.
- Physically linked, visible LPS crosshairs within one MPR volume, with canonical
  planes protected from oblique rotation and slab-thickness manipulation.
- Source-linked local key-image archives with display provenance, permanent review
  labeling, measurement evidence, and agent-verifiable integrity.
- Local clinician visit-packet assembly with hard longitudinal gates, a static
  side-by-side human review page, and a versioned agent-verifiable file manifest.
- One-click visit-packet export from the two live viewer panes through a bounded,
  authenticated same-origin loopback request; assembly and validation remain local
  and in memory.
- Dataset-aware Consult Prep mode when no valid dated same-modality longitudinal
  source pair exists. It uses neutral Image A/Image B roles, disables approximate
  cross-exam linking and lesion-pair arithmetic, and never silently treats MRI+CT as
  a treatment-response pair.
- Catalog-hash-bound longitudinal-readiness reporting for agents and a matching human
  card. Both require valid dates, eligible MR/CT stacks, distinct studies, and one
  opaque patient context before surfacing metadata candidates; all selection,
  registration, lesion, response, diagnosis, and conclusion authority remains false.
- Stable-catalog-content-bound agent consultation plans for 2–8 exact native MRI/CT
  source instances and bounded discussion headings. The local CLI creates and checks
  them; a same-origin browser-session endpoint rejoins every source to the live catalog;
  the viewer exposes only deliberate per-item navigation and never auto-opens or
  captures a proposal. Agent identity, source relevance, chronology, registration,
  lesion linkage, response, treatment effect, diagnosis, and conclusion authority
  all remain false.
- Source-bound DICOM GSPS display support for a deliberately narrow subset: hashed
  same-study single-frame MR/CT sources, source-equivalent linear modality transform,
  LINEAR VOI, identity presentation LUT, exact full-image SCALE TO FIT with matching
  aspect, and PIXEL POLYLINE/anchor-text annotations. Unsupported structures fail
  closed as a whole; runtime projection is atomic; deliberate display locks all
  manipulation, measurement, evidence, MPR, and agent-state paths until cleared.
  Creator identity and source-text clinical meaning are not assessed; measurement,
  finding, diagnosis, and response authority remain false.
- Source-carried DICOM SEG read-only display for a deliberately narrow profile:
  guarded uncompressed binary SEG plus exact regular single-frame MR/CT sources,
  exact per-frame native source mapping, consistent multi-frame dimensions, bounded
  decoding/masks, independent physical-order and mask-hash validation, and browser-
  session-only dense mask access. Spatial Locations Preserved may be `YES` or absent
  only after exact identity and geometry proof; explicit negative or unknown values
  fail closed. Full DICOM conformance, creator/algorithm identity, boundary accuracy,
  tissue meaning, diagnosis, and response authority remain absent.
- Independent source-SEG interoperability: an optional pinned highdicom test creates
  a sparse patient-free object, reconstructs it through highdicom's source-instance
  API, and requires identical ScanView dense bytes, hash, count, and native-grid
  arithmetic. The test denies socket connections while handling DICOM and adds no
  runtime dependency or broader clinical permission.
- A second independent source-SEG interoperability gate pins NCI/QIICR dcmqi as both
  writer and reader. It runs both executables inside OS-enforced external-network
  isolation, requires exact dcmqi/reference/ScanView mask equality, exercises the
  standard's optional Spatial Locations Preserved path, and adds no runtime dependency
  or broader clinical permission.
- Source-bound one-MR/one-CT consultation packets for clinician discussion. Neutral
  key-image archives, exact live-catalog position and source-byte rehashing, strict
  cross-study/patient-context gates, static human presentation, privacy-minimized
  validation, CLI workflows, and a bounded same-origin in-memory endpoint are
  implemented without external processing APIs.
- Source-bound consultation boards for 2–8 explicitly labeled native MRI/CT views.
  Each item is rejoined to the guarded live catalog and exact source bytes; the board
  remains a neutral discussion aid with no chronology, alignment, lesion identity,
  comparison, diagnosis, treatment-response, or external processing authority.
- Explicit, numeric-only local measurement comparison for agents.
- Human/agent measurement workspace with strict pasted-JSON import, session-only
  deletion, explicit labeled lesion pairing, local numeric preview/export, and a
  privacy-minimized comparison validator.
- Local comparison-review archives with exact visual/numeric evidence joins,
  script-free human presentation, self-attested checklist decisions, non-overwriting
  amendment history, and privacy-minimized integrity validation.
- One-click comparison-review export from the current explicit pair and its two exact
  live source slices through a bounded same-origin request; nested assembly and
  validation remain local, in memory, and source-read-only.
- Versioned agent-to-human navigation from exact opaque catalog series/instances via
  a one-use local fragment, with atomic catalog resolution, immediate URL cleanup,
  and no effect on pairing or review state.
- Explicit opt-in, read-only agent access to privacy-minimized live viewer state via
  the authenticated loopback service; publications are memory-only, validated
  against the catalog, revoked on opt-out, and expire after 30 seconds.
- Optional owner-only, privacy-minimized, hash-chained bearer-access auditing with
  secure resume, exclusive locking, application append/fsync, independent CLI
  verification, fixed no-content events, and fail-closed sensitive bearer reads.
- Same-origin loopback launcher for the UI, catalog, and protected native instances.
- Deterministic macOS/Linux offline runtime bundle with the embedded UI/contracts,
  pinned pure-Python DICOM dependency, exact payload manifest, hash-locked no-index
  installer, and per-launch runtime checks. Python 3.11+ is an explicit prerequisite;
  the packaged runtime, official checksum-verified Linux Slicer, private-display and
  mandatory engine network boundaries, and real synthetic registrations pass on
  Strawberry Ubuntu x86_64. ScanView release signing remains pending; Slicer's Linux
  artifact has no independent publisher signature in its documented release process.

### Phase 2 — robust local archive and tools

- Orthanc/DICOMweb import with localhost-only configuration.
- OHIF longitudinal mode or ScanView mode extension.
- Explicit clinician review/sign-off workflow built around the implemented key-image,
  measurement, and visit-packet contracts.

### Phase 3 — reviewed derivatives

- Version-gated local Slicer/BRAINSFit/BRAINSResample rigid-registration execution and
  source-hashed, generated-pending-QA seven-file v2 bundles with an explicit binary
  moving-image sampling-support mask (implemented; the authenticated official macOS
  engine and official-source/checksum-verified Strawberry Linux engine passed equal-
  and partial-field synthetic same-modality runs, while a real patient pair remains
  pending).
- Isolated local registration QA with derived reference/registered views, all three planes,
  opacity, swipe, checkerboard, edges, qualitative landmarks, quantitative 3-D
  residuals mandatory for acceptance, and a separate hash-linked accept/reject record
  (implemented; real-case review pending).
- Live-bundle-validated accepted-record consumption in the ordinary viewer, exposing
  only derived fixed/registered volumes plus the technical sampling-support mask and
  exploratory opacity/swipe (implemented; real-case review pending). Registered
  pixels are machine-gated to mask value one, with fixed pixels forced elsewhere.
  The mask is not shared anatomy, tumor, segmentation, registration quality, or
  clinical comparability. All other derived operations remain locked.
- Manual single-series binary DICOM SEG-format export plus a source-bound sidecar is
  implemented; SEG import, DICOM SR, a protected derivative store, and external
  conformance testing remain future work.
- Single-timepoint manual-boundary review and a separately reviewed cross-timepoint
  arithmetic-volume pairing transition are implemented. Spatial boundary-change
  localization, authenticated clinical sign-off, response assessment, and manual/
  semi-automatic component-specific tumor segmentation remain future work.
- Paused next slice: add a separate source-SEG volume-pairing review contract that
  consumes only two accepted `scanview.source-segmentation-review` archives. Do not
  broaden the manual-ROI comparison contract or mix evidence lineages. Recursively
  revalidate both source SEG/mask/source-image chains and live DICOM chronology;
  require qualified self-attested same-lesion, reviewer-defined-tissue,
  comparability, provenance-limit, and registration-need review before exposing
  technical volume arithmetic for discussion. Response, causality, registration,
  spatial change, diagnosis, conclusion, and sign-off remain locked. The exact
  restart state and verification gates are recorded in `docs/STATUS.md`.

### Research only

- Intensity-normalized longitudinal MRI subtraction.
- Deformable registration around tumor/resection anatomy.
- AI lesion proposals, automated matching, radiomics, response prediction.

## Acceptance criteria

1. **Source immutability:** cataloging/viewing does not change a source SHA-256;
   every derivative eventually resolves to exact source instances and hashes.
2. **Pairing transparency:** no candidate is auto-approved; results include score,
   warnings, reasons, and `review_status`; missing or different opaque patient
   contexts cannot produce a longitudinal candidate.
3. **Geometry honesty:** approximate index synchronization is labeled; clinical-looking
   overlay requires patient-space geometry or an accepted registration transform.
4. **Registration gating:** reject/accept state is explicit and auditable; rejected or
   unreviewed transforms cannot unlock overlay, and subtraction/mask propagation stay
   locked regardless of this exploratory QA decision.
5. **Measurement provenance:** geometry, source frames, units, method/version, author,
   timestamp, and tracking ID survive save/reopen.
6. **No false response label:** missing diagnosis/age, selected criteria, clinical
   status, steroids, treatment dates, baseline/nadir, or confirmation yields missing
   fields—not a response category.
7. **Agent safety:** default interface is read-only; source delete does not exist;
   outputs are versioned and separate observation/computation/interpretation/limits.
8. **Privacy:** loopback only, no analytics/outbound runtime calls, PHI excluded from
   logs; header removal is never represented as de-identification.
9. **Offline core:** all DICOM decoding, metadata indexing, comparison, registration,
   segmentation, and evidence generation must remain usable without an external API.
10. **Communication:** exported evidence shows dates, sequence/contrast,
   native/derived state, registration QA, measurement method, sources, limitations,
   and an unreviewed watermark until sign-off.
11. **Review trust:** local review records separate person-entered decisions from
   hash-bound observations/computations, identify self-asserted credentials as
   unverified, bind every event and parent derivative by hash, and never represent
   that chain as a digital signature or medical-record authentication.
12. **Session-state consent:** live viewer inspection is off by default, visible to
   the person, contains no pixels/direct identifiers/measurement values, is never
   persisted, and becomes unavailable on opt-out or heartbeat expiry.
13. **Exact navigation privacy:** agent navigation proves exact slice application,
    malformed-target refusal, clean URLs, and no fragment or opaque navigation
    references in HTTP logs.
14. **Registration authority separation:** QA volume access and decision submission
    require the separate browser session capability. Bearer access exposes only a
    privacy-minimized status and cannot approve a transform; the capability alone does
    not authenticate human presence.
15. **Cross-modality honesty:** MRI+CT consultation views use no timepoint roles,
    computed change, lesion linkage, intensity comparison, registration claim, or
    response assessment. The artifact proves its exact local DICOM source bytes while
    keeping clinical interpretation explicitly absent.
16. **Offline distribution:** a transferable macOS/Linux bundle installs only pinned,
    hashed local wheels with package-index access disabled, verifies its payload and
    installed runtime before launch, and requires no external DICOM-processing API.
    Platform execution and publisher signatures are separate, explicit release gates.
17. **Local processing boundary:** no feature that reads, decodes, indexes, registers,
    measures, compares, segments, renders, or packages DICOM may require an external
    API. A missing local engine or dependency must fail closed; it must never trigger
    a patient-data upload or cloud fallback.
18. **Manual ROI evidence honesty:** export requires one strict regular native source
    grid and binds a binary DICOM SEG-format mask to exact source bytes. Independent
    validation recomputes only marked-voxel geometry arithmetic, leaves boundary
    uncertainty unquantified, keeps the artifact unreviewed, and cannot establish
    tumor identity, longitudinal linkage, response, diagnosis, or clinical approval.
19. **Manual boundary-review separation:** a review record embeds and revalidates the
    exact source-bound evidence, labels reviewer identity/credentials self-asserted and
    unverified, requires complete three-plane/acquisition/tissue-definition gates for
    discussion-only acceptance, and cannot authorize lesion linkage, change arithmetic,
    response classification, diagnosis, or a clinical conclusion.
20. **Reviewed volume-comparison separation:** two accepted boundary reviews expose
    arithmetic change only after a distinct source-recursive human pairing review
    confirms chronology, same lesion/tissue, comparability, and registration need.
    Non-accepted or source-invalid states withhold every value, and acceptance never
    authorizes response, causality, spatial localization, diagnosis, or sign-off.
21. **Native-boundary display separation:** display startup recursively revalidates
    the accepted comparison, both nested masks, and every source byte. Agents cannot
    fetch mask pixels; browser masks are independently rehashed and remain read-only
    on separate native grids. Optional normalized navigation cannot become anatomical
    correspondence, registration, spatial change, or response evidence.
22. **Agent access accountability:** when explicitly configured, every covered
    sensitive bearer GET must durably append a schema-valid, hash-chained operation-
    class event before routing. Audit events contain no token, target, identifiers,
    paths, payload facts, pixels, masks, measurements, or clinical values; audit
    failure denies the bearer read, and the chain is never called identity proof or a
    filesystem immutability control.
23. **Follow-up readiness honesty:** a catalog-hash-bound local report and the human
    viewer apply the same strict MR↔MR/CT↔CT, distinct-study, valid-distinct-date, and
    opaque patient-context gates. Missing input is explicit, candidates stay
    unreviewed, and readiness never authorizes selection, registration, lesion
    linkage, response, diagnosis, treatment effect, or a clinical conclusion.
24. **Agent-to-person proposal separation:** an agent consultation plan is accepted
    only when its stable catalog-content digest, opaque patient context, MR/CT and
    distinct-study gates, exact series/instance membership, item order, and fixed
    permission locks match the live local catalog. Validation grants exact source
    navigation only. It cannot authenticate an agent, open or capture a source without
    a person's action, establish relevance or chronology, register images, link a
    lesion, assess response or treatment effect, diagnose, or create a conclusion.
25. **Source presentation-state separation:** a supported GSPS state must bind to the
    exact guarded PR bytes and every exact referenced local MR/CT instance. Only the
    documented unrotated/unflipped/full-image/linear-VOI/PIXEL-polyline/anchor-text
    subset may render. Opening is a person's explicit action; geometry is visually
    distinct and read-only; source text may contain identifiers and cannot become a
    ScanView measurement, finding, diagnosis, response label, or clinical conclusion.
    Unsupported or changed input displays no state-derived content.
26. **Source segmentation separation:** a supported source DICOM SEG must bind to the
    exact guarded SEG and every exact referenced MR/CT source, pass the documented
    uncompressed binary native-grid/dimension/spatial-preservation profile, and remain
    within catalog-wide work/memory limits. Bearer agents may read only the sensitive
    catalog; dense mask bytes require the browser session. The browser independently
    authenticates physical slab order, mask SHA-256, binary values, and foreground
    arithmetic before read-only display. No source edit, evidence conversion,
    longitudinal linkage, response, diagnosis, or conclusion is authorized; passing
    the profile is not full DICOM conformance or clinical validation.
27. **Independent SEG oracle:** the optional interoperability gate must use an exact
    pinned highdicom/NumPy/pydicom environment and patient-free source images, disable
    socket connections before DICOM generation/read, and compare highdicom's own
    source-instance reconstruction byte-for-byte with ScanView. Complete-series Common
    Instance References may be a superset of encoded sparse frames; every actual frame
    must still map to one exact referenced source plane. The optional packages must not
    enter the offline runtime or process Mila data.
28. **Second-project SEG oracle:** an exact pinned NCI/QIICR dcmqi writer and reader
    must independently round-trip one patient-free binary SEG under OS-enforced
    external-network isolation. ScanView may accept absent Spatial Locations Preserved
    only when every source identity, SOP, native position, matrix, orientation,
    spacing, hash, and bounds guard proves exact mapping; explicit `NO`,
    `REORIENTED_ONLY`, or any other value must fail closed. dcmqi must not enter the
    offline runtime or process Mila data.
29. **Neutral agent display-state separation:** viewer-state v2 must name generic
    Image A/Image B targets and declare either neutral `reference`/`reference` Consult
    Prep roles or explicit longitudinal `baseline`/`followup` roles. An active source-
    SEG display may expose only exact opaque object/segment/series references and its
    guarded catalog-content hash—never mask bytes/hash, source text, labels/codes,
    algorithms, volume, accuracy, or interpretation. All navigation-from-state,
    mutation, mask-read, SEG-interpretation, diagnosis, response, and conclusion
    permissions stay false; opt-out, TTL, and guarded-source change revoke the state.
30. **Source-SEG review authority separation:** reviewing a source-carried DICOM SEG
    must create a distinct v1 archive, never relabel the object as ScanView manual ROI
    evidence. Creation is browser-session/same-origin or explicit local CLI only and
    must revalidate the guarded catalog, original SEG bytes, every referenced MR/CT
    source, dense binary mask, source-metadata hash, and arithmetic. The archive must
    disclose original DICOM, source text, mask pixels, possible identifiers, and
    self-asserted reviewer identity. Acceptance permits only one-timepoint boundary
    and technical-volume discussion plus future pairing-review eligibility; source
    label/codes/creator/algorithm/accuracy/meaning, longitudinal link, change,
    response, diagnosis, and clinical conclusion remain unauthenticated, unverified,
    not assessed, or false. Agent validation output must omit IDs, reviewer identity,
    source text, pixels, paths, hashes, and numeric values.
