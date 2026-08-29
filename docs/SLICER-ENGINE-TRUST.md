# Local Slicer engine trust record

Verified 2026-08-28 on this macOS arm64 host and on Strawberry Ubuntu 26.04 x86_64.
No patient data was used in either download, authentication, preflight, or real-engine
synthetic registration workflow.

The machine-readable companions are the
[macOS record](../packaging/slicer/macos-amd64-5.12.3.json) and
[Linux record](../packaging/slicer/linux-amd64-5.12.3.json). They are checked-in
provenance records, not automatic software updaters, signature services, clinical
validation, or substitutes for ScanView's required per-run launcher hash.

## Official macOS release identity

- Product: 3D Slicer 5.12.3 for `macosx-amd64`.
- Official computed revision: `34627`.
- Official Git commit: `9034c71a8fce68ab312458b3d7d16f610562263d`.
- Runtime `slicer.app.repositoryRevision`: `9034c71`.
- Official download filename: `Slicer-5.12.3-macosx-amd64.dmg`.
- Official package byte count: `447327067`.
- Official and locally matched SHA-512:
  `2076f23458936a028d3d1a91686369b5979d3373012f11db0e90c30fdb34874eec2b150da4d5225b2ac6b1bf5552795e1783e621a8ae3c39c01983593b07283a`.
