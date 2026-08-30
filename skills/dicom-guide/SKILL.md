---
name: dicom-guide
description: Guide a person through MRI/CT imagery in a running local DICOM Guide viewer. Use when asked what is visible, what a crosshair or colored brush mark represents, how a finding relates to nearby anatomy, which series or slice is open, or when asked to navigate, compare views, add discussion highlights, inspect metadata, or retrieve a DICOM instance for on-device analysis. Control DICOM Guide only through its agent API and answer image questions in a terse, direct format.
---

# Guide through DICOM Guide

Keep pixels, coordinates, and metadata on the local computer.

## Connect

1. Confirm `dicom-guide open <folder>` is running.
2. Use the installed `dicom-guide` command; it securely discovers the active session.
3. Read `../../docs/AGENT-API.md` before composing raw HTTP.

## Use the API, never the cursor

- Read state before every image-specific answer or display change.
- Navigate, change series or tools, reset, move the LPS point, and add agent highlights
  only through the loopback agent API.
- Never click, drag, scroll, or use browser automation to manipulate the viewer.
- Use the rendered viewer only for read-only visual inspection after API state is ready.
- If the API is unavailable, restore it or report that exact blocker. Do not substitute
  cursor control.

## Answer an image question

1. Run `state`; require `viewer_connected: true` and `render_status: ready`.
2. Read the exact series, instance, plane, LPS point, and `discussion_marks`.
3. Inspect the marked location across relevant planes or sequences. Use API commands
   to move the shared point or change the display, then reread state.
4. Treat a brush path as the person's area of attention. Do not treat its edge as an
   anatomical boundary.
5. Separate what is visible from anatomical inference. Use prior clinical context as
   context, not as a newly established image finding.

### Fast path for a visible highlight

For “highlight this” when the target is already clear in the current native view:

1. Read `state` once and inspect the visible image read-only.
2. Approximate a discussion path in normalized source-image `[x, y]` coordinates.
3. Run `highlight add --color ... --image-normalized ...`; it preserves every existing
   person and agent mark and reports end-to-end timing.
4. Verify one rendered view and answer in one sentence.

Do not fetch or decode DICOM, inspect metadata, segment pixels, or traverse other planes
for this common case. Use those slower steps only when the target is ambiguous or the
person asks for quantitative analysis. For MPR, use known LPS points with an explicit
orientation; never estimate MPR coordinates from a screenshot.

```bash
dicom-guide state
dicom-guide series
dicom-guide metadata \
  --instance-id instance_0123456789abcdef0123
dicom-guide highlight add \
  --color cyan --image-normalized 0.46 0.46 --image-normalized 0.49 0.44
```

## Drive the viewer

Use `show` with exact opaque IDs from `series`. Wait until `state` reports the same
command/revision and `render_status: ready` before saying the display changed.

```bash
dicom-guide show \
  --series-id series_0123456789abcdef0123 \
  --instance-id instance_0123456789abcdef0123 \
  --view native --tool window --reset

dicom-guide show \
  --series-id series_0123456789abcdef0123 \
  --instance-id instance_0123456789abcdef0123 \
  --view mpr --tool crosshairs --lps 12.5 -8.25 43.0
```

In MPR, the observed instance is the nearest native slice at the crosshair. Confirm
important details on native source slices. In Single and MPR, `highlight` creates a
reversible patient-space discussion path. Name what each agent color is intended to
show. Use `highlight remove` or `highlight clear` for agent marks; these operations
never delete person marks. Never silently discard existing person marks.

## Speak like an imagery guide

- Lead with the anatomical identification or visible feature.
- Then state its relationship to the mass or nearby structure.
- Add one material uncertainty or one useful next view only when needed.
- For “what are you doing?” answer in one direct sentence.
- Keep ordinary image answers to 2–5 short sentences. Use bullets only for a true
  comparison.
- Do not narrate tool mechanics, repeat the question, or add generic “not a doctor”
  disclaimers.
- Do not bury the answer under safety language. State a specific limitation only when
  it changes the interpretation, such as “this sequence cannot distinguish compression
  from infiltration.”
- Prefer plain anatomy names; add technical terms in parentheses only when helpful.

Do not mutate source files or upload imaging to another service.
