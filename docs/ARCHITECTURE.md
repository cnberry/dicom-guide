# Architecture

## Decision

Use a local web UI based on Cornerstone3D, a versioned agent contract, and a
loopback-only catalog/API. Adopt OHIF + Orthanc as the durable DICOMweb layer when
the prototype moves beyond folder import. Use 3D Slicer command-line modules for
reviewable registration and segmentation jobs before considering custom algorithms.

This delivers a working macOS/Linux path without waiting for Docker or a PACS,
while preserving a standards-based migration path.

```text
Immutable copied DICOM
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

Alternate local input: browser folder picker --> Cornerstone3D

Later: DICOM --> Orthanc/DICOMweb --> OHIF longitudinal UI
                                --> Slicer registration/segmentation jobs
                                --> DICOM SEG/SR + provenance sidecars
```

## Trust boundaries

1. **Source:** copied originals are immutable; their hashes are evidence anchors.
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
   Single-series MPR additionally requires complete, regular patient-space geometry;
   its interpolated orthographic planes remain navigation-only derivatives and do
   not enter native key-image evidence. A Cornerstone crosshair controller moves one
   shared LPS point across those three planes. Minimal mode suppresses oblique rotation
   and slab controls, and the coordinate is neither persisted nor used to imply
   cross-exam registration.
4. **Local API:** binds to loopback only, uses an ephemeral bearer token for agents
   and an HttpOnly same-origin session for the browser, returns only opaque IDs and
   an allowlisted metadata contract, and has no source write/delete API. Its two
   POSTs accept bounded outer ZIPs from an exact local Origin. Visit input contains
   only `baseline.zip` and `followup.zip`; review input adds only `comparison.json`.
   The service assembles and revalidates every nested derivative in memory, returns
   it with `no-store`, and persists nothing. Service-backed measurement IDs join
   directly to the manifest; legacy folder IDs remain accepted.
5. **Derivatives:** future transforms, resampled images, masks, additional
   measurements, and reports go to a separate store with source references and
   review status. Manual length/bidirectional/elliptical ROI drafts use versioned
   local JSON; key-image ZIPs bind a watermarked display PNG to its exact source and
   visible measurements with local SHA-256 digests. Key-image v2 adds opaque
   patient/study context. Visit-packet ZIPs preserve both evidence bundles, add a
   static human review page, and cross-hash every payload after same-patient and
   strict longitudinal gates. The viewer and CLI share that Python assembler; the
   viewer transport does not persist an intermediate server-side file. None modifies
   native instances. Agent comparisons accept only explicit, distinct-series
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
   to its parent; no command overwrites an ancestor or changes DICOM.

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
