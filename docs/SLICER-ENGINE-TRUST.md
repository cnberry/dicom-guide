# Local Slicer engine trust record

Verified 2026-08-28 on this macOS arm64 host. No patient data was used in download,
authentication, preflight, or the real-engine synthetic registration.

The machine-readable companion is
[`packaging/slicer/macos-amd64-5.12.3.json`](../packaging/slicer/macos-amd64-5.12.3.json).
It is a checked-in provenance record, not an automatic software updater, signature
service, clinical validation, or substitute for ScanView's required per-run launcher
hash.

## Official release identity

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
- The bundled BRAINSFit executable is signed by the same Kitware team.

The x86_64 app is installed at `/Users/chris/Applications/Slicer.app` and runs on this
arm64 Mac through Rosetta 2. The installed bundle is 1,647,276 KiB. Local execution
identifiers are:

- Slicer launcher SHA-256:
  `710dfa764bf407377ee516b63f84cfb4cf0e0719218c7f43712cc0f231ed6b23`.
- BRAINSFit SHA-256:
  `75d173916e0d2d48f6d9ba9b0cd093349661953538748809d7ea2ad93c85da93`.

## Execution evidence

`registration-doctor` found the installed engine, matched the launcher hash, verified
version 5.12.3/runtime revision `9034c71`, found BRAINSFit, and reported the mandatory
macOS deny-all-network sandbox ready. A normal `run-rigid-registration` invocation then
processed two synthetic 16-slice MR studies through the real Slicer/BRAINSFit process
inside that sandbox.

The output remained `generated_pending_qa` and `unreviewed`; all overlay, swipe,
subtraction, and mask-propagation display flags stayed locked. Independent validation
accepted the six-file bundle, source hashes were identical before and after, and the
known synthetic +2 mm displacement produced an approximately -1.997 mm moving-to-fixed
x translation with near-identity rotation. The isolated local QA viewer rendered the
real NRRDs in all three planes and all four comparison modes without browser errors.
No decision was submitted. Synthetic sources, diagnostics, and derivatives were moved
out of active storage to recoverable Trash after verification.

## Remaining trust boundaries

- ScanView still requires the independently recorded launcher SHA-256 on every job
  and checks it before source staging and after execution.
- Slicer runs with settings, startup scripts, user-site Python, proxies, credentials,
  extension servers, and external/host networking excluded. There is no unsandboxed
  or cloud fallback.
- This record authenticates one official macOS package and installed copy. Linux
  package authentication and real execution remain pending.
- It does not establish patient identity, registration quality for Mila, lesion
  identity, tumor response, clinical suitability, or regulatory approval.
