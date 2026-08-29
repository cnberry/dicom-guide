# Architecture

## Source DICOM segmentation boundary

Source-carried SEG is a guarded read-only display path, not a ScanView measurement or
clinical interpretation path:

```text
guarded local manifest + exact SEG/source SHA-256
        │
        └── narrow binary native-grid parser
              ├── one regular single-frame MR/CT source series
              ├── Spatial Locations Preserved = YES
              ├── segment + plane-position dimension consistency
              ├── catalog-wide decode and dense-mask budgets
              └── unsupported object fails closed as a whole
                         │
                         ├── sensitive catalog → bearer/browser, no-store
                         └── dense 0/1 mask → HttpOnly browser session only
                                      │
                         independent hash/count/order validation
                                      │
                         read-only Cornerstone tri-planar overlay
                         no edit, evidence conversion, linking, or response claim
```

The parser physically orders source planes by the dot product of Image Position
(Patient) and the normal derived from Image Orientation (Patient). The browser derives
that order independently, authenticates the catalog mapping, and then reorders whole
mask slabs to Cornerstone's actual `volume.imageIds` by opaque instance identity.
Mask opening is cancellable and becomes “open” only after the source volume and locked
labelmap are ready. Full DICOM conformance, creator/algorithm identity, boundary
accuracy, represented tissue, and clinical meaning are outside this import profile.
All work is local; there is no external processing API or fallback.

The top-level Common Instance Reference may enumerate a complete guarded source
series while sparse empty planes are omitted from Pixel Data. ScanView therefore
requires every encoded frame to be a member of the top-level set but does not require
every top-level source to have a frame. The optional highdicom 0.28.1 interoperability
gate independently reconstructs the same dense mask and is excluded from the runtime:

```text
patient-free sources → highdicom SEG (24 top-level refs, 11 sparse frames)
         ├── highdicom source-instance reconstruction ─┐
         └── ScanView guarded parser + reconstruction ─┴─ byte/hash/count equality
```

## Source DICOM presentation-state boundary

GSPS is a guarded source-display path, not an evidence or interpretation path:

```text
guarded local DICOM catalog
        │
        ├── exact PR bytes ── stable read + SHA-256 ── conservative GSPS parser
        │                                             │
        └── hashed referenced MR/CT metadata ─────────┤
             same study/patient · single frame · matching linear grayscale/aspect
                                                      ▼
                                      versioned sensitive display catalog
                                      ├── full bearer/browser local endpoint
                                      ├── privacy-minimized CLI validation
                                      └── fixed false clinical permissions
                                                      │
                                           deliberate person click
                                                      ▼
                         exact native slice + forced LINEAR VOI/identity polarity
                         + atomic read-only orange overlay
                         all manipulation/evidence/MPR/agent state locked until cleared
```

The server caches the parsed artifact at startup and guards every supported PR and
referenced image by device, inode, byte count, mtime, and ctime. Any change returns
HTTP 409 instead of serving stale display instructions. The browser independently
validates exact fields, fixed permissions/privacy, source series/study/patient/
modality membership, dimensions, coordinates, display area, and VOI arithmetic. Source annotation
text may contain identifiers. It is not included in the privacy-minimized CLI summary,
but the authenticated full endpoint necessarily carries it for local display and
agent inspection. The artifact fixes ScanView interpretation to absent and source-text
clinical meaning to not assessed. There is no source-write route and no external
processing call.

Cornerstone image-data indices identify pixel centers; DICOM PIXEL graphic coordinates
identify pixel corners. The renderer therefore maps `(x-0.5,y-0.5,0)` through the
current image's `indexToWorld`, then through the stack viewport's `worldToCanvas`.
Projection is atomic: any expected graphic/text projection failure clears the entire
state. All viewport interaction is locked until a person clears the state.

## Decision

Use a local web UI based on Cornerstone3D, a versioned agent contract, and a
loopback-only catalog/API. Adopt OHIF + Orthanc as the durable DICOMweb layer when
the prototype moves beyond folder import. Use 3D Slicer command-line modules for
reviewable registration and segmentation jobs before considering custom algorithms.

This delivers a working macOS/Linux path without waiting for Docker or a PACS,
while preserving a standards-based migration path.

