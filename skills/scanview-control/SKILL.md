---
name: scanview-control
description: Inspect and control a running local ScanView MRI/CT viewer. Use when a person asks what is visible, what a pointed location represents, which series or slice is open, or asks Codex to switch series, open native or three-plane MPR, move to an exact DICOM LPS point, choose an image tool, reset the view, inspect local metadata, or retrieve an exact DICOM instance for on-device analysis.
---

# Control ScanView

Keep DICOM, pixels, coordinates, and source metadata on the local computer.

## Connect

1. Confirm `scanview-agent launch <folder>` is running and the printed URL is open.
2. Use the launcher's token through `SCANVIEW_AGENT_TOKEN`; never print or commit it.
3. Run `scripts/scanview_control.py` with the repository `.venv/bin/python`.
4. Read `../../docs/AGENT-API.md` before composing raw HTTP or debugging a response.

## Answer a viewer question

1. Run `state`. If `viewer_connected` is false, open/reload the viewer and retry.
2. Treat the returned series, instance, stack position, view mode, render status,
   tool, and LPS point as the exact visible context.
3. Use `series` and `metadata --instance-id ...` when more local source context is
   needed. Fetch DICOM bytes only for necessary on-device pixel analysis.
4. Separate source observations and reproducible computations from interpretation.
   Confirm medical conclusions with the treating team.

```bash
.venv/bin/python skills/scanview-control/scripts/scanview_control.py state
.venv/bin/python skills/scanview-control/scripts/scanview_control.py series
.venv/bin/python skills/scanview-control/scripts/scanview_control.py metadata \
  --instance-id instance_0123456789abcdef0123
```

## Drive the viewer

Use `show` with exact opaque IDs from `series`. Wait until `state` reports the same
command/revision and `render_status: ready` before saying the display changed.

```bash
.venv/bin/python skills/scanview-control/scripts/scanview_control.py show \
  --series-id series_0123456789abcdef0123 \
  --instance-id instance_0123456789abcdef0123 \
  --view native --tool window --reset

.venv/bin/python skills/scanview-control/scripts/scanview_control.py show \
  --series-id series_0123456789abcdef0123 \
  --instance-id instance_0123456789abcdef0123 \
  --view mpr --tool crosshairs --lps 12.5 -8.25 43.0
```

In MPR, the observed instance is the nearest native slice at the crosshair and may
differ from the source anchor. Confirm important observations on native slices.

Do not mutate source files, upload imaging to another service, or present the viewer
as diagnostic software.
