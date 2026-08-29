# ScanView local control API v1

## Connection

- Base URL: plain `http://127.0.0.1:<port>/`, `localhost`, or `[::1]` only.
- Agent authorization: `Authorization: Bearer <launcher token>`.
- Control media type: `application/vnd.scanview.viewer-control+json`.
- Responses use `Cache-Control: no-store`.
- The browser uses a separate HttpOnly session; a bearer cannot publish browser observations.
- The bundled helper disables environment proxies and HTTP redirects so a local request cannot fall through to another origin.

## Read health and sources

`GET /v1/health` needs no token.

`GET /v1/manifest` returns the sensitive local ScanView manifest. It excludes direct patient-identifier tags but is not de-identified. Series contain opaque IDs, acquisition metadata, geometry, and ordered exact instances.

`GET /v1/instances/{opaque_instance_id}` returns one exact local DICOM object as `application/dicom`. Keep it local and owner-only. The response includes `X-Content-SHA256`; source writes do not exist.

## Read control state

`GET /v1/viewer-control` returns:

```json
{
  "schema_version": "1.0.0",
  "viewer_connected": true,
  "observation_age_seconds": 0.4,
  "command": {},
  "observation": {},
  "permissions": {},
  "privacy": {}
}
```

`viewer_connected` requires a browser observation no older than five seconds. A connected observation contains:

- `applied_command_id` and `applied_revision`, or null/zero after person control;
- `interaction_source`: `agent` or `person`;
- `render_status`: `loading`, `ready`, or `error`;
- `view_mode`: `native` or `mpr`;
- exact `series_id`, `instance_id`, and one-based `stack_position`/`stack_count`;
- active display `tool`;
- `patient_point_lps_mm` and `point_pinned`.

The state contains no pixels, direct identifiers, source text, measurements, diagnosis, response, or clinical conclusion. Opaque references and patient coordinates remain sensitive and `deidentified` is false.

## Issue a command

`POST /v1/viewer-control` requires bearer authorization and the control media type. Browser-cookie authorization alone is refused.

```json
{
  "schema_version": "1.0.0",
  "command_id": "control_0123456789abcdef0123456789abcdef",
  "view_mode": "native",
  "series_id": "series_0123456789abcdef0123",
  "instance_id": "instance_0123456789abcdef0123",
  "tool": "window",
  "patient_point_lps_mm": null,
  "reset_view": false
}
```

Rules:

- IDs must have the documented opaque form and the instance must belong to the series in the live manifest.
- Native tools: `window`, `pan`, `zoom`.
- MPR tools: `crosshairs`, `window`, `pan`, `zoom`.
- A point is null or exactly three finite DICOM LPS millimeter coordinates.
- Each accepted command receives a server-monotonic `revision`. Last accepted command wins in memory.
- The browser polls, applies a revision once, and publishes its exact resulting state.
- Confirm the same command ID/revision, exact target, and `render_status: ready` before reporting success.
- If a person acts afterward, the observation switches to `interaction_source: person`; a new command needs a new ID and server revision.

For native view, the observed `instance_id` must exactly match the command. For MPR,
the command instance is a source-series anchor while the patient-space point is the
precise navigation target. The observation reports the exact nearest native source
slice at the rendered crosshair, which may differ from the anchor after volume
reconstruction or coordinate clamping.

## Browser observation route

`POST /v1/viewer-control/observation` is for the ScanView browser only. It requires the distinct HttpOnly browser session, exact loopback Origin, and the control media type. Agents must not attempt to forge it.

## Failure handling

- `401`: token/cookie missing or invalid.
- `403 bearer_agent_required`: attempted command with only a browser session.
- `403 browser_session_required`: attempted observation with a bearer.
- `415`: wrong media type.
- `422`: malformed, stale, mismatched, out-of-catalog, or safety-invalid command/observation.
- `viewer_connected: false`: open/reload the viewer and wait for a fresh browser heartbeat.

Never fall back to an external DICOM processor when the local API or decoder is unavailable.
