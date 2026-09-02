# Agent API

DICOM Guide exposes a small loopback HTTP API so an agent can observe and control the
same viewer a person sees. It is memory-only and source-read-only.

## Start from a person's question

The public agent workflow is intentionally smaller than the raw HTTP surface:

| Need | Supported command | Result |
| --- | --- | --- |
| What is visible now? | `dicom-guide state` | Exact ready series, instance, plane, slice, tool, LPS point, and discussion marks |
| What scans are available? | `dicom-guide series` | PHI-minimized MRI/CT study and series inventory with opaque IDs |
| Show a useful view | `dicom-guide show ...` | Targeted native or MPR display change with exact ready confirmation |
| Point something out | `dicom-guide highlight ...` | Reversible agent discussion mark that preserves person-authored marks |
| Clarify the acquisition | `dicom-guide metadata ...` | Selected non-identifier DICOM headers for one exact source instance |
| Inspect pixels locally | `dicom-guide fetch-instance ...` | Hash-verified, owner-only local copy of one source object |

A guide should inventory and explain candidate series before choosing one, use the
least invasive command that answers the question, reread ready state after every
change, and distinguish visible observation from metadata, anatomical inference,
supplied report text, and clinical conclusion. See
`.agents/skills/dicom-guide/SKILL.md` for that behavioral contract.

Someone who has only a folder path should not need to understand this API. The
`$dicom-guide-install` skill owns installation, recursive DICOM discovery, launch,
health verification, and the handoff to a first guided tour.

## Connection

- Base URL: `http://127.0.0.1:<port>` (also `localhost` or `[::1]`).
- Start it with `dicom-guide open <dicom-folder>`.
- `GET /v1/health` and the browser UI need no authentication.
- All agent reads and commands use `Authorization: Bearer <launcher-token>`.
- `POST /v1/viewer-control` uses
  `Content-Type: application/vnd.dicom-guide.viewer-control+json`.

Use the installed `dicom-guide` commands instead of writing a client from scratch.
They reject non-loopback URLs, disable proxies and redirects, verify DICOM response
hashes, and securely discover the active owner-only local session.

## Control loop

1. `GET /v1/manifest` to discover opaque series and instance IDs.
2. `GET /v1/viewer-control` to read what is actually visible.
3. `POST /v1/viewer-control` to request a display change.
4. Poll `GET /v1/viewer-control` until the observation has the accepted command ID
   and revision with `render_status: "ready"`.

The browser viewer uses one long poll at a time with `after_revision`, `wait_seconds`
(at most 25), and its opaque `viewer_id`. A matching long poll renews the exact
viewer's short local lease, so background-tab timer throttling does not make an open
viewer appear disconnected. Agent clients may continue using the immediate route.

The browser publishes a heartbeat every two seconds. `viewer_connected` becomes
false when no current browser observation has arrived for five seconds.

## Read viewer state

`GET /v1/viewer-control` returns:

```json
{
  "schema_version": "1.0.0",
  "viewer_connected": true,
  "observation_age_seconds": 0.4,
  "command": {},
  "observation": {
    "viewer_id": "viewer_0123456789abcdef0123",
    "applied_command_id": null,
    "applied_revision": 0,
    "interaction_source": "person",
    "render_status": "ready",
    "view_mode": "mpr",
    "series_id": "series_0123456789abcdef0123",
    "instance_id": "instance_0123456789abcdef0123",
    "stack_position": 84,
    "stack_count": 221,
    "tool": "crosshairs",
    "patient_point_lps_mm": [4.0, -45.5, 41.0],
    "point_pinned": true,
    "discussion_marks": [
      {
        "id": "mark_0123456789abcdef0123",
        "orientation": "sagittal",
        "color": "cyan",
        "author": "person",
        "points_lps_mm": [[4.0, -45.5, 41.0]]
      }
    ]
  },
  "permissions": {},
  "privacy": {}
}
```

`series_id` and `instance_id` are stable opaque references for the loaded catalog.
`stack_position` is one-based. In native mode the instance is the displayed source
slice. In MPR it is the nearest native slice to the rendered crosshair.

`patient_point_lps_mm` is a three-number DICOM LPS coordinate or `null`. It is the
precise bridge between a person's pinned point, all three MPR panes, and an agent's
analysis. Metadata alone is not an image interpretation.

`discussion_marks` contains up to 256 reversible color strokes with bounded LPS
paths. Marks work in Single and MPR views. A mark identifies an attention region in
one plane; it is not a segmentation, measurement, anatomical label, or clinical finding.

## Change the display

`POST /v1/viewer-control` accepts one exact command:

