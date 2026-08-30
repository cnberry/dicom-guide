---
name: dicom-guide-develop
description: Set up, change, test, package, deploy, and contribute to the DICOM Guide repository with Codex. Use when a contributor wants Codex to prepare the development environment, understand the architecture, fix a viewer or agent-interface problem, add a local DICOM capability, run checks, build or deploy native macOS/Linux/Windows releases, dogfood a change with synthetic scans, or prepare and respond to a pull request. Preserve user changes, follow repository instructions, keep all patient data out of development, verify affected behavior proportionally, and leave a concise upstream-ready handoff.
---

# Develop DICOM Guide with Codex

Take an outcome from request to verified contribution. The contributor should not need
to translate it into setup commands first.

## Orient before changing code

1. Read the repository `AGENTS.md`, `README.md`, and the nearest instructions for the
   files in scope.
2. Inspect Git status and preserve all unrelated user changes.
3. Trace the requested behavior from the public prompt or UI through the local agent
   interface, Python service, viewer, and packaging when relevant.
4. Keep the public experience centered on a person who has an unfamiliar scan folder,
   not on internal artifact or implementation terminology.

Do not spawn subagents unless the person explicitly requests delegation. Do not make
unrelated protocol or schema migrations as part of an ordinary feature.

## Prepare the contributor environment

The repository expects Python 3.11+, Node.js 22+, and pnpm 11+. Adapt commands to the
current OS and available tools. A contributor-only virtual environment is acceptable;
the shipped application must remain self-contained and must not require one.

In Codex desktop, load the bundled workspace dependencies before setup and ensure the
bundled Node directory and pnpm directory are on the same `PATH`. Check both
`node --version` and `pnpm --version` before `pnpm install`; if a lifecycle script says
`node: command not found`, correct `PATH` and rerun the frozen install instead of
installing another runtime.

Typical setup:

```bash
corepack enable
pnpm install --frozen-lockfile
python -m venv .venv
.venv/bin/python -m pip install -e 'packages/agent[test]'
```

On Windows use `.venv\Scripts\python.exe`. Do not commit environments, build output,
session files, or dependency caches.

## Engineering rules

- DICOM decoding, geometry, measurement, registration, and derived-data work remains
  local. Never add an external patient-data processing fallback.
- Source DICOM is read-only. Use temporary output locations with owner-only permissions
  for any locally fetched instance.
- Use opaque public IDs and the documented loopback control contract.
- Make viewer state observable before making it controllable; commands must target the
  exact viewer and wait for the exact ready revision.
- Preserve person-authored marks and make agent overlays reversible.
- Keep direct observation, computation, inference, report context, and clinical review
  distinct in data structures and language.
- Use synthetic, non-identifying DICOM fixtures. Never use a person's scan, report,
  screenshot, local path, token, or finding in tests, logs, commits, or PRs.
- Prefer small public surfaces and current behavior over speculative backlog.

## Verify in proportion to the change

Run the smallest relevant checks while iterating, then the full affected suite before
handoff:

```bash
pnpm test
pnpm typecheck
pnpm build
.venv/bin/python -m pytest packages/agent/tests
python scripts/build_native_distribution.py
```

On Windows use the appropriate Python executable. Packaging changes require archive
inspection and an install/launch smoke test on every affected platform, using native
CI where local hardware is unavailable. Viewer changes require at least one rendered
synthetic MRI or CT path plus the relevant state/control test.

Publish native packages only through the repository's `Native release` workflow and
the exact version tag documented in `docs/RELEASES.md`. Do not hand-upload partial
platform sets or describe checksum files as signatures. Require the workflow's
Sigstore provenance attestation and portable bundle for a published release.

## Deploy a development build

Deploy the exact packaged artifact, not the source entry point or contributor virtual
environment:

1. Run `pnpm build` and create a fresh temporary output directory.
2. Run `python3 scripts/build_native_distribution.py --output-dir <temporary-output>`
   (`python` on Windows) and verify the adjacent `.sha256` file.
3. Extract the archive into a fresh staging directory. Do not run `install.sh` or
   `install.ps1` for an ordinary developer deployment.
4. Set `DICOM_GUIDE_STATE_HOME` to a private temporary directory and launch
   `app/dicom-guide open <synthetic-dicom-folder> --port <unused-loopback-port>`;
   on Windows use `app\dicom-guide.exe`. Use the same state variable for control
   commands so an installed or person-owned session is never disturbed.
5. Check `/v1/health`, open the viewer, and use that same staged binary's `state`
   command. Require `viewer_connected: true` and `render_status: ready` for a rendered
   synthetic series.

Use synthetic DICOM by default. Use a person-owned scan only when they explicitly ask
for that dogfood path; keep it outside the repository and out of logs and commits.
Stop the isolated process and remove its staging and state directories when finished,
unless the contributor asks to keep the development deployment running.

Generate the standard patient-free CT fixture from the prepared contributor
environment when a rendered smoke path is needed:

```bash
.venv/bin/python scripts/generate_synthetic_presentation_state.py <empty-temp-folder>
```

On Windows use `.venv\Scripts\python.exe`. Do not create a second environment only for
the fixture generator.

## Dogfood and contribute

Use the isolated developer deployment above and `$dicom-guide` to exercise the public
first-session prompts. Check that a person can start with only a folder path and
receive a useful explanation without knowing DICOM vocabulary. Reserve
`$dicom-guide-install` for explicitly testing the non-developer installation journey.

Before opening or updating a PR:

1. Review the diff for patient data, local paths, tokens, screenshots, generated
   archives, stale names, and unrelated edits.
2. Report exact tests and platform coverage; distinguish local verification from CI.
3. Explain the person-facing outcome first, then compatibility or migration details.
4. Keep follow-up work out of the PR unless it blocks the requested outcome.
5. Respond to review comments by fixing the underlying product theme, not only the
   literal line mentioned.

Finish with a concise status: what changed, what was verified, any material limitation,
and the PR or branch link when one exists.
