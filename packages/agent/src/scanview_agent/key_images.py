from __future__ import annotations

import hashlib
import json
import math
import re
import struct
import zipfile
import zlib
from datetime import datetime
from pathlib import Path
from typing import Any, BinaryIO

from .measurements import validate_measurement_packet


OPAQUE_ID = re.compile(r"^[0-9a-f]{16}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
ORIENTATION = re.compile(r"^[RLAPHF]{1,3}$")
EXPECTED_ARCHIVE_FILES = {"key-image.json", "key-image.png", "measurements.json"}
MAX_ARCHIVE_MEMBER_BYTES = 64 * 1024 * 1024


def _has_only_keys(value: dict[str, Any], allowed: set[str]) -> bool:
    return not (set(value) - allowed)


def _valid_opaque_id(value: Any, kind: str) -> bool:
    return isinstance(value, str) and bool(
        OPAQUE_ID.fullmatch(value)
        or re.fullmatch(rf"{re.escape(kind)}_[0-9a-f]{{20}}", value)
    )


def _finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _positive_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _valid_datetime(value: Any) -> bool:
    if not isinstance(value, str) or "T" not in value:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def validate_key_image_packet(packet: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(packet, dict):
        return ["key-image packet must be a JSON object"]
    if not _has_only_keys(
        packet,
        {
            "schema_version",
            "created_at",
            "review_status",
            "artifact_type",
            "source",
            "display",
            "image",
            "measurement_evidence",
            "implementation",
            "limitations",
        },
    ):
        errors.append("key-image packet contains unsupported fields")
    schema_version = packet.get("schema_version")
    if schema_version not in {"1.0.0", "2.0.0"}:
        errors.append("schema_version must be 1.0.0 or 2.0.0")
    if not _valid_datetime(packet.get("created_at")):
        errors.append("created_at must be an ISO 8601 date-time")
    if packet.get("review_status") != "unreviewed":
        errors.append("review_status must be unreviewed")
    if packet.get("artifact_type") != "derived_display_key_image":
        errors.append("artifact_type must be derived_display_key_image")

    source = packet.get("source")
    if not isinstance(source, dict):
        errors.append("source must be an object")
    else:
        if not _has_only_keys(
            source,
            {
                "study_id",
                "series_id",
                "instance_id",
                "patient_context_id",
                "frame_of_reference_id",
                "modality",
                "acquisition_date",
                "series_description",
                "instance_number",
            },
        ):
            errors.append("source contains unsupported fields")
        study = source.get("study_id")
        patient_context = source.get("patient_context_id")
        if schema_version == "2.0.0":
            if not _valid_opaque_id(study, "study"):
                errors.append("source.study_id must be a supported opaque ID")
            if not _valid_opaque_id(patient_context, "patient"):
                errors.append("source.patient_context_id must be a supported opaque ID")
        elif study is not None or patient_context is not None:
            errors.append("key-image v1 source cannot contain v2 context fields")
        if not _valid_opaque_id(source.get("series_id"), "series"):
            errors.append("source.series_id must be a supported opaque ID")
        if not _valid_opaque_id(source.get("instance_id"), "instance"):
            errors.append("source.instance_id must be a supported opaque ID")
        frame = source.get("frame_of_reference_id")
        if frame is not None and not _valid_opaque_id(frame, "frame"):
            errors.append("source.frame_of_reference_id must be a supported opaque ID")
        if not isinstance(source.get("modality"), str) or not source["modality"]:
            errors.append("source.modality must be a non-empty string")
        acquisition_date = source.get("acquisition_date")
        if acquisition_date is not None and (
            not isinstance(acquisition_date, str)
            or not re.fullmatch(r"[0-9]{8}", acquisition_date)
        ):
            errors.append("source.acquisition_date must be an eight-digit DICOM date")
        if (
            not isinstance(source.get("series_description"), str)
            or not source["series_description"]
        ):
            errors.append("source.series_description must be a non-empty string")
        if not isinstance(source.get("instance_number"), int) or isinstance(
            source.get("instance_number"), bool
        ):
            errors.append("source.instance_number must be an integer")

    display = packet.get("display")
    if not isinstance(display, dict):
        errors.append("display must be an object")
    else:
        if not _has_only_keys(
            display,
            {
                "viewport_role",
                "stack_position",
                "stack_count",
                "source_kind",
                "viewport_width_px",
                "viewport_height_px",
                "patient_orientation",
                "presentation",
            },
        ):
            errors.append("display contains unsupported fields")
        if display.get("viewport_role") not in {"baseline", "followup"}:
            errors.append("display.viewport_role is invalid")
        if not _positive_integer(display.get("stack_position")):
            errors.append("display.stack_position must be a positive integer")
        if not _positive_integer(display.get("stack_count")):
            errors.append("display.stack_count must be a positive integer")
        if (
            _positive_integer(display.get("stack_position"))
            and _positive_integer(display.get("stack_count"))
            and display["stack_position"] > display["stack_count"]
        ):
            errors.append("display.stack_position exceeds stack_count")
        if display.get("source_kind") not in {"browser-folder", "loopback-service"}:
            errors.append("display.source_kind is invalid")
        for key in ("viewport_width_px", "viewport_height_px"):
            if not _positive_integer(display.get(key)):
                errors.append(f"display.{key} must be a positive integer")
        orientation = display.get("patient_orientation")
        if orientation is not None:
            if not isinstance(orientation, dict) or not _has_only_keys(
                orientation, {"left", "right", "top", "bottom"}
            ):
                errors.append("display.patient_orientation is invalid")
            elif not all(
                isinstance(orientation.get(key), str)
                and bool(ORIENTATION.fullmatch(orientation[key]))
                for key in ("left", "right", "top", "bottom")
            ):
                errors.append("display.patient_orientation labels are invalid")
        presentation = display.get("presentation")
        if not isinstance(presentation, dict) or not _has_only_keys(
            presentation, {"voi_range", "invert", "zoom", "pan"}
        ):
            errors.append("display.presentation is invalid")
        else:
            voi_range = presentation.get("voi_range")
            if voi_range is not None:
                if (
                    not isinstance(voi_range, dict)
                    or not _has_only_keys(voi_range, {"lower", "upper"})
                    or not _finite_number(voi_range.get("lower"))
                    or not _finite_number(voi_range.get("upper"))
                    or voi_range["upper"] <= voi_range["lower"]
                ):
                    errors.append("display.presentation.voi_range is invalid")
            invert = presentation.get("invert")
            if invert is not None and not isinstance(invert, bool):
                errors.append("display.presentation.invert must be boolean")
            zoom = presentation.get("zoom")
            if zoom is not None and (not _finite_number(zoom) or zoom <= 0):
                errors.append("display.presentation.zoom must be positive and finite")
            pan = presentation.get("pan")
            if pan is not None and (
                not isinstance(pan, list)
                or len(pan) != 2
                or not all(_finite_number(value) for value in pan)
            ):
                errors.append("display.presentation.pan must contain two finite numbers")

    image = packet.get("image")
    if not isinstance(image, dict) or not _has_only_keys(
        image, {"filename", "mime_type", "width_px", "height_px", "sha256"}
    ):
        errors.append("image must be a supported object")
    else:
        if image.get("filename") != "key-image.png":
            errors.append("image.filename must be key-image.png")
        if image.get("mime_type") != "image/png":
            errors.append("image.mime_type must be image/png")
        for key in ("width_px", "height_px"):
            if not _positive_integer(image.get(key)):
                errors.append(f"image.{key} must be a positive integer")
        if not isinstance(image.get("sha256"), str) or not SHA256.fullmatch(image["sha256"]):
            errors.append("image.sha256 must be a lowercase SHA-256 digest")

    measurements = packet.get("measurement_evidence")
    if not isinstance(measurements, dict) or not _has_only_keys(
        measurements,
        {"filename", "schema_version", "measurement_count", "tracking_ids", "sha256"},
    ):
        errors.append("measurement_evidence must be a supported object")
    else:
        if measurements.get("filename") != "measurements.json":
            errors.append("measurement_evidence.filename must be measurements.json")
        if measurements.get("schema_version") != "3.0.0":
            errors.append("measurement_evidence.schema_version must be 3.0.0")
        count = measurements.get("measurement_count")
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            errors.append("measurement_evidence.measurement_count must be non-negative")
        tracking_ids = measurements.get("tracking_ids")
        if not isinstance(tracking_ids, list) or not all(
            isinstance(value, str) and value for value in tracking_ids
        ):
            errors.append("measurement_evidence.tracking_ids must be a string array")
        elif len(tracking_ids) != len(set(tracking_ids)):
            errors.append("measurement_evidence.tracking_ids must be unique")
        elif isinstance(count, int) and count != len(tracking_ids):
            errors.append("measurement_evidence count disagrees with tracking_ids")
        if not isinstance(measurements.get("sha256"), str) or not SHA256.fullmatch(
            measurements["sha256"]
        ):
            errors.append("measurement_evidence.sha256 must be a lowercase SHA-256 digest")

    implementation = packet.get("implementation")
    if not isinstance(implementation, dict) or not _has_only_keys(
        implementation, {"name", "version", "renderer"}
    ):
        errors.append("implementation must be a supported object")
    else:
        expected_exporter_version = "0.2.0" if schema_version == "2.0.0" else "0.1.0"
        if (
            implementation.get("name") != "ScanView key-image exporter"
            or implementation.get("version") != expected_exporter_version
            or implementation.get("renderer") != "Cornerstone3D 5.8.2"
        ):
            errors.append("implementation is unsupported")

    limitations = packet.get("limitations")
    if not isinstance(limitations, list) or not limitations or not all(
        isinstance(value, str) and value for value in limitations
    ):
        errors.append("limitations must be a non-empty string array")
    return errors


def _png_dimensions(data: bytes) -> tuple[int, int] | None:
    if len(data) < 45 or data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    offset = 8
    dimensions: tuple[int, int] | None = None
    saw_idat = False
    saw_iend = False
    while offset + 12 <= len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        chunk_end = offset + 12 + length
        if chunk_end > len(data):
            return None
        chunk_type = data[offset + 4 : offset + 8]
        chunk_data = data[offset + 8 : offset + 8 + length]
        expected_crc = struct.unpack(">I", data[offset + 8 + length : chunk_end])[0]
        if zlib.crc32(chunk_type + chunk_data) & 0xFFFFFFFF != expected_crc:
            return None
        if offset == 8:
            if chunk_type != b"IHDR" or length != 13:
                return None
            width, height = struct.unpack(">II", chunk_data[:8])
            if width <= 0 or height <= 0:
                return None
            dimensions = (width, height)
        elif chunk_type == b"IDAT":
            saw_idat = True
        elif chunk_type == b"IEND":
            if length != 0 or chunk_end != len(data):
                return None
            saw_iend = True
            break
        offset = chunk_end
    return dimensions if dimensions and saw_idat and saw_iend else None


def key_image_archive_summary(path: Path | BinaryIO) -> dict[str, Any]:
    errors: list[str] = []
    packet: Any = None
    measurements: Any = None
    png_bytes = b""
    measurement_bytes = b""
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            names = {info.filename for info in infos}
            if names != EXPECTED_ARCHIVE_FILES or len(infos) != len(EXPECTED_ARCHIVE_FILES):
                errors.append("archive must contain exactly the three supported files")
            if any(info.flag_bits & 0x1 for info in infos):
                errors.append("encrypted archive members are unsupported")
            if any(info.file_size > MAX_ARCHIVE_MEMBER_BYTES for info in infos):
                errors.append("archive member exceeds the local safety limit")
            if not errors:
                packet_bytes = archive.read("key-image.json")
                png_bytes = archive.read("key-image.png")
                measurement_bytes = archive.read("measurements.json")
                packet = json.loads(packet_bytes)
                measurements = json.loads(measurement_bytes)
    except (OSError, zipfile.BadZipFile, KeyError, UnicodeDecodeError, json.JSONDecodeError) as error:
        errors.append(f"archive could not be read: {type(error).__name__}")

    packet_errors = validate_key_image_packet(packet) if packet is not None else []
    errors.extend(packet_errors)
    measurement_errors = (
        validate_measurement_packet(measurements) if measurements is not None else []
    )
    errors.extend(f"measurements.json: {error}" for error in measurement_errors)

    image_integrity = False
    measurement_integrity = False
    if isinstance(packet, dict):
        image = packet.get("image")
        if isinstance(image, dict) and png_bytes:
            dimensions = _png_dimensions(png_bytes)
            image_integrity = bool(
                dimensions
                and hashlib.sha256(png_bytes).hexdigest() == image.get("sha256")
                and dimensions == (image.get("width_px"), image.get("height_px"))
            )
            if not image_integrity:
                errors.append("key-image.png digest or dimensions disagree with key-image.json")
        evidence = packet.get("measurement_evidence")
        if isinstance(evidence, dict) and measurement_bytes:
            measurement_integrity = (
                hashlib.sha256(measurement_bytes).hexdigest() == evidence.get("sha256")
            )
            if not measurement_integrity:
                errors.append("measurements.json digest disagrees with key-image.json")

    if isinstance(packet, dict) and isinstance(measurements, dict):
        evidence = packet.get("measurement_evidence")
        records = measurements.get("measurements")
        if isinstance(evidence, dict) and isinstance(records, list):
            tracking_ids = [
                record.get("tracking_id") for record in records if isinstance(record, dict)
            ]
            if evidence.get("measurement_count") != len(records):
                errors.append("measurement count disagrees with measurements.json")
            if evidence.get("tracking_ids") != tracking_ids:
                errors.append("tracking IDs disagree with measurements.json")
            source = packet.get("source")
            if isinstance(source, dict) and any(
                not isinstance(record, dict)
                or not isinstance(record.get("source"), dict)
                or record["source"].get("series_id") != source.get("series_id")
                or record["source"].get("instance_id") != source.get("instance_id")
                for record in records
            ):
                errors.append("measurement source disagrees with the key-image source instance")

    measurement_count = 0
    if isinstance(packet, dict) and isinstance(packet.get("measurement_evidence"), dict):
        value = packet["measurement_evidence"].get("measurement_count")
        if isinstance(value, int) and not isinstance(value, bool):
            measurement_count = value
    return {
        "valid": not errors,
        "schema_version": packet.get("schema_version") if isinstance(packet, dict) else None,
        "review_status": packet.get("review_status") if isinstance(packet, dict) else None,
        "artifact_type": packet.get("artifact_type") if isinstance(packet, dict) else None,
        "measurement_count": measurement_count,
        "image_integrity": image_integrity,
        "measurement_integrity": measurement_integrity,
        "errors": errors,
    }
