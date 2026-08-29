from __future__ import annotations

import html
import io
import json
import os
import re
import stat
import unicodedata
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .consultation_packets import (
    MAX_ARCHIVE_MEMBER_BYTES,
    MAX_ARCHIVE_TOTAL_BYTES,
    _catalog_source_anchor,
    _consultation_component,
    _write_new_owner_only,
)
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
ARTIFACT_TYPE = "clinician_consultation_board"
INPUT_ARTIFACT_TYPE = "consultation_board_input"
IMPLEMENTATION = {
    "name": "ScanView clinician consultation-board assembler",
    "version": "0.1.0",
}
MIN_ITEMS = 2
MAX_ITEMS = 8
MAX_LABEL_CHARACTERS = 80
MAX_BOARD_ARCHIVE_BYTES = 512 * 1024 * 1024
MAX_BOARD_TRANSPORT_BYTES = 512 * 1024 * 1024
MAX_INPUT_MANIFEST_BYTES = 16 * 1024
MAX_TRANSPORT_KEY_IMAGE_BYTES = 96 * 1024 * 1024
ITEM_ID = re.compile(r"^item_[0-9]{2}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")

LIMITATIONS = [
    "The selected images are unreviewed reference views only; their order and discussion labels do not establish chronology, anatomy, lesion identity, diagnosis, or treatment response.",
    "MR and CT have different acquisition physics and intensity meaning and must not be compared as if their pixel values were equivalent.",
    "The images are not registered, spatially aligned, or guaranteed to show the same anatomy, lesion, or tumor component.",
    "Discussion labels are person-entered headings and have not been clinically authenticated or interpreted by ScanView.",
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
    "What anatomy or tumor-related feature, if any, is clinically relevant in each labeled view?",
    "Which labels should be corrected before this material is used for discussion?",
    "What different questions do the MRI and CT answer, and what should not be compared between them?",
    "Which MRI sequence and follow-up timepoint should be used for a future treatment-response comparison?",
    "What findings, uncertainties, and next-step questions should be recorded in the medical record?",
]


def _item_id(index: int) -> str:
    return f"item_{index + 1:02d}"


def _item_directory(item_id: str) -> str:
    return f"items/{item_id.replace('_', '-')}"


def _label_error(value: Any) -> str | None:
    if not isinstance(value, str):
        return "discussion label must be a string"
    if value != value.strip() or not value or len(value) > MAX_LABEL_CHARACTERS:
        return (
            "discussion label must be trimmed and contain 1 to "
            f"{MAX_LABEL_CHARACTERS} characters"
        )
    if any(unicodedata.category(character).startswith("C") for character in value):
        return "discussion label contains unsupported control characters"
    return None


def _zip_member_is_link(info: zipfile.ZipInfo) -> bool:
    return stat.S_ISLNK((info.external_attr >> 16) & 0xFFFF)


def _valid_source_anchor(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == {"catalog_match", "dicom_bytes", "dicom_sha256"}
        and value.get("catalog_match") is True
        and isinstance(value.get("dicom_bytes"), int)
        and not isinstance(value.get("dicom_bytes"), bool)
        and value["dicom_bytes"] > 0
        and isinstance(value.get("dicom_sha256"), str)
        and bool(SHA256.fullmatch(value["dicom_sha256"]))
    )


