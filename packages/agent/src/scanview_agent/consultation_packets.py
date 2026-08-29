from __future__ import annotations

import html
import hashlib
import io
import json
import os
import re
import stat
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .key_images import _png_dimensions, validate_key_image_packet
from .measurements import validate_measurement_packet
from .registration_reviews import _strict_json_loads
from .visit_packets import (
    ArchiveSource,
    KeyImageBundle,
    _digest,
    _json_bytes,
    _rewind,
    _valid_datetime,
)


SCHEMA_VERSION = "1.0.0"
ARTIFACT_TYPE = "clinician_consultation_packet"
IMPLEMENTATION = {
    "name": "ScanView clinician consultation-packet assembler",
    "version": "0.1.0",
}
CONSULTATION_KEY_IMAGE_IMPLEMENTATION = {
    "name": "ScanView consultation key-image normalizer",
    "version": "0.1.0",
    "renderer": "Cornerstone3D 5.8.2",
    "source_key_image_schema": "2.0.0",
}
CONSULTATION_KEY_IMAGE_LIMITATIONS = [
    "This PNG is an unreviewed derived display capture for source-image discussion only; original DICOM remains authoritative.",
    "The packet-local view slot does not establish chronology, lesion matching, diagnosis, or treatment response.",
    "Rendered pixels and burned-in text may identify the patient; this evidence is sensitive and not deidentified.",
]
VIEW_SLOTS = ("view_a", "view_b")
EXPECTED_FILES = {
    "consultation-packet.json",
    "review.html",
    "README.txt",
    "view-a/key-image.json",
    "view-a/key-image.png",
    "view-a/measurements.json",
    "view-b/key-image.json",
    "view-b/key-image.png",
    "view-b/measurements.json",
}
PAYLOAD_MEDIA_TYPES = {
    "review.html": "text/html",
    "README.txt": "text/plain",
    "view-a/key-image.json": "application/json",
    "view-a/key-image.png": "image/png",
    "view-a/measurements.json": "application/json",
    "view-b/key-image.json": "application/json",
    "view-b/key-image.png": "image/png",
    "view-b/measurements.json": "application/json",
}
CONSULTATION_PACKET_TRANSPORT_FILES = {"view-a.zip", "view-b.zip"}
MAX_ARCHIVE_MEMBER_BYTES = 64 * 1024 * 1024
MAX_ARCHIVE_TOTAL_BYTES = 128 * 1024 * 1024
MAX_CONSULTATION_PACKET_TRANSPORT_BYTES = 128 * 1024 * 1024
MAX_TRANSPORT_KEY_IMAGE_BYTES = 96 * 1024 * 1024
SHA256 = re.compile(r"^[0-9a-f]{64}$")

LIMITATIONS = [
    "The two images were explicitly selected as reference views only; no temporal, longitudinal, anatomical, or lesion relationship is asserted.",
    "MR and CT have different acquisition physics and intensity meaning and must not be compared as if their pixel values were equivalent.",
    "The images are not registered, spatially aligned, or guaranteed to show the same anatomy, lesion, or tumor component.",
    "Measurements are manual, source-linked, and unreviewed; they do not establish diagnosis, lesion identity, treatment response, or clinical significance.",
    "Original DICOM instances remain authoritative; all included PNG and JSON files are derived evidence and may retain identifying pixel content.",
]
MISSING_CONTEXT = [
    "Clinical confirmation of patient identity, diagnosis, pathology, treatment timeline, symptoms, medications, and operative history.",
    "Qualified identification of the anatomy, lesion, tumor component, and purpose represented by each selected view.",
    "The intended same-modality MRI sequence and timepoints for any future longitudinal response assessment.",
]
QUESTIONS_FOR_CLINICIAN = [
    "Are these the correct source exams, series, and images for this consultation?",
    "What anatomy or tumor-related feature is clinically relevant in each selected view?",
    "What different questions do the MRI and CT answer, and what should not be compared between them?",
    "Which MRI sequence and follow-up timepoint should be used for a future treatment-response comparison?",
    "What findings, uncertainties, and next-step questions should be recorded in the medical record?",
]


def _relationship(view_a: KeyImageBundle, view_b: KeyImageBundle) -> dict[str, Any]:
    first = view_a.packet
    second = view_b.packet
    first_source = first.get("source")
    second_source = second.get("source")
    if not isinstance(first_source, dict) or not isinstance(second_source, dict):
        raise ValueError("consultation packet key-image sources are invalid")
    first_context = first_source.get("patient_context_id")
    second_context = second_source.get("patient_context_id")
    if not isinstance(first_context, str) or not first_context or first_context != second_context:
        raise ValueError("consultation packets require one matching opaque patient context")
    first_modality = first_source.get("modality")
    second_modality = second_source.get("modality")
    if {first_modality, second_modality} != {"MR", "CT"}:
        raise ValueError("consultation packets require one MR and one CT reference view")
    if first_source.get("study_id") == second_source.get("study_id"):
        raise ValueError("consultation packets require two distinct source studies")
    if first_source.get("instance_id") == second_source.get("instance_id"):
        raise ValueError("consultation packets require two distinct source instances")
    return {
        "selection_method": "explicit_two_view_selection",
        "same_patient_context": True,
        "modalities": [first_modality, second_modality],
        "modality_relationship": "cross_modality",
        "distinct_source_studies": True,
        "same_source_instance": False,
        "temporal_relationship": "not_asserted",
        "registration_status": "not_registered",
        "spatial_relationship": "not_aligned",
        "longitudinal_comparison_authorized": False,
        "response_assessment_authorized": False,
    }