```text
Copied DICOM (source-read-only in ScanView)
        |
        +--> scanview-agent launch (loopback only)
                         |
                         +--> manifest v1 ------------------> agents / automation
                         |                                      |
                         |                                      +--> exact opaque fragment
                         |                                            (one-use local navigation)
                         |
                         +--> protected native instances --> Cornerstone3D human view
                         |                                      |
                         |                                      +--> geometry gate --> local MPR
                         |                                      |                     (derived navigation)
                         |                                      |                           |
                         |                                      |                           +--> strict native-grid gate
                         |                                      |                                  |
                         |                                      |                                  +--> person-painted binary ROI
                         |                                      |                                         |
                         |                                      |                                         +--> DICOM SEG-format + sidecar
                         |                                      |                                                |
                         |                                      |                                                +--> independent local validator
                         |                                      |                                                |
                         |                                      |                                                +--> qualified boundary-review ZIP
                         |                                      |                                                       |
                         |                                      |                                two accepted reviews --+--> explicit pairing review
                         |                                      |                                                                 |
                         |                                      |                                                                 +--> reviewed volume arithmetic
                         |                                      |
                         |                                      +--> measurement packet
                         |                                                   |
                         +--> static bundled UI                              +--> table / reopen
                         |                                      |
                         |                                      +--> opt-in viewer state
                         |                                           (30-second memory TTL)
                         |                                                   |
                         |                                                   +--> authorized local agent
                         |                                      |
                         |                                      +--> key-image ZIP
                         |                                           (PNG + provenance + measurements)
                         |                                                   |
                         +---------------------------------------------------+--> local agent validation
                                                                             +--> local numeric comparison

two validated dated key images -- CLI or in-memory local POST --> Python gates
                                                                       |
                                                                       +--> visit-packet ZIP
                                                                               |
                                                                               +--> static human review
                                                                               +--> agent manifest

one neutral MR view + one neutral CT view --> live catalog/source-byte gates
                                                   |
                                                   +--> consultation-packet ZIP
                                                        (no chronology/comparison/response)
                                                              |
                                                              +--> static clinician questions
                                                              +--> minimized agent validation

Alternate local input: browser folder picker --> Cornerstone3D

Later: DICOM --> Orthanc/DICOMweb --> OHIF longitudinal UI
                                --> additional Slicer segmentation jobs
                                --> DICOM SEG/SR + provenance sidecars

explicit same-modality pair --> local Slicer/BRAINSFit + BRAINSResample rigid job
                                      (OS-enforced no-network execution)
                                      |
                                      +--> hashed derivative bundle (pending QA only)
                                                   |
                                                   +--> browser-capability QA preview
                                                               |
                                                               +--> separate review JSON
                                                                    (seven-file hash anchor)
                                                                            |
                                      exact accepted review + live bundle ---+
                                                                            |
                                                                            +--> reviewed browser display
                                                                                 (mask-gated opacity/swipe only)
```

## Trust boundaries

1. **Source:** ScanView has no source write/delete operation; copied-original hashes
   are evidence anchors. This is an application boundary, not an operating-system
   immutable-file flag. Each service-streamed instance is anchored to startup
   device/inode/size/change metadata, opened without following a final symlink, copied
   into one owner-only ephemeral local snapshot, hashed, and only then served. A source
   changed after catalog/startup is refused before patient bytes are sent.
2. **Catalog:** direct patient name/ID tags are excluded, but all output remains
   sensitive and is explicitly not claimed to be de-identified. An opaque patient-
   context digest is derived locally and gates all cross-exam suggestions; raw
   identity values are never emitted.
3. **Viewer:** local files are added to Cornerstone's in-browser file manager, or
   protected native instances are streamed from the same loopback process.
   There are no runtime third-party requests or analytics. A Content Security
   Policy limits code, workers, codecs, images, and connections to the local origin
   (plus in-memory `blob:`/`data:` assets where required).
   Loading a different folder clears annotations, decoded-image cache, and file
   registry before the new imaging session begins.
   A versioned agent navigation fragment is never sent to the server. The viewer
   consumes it once, clears it immediately, validates an exact allowlist and local
   catalog membership, then applies both requested panes atomically. Navigation does
   not alter compatibility, registration, or review state.
   A separate visible opt-in publishes only opaque current pane positions, tool/link
   state, optional MPR series, and evidence counts. The browser never publishes
   pixels, descriptions, dates, measurement content, paths, or direct identifiers.
   Opt-out rotates and revokes the tab publisher; page close clears it and a missing
   heartbeat expires it within 30 seconds. Consult Prep disables this v1 bridge
   because its pane fields use baseline/follow-up names; neutral agent evidence uses
   the consultation packet instead.
   Single-series MPR additionally requires complete, regular patient-space geometry;
   its interpolated orthographic planes remain navigation-only derivatives and do
   not enter native key-image evidence. A Cornerstone crosshair controller moves one
   shared LPS point across those three planes. Minimal mode suppresses oblique rotation
   and slab controls, and the coordinate is neither persisted nor used to imply
   cross-exam registration. A stricter second gate controls manual ROI evidence:
   every source must be single-frame with consistent matrix, spacing, orientation,
   regular projected spacing, and no in-plane drift. The binary labelmap is stored on
   the native grid; rendered MPR pixels are never exported as measurement evidence.