def _read_board_key_image(
    source: ArchiveSource,
    *,
    remaining_board_bytes: int = MAX_BOARD_ARCHIVE_BYTES,
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
                    "board key image must contain exactly the three supported files"
                )
            if any(info.flag_bits & 0x1 for info in infos):
                raise ValueError("encrypted board key-image members are unsupported")
            if any(_zip_member_is_link(info) for info in infos):
                raise ValueError("linked board key-image members are unsupported")
            if any(info.file_size > MAX_ARCHIVE_MEMBER_BYTES for info in infos):
                raise ValueError("board key-image member exceeds the local safety limit")
            content_bytes = sum(info.file_size for info in infos)
            if content_bytes > MAX_ARCHIVE_TOTAL_BYTES:
                raise ValueError("board key-image content exceeds the local safety limit")
            if content_bytes > remaining_board_bytes:
                raise ValueError("consultation-board content exceeds the local safety limit")
            packet_bytes = archive.read("key-image.json")
            png_bytes = archive.read("key-image.png")
            measurement_bytes = archive.read("measurements.json")
    except (OSError, zipfile.BadZipFile, KeyError) as error:
        raise ValueError(
            f"board key image could not be read: {type(error).__name__}"
        ) from error
    try:
        candidate = _strict_json_loads(packet_bytes)
    except ValueError as error:
        raise ValueError(f"board key-image sidecar is invalid: {error}") from error
    display = candidate.get("display") if isinstance(candidate, dict) else None
    slot = display.get("selection_slot") if isinstance(display, dict) else None
    if slot not in {"view_a", "view_b"}:
        raise ValueError("board key image has an unsupported capture slot")
    packet, errors = _consultation_component(
        packet_bytes,
        png_bytes,
        measurement_bytes,
        slot,
    )
    if packet is None or errors:
        raise ValueError(f"board key image is invalid: {'; '.join(errors)}")
    return KeyImageBundle(packet, packet_bytes, png_bytes, measurement_bytes)


def _relationship(bundles: list[KeyImageBundle]) -> dict[str, Any]:
    sources = [bundle.packet.get("source") for bundle in bundles]
    if any(not isinstance(source, dict) for source in sources):
        raise ValueError("consultation-board key-image sources are invalid")
    typed_sources = [source for source in sources if isinstance(source, dict)]
    contexts = {source.get("patient_context_id") for source in typed_sources}
    if len(contexts) != 1 or None in contexts or "" in contexts:
        raise ValueError("consultation boards require one matching opaque patient context")
    modalities = {source.get("modality") for source in typed_sources}
    if modalities != {"MR", "CT"}:
        raise ValueError("consultation boards require at least one MR and one CT view")
    study_ids = {source.get("study_id") for source in typed_sources}
    if None in study_ids or len(study_ids) < 2:
        raise ValueError("consultation boards require at least two distinct source studies")
    instance_ids = [source.get("instance_id") for source in typed_sources]
    if None in instance_ids or len(instance_ids) != len(set(instance_ids)):
        raise ValueError("consultation boards require distinct source instances")
    return {
        "selection_method": "explicit_2_to_8_view_selection",
        "same_patient_context": True,
        "item_count": len(bundles),
        "modalities_present": ["MR", "CT"],
        "modality_relationship": "cross_modality_context_only",
        "distinct_source_study_count": len(study_ids),
        "distinct_source_instances": True,
        "temporal_relationship": "not_asserted",
        "registration_status": "not_registered",
        "spatial_relationship": "not_aligned",
        "longitudinal_comparison_authorized": False,
        "response_assessment_authorized": False,
    }


def _observation(
    item_id: str,
    label: str,
    bundle: KeyImageBundle,
    source_anchor: dict[str, Any],
) -> dict[str, Any]:
    directory = _item_directory(item_id)
    evidence = bundle.packet["measurement_evidence"]
    display = bundle.packet["display"]
    return {
        "item_id": item_id,
        "discussion_label": label,
        "capture_slot": display["selection_slot"],
        "source": bundle.packet["source"],
        "source_anchor": source_anchor,
        "display": display,
        "key_image_path": f"{directory}/key-image.png",
        "key_image_sidecar_path": f"{directory}/key-image.json",
        "measurement_path": f"{directory}/measurements.json",
        "measurement_count": evidence["measurement_count"],
        "tracking_ids": evidence["tracking_ids"],
        "review_status": "unreviewed",
    }


def _format_date(value: Any) -> str:
    if isinstance(value, str) and re.fullmatch(r"[0-9]{8}", value):
        try:
            return datetime.strptime(value, "%Y%m%d").date().isoformat()
        except ValueError:
            pass
    return "Date unavailable"