def _observation(
    slot: str,
    bundle: KeyImageBundle,
    source_anchor: dict[str, Any],
) -> dict[str, Any]:
    directory = slot.replace("_", "-")
    evidence = bundle.packet["measurement_evidence"]
    return {
        "slot": slot,
        "source": bundle.packet["source"],
        "source_anchor": source_anchor,
        "display": bundle.packet["display"],
        "key_image_path": f"{directory}/key-image.png",
        "key_image_sidecar_path": f"{directory}/key-image.json",
        "measurement_path": f"{directory}/measurements.json",
        "measurement_count": evidence["measurement_count"],
        "tracking_ids": evidence["tracking_ids"],
        "review_status": "unreviewed",
    }


def _catalog_source_anchor(
    catalog: dict[str, Any],
    registry: dict[str, Path],
    source: dict[str, Any],
    display: dict[str, Any],
) -> dict[str, Any]:
    matching_series: dict[str, Any] | None = None
    matching_instance: dict[str, Any] | None = None
    matching_instance_index: int | None = None
    for study in catalog.get("studies", []):
        if not isinstance(study, dict) or study.get("id") != source.get("study_id"):
            continue
        for series in study.get("series", []):
            if not isinstance(series, dict) or series.get("id") != source.get("series_id"):
                continue
            matching_series = series
            for index, instance in enumerate(series.get("instances", [])):
                if (
                    isinstance(instance, dict)
                    and instance.get("id") == source.get("instance_id")
                ):
                    matching_instance = instance
                    matching_instance_index = index
                    break
            break
    if matching_series is None or matching_instance is None:
        raise ValueError("consultation key image is not an exact member of the live catalog")
    expected_series_values = {
        "patient_context_id": source.get("patient_context_id"),
        "modality": source.get("modality"),
        "acquisition_date": source.get("acquisition_date"),
        "series_description": source.get("series_description"),
        "frame_of_reference_id": source.get("frame_of_reference_id"),
    }
    if any(
        matching_series.get(key) != value
        for key, value in expected_series_values.items()
    ) or matching_instance.get("instance_number") != source.get("instance_number"):
        raise ValueError("consultation key-image metadata disagrees with the live catalog")
    catalog_instances = matching_series.get("instances")
    if (
        not isinstance(catalog_instances, list)
        or matching_instance_index is None
        or display.get("stack_position") != matching_instance_index + 1
        or display.get("stack_count") != len(catalog_instances)
        or display.get("source_kind") != "loopback-service"
    ):
        raise ValueError("consultation key-image display position disagrees with the live catalog")
    expected_bytes = matching_instance.get("bytes")
    expected_sha256 = matching_instance.get("sha256")
    if (
        not isinstance(expected_bytes, int)
        or isinstance(expected_bytes, bool)
        or expected_bytes <= 0
        or not isinstance(expected_sha256, str)
        or not SHA256.fullmatch(expected_sha256)
    ):
        raise ValueError("consultation packet assembly requires a source-hashed catalog")
    path = registry.get(str(source.get("instance_id")))
    if path is None:
        raise ValueError("consultation key-image source is unavailable")
    descriptor = -1
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size != expected_bytes:
            raise ValueError("consultation key-image source changed after cataloging")
        digest = hashlib.sha256()
        total = 0
        while chunk := os.read(descriptor, 1024 * 1024):
            total += len(chunk)
            if total > expected_bytes:
                raise ValueError("consultation key-image source grew while it was read")
            digest.update(chunk)
        after = os.fstat(descriptor)
        before_identity = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        after_identity = (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        if (
            before_identity != after_identity
            or total != expected_bytes
            or digest.hexdigest() != expected_sha256
        ):
            raise ValueError("consultation key-image source integrity changed")
    except OSError as error:
        raise ValueError("consultation key-image source cannot be read safely") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    return {
        "catalog_match": True,
        "dicom_bytes": expected_bytes,
        "dicom_sha256": expected_sha256,
    }


def _format_date(value: Any) -> str:
    if isinstance(value, str) and re.fullmatch(r"[0-9]{8}", value):
        try:
            return datetime.strptime(value, "%Y%m%d").date().isoformat()
        except ValueError:
            pass
    return "Date unavailable"


def _render_review_html(packet: dict[str, Any]) -> bytes:
    observations = {item["slot"]: item for item in packet["observations"]}

    def card(slot: str, heading: str) -> str:
        observation = observations[slot]
        source = observation["source"]
        display = observation["display"]
        description = html.escape(str(source["series_description"]))
        modality = html.escape(str(source["modality"]))
        acquisition_date = html.escape(_format_date(source.get("acquisition_date")))
        image_path = html.escape(observation["key_image_path"], quote=True)
        anchor = observation["source_anchor"]
        anchor_sha256 = html.escape(str(anchor["dicom_sha256"]))
        anchor_bytes = html.escape(str(anchor["dicom_bytes"]))
        return f"""
        <article class="card">
          <header><span>{heading}</span><strong>{modality} · {acquisition_date}</strong></header>
          <img src="{image_path}" alt="{heading} unreviewed derived reference key image">
          <dl>
            <div><dt>Series</dt><dd>{description}</dd></div>
            <div><dt>Modality</dt><dd>{modality}</dd></div>
            <div><dt>Source slice</dt><dd>{display['stack_position']} / {display['stack_count']}</dd></div>
            <div><dt>Visible measurements</dt><dd>{observation['measurement_count']}</dd></div>
            <div><dt>Exact DICOM source</dt><dd>{anchor_bytes} bytes · SHA-256 <code>{anchor_sha256}</code></dd></div>
          </dl>
        </article>"""

    question_items = "".join(
        f"<li>{html.escape(question)}</li>" for question in packet["questions_for_clinician"]
    )
    first_modality, second_modality = packet["relationship"]["modalities"]
    modality_note = "The selected views use different modalities. MR and CT intensity values and appearance are not directly comparable."
    document = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="referrer" content="no-referrer">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'">
  <title>ScanView unreviewed clinician consultation packet</title>
  <style>
    :root {{ color-scheme: dark; font-family: Inter, system-ui, sans-serif; background: #07110f; color: #e7f3ef; }}
    * {{ box-sizing: border-box; }} body {{ margin: 0; padding: 24px; }} main {{ max-width: 1500px; margin: auto; }}
    h1 {{ margin: 0 0 8px; font-size: 25px; }}
    .banner {{ border: 1px solid #e8b35c; background: #291d09; color: #ffe4ac; padding: 12px 14px; margin: 16px 0; font-weight: 700; }}
    .context {{ color: #afc2bc; margin-bottom: 18px; }}
    .grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }}
    .card {{ border: 1px solid #29433c; background: #0b1916; padding: 12px; min-width: 0; }}
    .card header {{ display: flex; justify-content: space-between; gap: 12px; margin-bottom: 10px; color: #7de9ca; }}
    img {{ display: block; width: 100%; height: auto; background: #000; border: 1px solid #213a34; }}
    dl {{ margin: 10px 0 0; }} dl div {{ display: grid; grid-template-columns: 150px 1fr; gap: 8px; border-top: 1px solid #1c312c; padding: 6px 0; }}
    dt {{ color: #93aaa3; }} dd {{ margin: 0; overflow-wrap: anywhere; }} section {{ margin-top: 22px; }}
    .checklist {{ list-style: none; padding: 0; }} .checklist li {{ margin: 10px 0; }}
    .notes {{ min-height: 110px; border: 1px solid #29433c; background: repeating-linear-gradient(#0b1916 0 27px, #29433c 28px); }}
    footer {{ margin-top: 24px; color: #93aaa3; font-size: 12px; }}
    @media (max-width: 850px) {{ .grid {{ grid-template-columns: 1fr; }} }}
    @media print {{ :root {{ color-scheme: light; background: white; color: black; }} body {{ padding: 8mm; }} .card, .notes {{ background: white; border-color: #777; }} .banner {{ color: black; background: #fff4d7; }} .context, dt, footer {{ color: #444; }} }}
  </style>
</head>
<body><main>
  <h1>ScanView clinician consultation packet</h1>
  <div class="banner">REFERENCE VIEWS ONLY · NOT A COMPARISON · UNREVIEWED · NOT FOR DIAGNOSIS · NO RESPONSE CONCLUSION</div>
  <p class="context">Explicitly selected {html.escape(str(first_modality))} and {html.escape(str(second_modality))} views. Dates identify sources only; no chronological role is assigned. Images are not registered or spatially aligned. {html.escape(modality_note)}</p>
  <div class="grid">{card('view_a', 'SELECTED VIEW A')}{card('view_b', 'SELECTED VIEW B')}</div>
  <section><h2>Questions for the clinical team</h2><ul>{question_items}</ul></section>
  <section><h2>Review checklist</h2><ul class="checklist"><li>□ Correct patient and source exams confirmed in the clinical system</li><li>□ Relevant anatomy or tumor feature identified for each view</li><li>□ Modality differences and non-comparable features explained</li><li>□ Future same-modality MRI sequence and timepoint identified</li><li>□ Clinical interpretation recorded in the medical record</li></ul></section>
  <section><h2>Clinician notes</h2><div class="notes" aria-label="Blank area for clinician notes"></div></section>
  <footer>Original DICOM instances remain authoritative. Validate this archive locally with scanview-agent before use. This packet contains sensitive medical imagery and may contain identifying pixels.</footer>
</main></body></html>\n"""
    return document.encode()


def _render_readme() -> bytes:
    return (
        "ScanView clinician consultation packet\n"
        "\n"
        "1. Extract the entire ZIP into one local folder.\n"
        "2. Open review.html in a browser, or print it for a clinical conversation.\n"
        "3. Keep every file together so integrity validation can succeed.\n"
        "4. Validate locally: scanview-agent validate-consultation-packet <archive.zip>\n"
        "\n"
        "REFERENCE VIEWS ONLY. NOT A COMPARISON. UNREVIEWED. NOT FOR DIAGNOSIS.\n"
        "No temporal relationship, registration, lesion matching, response category, or treatment conclusion is provided.\n"
        "MRI and CT intensity values are not directly comparable. Original DICOM files remain authoritative.\n"
        "Treat this archive as sensitive medical data; rendered pixels may identify the patient.\n"
    ).encode()


def _payloads(view_a: KeyImageBundle, view_b: KeyImageBundle) -> dict[str, bytes]:
    return {
        "view-a/key-image.json": view_a.packet_bytes,
        "view-a/key-image.png": view_a.png_bytes,
        "view-a/measurements.json": view_a.measurement_bytes,
        "view-b/key-image.json": view_b.packet_bytes,
        "view-b/key-image.png": view_b.png_bytes,
        "view-b/measurements.json": view_b.measurement_bytes,
    }


def _file_manifest(payloads: dict[str, bytes]) -> dict[str, dict[str, Any]]:
    return {
        path: {
            "media_type": PAYLOAD_MEDIA_TYPES[path],
            "byte_count": len(content),
            "sha256": _digest(content),
        }
        for path, content in sorted(payloads.items())
    }


def _read_consultation_key_image(
    source: ArchiveSource,
    slot: str,
) -> KeyImageBundle:
    _rewind(source)
    try:
        with zipfile.ZipFile(source) as archive:
            infos = archive.infolist()
            names = {info.filename for info in infos}
            if names != {"key-image.json", "key-image.png", "measurements.json"} or len(
                infos
            ) != 3:
                raise ValueError(
                    "consultation key image must contain exactly the three supported files"
                )
            if any(info.flag_bits & 0x1 for info in infos):
                raise ValueError("encrypted consultation key-image members are unsupported")
            if any(info.file_size > MAX_ARCHIVE_MEMBER_BYTES for info in infos):
                raise ValueError("consultation key-image member exceeds the local safety limit")
            if sum(info.file_size for info in infos) > MAX_ARCHIVE_TOTAL_BYTES:
                raise ValueError("consultation key-image content exceeds the local safety limit")
            packet_bytes = archive.read("key-image.json")
            png_bytes = archive.read("key-image.png")
            measurement_bytes = archive.read("measurements.json")
    except (OSError, zipfile.BadZipFile, KeyError) as error:
        raise ValueError(
            f"consultation key image could not be read: {type(error).__name__}"
        ) from error
    packet, errors = _consultation_component(
        packet_bytes,
        png_bytes,
        measurement_bytes,
        slot,
    )
    if packet is None or errors:
        raise ValueError(f"{slot} consultation key image is invalid: {'; '.join(errors)}")
    return KeyImageBundle(packet, packet_bytes, png_bytes, measurement_bytes)


def build_consultation_packet(
    view_a_path: ArchiveSource,
    view_b_path: ArchiveSource,
    catalog: dict[str, Any],
    registry: dict[str, Path],
    *,
    created_at: str | None = None,
) -> tuple[dict[str, Any], dict[str, bytes]]:
    view_a = _read_consultation_key_image(view_a_path, "view_a")
    view_b = _read_consultation_key_image(view_b_path, "view_b")
    relationship = _relationship(view_a, view_b)
    view_a_anchor = _catalog_source_anchor(
        catalog,
        registry,
        view_a.packet["source"],
        view_a.packet["display"],
    )
    view_b_anchor = _catalog_source_anchor(
        catalog,
        registry,
        view_b.packet["source"],
        view_b.packet["display"],
    )
    created = created_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    if not _valid_datetime(created):
        raise ValueError("created_at must be an ISO 8601 date-time")
    packet: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "created_at": created,
        "review_status": "unreviewed",
        "artifact_type": ARTIFACT_TYPE,
        "purpose": "two_source_views_for_clinician_discussion_only",
        "relationship": relationship,
        "observations": [
            _observation("view_a", view_a, view_a_anchor),
            _observation("view_b", view_b, view_b_anchor),
        ],
        "computed_results": [],
        "candidate_interpretations": [],
        "limitations": list(LIMITATIONS),
        "missing_context": list(MISSING_CONTEXT),
        "questions_for_clinician": list(QUESTIONS_FOR_CLINICIAN),
        "implementation": dict(IMPLEMENTATION),
        "files": {},
    }
    payloads = _payloads(view_a, view_b)
    payloads["review.html"] = _render_review_html(packet)
    payloads["README.txt"] = _render_readme()
    packet["files"] = _file_manifest(payloads)
    return packet, payloads


def consultation_packet_archive_bytes(
    view_a_path: ArchiveSource,
    view_b_path: ArchiveSource,
    catalog: dict[str, Any],
    registry: dict[str, Path],
    *,
    created_at: str | None = None,
) -> bytes:
    packet, payloads = build_consultation_packet(
        view_a_path,
        view_b_path,
        catalog,
        registry,
        created_at=created_at,
    )
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.writestr("consultation-packet.json", _json_bytes(packet))
        for path, content in sorted(payloads.items()):
            archive.writestr(path, content)
    return output.getvalue()


def consultation_packet_from_transport(
    transport_bytes: bytes,
    catalog: dict[str, Any],
    registry: dict[str, Path],
    *,
    created_at: str | None = None,
) -> bytes:
    if (
        not transport_bytes
        or len(transport_bytes) > MAX_CONSULTATION_PACKET_TRANSPORT_BYTES
    ):
        raise ValueError("consultation-packet request exceeds the local safety limit")
    try:
        with zipfile.ZipFile(io.BytesIO(transport_bytes)) as archive:
            infos = archive.infolist()
            names = {info.filename for info in infos}
            if names != CONSULTATION_PACKET_TRANSPORT_FILES or len(infos) != 2:
                raise ValueError(
                    "consultation-packet request must contain exactly view-a.zip and view-b.zip"
                )
            if any(info.flag_bits & 0x1 for info in infos):
                raise ValueError("encrypted consultation-packet request members are unsupported")
            if any(info.file_size > MAX_TRANSPORT_KEY_IMAGE_BYTES for info in infos) or sum(
                info.file_size for info in infos
            ) > MAX_CONSULTATION_PACKET_TRANSPORT_BYTES:
                raise ValueError(
                    "consultation-packet request member exceeds the local safety limit"
                )
            view_a_bytes = archive.read("view-a.zip")
            view_b_bytes = archive.read("view-b.zip")
    except (OSError, zipfile.BadZipFile, KeyError) as error:
        raise ValueError(
            f"consultation-packet request could not be read: {type(error).__name__}"
        ) from error
    return consultation_packet_archive_bytes(
        io.BytesIO(view_a_bytes),
        io.BytesIO(view_b_bytes),
        catalog,
        registry,
        created_at=created_at,
    )


def _write_new_owner_only(output: Path, payload: bytes) -> None:
    requested = output.expanduser()
    requested.parent.mkdir(parents=True, exist_ok=True)
    parent = requested.parent.resolve(strict=True)
    destination = parent / requested.name
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, destination, follow_symlinks=False)
        temporary.unlink()
        parent_descriptor = os.open(parent, os.O_RDONLY)
        try:
            os.fsync(parent_descriptor)
        finally:
            os.close(parent_descriptor)
    finally:
        temporary.unlink(missing_ok=True)


def write_consultation_packet(
    dicom_root: Path,
    view_a_path: Path,
    view_b_path: Path,
    output: Path,
    *,
    created_at: str | None = None,
) -> dict[str, Any]:
    from .catalog import build_catalog

    catalog, registry = build_catalog(dicom_root, include_hashes=True)
    archive_bytes = consultation_packet_archive_bytes(
        view_a_path,
        view_b_path,
        catalog,
        registry,
        created_at=created_at,
    )
    _write_new_owner_only(output, archive_bytes)
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        value = _strict_json_loads(archive.read("consultation-packet.json"))
    assert isinstance(value, dict)
    return value


def _validate_packet_shape(packet: Any) -> list[str]:
    errors: list[str] = []
    required = {
        "schema_version",
        "created_at",
        "review_status",
        "artifact_type",
        "purpose",
        "relationship",
        "observations",
        "computed_results",
        "candidate_interpretations",
        "limitations",
        "missing_context",
        "questions_for_clinician",
        "implementation",
        "files",
    }
    if not isinstance(packet, dict):
        return ["consultation packet must be a JSON object"]
    if set(packet) != required:
        errors.append("consultation packet fields are incomplete or unsupported")
    if packet.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if not _valid_datetime(packet.get("created_at")):
        errors.append("created_at must be an ISO 8601 date-time")
    if packet.get("review_status") != "unreviewed":
        errors.append("review_status must be unreviewed")
    if packet.get("artifact_type") != ARTIFACT_TYPE:
        errors.append(f"artifact_type must be {ARTIFACT_TYPE}")
    if packet.get("purpose") != "two_source_views_for_clinician_discussion_only":
        errors.append("purpose is invalid")

    relationship = packet.get("relationship")
    relationship_keys = {
        "selection_method",
        "same_patient_context",
        "modalities",
        "modality_relationship",
        "distinct_source_studies",
        "same_source_instance",
        "temporal_relationship",
        "registration_status",
        "spatial_relationship",
        "longitudinal_comparison_authorized",
        "response_assessment_authorized",
    }
    if not isinstance(relationship, dict) or set(relationship) != relationship_keys:
        errors.append("relationship is invalid")
    else:
        modalities = relationship.get("modalities")
        if relationship.get("selection_method") != "explicit_two_view_selection":
            errors.append("relationship selection method is invalid")
        if relationship.get("same_patient_context") is not True:
            errors.append("relationship must use one matching patient context")
        if relationship.get("distinct_source_studies") is not True:
            errors.append("relationship must use two distinct source studies")
        if (
            not isinstance(modalities, list)
            or len(modalities) != 2
            or not all(isinstance(value, str) for value in modalities)
            or modalities[0] not in {"MR", "CT"}
            or modalities[1] not in {"MR", "CT"}
            or modalities[0] == modalities[1]
        ):
            errors.append("relationship modalities are invalid")
        if relationship.get("modality_relationship") != "cross_modality":
            errors.append("relationship modality classification is invalid")
        if relationship.get("same_source_instance") is not False:
            errors.append("relationship must use distinct source instances")
        expected_constants = {
            "temporal_relationship": "not_asserted",
            "registration_status": "not_registered",
            "spatial_relationship": "not_aligned",
            "longitudinal_comparison_authorized": False,
            "response_assessment_authorized": False,
        }
        if any(relationship.get(key) != value for key, value in expected_constants.items()):
            errors.append("relationship safety gates are invalid")

    observations = packet.get("observations")
    observation_keys = {
        "slot",
        "source",
        "source_anchor",
        "display",
        "key_image_path",
        "key_image_sidecar_path",
        "measurement_path",
        "measurement_count",
        "tracking_ids",
        "review_status",
    }
    if not isinstance(observations, list) or len(observations) != 2:
        errors.append("observations must contain exactly view A and view B")
    else:
        for index, slot in enumerate(VIEW_SLOTS):
            observation = observations[index]
            directory = slot.replace("_", "-")
            if not isinstance(observation, dict) or set(observation) != observation_keys:
                errors.append(f"{slot} observation is invalid")
                continue
            if observation.get("slot") != slot:
                errors.append(f"{slot} observation has the wrong slot")
            if not isinstance(observation.get("source"), dict) or not isinstance(
                observation.get("display"), dict
            ):
                errors.append(f"{slot} observation source/display is invalid")
            source_anchor = observation.get("source_anchor")
            if (
                not isinstance(source_anchor, dict)
                or set(source_anchor) != {"catalog_match", "dicom_bytes", "dicom_sha256"}
                or source_anchor.get("catalog_match") is not True
                or not isinstance(source_anchor.get("dicom_bytes"), int)
                or isinstance(source_anchor.get("dicom_bytes"), bool)
                or source_anchor["dicom_bytes"] <= 0
                or not isinstance(source_anchor.get("dicom_sha256"), str)
                or not SHA256.fullmatch(source_anchor["dicom_sha256"])
            ):
                errors.append(f"{slot} source anchor is invalid")
            expected_paths = {
                "key_image_path": f"{directory}/key-image.png",
                "key_image_sidecar_path": f"{directory}/key-image.json",
                "measurement_path": f"{directory}/measurements.json",
            }
            if any(observation.get(key) != value for key, value in expected_paths.items()):
                errors.append(f"{slot} observation paths are invalid")
            count = observation.get("measurement_count")
            tracking_ids = observation.get("tracking_ids")
            if not isinstance(count, int) or isinstance(count, bool) or count < 0:
                errors.append(f"{slot} measurement_count is invalid")
            if not isinstance(tracking_ids, list) or not all(
                isinstance(value, str) and value for value in tracking_ids
            ) or len(tracking_ids) != len(set(tracking_ids)):
                errors.append(f"{slot} tracking_ids are invalid")
            elif isinstance(count, int) and count != len(tracking_ids):
                errors.append(f"{slot} measurement count disagrees with tracking_ids")
            if observation.get("review_status") != "unreviewed":
                errors.append(f"{slot} review_status must be unreviewed")

    for key in ("computed_results", "candidate_interpretations"):
        if packet.get(key) != []:
            errors.append(f"{key} must remain empty")
    fixed_arrays = {
        "limitations": LIMITATIONS,
        "missing_context": MISSING_CONTEXT,
        "questions_for_clinician": QUESTIONS_FOR_CLINICIAN,
    }
    if any(packet.get(key) != value for key, value in fixed_arrays.items()):
        errors.append("consultation packet safety text is incomplete or altered")
    if packet.get("implementation") != IMPLEMENTATION:
        errors.append("implementation is unsupported")

    files = packet.get("files")
    if not isinstance(files, dict) or set(files) != set(PAYLOAD_MEDIA_TYPES):
        errors.append("files manifest is incomplete or unsupported")
    else:
        for path, media_type in PAYLOAD_MEDIA_TYPES.items():
            value = files.get(path)
            if not isinstance(value, dict) or set(value) != {
                "media_type",
                "byte_count",
                "sha256",
            }:
                errors.append(f"files entry is invalid: {path}")
                continue
            if value.get("media_type") != media_type:
                errors.append(f"files media type is invalid: {path}")
            byte_count = value.get("byte_count")
            if not isinstance(byte_count, int) or isinstance(byte_count, bool) or byte_count <= 0:
                errors.append(f"files byte count is invalid: {path}")
            digest = value.get("sha256")
            if not isinstance(digest, str) or not SHA256.fullmatch(digest):
                errors.append(f"files digest is invalid: {path}")
    return errors


def _consultation_component(
    packet_bytes: bytes,
    png_bytes: bytes,
    measurement_bytes: bytes,
    slot: str,
) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    packet: Any = None
    measurements: Any = None
    try:
        packet = _strict_json_loads(packet_bytes)
        measurements = _strict_json_loads(measurement_bytes)
    except ValueError as error:
        return None, [f"component JSON is invalid: {error}"]
    required = {
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
    }
    if not isinstance(packet, dict) or set(packet) != required:
        return None, ["consultation key-image sidecar has unsupported fields"]
    display = packet.get("display")
    if not isinstance(display, dict) or display.get("selection_slot") != slot:
        errors.append("consultation key-image slot is invalid")
    if packet.get("schema_version") != "1.0.0":
        errors.append("consultation key-image schema_version is invalid")
    if packet.get("review_status") != "unreviewed":
        errors.append("consultation key-image review_status is invalid")
    if packet.get("artifact_type") != "derived_display_consultation_key_image":
        errors.append("consultation key-image artifact_type is invalid")
    if packet.get("implementation") != CONSULTATION_KEY_IMAGE_IMPLEMENTATION:
        errors.append("consultation key-image implementation is unsupported")
    if packet.get("limitations") != CONSULTATION_KEY_IMAGE_LIMITATIONS:
        errors.append("consultation key-image limitations are incomplete or altered")

    synthetic_display = dict(display) if isinstance(display, dict) else {}
    synthetic_display.pop("selection_slot", None)
    synthetic_display["viewport_role"] = "baseline" if slot == "view_a" else "followup"
    synthetic_packet = {
        "schema_version": "2.0.0",
        "created_at": packet.get("created_at"),
        "review_status": packet.get("review_status"),
        "artifact_type": "derived_display_key_image",
        "source": packet.get("source"),
        "display": synthetic_display,
        "image": packet.get("image"),
        "measurement_evidence": packet.get("measurement_evidence"),
        "implementation": {
            "name": "ScanView key-image exporter",
            "version": "0.2.0",
            "renderer": "Cornerstone3D 5.8.2",
        },
        "limitations": packet.get("limitations"),
    }
    errors.extend(validate_key_image_packet(synthetic_packet))
    measurement_errors = validate_measurement_packet(measurements)
    errors.extend(f"measurements.json: {error}" for error in measurement_errors)

    image = packet.get("image")
    if isinstance(image, dict):
        dimensions = _png_dimensions(png_bytes)
        if not (
            dimensions
            and hashlib.sha256(png_bytes).hexdigest() == image.get("sha256")
            and dimensions == (image.get("width_px"), image.get("height_px"))
        ):
            errors.append("key-image.png digest or dimensions disagree with the sidecar")
    evidence = packet.get("measurement_evidence")
    if isinstance(evidence, dict):
        if hashlib.sha256(measurement_bytes).hexdigest() != evidence.get("sha256"):
            errors.append("measurements.json digest disagrees with the sidecar")
        if isinstance(measurements, dict):
            records = measurements.get("measurements")
            if isinstance(records, list):
                tracking_ids = [
                    record.get("tracking_id")
                    for record in records
                    if isinstance(record, dict)
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
                    errors.append(
                        "measurement source disagrees with the consultation key-image source instance"
                    )
    return packet, errors


def consultation_packet_summary(path: ArchiveSource) -> dict[str, Any]:
    errors: list[str] = []
    packet: Any = None
    payloads: dict[str, bytes] = {}
    try:
        _rewind(path)
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            names = {info.filename for info in infos}
            if names != EXPECTED_FILES or len(infos) != len(EXPECTED_FILES):
                errors.append("archive must contain exactly the nine supported files")
            if any(info.flag_bits & 0x1 for info in infos):
                errors.append("encrypted archive members are unsupported")
            if any(info.file_size > MAX_ARCHIVE_MEMBER_BYTES for info in infos) or sum(
                info.file_size for info in infos
            ) > MAX_ARCHIVE_TOTAL_BYTES:
                errors.append("archive content exceeds the local safety limit")
            if not errors:
                packet = _strict_json_loads(archive.read("consultation-packet.json"))
                payloads = {name: archive.read(name) for name in PAYLOAD_MEDIA_TYPES}
    except (OSError, zipfile.BadZipFile, KeyError, ValueError) as error:
        errors.append(f"archive could not be read: {type(error).__name__}")

    errors.extend(_validate_packet_shape(packet) if packet is not None else [])
    file_integrity = False
    component_integrity = False
    presentation_integrity = False
    if isinstance(packet, dict) and payloads:
        files = packet.get("files")
        if isinstance(files, dict):
            file_integrity = all(
                isinstance(files.get(name), dict)
                and files[name].get("byte_count") == len(content)
                and files[name].get("sha256") == _digest(content)
                for name, content in payloads.items()
            )
            if not file_integrity:
                errors.append("one or more payload digests or byte counts disagree")

        component_packets: dict[str, dict[str, Any]] = {}
        component_integrity = True
        observations = packet.get("observations")
        for slot in VIEW_SLOTS:
            directory = slot.replace("_", "-")
            component, component_errors = _consultation_component(
                payloads[f"{directory}/key-image.json"],
                payloads[f"{directory}/key-image.png"],
                payloads[f"{directory}/measurements.json"],
                slot,
            )
            if component_errors:
                component_integrity = False
                errors.extend(
                    f"{slot} key image: {message}" for message in component_errors
                )
            if isinstance(component, dict):
                component_packets[slot] = component

        if isinstance(observations, list) and len(observations) == 2:
            for index, slot in enumerate(VIEW_SLOTS):
                directory = slot.replace("_", "-")
                component = component_packets.get(slot)
                observation = observations[index]
                if not isinstance(component, dict) or not isinstance(observation, dict):
                    component_integrity = False
                    continue
                expected = _observation(
                    slot,
                    KeyImageBundle(
                        component,
                        payloads[f"{directory}/key-image.json"],
                        payloads[f"{directory}/key-image.png"],
                        payloads[f"{directory}/measurements.json"],
                    ),
                    observation.get("source_anchor", {}),
                )
                if observation != expected:
                    component_integrity = False
            if not component_integrity:
                errors.append(
                    "consultation observations disagree with embedded key-image evidence"
                )

        if len(component_packets) == 2:
            try:
                expected_relationship = _relationship(
                    KeyImageBundle(component_packets["view_a"], b"", b"", b""),
                    KeyImageBundle(component_packets["view_b"], b"", b"", b""),
                )
                if packet.get("relationship") != expected_relationship:
                    errors.append(
                        "relationship metadata disagrees with embedded key images"
                    )
                    component_integrity = False
            except (KeyError, TypeError, ValueError) as error:
                errors.append(f"embedded key images are not a valid consultation set: {error}")
                component_integrity = False

        try:
            presentation_integrity = (
                payloads["review.html"] == _render_review_html(packet)
                and payloads["README.txt"] == _render_readme()
            )
        except (KeyError, TypeError, IndexError):
            presentation_integrity = False
        if not presentation_integrity:
            errors.append("review presentation does not match the local static template")

    relationship = packet.get("relationship") if isinstance(packet, dict) else None
    observations = packet.get("observations") if isinstance(packet, dict) else None
    measurement_counts = {"view_a": 0, "view_b": 0}
    if isinstance(observations, list) and len(observations) == 2:
        for observation in observations:
            if isinstance(observation, dict) and observation.get("slot") in measurement_counts:
                count = observation.get("measurement_count")
                if isinstance(count, int) and not isinstance(count, bool):
                    measurement_counts[observation["slot"]] = count
    return {
        "valid": not errors,
        "schema_version": packet.get("schema_version") if isinstance(packet, dict) else None,
        "review_status": packet.get("review_status") if isinstance(packet, dict) else None,
        "artifact_type": packet.get("artifact_type") if isinstance(packet, dict) else None,
        "modality_relationship": (
            relationship.get("modality_relationship")
            if isinstance(relationship, dict)
            else None
        ),
        "measurement_counts": measurement_counts,
        "file_integrity": file_integrity,
        "component_integrity": component_integrity,
        "presentation_integrity": presentation_integrity,
        "longitudinal_comparison_authorized": False,
        "response_assessment_authorized": False,
        "errors": errors,
    }