```json
{
  "schema_version": "1.0.0",
  "command_id": "control_0123456789abcdef0123456789abcdef",
  "view_mode": "native",
  "series_id": "series_0123456789abcdef0123",
  "instance_id": "instance_0123456789abcdef0123",
  "tool": "highlight",
  "patient_point_lps_mm": null,
  "reset_view": false,
  "target_viewer_id": "viewer_0123456789abcdef0123",
  "discussion_marks_patch": {
    "add": [
      {
        "id": "mark_0123456789abcdef0123",
        "color": "cyan",
        "points_image_px": [[234, 237], [250, 224], [276, 221], [300, 236]]
      }
    ]
  }
}
```

The server adds a monotonic `revision` and `issued_at`. Last accepted command wins.

| Field | Effect |
| --- | --- |
| `view_mode` | Select `native` or three-plane `mpr`. |
| `series_id` | Select the exact MRI/CT series. |
| `instance_id` | Select the native slice or provide the MPR source anchor. |
| `tool` | Select the active interaction tool. |
| `patient_point_lps_mm` | Move and pin the MPR crosshair or native point. |
| `reset_view` | Refit the image and clear display transforms. |
| `target_viewer_id` | Bind the command to the exact browser that published the observed state. |
| `discussion_marks_patch` | Atomically add, remove, or clear agent highlights without changing person-authored marks. |

Native tools are `window`, `pan`, `zoom`, and `highlight`. MPR tools are `crosshairs`,
`window`, `pan`, `zoom`, and `highlight`. Agents must use this API for navigation and
display changes; do not simulate browser clicks, drags, or scrolling.

`discussion_marks_patch.add` accepts an opaque `mark_` ID, one color (`yellow`,
`cyan`, `violet`, or `green`), and either 1–64 `points_image_px` values, 1–64
`points_image_normalized` values, or an `orientation` with 1–64
`points_lps_mm` values. Image points are `[column, row]`, zero-based, and converted
to LPS by the local service using cataloged DICOM geometry. Normalized points are
`[x, y]` from 0 to 1 across the exact native source image. `remove_ids` and
`clear_agent: true` affect agent marks only. Person-painted marks retain
`author: "person"`; agent additions are assigned `author: "agent"` locally.
Marks stay in memory and source pixels are unchanged.

Prefer patches. They are atomic against the latest observed overlay, preserve mark
provenance, and avoid resending every existing stroke. The accepted command returned
by `GET /v1/viewer-control` contains the resolved complete `discussion_marks` list so
the browser can apply and confirm the exact result.

Copy `observation.viewer_id` into `target_viewer_id` for every command derived from
visible state. Other open DICOM Guide tabs ignore that command and cannot replace its
ready confirmation while the targeted viewer remains connected. The helper does this
automatically.

The helper provides the common fast path:

```bash
dicom-guide highlight add \
  --color cyan \
  --image-normalized 0.46 0.46 --image-normalized 0.49 0.44 \
  --image-normalized 0.54 0.43

dicom-guide highlight remove \
  --mark-id mark_0123456789abcdef0123

dicom-guide highlight clear
```

`highlight` reads the current ready viewer target, applies one command, waits for the
exact render confirmation, and returns local stage timings. Pixel points require the
native Single view. Use `--lps-point L P S --orientation axial|coronal|sagittal` for
MPR or already known patient-space paths.

When a person changes the viewer, `interaction_source` becomes `person` and applied
command provenance clears. Always reread state before answering “what am I looking
at?” or issuing a follow-up command.

## Source access

### `GET /v1/manifest`

Returns the local catalog: studies, MRI/CT series, acquisition and geometry metadata,
and ordered opaque instance IDs. It omits direct patient-identifier tags but is not
de-identified.

### `GET /v1/instances/{instance_id}`

Returns one exact source object as `application/dicom`. Verify the SHA-256 value in
`X-Content-SHA256`. Keep the bytes on-device and do not edit the source.

### `GET /v1/health`

Returns basic local service health without a token.

## Examples

```bash
# Exact visible state
dicom-guide state

# Local series summary
dicom-guide series

# Open an exact native source slice
dicom-guide show \
  --series-id series_0123456789abcdef0123 \
  --instance-id instance_0123456789abcdef0123 \
  --view native --tool window --reset

# Read selected non-identifier headers locally
dicom-guide metadata \
  --instance-id instance_0123456789abcdef0123
```

The helper also supports `fetch-instance --output <owner-only-path>` for local pixel
analysis. Remove temporary copies when finished and never add them to Git.

## Response and failure rules

- `401` — missing or incorrect bearer token.
- `403` — browser-only write without the exact loopback origin.
- `415` — incorrect control media type.
- `422` — malformed or out-of-catalog target/state.
- `viewer_connected: false` — open or reload the viewer before relying on state.

The control response intentionally contains no pixels, direct identifiers,
measurements, diagnosis, or clinical conclusion. If local decoding is unavailable,
fail locally; never fall back to an external DICOM service.
