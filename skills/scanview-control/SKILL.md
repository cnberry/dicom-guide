---
name: scanview-control
description: Inspect and control a running local ScanView DICOM workspace through its authenticated loopback API. Use when Codex needs to identify MRI/CT series, read the exact active source image and pinned DICOM LPS point, switch between native and three-plane MPR views, select an exact series/instance, change display tools, reset the view, or retrieve one exact DICOM instance for strictly local analysis without screenshots or external DICOM processing.
---

# ScanView Control

Treat ScanView as the visualization surface and the Codex conversation as the human interface. Keep every DICOM read, decode, and computation on the local computer.

## Connect

1. Confirm `scanview-agent launch` is running and the viewer is open in the Codex side panel.
2. Obtain the loopback base URL and bearer token from the current launcher output or user-provided context. Never inspect browser storage, print the token, put it in a URL, or commit it.
3. Pass the token with `--token` or the `SCANVIEW_AGENT_TOKEN` environment variable to `scripts/scanview_control.py`. Run metadata or DICOM retrieval through the repository's `.venv/bin/python`, whose local ScanView installation includes `pydicom`; never substitute a remote parser.
4. Read [references/api.md](references/api.md) before composing a raw request or interpreting a control response.

## Inspect before answering

Run `state` first. Use its exact opaque series/instance, stack position, view mode, tool, render status, and pinned LPS point. If `viewer_connected` is false, open or reload the viewer and retry; do not claim to know what is visible.

Use `series` to find candidate local series. Treat descriptions and acquisition metadata as sensitive source text, not as findings. Use `metadata --instance-id ...` for a PHI-minimized exact-header view. Use `fetch-instance` only when local pixel processing is necessary; write to a temporary owner-only path, keep it out of Git, and remove it recoverably after use.

Never infer a finding from metadata, series names, or one intensity value. Separate:

- exact source observations;
- local computations and their method;
- tentative interpretation;
- questions or conclusions requiring a radiologist, neurosurgeon, or oncology team.

## Drive the viewer

Use `show` with one exact series and instance. Choose `native` for an authoritative source slice or `mpr` for a locally reconstructed navigation view. For MPR, supply a pinned LPS point when spatial focus matters. Wait for the matching applied revision and `render_status: ready` before telling the user the view changed.

In native view, the applied instance must equal the requested instance. In MPR, the requested instance is a source-series anchor; the applied observation reports the exact nearest native slice at the rendered crosshair and may differ from that anchor. Treat the applied LPS point and ready revision as authoritative.

Examples:

```bash
.venv/bin/python skills/scanview-control/scripts/scanview_control.py --token "$SCANVIEW_AGENT_TOKEN" state
.venv/bin/python skills/scanview-control/scripts/scanview_control.py --token "$SCANVIEW_AGENT_TOKEN" series
.venv/bin/python skills/scanview-control/scripts/scanview_control.py --token "$SCANVIEW_AGENT_TOKEN" show \
  --series-id series_0123456789abcdef0123 \
  --instance-id instance_0123456789abcdef0123 \
  --view native --tool window --reset
.venv/bin/python skills/scanview-control/scripts/scanview_control.py --token "$SCANVIEW_AGENT_TOKEN" show \
  --series-id series_0123456789abcdef0123 \
  --instance-id instance_0123456789abcdef0123 \
  --view mpr --tool crosshairs --lps 12.5 -8.25 43.0
```

If the person clicks a native image, ScanView pins a visible marker and reports that point until it is cleared or the source changes. Read `state` after the click; do not rely on hover or cursor position.

## Safety boundary

- Use only plain loopback HTTP and the authenticated local API.
- Do not send DICOM, pixels, screenshots, source text, coordinates, or bearer credentials to web search, an external API, telemetry, or a remote model tool.
- Do not mutate source files. Viewer control authorizes navigation, display tools, and patient-space focus only.
- Do not create measurements, diagnose, classify response, or state a clinical conclusion through this control channel.
- Preserve exact opaque source references in internal reasoning, but avoid repeating sensitive IDs or source metadata unless it helps the user verify the view.
- Treat MPR as an interpolated local navigation view. Confirm important observations on native source images and with qualified clinicians.
