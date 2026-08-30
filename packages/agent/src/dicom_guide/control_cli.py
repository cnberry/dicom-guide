#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import secrets
import stat
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


MEDIA_TYPE = "application/vnd.dicom-guide.viewer-control+json"
SERIES_ID = re.compile(r"^series_[0-9a-f]{20}$")
INSTANCE_ID = re.compile(r"^instance_[0-9a-f]{20}$")
MARK_ID = re.compile(r"^mark_[0-9a-f]{20}$")
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


def local_base_url(value: str) -> str:
    parsed = urlparse(value)
    try:
        port = parsed.port
    except ValueError as error:
        raise ValueError("base URL is invalid") from error
    if (
        parsed.scheme != "http"
        or parsed.hostname not in LOOPBACK_HOSTS
        or port is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ValueError("base URL must be a plain loopback HTTP origin with a port")
    host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
    return f"http://{host}:{port}"


class Client:
    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = local_base_url(base_url)
        if not token or "\n" in token or "\r" in token:
            raise ValueError("a valid bearer token is required")
        self.token = token
        self.opener = build_opener(ProxyHandler({}), NoRedirect())

    def request(self, path: str, *, body: dict[str, Any] | None = None) -> tuple[bytes, dict[str, str]]:
        headers = {
            "Accept": "application/json" if body is not None or not path.startswith("/v1/instances/") else "application/dicom",
            "Authorization": f"Bearer {self.token}",
        }
        payload = None
        method = "GET"
        if body is not None:
            payload = json.dumps(body, separators=(",", ":")).encode()
            headers["Content-Type"] = MEDIA_TYPE
            method = "POST"
        request = Request(self.base_url + path, data=payload, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=10) as response:
                return response.read(), dict(response.headers.items())
        except HTTPError as error:
            detail = error.read().decode("utf-8", "replace")[:1000]
            raise RuntimeError(f"local DICOM Guide request failed ({error.code}): {detail}") from error
        except URLError as error:
            raise RuntimeError(f"local DICOM Guide is unavailable: {error.reason}") from error

    def json(self, path: str, *, body: dict[str, Any] | None = None) -> dict[str, Any]:
        payload, _ = self.request(path, body=body)
        value = json.loads(payload)
        if not isinstance(value, dict):
            raise RuntimeError("local DICOM Guide returned non-object JSON")
        return value


def exact_dicom(client: Client, instance_id: str) -> tuple[bytes, str]:
    payload, headers = client.request(f"/v1/instances/{instance_id}")
    content_type = headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
    expected = headers.get("X-Content-SHA256", "")
    observed = hashlib.sha256(payload).hexdigest()
    if content_type != "application/dicom":
        raise RuntimeError("local DICOM Guide returned an unexpected instance media type")
    if not re.fullmatch(r"[0-9a-f]{64}", expected) or not secrets.compare_digest(
        expected, observed
    ):
        raise RuntimeError("local DICOM Guide instance hash did not match its protected source")
    return payload, observed


def print_json(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def series_summary(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for study in manifest.get("studies", []):
        for series in study.get("series", []):
            if series.get("modality") not in {"MR", "CT"}:
                continue
            result.append(
                {
                    "series_id": series.get("id"),
                    "study_id": study.get("id"),
                    "date": series.get("acquisition_date"),
                    "modality": series.get("modality"),
                    "description": series.get("series_description"),
                    "protocol": series.get("protocol_name"),
                    "body_part": series.get("body_part"),
                    "instance_count": series.get("instance_count"),
                    "rows": series.get("rows"),
                    "columns": series.get("columns"),
                    "pixel_spacing": series.get("pixel_spacing"),
                    "slice_thickness": series.get("slice_thickness"),
                    "first_instance_id": (
                        series.get("instances", [{}])[0].get("id")
                        if series.get("instances")
                        else None
                    ),
                }
            )
    return result


def metadata(payload: bytes, instance_id: str) -> dict[str, Any]:
    try:
        from pydicom import dcmread
    except ImportError as error:
        raise RuntimeError(
            "the installed local DICOM reader is unavailable"
        ) from error
    dataset = dcmread(io.BytesIO(payload), stop_before_pixels=True, force=False)
    names = [
        "Modality",
        "AcquisitionDate",
        "SeriesDescription",
        "ProtocolName",
        "BodyPartExamined",
        "Rows",
        "Columns",
        "PixelSpacing",
        "SliceThickness",
        "SpacingBetweenSlices",
        "ImagePositionPatient",
        "ImageOrientationPatient",
        "InstanceNumber",
        "NumberOfFrames",
        "PhotometricInterpretation",
        "BitsAllocated",
        "BitsStored",
        "PixelRepresentation",
        "RescaleSlope",
        "RescaleIntercept",
        "WindowCenter",
        "WindowWidth",
        "RepetitionTime",
        "EchoTime",
        "InversionTime",
        "FlipAngle",
    ]
    result: dict[str, Any] = {"instance_id": instance_id, "local_only": True}
    for name in names:
        value = getattr(dataset, name, None)
        if value is None:
            continue
        if isinstance(value, (str, int, float)):
            result[name] = value
        else:
            try:
                result[name] = [float(item) for item in value]
            except (TypeError, ValueError):
                result[name] = str(value)
    return result


def owner_only_write(path: Path, payload: bytes) -> None:
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    if stat.S_IMODE(path.stat().st_mode) != 0o600:
        path.unlink(missing_ok=True)
        raise RuntimeError("output permissions are not owner-only")


def ready_observation(state: dict[str, Any]) -> dict[str, Any]:
    observation = state.get("observation")
    if (
        state.get("viewer_connected") is not True
        or not isinstance(observation, dict)
        or observation.get("render_status") != "ready"
    ):
        raise RuntimeError("the local viewer is not connected and ready")
    return observation


def issue_and_wait(
    client: Client, command: dict[str, Any], wait_seconds: float, started: float
) -> dict[str, Any]:
    accepted_at = time.monotonic()
    accepted = client.json("/v1/viewer-control", body=command)
    revision = accepted.get("revision")
    posted_at = time.monotonic()
    deadline = posted_at + max(0.0, wait_seconds)
    while time.monotonic() <= deadline:
        current = client.json("/v1/viewer-control")
        observation = current.get("observation")
        if (
            current.get("viewer_connected") is True
            and isinstance(observation, dict)
            and observation.get("applied_command_id") == command["command_id"]
            and observation.get("applied_revision") == revision
            and observation.get("render_status") == "ready"
        ):
            finished = time.monotonic()
            return {
                "accepted": accepted,
                "applied": observation,
                "timing_ms": {
                    "prepare": round((accepted_at - started) * 1000),
                    "accept": round((posted_at - accepted_at) * 1000),
                    "render_ready": round((finished - posted_at) * 1000),
                    "total": round((finished - started) * 1000),
                },
            }
        time.sleep(0.1)
    raise RuntimeError("viewer did not confirm the exact ready command before timeout")


def command_for_observation(
    observation: dict[str, Any], *, tool: str, patch: dict[str, Any] | None = None
) -> dict[str, Any]:
    command = {
        "schema_version": "1.0.0",
        "command_id": f"control_{secrets.token_hex(16)}",
        "view_mode": observation["view_mode"],
        "series_id": observation["series_id"],
        "instance_id": observation["instance_id"],
        "tool": tool,
        "patient_point_lps_mm": observation.get("patient_point_lps_mm"),
        "reset_view": False,
        "target_viewer_id": observation["viewer_id"],
    }
    if patch is not None:
        command["discussion_marks_patch"] = patch
    return command


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="dicom-guide",
        description="Inspect and drive a local DICOM Guide workspace",
    )
    root.add_argument("--base-url")
    root.add_argument("--token")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("state")
    commands.add_parser("series")
    show = commands.add_parser("show")
    show.add_argument("--series-id", required=True)
    show.add_argument("--instance-id", required=True)
    show.add_argument("--view", choices=["native", "mpr"], required=True)
    show.add_argument(
        "--tool",
        choices=["window", "pan", "zoom", "crosshairs", "highlight"],
    )
    show.add_argument("--lps", nargs=3, type=float)
    show.add_argument("--reset", action="store_true")
    show.add_argument("--wait-seconds", type=float, default=12.0)
    highlight = commands.add_parser("highlight")
    highlight.add_argument("--wait-seconds", type=float, default=8.0)
    highlight_commands = highlight.add_subparsers(dest="highlight_command", required=True)
    add = highlight_commands.add_parser("add")
    add.add_argument("--color", choices=["yellow", "cyan", "violet", "green"], required=True)
    add.add_argument("--mark-id")
    points = add.add_mutually_exclusive_group(required=True)
    points.add_argument(
        "--image-point",
        nargs=2,
        type=float,
        action="append",
        metavar=("COLUMN", "ROW"),
    )
    points.add_argument(
        "--lps-point",
        nargs=3,
        type=float,
        action="append",
        metavar=("L", "P", "S"),
    )
    points.add_argument(
        "--image-normalized",
        nargs=2,
        type=float,
        action="append",
        metavar=("X", "Y"),
    )
    add.add_argument("--orientation", choices=["axial", "coronal", "sagittal"])
    remove = highlight_commands.add_parser("remove")
    remove.add_argument("--mark-id", action="append", required=True)
    highlight_commands.add_parser("clear")
    inspect = commands.add_parser("metadata")
    inspect.add_argument("--instance-id", required=True)
    fetch = commands.add_parser("fetch-instance")
    fetch.add_argument("--instance-id", required=True)
    fetch.add_argument("--output", type=Path, required=True)
    return root


def main() -> None:
    arguments = parser().parse_args()
    started = time.monotonic()
    try:
        from .session import active_session

        session = active_session()
        base_url = arguments.base_url or (session or {}).get("base_url")
        token = arguments.token or os.environ.get("DICOM_GUIDE_TOKEN") or (session or {}).get("token")
        if not base_url or not token:
            raise RuntimeError("no running DICOM Guide session was found")
        client = Client(base_url, token)
        if arguments.command == "state":
            print_json(client.json("/v1/viewer-control"))
            return
        if arguments.command == "series":
            print_json(series_summary(client.json("/v1/manifest")))
            return
        if arguments.command == "highlight":
            observation = ready_observation(client.json("/v1/viewer-control"))
            if arguments.highlight_command == "add":
                mark_id = arguments.mark_id or f"mark_{secrets.token_hex(10)}"
                if not MARK_ID.fullmatch(mark_id):
                    raise ValueError("mark ID is not a supported opaque ID")
                addition: dict[str, Any] = {"id": mark_id, "color": arguments.color}
                if arguments.image_point:
                    if observation["view_mode"] != "native":
                        raise ValueError("image-pixel highlights require the native Single view")
                    addition["points_image_px"] = arguments.image_point
                elif arguments.image_normalized:
                    if observation["view_mode"] != "native":
                        raise ValueError(
                            "normalized image highlights require the native Single view"
                        )
                    addition["points_image_normalized"] = arguments.image_normalized
                else:
                    if arguments.orientation is None:
                        raise ValueError("--orientation is required with --lps-point")
                    addition["orientation"] = arguments.orientation
                    addition["points_lps_mm"] = arguments.lps_point
                patch = {"add": [addition]}
            elif arguments.highlight_command == "remove":
                if any(not MARK_ID.fullmatch(mark_id) for mark_id in arguments.mark_id):
                    raise ValueError("mark ID is not a supported opaque ID")
                patch = {"remove_ids": arguments.mark_id}
            else:
                patch = {"clear_agent": True}
            command = command_for_observation(observation, tool="highlight", patch=patch)
            print_json(issue_and_wait(client, command, arguments.wait_seconds, started))
            return
        if not INSTANCE_ID.fullmatch(arguments.instance_id):
            raise ValueError("instance ID is not a supported opaque ID")
        if arguments.command == "metadata":
            payload, _ = exact_dicom(client, arguments.instance_id)
            print_json(metadata(payload, arguments.instance_id))
            return
        if arguments.command == "fetch-instance":
            payload, digest = exact_dicom(client, arguments.instance_id)
            owner_only_write(arguments.output, payload)
            print_json(
                {
                    "saved": True,
                    "bytes": len(payload),
                    "sha256": digest,
                    "local_only": True,
                }
            )
            return
        if not SERIES_ID.fullmatch(arguments.series_id):
            raise ValueError("series ID is not a supported opaque ID")
        tool = arguments.tool or ("crosshairs" if arguments.view == "mpr" else "window")
        if arguments.view == "native" and tool == "crosshairs":
            raise ValueError("crosshairs are available only in MPR")
        command_id = f"control_{secrets.token_hex(16)}"
        command = {
            "schema_version": "1.0.0",
            "command_id": command_id,
            "view_mode": arguments.view,
            "series_id": arguments.series_id,
            "instance_id": arguments.instance_id,
            "tool": tool,
            "patient_point_lps_mm": arguments.lps,
            "reset_view": arguments.reset,
        }
        print_json(issue_and_wait(client, command, arguments.wait_seconds, started))
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"dicom-guide: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
