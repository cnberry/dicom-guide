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
                         |
                         +--> protected native instances --> Cornerstone3D human view
                         |                                      |
                         |                                      +--> measurement packet
                         |                                                   |
                         +--> static bundled UI                              +--> table / reopen
                                                                             |
                                                                             +--> local numeric comparison

Alternate local input: browser folder picker --> Cornerstone3D

Later: DICOM --> Orthanc/DICOMweb --> OHIF longitudinal UI
                                --> Slicer registration/segmentation jobs
                                --> DICOM SEG/SR + provenance sidecars
```

## Trust boundaries

1. **Source:** copied originals are immutable; their hashes are evidence anchors.
2. **Catalog:** direct patient name/ID tags are excluded, but all output remains
   sensitive and is explicitly not claimed to be de-identified.
3. **Viewer:** local files are added to Cornerstone's in-browser file manager, or
   protected native instances are streamed from the same loopback process.
   There are no runtime third-party requests or analytics. A Content Security
   Policy limits code, workers, codecs, images, and connections to the local origin
   (plus in-memory `blob:`/`data:` assets where required).
   Loading a different folder clears annotations, decoded-image cache, and file
   registry before the new imaging session begins.
4. **Agent API:** binds to loopback only, uses an ephemeral bearer token for agents
   and an HttpOnly same-origin session for the browser, returns only opaque IDs and
   an allowlisted metadata contract, and has no write/delete API. Service-backed
   measurement IDs join directly to that manifest; legacy folder IDs remain accepted.
5. **Derivatives:** future transforms, resampled images, masks, additional
   measurements, and reports go to a separate store with source references and
   review status. Manual length/bidirectional/elliptical ROI drafts already use this contract as
   versioned local JSON and never modify native instances. Agent comparisons accept
   only explicit, distinct-series measurement selections and emit no response label.

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

Raw slice-index synchronization is marked as approximate. Physical-coordinate
synchronization requires compatible geometry or an accepted transform. Subtraction
is not an MVP feature and is never allowed between CT and MRI.

## Packaging path

- Today: Vite static app plus a Python 3.11+ same-origin local launcher; a staged
  release builder embeds both into a self-contained wheel without modifying source.
- Next: signed/notarized macOS and Linux release artifacts; optional Orthanc.
- Later: Tauri/Electron or a packaged runtime after macOS and Linux smoke tests.