4. **Local API:** binds to loopback only, uses an ephemeral bearer token for agents
   and an HttpOnly same-origin session for the browser, returns only opaque IDs and
   an allowlisted metadata contract, and has no source write/delete API. Its
   derivative POSTs accept bounded outer ZIPs from an exact local Origin. Visit input
   contains only `baseline.zip` and `followup.zip`; review input adds only
   `comparison.json`; consultation input contains only neutral `view-a.zip` and
   `view-b.zip`; consultation-board input contains only a strict label manifest and
   2–8 ordered neutral key-image ZIPs; reviewed volume-comparison input contains only
   two complete boundary-review ZIPs and one strict pairing request. That route also
   holds the exact local source root, joins both reviewed series to the live catalog,
   and derives chronology from consistent per-instance DICOM dates.
   The service assembles and revalidates every nested derivative in memory, returns
   it with `no-store`, and persists nothing. Service-backed measurement IDs join
   directly to the manifest; legacy folder IDs remain accepted.
   The viewer-state POST is a distinct bounded session-control route, not a source or
   derivative write. It independently validates exact catalog positions, retains one
   latest publication under a lock, marks it `unreviewed`, and serves it only to an
   authenticated local GET with `no-store`. Publisher revocation closes opt-out races;
   the in-memory TTL is a fallback, not a consent substitute.
   Optional bearer auditing is a separate local persistence boundary. It records only
   fixed operation classes and authorization, never request targets or response
   content. The owner-only single-link JSONL file is opened without following the
   final symlink, exclusively locked, application-appended, fsynced, and hash-chained
   across restarts. Covered bearer reads are fail-closed on audit error. Browser
   sessions do not use the bearer and are outside this log. The hash chain detects
   modification but neither authenticates the bearer holder nor supplies an OS
   immutable/append-only guarantee.
   Registration QA is a separately mounted mode: a bearer-authorized agent receives
   only a minimized status, while preview context, the four allowlisted NRRDs, and
   decision submission require the distinct HttpOnly browser session; the POST also
   requires exact Origin. This separates bearer-agent authority but does not prove a person is present.
   The server returns one validated decision JSON in memory and does not persist it.
   A launch that also supplies a saved review enters a distinct reviewed-display mode.
   The server validates the owner-only, unlinked review against the exact live bundle,
   rechecks every evidence-file identity and metadata on access, suppresses pending-QA
   authority, and exposes only fixed-reference, registered-moving, and the separate
   technical sampling-support NRRD to the browser session. Rejected or invalid review input falls back to
   ordinary DICOM with every registered route locked. Bearer access gets only a
   privacy-minimized authorization summary.
