# Agent API

ScanView exposes a small loopback HTTP API so an agent can observe and control the
same viewer a person sees. It is memory-only and source-read-only.

## Connection

- Base URL: `http://127.0.0.1:<port>` (also `localhost` or `[::1]`).
- Start it with `scanview-agent launch <dicom-folder>`.
- `GET /v1/health` and the browser UI need no authentication.
- All agent reads and commands use `Authorization: Bearer <launcher-token>`.
- `POST /v1/viewer-control` uses
  `Content-Type: application/vnd.scanview.viewer-control+json`.

Use `skills/scanview-control/scripts/scanview_control.py` instead of writing a client
from scratch. It rejects non-loopback URLs, disables proxies and redirects, verifies
DICOM response hashes, and reads the token from `SCANVIEW_AGENT_TOKEN`.

## Control loop

1. `GET /v1/manifest` to discover opaque series and instance IDs.
2. `GET /v1/viewer-control` to read what is actually visible.
3. `POST /v1/viewer-control` to request a display change.
4. Poll `GET /v1/viewer-control` until the observation has the accepted command ID
   and revision with `render_status: "ready"`.

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
    "point_pinned": true
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

## Change the display

`POST /v1/viewer-control` accepts one exact command:

```json
{
  "schema_version": "1.0.0",
  "command_id": "control_0123456789abcdef0123456789abcdef",
  "view_mode": "mpr",
  "series_id": "series_0123456789abcdef0123",
  "instance_id": "instance_0123456789abcdef0123",
  "tool": "crosshairs",
  "patient_point_lps_mm": [4.0, -45.5, 41.0],
  "reset_view": false
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

Native tools are `window`, `pan`, and `zoom`. MPR tools are `crosshairs`, `window`,
`pan`, `zoom`, and `crop`. Selecting a tool makes it active in the viewer; continuous
drag geometry remains a visible person/agent-browser interaction. Exact navigation
should use series/instance IDs and LPS coordinates rather than simulated scrolling.

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
export SCANVIEW_AGENT_TOKEN='<launcher token>'

# Exact visible state
.venv/bin/python skills/scanview-control/scripts/scanview_control.py state

# Local series summary
.venv/bin/python skills/scanview-control/scripts/scanview_control.py series

# Open an exact native source slice
.venv/bin/python skills/scanview-control/scripts/scanview_control.py show \
  --series-id series_0123456789abcdef0123 \
  --instance-id instance_0123456789abcdef0123 \
  --view native --tool window --reset

# Read selected non-identifier headers locally
.venv/bin/python skills/scanview-control/scripts/scanview_control.py metadata \
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