- Sources: [official download page](https://download.slicer.org/),
  [official release details](https://github.com/Slicer/Slicer/wiki/Release-Details),
  and [official bitstream](https://download.slicer.org/bitstream/6a61a0b02eb3d967f032af6c).

The distinction between the computed revision and runtime repository revision is
important. ScanView's executable preflight compares the runtime value `9034c71`; the
earlier `34627` runtime pin was incorrect and failed closed before source staging.

## Local authentication evidence

- The downloaded SHA-512 matched the value on the official download page.
- `hdiutil verify` passed for the DMG.
- `xcrun stapler validate` passed for the DMG.
- Gatekeeper accepted the DMG install assessment as Notarized Developer ID.
- The mounted and installed app passed `codesign --verify --deep --strict`.
- Gatekeeper accepted the mounted and installed app as Notarized Developer ID.
- Signature identity: Developer ID Application Kitware Inc. (`W38PE5Y733`), team
  identifier `W38PE5Y733`, hardened runtime enabled.
- The app did not independently carry a stapled ticket. The DMG did; Gatekeeper still
  accepted the app. This distinction is retained rather than reported as an app
  stapling success.
- The bundled BRAINSFit and BRAINSResample executables are signed by the same Kitware
  team.

The x86_64 app is installed at `/Users/chris/Applications/Slicer.app` and runs on this
arm64 Mac through Rosetta 2. The installed bundle is 1,647,276 KiB. Local execution
identifiers are:

- Slicer launcher SHA-256:
  `710dfa764bf407377ee516b63f84cfb4cf0e0719218c7f43712cc0f231ed6b23`.
- BRAINSFit SHA-256:
  `75d173916e0d2d48f6d9ba9b0cd093349661953538748809d7ea2ad93c85da93`.
- BRAINSResample SHA-256:
  `bd1e042194ff56673c01955782f9415a3e8706be75c7131ea93fbdcd310f207b`.

## Execution evidence

`registration-doctor` found the installed engine, matched the launcher hash, verified
version 5.12.3/runtime revision `9034c71`, found BRAINSFit and BRAINSResample, and
reported the mandatory macOS deny-all-network sandbox ready. Normal
`run-rigid-registration` invocations then processed two pairs of synthetic 16-slice MR
studies through the real Slicer/BRAINSFit/BRAINSResample process inside that sandbox.

Each engine output remained `generated_pending_qa` and `unreviewed`; all overlay,
swipe, subtraction, and mask-propagation display flags stayed locked. Independent
validation accepted both seven-file v2 bundles, source hashes were identical before
and after, and the known synthetic +2 mm displacement produced approximately -2.008 mm
and -1.998 mm moving-to-fixed x translations with near-identity rotations. The
equal-field case produced 65,536/65,536 supported fixed-grid voxels. The deliberately
wider fixed-field case produced 65,536/69,632 (94.117647%) and therefore independently
confirmed a nontrivial BRAINSResample support boundary and transform direction.

A production-build pending-QA session then consumed the live v2 backend context for
that partial-coverage bundle. It verified and loaded the four allowlisted loopback
NRRDs sequentially, exercised mask-gated opacity/swipe/checkerboard/edges, and opened
the technical boundary view in axial, coronal, and sagittal planes before the boundary
attestation became available. Browser diagnostics were empty, all page resources were
loopback-only, and no review decision was submitted.

A separate synthetic commissioning-only accepted review then opened the reviewed
surface from the partial-coverage bundle. The browser loaded only loopback UI/context
plus fixed, registered-moving, and sampling-support NRRDs; all three patient-space
planes and opacity/swipe modes were exercised, the console was clean, and visible and
accessible copy identified machine-enforced sampling support without calling it
anatomy or segmentation. No patient data or medical review was used. Synthetic sources,
diagnostics, derivatives, and review records were moved out of active storage to
recoverable Trash after verification.

## Strawberry Linux authentication and installation

The official `Slicer-5.12.3-linux-amd64.tar.gz` is pinned to immutable bitstream
`6a6159372eb3d967f032505f`, 498,683,944 bytes, and SHA-512
`66bd3a1b9a7f636b40b96cb8c49f395ee783cdcaf7b43a4b895d6a40df9e0af8393f5ab7631ba50f6bbe06aa17dbcd8a46984a53b693bdf203d34337e2e80401`.
The downloaded owner-only archive matched all three values from the official Slicer
metadata. Before extraction, all 10,572 archive members and 385 links were checked;
none was absolute, traversed a parent, or resolved outside the single package root.

Slicer's documented release process does not provide an independent Linux package
signature: its signing guidance covers macOS and Windows, and the 5.12 release
checklist marks Linux signing not applicable. The Linux result is therefore recorded
as official-HTTPS plus published-checksum verification, not publisher-signature
verification. The distinction is machine-readable and is not promoted to a signing
claim.

Sources: [official download page](https://download.slicer.org/),
[immutable official bitstream](https://download.slicer.org/bitstream/6a6159372eb3d967f032505f),
[v5.12.3 Linux instructions](https://github.com/Slicer/Slicer/blob/v5.12.3/Docs/user_guide/getting_started.md#linux),
[package-signing guidance](https://github.com/Slicer/Slicer/wiki/Signing-Application-Packages),
and [5.12 release checklist](https://github.com/Slicer/Slicer/issues/9180).

The recursively owner-only x86_64 package is installed at
`/home/chris-berry/Applications/Slicer-5.12.3-linux-amd64` on Strawberry Ubuntu 26.04.
The install occupies 1,708,032 KiB. Local execution identifiers are:

- Slicer launcher SHA-256:
  `4ae4a2ce8a2221e0b8a2e9047fbac1d698352df39f5159ce7b322d800085b6ef`.
- BRAINSFit SHA-256:
  `ebe31c26141ac6ebf47aa535642e323ef6f3bd114e0638148748dc846761f8c7`.
- BRAINSResample SHA-256:
  `0a9728c2834ce89487e0da1ba055dd14c099cbd28e3a9234e9f81bd01249138a`.

The documented Ubuntu runtime packages plus local `bubblewrap`, Xvfb, and Xauthority
support are installed and version-recorded. ScanView always gives Linux Slicer a
private Xvfb display with TCP listening disabled and refuses an inherited desktop
display. The Slicer process remains inside bubblewrap's separate network namespace.
Its seccomp filter allows only `AF_UNIX` socket creation for private local IPC, rejects
network socket domains and io_uring setup, and has no unisolated fallback. Xvfb itself
runs inside that boundary. The mount namespace replaces host `/tmp` and `/run`, creates
the private X socket inside the isolated `/tmp`, re-exposes only the private job, and
executes a runner copy whose hash is checked before and after private staging.

## Strawberry Linux execution evidence

The exact retained offline ScanView ZIP verified and installed using `PIP_NO_INDEX=1`,
`--no-index`, and required hashes. `registration-doctor` matched the launcher hash,
reported Linux x86_64 plus Slicer 5.12.3/runtime revision `9034c71`, and found both the
network and private-display boundaries ready. A data-free engine preflight completed
inside those boundaries.

Normal `run-rigid-registration` commands then processed the same patient-free equal-
and partial-field synthetic MR pairs used on macOS. Both owner-only seven-file v2
bundles independently validated and stayed `generated_pending_qa`/`unreviewed`; every
display unlock remained false, and computation and interpretation arrays remained
empty. Source SHA-256 manifests were unchanged. The known +2 mm displacement produced
-2.008290 mm and -1.998159 mm moving-to-fixed x translations. Sampling support was
65,536/65,536 for equal fields and 65,536/69,632 (94.117647%) for the wider fixed
field, matching the macOS coverage oracle.

A live Linux probe confirmed that `AF_UNIX` socket pairs work for the private display
while `AF_INET` socket creation fails with `EPERM`. Xvfb left no TCP listener after
either run. No Mila data was transferred to Strawberry, and no external DICOM-
processing API was requested or available. Patient-free synthetic inputs, derivatives,
diagnostics, extracted runtimes, and duplicate bundles were moved to recoverable Trash;
the checksum-verified archive and owner-only Slicer installation were retained.

## Remaining trust boundaries

- ScanView still requires the independently recorded launcher SHA-256 on every job
  and checks it before source staging and after execution.
- Slicer runs with settings, startup scripts, user-site Python, proxies, credentials,
  extension servers, and external/host networking excluded. Linux allows only private
  local Unix-domain display IPC. There is no unsandboxed or cloud fallback.
- The macOS package has independently verified Developer ID/notarization evidence. The
  Linux package has official-source checksum evidence but no publisher signature in
  Slicer's documented Linux release process. ScanView itself is not yet signed.
- It does not establish patient identity, registration quality for Mila, lesion
  identity, tumor response, clinical suitability, or regulatory approval.