5. **Derivatives:** a manual ROI volume export is a new sensitive three-file draft,
   not a source mutation. It binds a DICOM SEG-format object to ordered source
   byte/SHA anchors and a v1 sidecar. The browser computes a native-grid marked-voxel
   volume; an independent Python validator reopens stable source descriptors, resolves
   the DICOM references, rebuilds the dense binary mask, and recomputes the arithmetic.
   Source/format/arithmetic validation never changes its `draft_unreviewed` state or
   unlocks longitudinal linking, percentage change, response, diagnosis, or a clinical
   conclusion. A separate boundary-review ZIP can authorize one-timepoint discussion.
   Two such accepted reviews can enter a second explicit pairing review only after
   same-patient-context, same-modality, source-date, same-lesion, same-tissue,
   acquisition/boundary-comparability, registration-consideration, and checklist gates.
   The five-file output recursively embeds and revalidates both review/evidence chains
   and exposes only transparent reviewed volume arithmetic. Response classification,
   treatment causality, spatial overlay, voxelwise localization, diagnosis, clinical
   conclusion, and medical-record sign-off remain locked. Rigid transforms and
   resampled volumes now go to a separate,
   owner-only, atomic no-replace directory with exact source hashes, version-gated
   local Slicer/BRAINSFit/BRAINSResample provenance, and every display use locked pending QA. Future lesion masks,
   additional measurements, and reports follow the same boundary. Manual
   length/bidirectional/elliptical ROI drafts use versioned
   local JSON; key-image ZIPs bind a watermarked display PNG to its exact source and
   visible measurements with local SHA-256 digests. Key-image v2 adds opaque
   patient/study context. Visit-packet ZIPs preserve both evidence bundles, add a
   static human review page, and cross-hash every payload after matching opaque
   patient-context and
   strict longitudinal gates. The viewer and CLI share that Python assembler; the
   viewer transport does not persist an intermediate server-side file. None modifies
   native instances. Consultation key images instead use neutral selection slots.
   Their assembler requires exactly one MR and one CT from distinct studies with one
   matching opaque patient context, verifies the displayed instance/position against
   the live hashed catalog, and reads each guarded DICOM descriptor without following
   a final symlink. The exact byte count and SHA-256 are bound into the deterministic
   manifested review page. Computed and interpretation arrays stay empty; source
   dates have no timepoint meaning. A separate agent consultation-plan artifact binds
   2–8 exact opaque series/instance pairs and bounded discussion headings to the stable
   content of one catalog. A browser-session-only same-origin validator rebuilds the
   plan from the live catalog before the viewer exposes deliberate per-item navigation.
   The viewer never auto-opens or captures a proposal, and the plan grants no identity,
   relevance, chronology, registration, lesion, response, treatment-effect, diagnostic,
   or clinical-conclusion authority. Agent comparisons accept only explicit, distinct-series
   measurement selections and emit no response label. The browser can feed that path
   through a bounded strict JSON paste, session-only deletion, and a transient working
   lesion label; the label lives only in the exported comparison draft and never
   rewrites measurement geometry. Visit packets emit neither numeric results nor
   candidate interpretations. Comparison-review ZIPs then bind one validated visit
   packet to one exact comparison through visible measurement IDs, sources, units,
   and values. They duplicate the two PNGs for a static human page and keep
   self-attested review/amendment events in a separate hash chain. The viewer exposes
   this assembler only while the live panes display the exact source instances named
   by the explicit pair. Each event-derived archive is a new owner-only file anchored
   to its parent; no command overwrites an ancestor or changes DICOM. The registration
   runner stages rehashed source instances under generic private filenames, passes
   paths through a private environment request rather than command arguments, captures
   diagnostics only in the deleted private job directory, terminates the process group
   on timeout, and accepts only the required version/runtime repository revision
   report, expected launcher hash, parsed scalar-volume geometry, complete binary
   sampling-support payload/counts, and finite proper-rigid transform. The engine
   runs inside a mandatory macOS deny-network sandbox or, on supported 64-bit Linux,
   `bwrap` private namespaces plus a seccomp filter that permits only local `AF_UNIX`
   IPC and rejects network socket domains and io_uring. Linux uses private Xvfb with
   TCP listening disabled; inherited displays and weaker `unshare`-only or unsandboxed
   fallback do not exist. The hash
   match does not authenticate the software distributor. A generated transform is not
   display-approved. Registration review does not mutate that bundle: a separate JSON
   event anchors the exact seven filenames, byte counts, hashes, manifest, transform,
   fixed/registered/mask geometry, mask semantics/counts, and any prior-record digest.
   Event hashing detects edits
   but does not authenticate the reviewer. Acceptance expresses only an authorization
   input for exploratory shared-coverage overlay/swipe; subtraction, mask propagation, segmentation,
   resampled-image measurements, and response conclusions remain locked. The ordinary
   viewer consumes that input only through the separate live-bundle-validated reviewed
   surface. It implements opacity/swipe only, identifies both image NRRDs as derived,
   labels registered moving as resampled, independently verifies the binary support
   mask before render, and forces the fixed pixel wherever mask support is zero. The
   mask represents transformed moving-image sampling support only; shared anatomy and
   registration acceptability remain reviewer judgments.

External APIs are outside the architecture: no DICOM pixel/header, measurement,
registration, segmentation, or interpretation pipeline may require a network
service. Optional model integrations, if ever added, must be separately consented
and cannot be required for core operation.

## Why Cornerstone3D first

Cornerstone3D is the maintained rendering/tool foundation used by OHIF. It supports
DICOM P10 local files, compressed transfer syntaxes, stacks, volumes, physical-space
annotations, synchronization, fusion, and segmentations. Starting at this layer
keeps the MVP small and provides a direct route to OHIF extensions later.

## Longitudinal comparison states

