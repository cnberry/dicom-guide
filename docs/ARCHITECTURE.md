# Architecture

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

explicit same-modality pair --> local Slicer/BRAINSFit rigid job
                                      (OS-enforced no-network execution)
                                      |
                                      +--> hashed derivative bundle (pending QA only)
                                                   |
                                                   +--> browser-capability QA preview
                                                               |
                                                               +--> separate review JSON
                                                                    (six-file hash anchor)
                                                                            |
                                      exact accepted review + live bundle ---+
                                                                            |
                                                                            +--> reviewed browser display
                                                                                 (opacity/swipe only)
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
   cross-exam registration.
4. **Local API:** binds to loopback only, uses an ephemeral bearer token for agents
   and an HttpOnly same-origin session for the browser, returns only opaque IDs and
   an allowlisted metadata contract, and has no source write/delete API. Its
   derivative POSTs accept bounded outer ZIPs from an exact local Origin. Visit input
   contains only `baseline.zip` and `followup.zip`; review input adds only
   `comparison.json`; consultation input contains only neutral `view-a.zip` and
   `view-b.zip`.
   The service assembles and revalidates every nested derivative in memory, returns
   it with `no-store`, and persists nothing. Service-backed measurement IDs join
   directly to the manifest; legacy folder IDs remain accepted.
   The viewer-state POST is a distinct bounded session-control route, not a source or
   derivative write. It independently validates exact catalog positions, retains one
   latest publication under a lock, marks it `unreviewed`, and serves it only to an
   authenticated local GET with `no-store`. Publisher revocation closes opt-out races;
   the in-memory TTL is a fallback, not a consent substitute.
   Registration QA is a separately mounted mode: a bearer-authorized agent receives
   only a minimized status, while preview context, the three allowlisted NRRDs, and
   decision submission require the distinct HttpOnly browser session; the POST also
   requires exact Origin. This separates bearer-agent authority but does not prove a person is present.
   The server returns one validated decision JSON in memory and does not persist it.
   A launch that also supplies a saved review enters a distinct reviewed-display mode.
   The server validates the owner-only, unlinked review against the exact live bundle,
   rechecks every evidence-file identity and metadata on access, suppresses pending-QA
   authority, and exposes only fixed-reference and registered-moving NRRDs to the
   browser session. Rejected or invalid review input falls back to
   ordinary DICOM with every registered route locked. Bearer access gets only a
   privacy-minimized authorization summary.
5. **Derivatives:** rigid transforms and resampled volumes now go to a separate,
   owner-only, atomic no-replace directory with exact source hashes, version-gated
   local Slicer/BRAINSFit provenance, and every display use locked pending QA. Future masks,
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
   dates have no timepoint meaning. Agent comparisons accept only explicit, distinct-series
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
   on timeout, and accepts only the required version/revision report, expected launcher
   hash, parsed scalar-volume geometry, and finite proper-rigid transform. The engine
   runs inside a mandatory macOS deny-network sandbox or, on supported 64-bit Linux,
   `bwrap` private namespaces plus a no-socket/io_uring seccomp filter; no weaker
   `unshare`-only or unsandboxed fallback exists. The hash
   match does not authenticate the software distributor. A generated transform is not
   display-approved. Registration review does not mutate that bundle: a separate JSON
   event anchors the exact six filenames, byte counts, hashes, manifest, transform,
   fixed/registered geometry, and any prior-record digest. Event hashing detects edits
   but does not authenticate the reviewer. Acceptance expresses only an authorization
   input for exploratory shared-coverage overlay/swipe; subtraction, masks, segmentation,
   resampled-image measurements, and response conclusions remain locked. The ordinary
   viewer consumes that input only through the separate live-bundle-validated reviewed
   surface. It implements opacity/swipe only, identifies both NRRDs as derived, labels
   registered moving as resampled, and states that shared coverage is reviewer-visual
   because no pixel-level overlap mask exists.

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

When a catalog contains no valid dated same-modality cross-study source pair, the
ordinary viewer enters a separate neutral state:

```text
catalog has no longitudinal pair --> Consult Prep --> explicit MR + CT selection
                                                           |
                                                           +--> independent native views
                                                           +--> consultation packet
                                                           +--> clinician questions

chronology / lesion pairing / registration / response assessment: unavailable
viewer-state v1 publication: unavailable (timepoint-named schema)
```

The hashes make partial edits evident but do not authenticate a clinician. Signed
medical-record integration remains outside the current trust boundary.

Raw slice-index synchronization is marked as approximate. Physical-coordinate
synchronization requires compatible geometry or an accepted transform. Subtraction
is not an MVP feature and is never allowed between CT and MRI.

## Packaging path

- Today: Vite static app plus a Python 3.11+ same-origin local launcher; a staged
  release builder embeds both into a self-contained wheel without modifying source.
- Next: signed/notarized macOS and Linux release artifacts; optional Orthanc.
- Later: Tauri/Electron or a packaged runtime after macOS and Linux smoke tests.