def _render_review_html(packet: dict[str, Any]) -> bytes:
    cards: list[str] = []
    for observation in packet["observations"]:
        source = observation["source"]
        display = observation["display"]
        anchor = observation["source_anchor"]
        label = html.escape(str(observation["discussion_label"]))
        modality = html.escape(str(source["modality"]))
        acquisition_date = html.escape(_format_date(source.get("acquisition_date")))
        description = html.escape(str(source["series_description"]))
        image_path = html.escape(observation["key_image_path"], quote=True)
        anchor_sha256 = html.escape(str(anchor["dicom_sha256"]))
        cards.append(
            f"""
        <article class="card">
          <header><span>{label}</span><strong>{modality} · {acquisition_date}</strong></header>
          <div class="label-warning">Person-entered discussion label · unreviewed</div>
          <img src="{image_path}" alt="{label} unreviewed derived reference key image">
          <dl>
            <div><dt>Series</dt><dd>{description}</dd></div>
            <div><dt>Modality</dt><dd>{modality}</dd></div>
            <div><dt>Source slice</dt><dd>{display['stack_position']} / {display['stack_count']}</dd></div>
            <div><dt>Visible measurements</dt><dd>{observation['measurement_count']}</dd></div>
            <div><dt>Exact DICOM source</dt><dd>{anchor['dicom_bytes']} bytes · SHA-256 <code>{anchor_sha256}</code></dd></div>
          </dl>
        </article>"""
        )
    question_items = "".join(
        f"<li>{html.escape(question)}</li>"
        for question in packet["questions_for_clinician"]
    )
    document = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="referrer" content="no-referrer">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'">
  <title>ScanView unreviewed clinician consultation evidence board</title>
  <style>
    :root {{ color-scheme: dark; font-family: Inter, system-ui, sans-serif; background: #07110f; color: #e7f3ef; }}
    * {{ box-sizing: border-box; }} body {{ margin: 0; padding: 24px; }} main {{ max-width: 1600px; margin: auto; }}
    h1 {{ margin: 0 0 8px; font-size: 25px; }}
    .banner {{ border: 1px solid #e8b35c; background: #291d09; color: #ffe4ac; padding: 12px 14px; margin: 16px 0; font-weight: 700; }}
    .context {{ color: #afc2bc; margin-bottom: 18px; }}
    .grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; align-items: start; }}
    .card {{ border: 1px solid #29433c; background: #0b1916; padding: 12px; min-width: 0; break-inside: avoid; }}
    .card header {{ display: flex; justify-content: space-between; gap: 12px; margin-bottom: 4px; color: #7de9ca; }}
    .label-warning {{ color: #e8b35c; font-size: 12px; margin-bottom: 10px; }}
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
  <h1>ScanView clinician consultation evidence board</h1>
  <div class="banner">REFERENCE VIEWS ONLY · LABELS UNREVIEWED · NOT A COMPARISON · NOT FOR DIAGNOSIS · NO RESPONSE CONCLUSION</div>
  <p class="context">{len(cards)} explicitly selected MR/CT source views. Order and dates identify sources only; no chronological, same-lesion, registered, aligned, diagnostic, or response relationship is assigned.</p>
  <div class="grid">{''.join(cards)}</div>
  <section><h2>Questions for the clinical team</h2><ul>{question_items}</ul></section>
  <section><h2>Review checklist</h2><ul class="checklist"><li>□ Correct patient and every source image confirmed in the clinical system</li><li>□ Every discussion label reviewed and corrected where necessary</li><li>□ Relevant anatomy or tumor feature, if any, identified for each view</li><li>□ Modality differences and non-comparable features explained</li><li>□ Future same-modality MRI sequence and timepoint identified</li><li>□ Clinical interpretation recorded in the medical record</li></ul></section>
  <section><h2>Clinician notes</h2><div class="notes" aria-label="Blank area for clinician notes"></div></section>
  <footer>Original DICOM instances remain authoritative. Validate this archive locally with scanview-agent before use. This board contains sensitive medical imagery and may contain identifying pixels.</footer>
</main></body></html>\n"""
    return document.encode()


def _render_readme() -> bytes:
    return (
        "ScanView clinician consultation evidence board\n"
        "\n"
        "1. Extract the entire ZIP into one local folder.\n"
        "2. Open review.html in a browser, or print it for a clinical conversation.\n"
        "3. Keep every file together so integrity validation can succeed.\n"
        "4. Validate locally: scanview-agent validate-consultation-board <archive.zip>\n"
        "\n"
        "REFERENCE VIEWS ONLY. LABELS UNREVIEWED. NOT A COMPARISON. NOT FOR DIAGNOSIS.\n"
        "No chronology, registration, alignment, lesion matching, response category, or treatment conclusion is provided.\n"
        "MRI and CT intensity values are not directly comparable. Original DICOM files remain authoritative.\n"
        "Treat this archive as sensitive medical data; rendered pixels may identify the patient.\n"
    ).encode()


def _payloads(bundles: list[KeyImageBundle]) -> dict[str, bytes]:
    payloads: dict[str, bytes] = {}
    for index, bundle in enumerate(bundles):
        directory = _item_directory(_item_id(index))
        payloads[f"{directory}/key-image.json"] = bundle.packet_bytes
        payloads[f"{directory}/key-image.png"] = bundle.png_bytes
        payloads[f"{directory}/measurements.json"] = bundle.measurement_bytes
    return payloads


def _payload_media_type(path: str) -> str:
    if path == "review.html":
        return "text/html"
    if path == "README.txt":
        return "text/plain"
    if path.endswith(".png"):
        return "image/png"
    return "application/json"


def _file_manifest(payloads: dict[str, bytes]) -> dict[str, dict[str, Any]]:
    return {
        path: {
            "media_type": _payload_media_type(path),
            "byte_count": len(content),
            "sha256": _digest(content),
        }
        for path, content in sorted(payloads.items())
    }


def _validate_generated_archive_size(
    packet: dict[str, Any], payloads: dict[str, bytes]
) -> None:
    packet_bytes = _json_bytes(packet)
    contents = [packet_bytes, *payloads.values()]
    if any(len(content) > MAX_ARCHIVE_MEMBER_BYTES for content in contents):
        raise ValueError("consultation-board member exceeds the local safety limit")
    if sum(len(content) for content in contents) > MAX_BOARD_ARCHIVE_BYTES:
        raise ValueError("consultation-board content exceeds the local safety limit")


def build_consultation_board(
    items: list[tuple[str, ArchiveSource]],
    catalog: dict[str, Any],
    registry: dict[str, Path],
    *,
    created_at: str | None = None,
) -> tuple[dict[str, Any], dict[str, bytes]]:
    if not MIN_ITEMS <= len(items) <= MAX_ITEMS:
        raise ValueError(
            f"consultation boards require {MIN_ITEMS} to {MAX_ITEMS} selected views"
        )
    labels: list[str] = []
    bundles: list[KeyImageBundle] = []
    component_bytes = 0
    for label, source in items:
        error = _label_error(label)
        if error:
            raise ValueError(error)
        labels.append(label)
        bundle = _read_board_key_image(
            source,
            remaining_board_bytes=MAX_BOARD_ARCHIVE_BYTES - component_bytes,
        )
        component_bytes += (
            len(bundle.packet_bytes)
            + len(bundle.png_bytes)
            + len(bundle.measurement_bytes)
        )
        bundles.append(bundle)
    relationship = _relationship(bundles)
    anchors = [
        _catalog_source_anchor(
            catalog,
            registry,
            bundle.packet["source"],
            bundle.packet["display"],
        )
        for bundle in bundles
    ]
    created = created_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    if not _valid_datetime(created):
        raise ValueError("created_at must be an ISO 8601 date-time")
    packet: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "created_at": created,
        "review_status": "unreviewed",
        "artifact_type": ARTIFACT_TYPE,
        "purpose": "two_to_eight_source_views_for_clinician_discussion_only",
        "relationship": relationship,
        "observations": [
            _observation(_item_id(index), labels[index], bundle, anchors[index])
            for index, bundle in enumerate(bundles)
        ],
        "computed_results": [],
        "candidate_interpretations": [],
        "limitations": list(LIMITATIONS),
        "missing_context": list(MISSING_CONTEXT),
        "questions_for_clinician": list(QUESTIONS_FOR_CLINICIAN),
        "implementation": dict(IMPLEMENTATION),
        "files": {},
    }
    payloads = _payloads(bundles)
    payloads["review.html"] = _render_review_html(packet)
    payloads["README.txt"] = _render_readme()
    packet["files"] = _file_manifest(payloads)
    _validate_generated_archive_size(packet, payloads)
    return packet, payloads


def consultation_board_archive_bytes(
    items: list[tuple[str, ArchiveSource]],
    catalog: dict[str, Any],
    registry: dict[str, Path],
    *,
    created_at: str | None = None,
) -> bytes:
    packet, payloads = build_consultation_board(
        items,
        catalog,
        registry,
        created_at=created_at,
    )
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("consultation-board.json", _json_bytes(packet))
        for path, content in sorted(payloads.items()):
            archive.writestr(path, content)
    return output.getvalue()


def consultation_board_from_transport(
    transport_bytes: bytes,
    catalog: dict[str, Any],
    registry: dict[str, Path],
    *,
    created_at: str | None = None,
) -> bytes:
    if not transport_bytes or len(transport_bytes) > MAX_BOARD_TRANSPORT_BYTES:
        raise ValueError("consultation-board request exceeds the local safety limit")
    try:
        with zipfile.ZipFile(io.BytesIO(transport_bytes)) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(names) != len(set(names)) or "board-input.json" not in names:
                raise ValueError("consultation-board request members are ambiguous")
            if any(info.flag_bits & 0x1 for info in infos):
                raise ValueError("encrypted consultation-board request members are unsupported")
            if any(_zip_member_is_link(info) for info in infos):
                raise ValueError("linked consultation-board request members are unsupported")
            if sum(info.file_size for info in infos) > MAX_BOARD_TRANSPORT_BYTES:
                raise ValueError("consultation-board request content exceeds the local safety limit")
            manifest_info = next(
                info for info in infos if info.filename == "board-input.json"
            )
            if manifest_info.file_size > MAX_INPUT_MANIFEST_BYTES:
                raise ValueError("consultation-board input manifest is too large")
            manifest = _strict_json_loads(archive.read("board-input.json"))
            required_manifest_fields = {"schema_version", "artifact_type", "items"}
            if not isinstance(manifest, dict) or set(manifest) != required_manifest_fields:
                raise ValueError("consultation-board input manifest is invalid")
            if (
                manifest.get("schema_version") != SCHEMA_VERSION
                or manifest.get("artifact_type") != INPUT_ARTIFACT_TYPE
            ):
                raise ValueError("consultation-board input contract is unsupported")
            manifest_items = manifest.get("items")
            if not isinstance(manifest_items, list) or not MIN_ITEMS <= len(
                manifest_items
            ) <= MAX_ITEMS:
                raise ValueError(
                    f"consultation-board input requires {MIN_ITEMS} to {MAX_ITEMS} items"
                )
            expected_names = {"board-input.json"}
            parsed_items: list[tuple[str, bytes]] = []
            for index, item in enumerate(manifest_items):
                expected_archive = f"item-{index + 1:02d}.zip"
                if (
                    not isinstance(item, dict)
                    or set(item) != {"archive", "discussion_label"}
                    or item.get("archive") != expected_archive
                ):
                    raise ValueError("consultation-board input item order is invalid")
                label = item.get("discussion_label")
                error = _label_error(label)
                if error:
                    raise ValueError(error)
                expected_names.add(expected_archive)
                info = next(
                    (candidate for candidate in infos if candidate.filename == expected_archive),
                    None,
                )
                if info is None or info.file_size > MAX_TRANSPORT_KEY_IMAGE_BYTES:
                    raise ValueError(
                        "consultation-board key-image input is missing or too large"
                    )
                parsed_items.append((label, archive.read(expected_archive)))
            if set(names) != expected_names or len(infos) != len(expected_names):
                raise ValueError("consultation-board request contains unsupported files")
    except (OSError, zipfile.BadZipFile, KeyError, StopIteration) as error:
        raise ValueError(
            f"consultation-board request could not be read: {type(error).__name__}"
        ) from error
    return consultation_board_archive_bytes(
        [(label, io.BytesIO(payload)) for label, payload in parsed_items],
        catalog,
        registry,
        created_at=created_at,
    )


def write_consultation_board(
    dicom_root: Path,
    items: list[tuple[str, Path]],
    output: Path,
    *,
    created_at: str | None = None,
) -> dict[str, Any]:
    from .catalog import build_catalog

    catalog, registry = build_catalog(dicom_root, include_hashes=True)
    archive_bytes = consultation_board_archive_bytes(
        [(label, path) for label, path in items],
        catalog,
        registry,
        created_at=created_at,
    )
    _write_new_owner_only(output, archive_bytes)
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        value = _strict_json_loads(archive.read("consultation-board.json"))
    assert isinstance(value, dict)
    return value


def _expected_payload_paths(item_count: int) -> set[str]:
    if (
        not isinstance(item_count, int)
        or isinstance(item_count, bool)
        or not 0 <= item_count <= MAX_ITEMS
    ):
        raise ValueError("consultation-board item count exceeds the supported range")
    paths = {"review.html", "README.txt"}
    for index in range(item_count):
        directory = _item_directory(_item_id(index))
        paths.update(
            {
                f"{directory}/key-image.json",
                f"{directory}/key-image.png",
                f"{directory}/measurements.json",
            }
        )
    return paths


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
        return ["consultation board must be a JSON object"]
    if set(packet) != required:
        errors.append("consultation-board fields are incomplete or unsupported")
    if packet.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if not _valid_datetime(packet.get("created_at")):
        errors.append("created_at must be an ISO 8601 date-time")
    if packet.get("review_status") != "unreviewed":
        errors.append("review_status must be unreviewed")
    if packet.get("artifact_type") != ARTIFACT_TYPE:
        errors.append(f"artifact_type must be {ARTIFACT_TYPE}")
    if packet.get("purpose") != "two_to_eight_source_views_for_clinician_discussion_only":
        errors.append("purpose is invalid")

    relationship = packet.get("relationship")
    relationship_keys = {
        "selection_method",
        "same_patient_context",
        "item_count",
        "modalities_present",
        "modality_relationship",
        "distinct_source_study_count",
        "distinct_source_instances",
        "temporal_relationship",
        "registration_status",
        "spatial_relationship",
        "longitudinal_comparison_authorized",
        "response_assessment_authorized",
    }
    if not isinstance(relationship, dict) or set(relationship) != relationship_keys:
        errors.append("relationship is invalid")
    else:
        constants = {
            "selection_method": "explicit_2_to_8_view_selection",
            "same_patient_context": True,
            "modalities_present": ["MR", "CT"],
            "modality_relationship": "cross_modality_context_only",
            "distinct_source_instances": True,
            "temporal_relationship": "not_asserted",
            "registration_status": "not_registered",
            "spatial_relationship": "not_aligned",
            "longitudinal_comparison_authorized": False,
            "response_assessment_authorized": False,
        }
        if any(relationship.get(key) != value for key, value in constants.items()):
            errors.append("relationship safety gates are invalid")
        count = relationship.get("item_count")
        studies = relationship.get("distinct_source_study_count")
        if not isinstance(count, int) or isinstance(count, bool) or not MIN_ITEMS <= count <= MAX_ITEMS:
            errors.append("relationship item_count is invalid")
        if not isinstance(studies, int) or isinstance(studies, bool) or studies < 2:
            errors.append("relationship source-study count is invalid")

    observations = packet.get("observations")
    observation_keys = {
        "item_id",
        "discussion_label",
        "capture_slot",
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
    if not isinstance(observations, list) or not MIN_ITEMS <= len(observations) <= MAX_ITEMS:
        errors.append(f"observations must contain {MIN_ITEMS} to {MAX_ITEMS} items")
        observations = []
    for index, observation in enumerate(observations):
        item_id = _item_id(index)
        if not isinstance(observation, dict) or set(observation) != observation_keys:
            errors.append(f"{item_id} observation is invalid")
            continue
        if observation.get("item_id") != item_id:
            errors.append(f"{item_id} observation order is invalid")
        label_error = _label_error(observation.get("discussion_label"))
        if label_error:
            errors.append(f"{item_id} {label_error}")
        if observation.get("capture_slot") not in {"view_a", "view_b"}:
            errors.append(f"{item_id} capture slot is invalid")
        if not isinstance(observation.get("source"), dict) or not isinstance(
            observation.get("display"), dict
        ):
            errors.append(f"{item_id} source/display is invalid")
        anchor = observation.get("source_anchor")
        if not _valid_source_anchor(anchor):
            errors.append(f"{item_id} source anchor is invalid")
        directory = _item_directory(item_id)
        expected_paths = {
            "key_image_path": f"{directory}/key-image.png",
            "key_image_sidecar_path": f"{directory}/key-image.json",
            "measurement_path": f"{directory}/measurements.json",
        }
        if any(observation.get(key) != value for key, value in expected_paths.items()):
            errors.append(f"{item_id} observation paths are invalid")
        count = observation.get("measurement_count")
        tracking_ids = observation.get("tracking_ids")
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            errors.append(f"{item_id} measurement_count is invalid")
        if (
            not isinstance(tracking_ids, list)
            or not all(isinstance(value, str) and value for value in tracking_ids)
            or len(tracking_ids) != len(set(tracking_ids))
        ):
            errors.append(f"{item_id} tracking_ids are invalid")
        elif isinstance(count, int) and count != len(tracking_ids):
            errors.append(f"{item_id} measurement count disagrees with tracking_ids")
        if observation.get("review_status") != "unreviewed":
            errors.append(f"{item_id} review_status must be unreviewed")

    if isinstance(relationship, dict) and relationship.get("item_count") != len(observations):
        errors.append("relationship item count disagrees with observations")
    for key in ("computed_results", "candidate_interpretations"):
        if packet.get(key) != []:
            errors.append(f"{key} must remain empty")
    fixed_arrays = {
        "limitations": LIMITATIONS,
        "missing_context": MISSING_CONTEXT,
        "questions_for_clinician": QUESTIONS_FOR_CLINICIAN,
    }
    if any(packet.get(key) != value for key, value in fixed_arrays.items()):
        errors.append("consultation-board safety text is incomplete or altered")
    if packet.get("implementation") != IMPLEMENTATION:
        errors.append("implementation is unsupported")

    files = packet.get("files")
    expected_paths = _expected_payload_paths(len(observations))
    if not isinstance(files, dict) or set(files) != expected_paths:
        errors.append("files manifest is incomplete or unsupported")
    else:
        for path in expected_paths:
            record = files.get(path)
            if not isinstance(record, dict) or set(record) != {
                "media_type",
                "byte_count",
                "sha256",
            }:
                errors.append(f"files entry is invalid: {path}")
                continue
            if record.get("media_type") != _payload_media_type(path):
                errors.append(f"files media type is invalid: {path}")
            byte_count = record.get("byte_count")
            if (
                not isinstance(byte_count, int)
                or isinstance(byte_count, bool)
                or byte_count <= 0
            ):
                errors.append(f"files byte count is invalid: {path}")
            digest = record.get("sha256")
            if not isinstance(digest, str) or not SHA256.fullmatch(digest):
                errors.append(f"files digest is invalid: {path}")
    return errors


def consultation_board_summary(path: ArchiveSource) -> dict[str, Any]:
    errors: list[str] = []
    packet: Any = None
    payloads: dict[str, bytes] = {}
    try:
        _rewind(path)
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(names) != len(set(names)):
                errors.append("archive members are ambiguous")
            if any(info.flag_bits & 0x1 for info in infos):
                errors.append("encrypted archive members are unsupported")
            if any(_zip_member_is_link(info) for info in infos):
                errors.append("linked archive members are unsupported")
            if any(info.file_size > MAX_ARCHIVE_MEMBER_BYTES for info in infos) or sum(
                info.file_size for info in infos
            ) > MAX_BOARD_ARCHIVE_BYTES:
                errors.append("archive content exceeds the local safety limit")
            if "consultation-board.json" not in names:
                errors.append("consultation-board.json is missing")
            if not errors:
                packet = _strict_json_loads(archive.read("consultation-board.json"))
                observations = packet.get("observations") if isinstance(packet, dict) else None
                if not isinstance(observations, list) or not MIN_ITEMS <= len(
                    observations
                ) <= MAX_ITEMS:
                    errors.append(
                        f"consultation-board observations must contain {MIN_ITEMS} to {MAX_ITEMS} items"
                    )
                else:
                    item_count = len(observations)
                    expected_names = {
                        "consultation-board.json"
                    } | _expected_payload_paths(item_count)
                    if set(names) != expected_names or len(infos) != len(expected_names):
                        errors.append("archive contains unsupported or missing files")
                    else:
                        payloads = {
                            name: archive.read(name)
                            for name in _expected_payload_paths(item_count)
                        }
    except (OSError, zipfile.BadZipFile, KeyError, ValueError) as error:
        errors.append(f"archive could not be read: {type(error).__name__}")

    errors.extend(_validate_packet_shape(packet) if packet is not None else [])
    file_integrity = False
    component_integrity = False
    presentation_integrity = False
    source_anchor_integrity = False
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

        observations = packet.get("observations")
        components: list[KeyImageBundle] = []
        component_integrity = isinstance(observations, list)
        if isinstance(observations, list):
            for index, observation in enumerate(observations):
                item_id = _item_id(index)
                directory = _item_directory(item_id)
                packet_bytes = payloads.get(f"{directory}/key-image.json", b"")
                png_bytes = payloads.get(f"{directory}/key-image.png", b"")
                measurement_bytes = payloads.get(f"{directory}/measurements.json", b"")
                try:
                    sidecar = _strict_json_loads(packet_bytes)
                    display = sidecar.get("display") if isinstance(sidecar, dict) else None
                    slot = display.get("selection_slot") if isinstance(display, dict) else None
                    if slot not in {"view_a", "view_b"}:
                        raise ValueError("capture slot is invalid")
                    component, component_errors = _consultation_component(
                        packet_bytes,
                        png_bytes,
                        measurement_bytes,
                        slot,
                    )
                except ValueError as error:
                    component = None
                    component_errors = [str(error)]
                if component_errors or not isinstance(component, dict):
                    component_integrity = False
                    errors.extend(
                        f"{item_id} key image: {message}"
                        for message in component_errors
                    )
                    continue
                bundle = KeyImageBundle(
                    component,
                    packet_bytes,
                    png_bytes,
                    measurement_bytes,
                )
                components.append(bundle)
                if not isinstance(observation, dict) or observation != _observation(
                    item_id,
                    observation.get("discussion_label", ""),
                    bundle,
                    observation.get("source_anchor", {}),
                ):
                    component_integrity = False
            if not component_integrity:
                errors.append(
                    "consultation-board observations disagree with embedded key-image evidence"
                )

        if components and len(components) == len(observations or []):
            try:
                expected_relationship = _relationship(components)
                if packet.get("relationship") != expected_relationship:
                    component_integrity = False
                    errors.append(
                        "relationship metadata disagrees with embedded key images"
                    )
            except (KeyError, TypeError, ValueError) as error:
                component_integrity = False
                errors.append(f"embedded key images are not a valid board: {error}")

        source_anchor_shape_integrity = bool(observations) and all(
            isinstance(observation, dict)
            and _valid_source_anchor(observation.get("source_anchor"))
            for observation in (observations or [])
        )
        try:
            presentation_integrity = (
                payloads["review.html"] == _render_review_html(packet)
                and payloads["README.txt"] == _render_readme()
            )
        except (KeyError, TypeError, IndexError):
            presentation_integrity = False
        if not presentation_integrity:
            errors.append("review presentation does not match the local static template")
        source_anchor_integrity = bool(
            source_anchor_shape_integrity
            and file_integrity
            and presentation_integrity
        )

    relationship = packet.get("relationship") if isinstance(packet, dict) else None
    observations = packet.get("observations") if isinstance(packet, dict) else None
    item_count = len(observations) if isinstance(observations, list) else 0
    measurement_count = 0
    if isinstance(observations, list):
        for observation in observations:
            if isinstance(observation, dict):
                value = observation.get("measurement_count")
                if isinstance(value, int) and not isinstance(value, bool):
                    measurement_count += value
    return {
        "valid": not errors,
        "schema_version": packet.get("schema_version") if isinstance(packet, dict) else None,
        "review_status": packet.get("review_status") if isinstance(packet, dict) else None,
        "artifact_type": packet.get("artifact_type") if isinstance(packet, dict) else None,
        "item_count": item_count,
        "modalities_present": (
            relationship.get("modalities_present")
            if isinstance(relationship, dict)
            else []
        ),
        "distinct_source_study_count": (
            relationship.get("distinct_source_study_count")
            if isinstance(relationship, dict)
            else 0
        ),
        "measurement_count": measurement_count,
        "file_integrity": file_integrity,
        "component_integrity": component_integrity,
        "source_anchor_integrity": source_anchor_integrity,
        "presentation_integrity": presentation_integrity,
        "longitudinal_comparison_authorized": False,
        "response_assessment_authorized": False,
        "external_api_required": False,
        "errors": errors,
    }