```text
series suggested --> person confirms pairing --> native side-by-side
                                            |
                                            +--> registration job creates derivative
                                                       |
                                                       +--> QA rejected (stay native)
                                                       |
                                                       +--> QA accepted for display
                                                                |
                                                                +--> overlay/swipe
```

The separate communication/review path is:

```text
two validated key images --> visit packet ----+
                                              +--> exact source/value join --> review ZIP
explicit measurement pair --> comparison ----+                              |
                                                                             +--> self-attested review (new ZIP)
                                                                             +--> amended comparison (new ZIP, unreviewed)
```

The manual boundary-evidence path reaches longitudinal arithmetic only through a
second person-reviewed transition:

```text
strict native source grid --> person-painted binary ROI --> DICOM SEG-format + sidecar
                                                                  |
                                                                  +--> exact-source local validation
                                                                  |
                                                                  +--> self-attested qualified boundary review
                                                                          |
                                                                          +--> nested evidence + printable record --+
                                                                                                                   |
                       independently accepted later boundary review ----------------------------------------------+
                                                                                                                   |
                                                                                                                   +--> explicit qualified pairing review
                                                                                                                          |
                                                                                                                          +--> arithmetic volume change for discussion only

software-established lesion identity / spatial change / response / causality: unavailable
```

An accepted arithmetic review can authorize a display-only reopening of those two
exact native masks without authorizing registration:

```text
accepted volume-comparison archive + exact local source root
                         |
                         +--> recursive startup validation and guarded source identities
                                      |
                                      +--> browser-session-only context + two binary masks
                                                   |
                                                   +--> native baseline MPR + read-only mask
                                                   +--> native follow-up MPR + read-only mask

default: independent centers at each mask centroid
optional: mirrored normalized grid fraction (navigation only)
unavailable: cross-scan overlay / subtraction / propagation / spatial change / response
```

The bearer agent sees a minimized authorization/arithmetic summary but cannot fetch
mask bytes or the full human context. The browser rehashes and recounts every mask
before rendering. This is a capability boundary, not proof that a person is present
or that the reviewed tissue is clinically correct.

When a catalog contains no valid dated same-modality cross-study source pair, the
ordinary viewer enters a separate neutral state:

```text
catalog has no longitudinal pair --> Consult Prep --> explicit MR + CT selection
                                                           |
                                                           +--> independent native views
                                                           +--> consultation packet
                                                           +--> 2–8-view discussion board
                                                           +--> clinician questions

chronology / lesion pairing / registration / response assessment: unavailable
viewer-state v1 publication: unavailable (timepoint-named schema)
```

The hashes make partial edits evident but do not authenticate a clinician. Signed
medical-record integration remains outside the current trust boundary.

The local-processing boundary is architectural, not optional. DICOM bytes and
derived pixels may be read only by the browser runtime, the loopback Python service,
and an explicitly selected locally installed registration engine inside mandatory
network isolation. ScanView has no adapter, endpoint, credential, or fallback for an
external DICOM-processing API; missing local capability fails closed.

Raw slice-index synchronization is marked as approximate. Physical-coordinate
synchronization requires compatible geometry or an accepted transform. Subtraction
is not an MVP feature and is never allowed between CT and MRI.

## Packaging path

- Today: Vite static app plus a Python 3.11+ same-origin local launcher. A staged
  release builder embeds the UI, codecs, and contracts into the ScanView wheel. A
  second non-overwriting builder combines that wheel with pinned pure-Python
  `pydicom` 3.0.2 into a deterministic macOS/Linux ZIP. `bundle.json` hashes every
  payload; `requirements.lock` hashes both wheels; installation uses only `--no-index`
  and `--require-hashes`; every launch verifies the bundle and probes installed
  versions, UI, all 30 schemas, consultation contracts, agent consultation-plan,
  source-segmentation validation, manual ROI review/comparison, native-boundary
  display, agent-access
  audit, and longitudinal-readiness support
  before cataloging DICOM.
- Trust boundary: the offline manifest detects payload corruption but is not publisher
  authentication. Python 3.11+ is supplied by the host and is not covered by the
  bundle. The builder may fetch the pinned wheel; installation and runtime do not.
- Interoperability boundary: pinned highdicom and dcmqi environments are independent,
  patient-free test oracles only. dcmqi writer/reader processes run under
  OS-enforced external-network isolation. Neither project enters the runtime bundle
  or provides an external processing service.
- Next: produce signed/notarized macOS and Linux distributions; optional Orthanc
  remains separate.
- Later: Tauri/Electron or a packaged interpreter after both platform smoke tests.
