from __future__ import annotations

import hashlib
import html
import io
import json
import os
import re
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from .key_images import key_image_archive_summary


EXPECTED_FILES = {
    "visit-packet.json",
    "review.html",
    "README.txt",
    "baseline/key-image.json",
    "baseline/key-image.png",
    "baseline/measurements.json",
    "followup/key-image.json",
    "followup/key-image.png",
    "followup/measurements.json",
}
PAYLOAD_MEDIA_TYPES = {
    "review.html": "text/html",
    "README.txt": "text/plain",
    "baseline/key-image.json": "application/json",
    "baseline/key-image.png": "image/png",
    "baseline/measurements.json": "application/json",
    "followup/key-image.json": "application/json",
    "followup/key-image.png": "image/png",
    "followup/measurements.json": "application/json",
}
MAX_ARCHIVE_MEMBER_BYTES = 64 * 1024 * 1024
SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class KeyImageBundle:
    packet: dict[str, Any]
    packet_bytes: bytes
    png_bytes: bytes
    measurement_bytes: bytes


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2) + "\n").encode()


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _valid_datetime(value: Any) -> bool:
    if not isinstance(value, str) or "T" not in value:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _parse_dicom_date(value: Any) -> date | None:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{8}", value):
        return None
    try:
        return datetime.strptime(value, "%Y%m%d").date()
    except ValueError:
        return None


def _read_key_image(path: Path, role: str) -> KeyImageBundle:
    summary = key_image_archive_summary(path)
    if not summary["valid"]:
        details = "; ".join(summary["errors"])
        raise ValueError(f"{role} key image is invalid: {details}")
    with zipfile.ZipFile(path) as archive:
        packet_bytes = archive.read("key-image.json")
        png_bytes = archive.read("key-image.png")
        measurement_bytes = archive.read("measurements.json")
    packet = json.loads(packet_bytes)
    if packet["display"]["viewport_role"] != role:
        raise ValueError(f"{role} key image has the wrong viewport role")
    return KeyImageBundle(packet, packet_bytes, png_bytes, measurement_bytes)


def _component_summary(
    packet_bytes: bytes, png_bytes: bytes, measurement_bytes: bytes
) -> dict[str, Any]:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("key-image.json", packet_bytes)
        archive.writestr("key-image.png", png_bytes)
        archive.writestr("measurements.json", measurement_bytes)
    buffer.seek(0)
    return key_image_archive_summary(buffer)


def _pairing_values(
    baseline: KeyImageBundle, followup: KeyImageBundle
) -> dict[str, Any]:
    baseline_source = baseline.packet["source"]
    followup_source = followup.packet["source"]
    if baseline.packet.get("schema_version") != "2.0.0" or (
        followup.packet.get("schema_version") != "2.0.0"
    ):
        raise ValueError("visit packets require key-image v2 patient/study context")
    if not baseline_source.get("patient_context_id") or (
        baseline_source.get("patient_context_id")
        != followup_source.get("patient_context_id")
    ):
        raise ValueError("visit packets require a matching opaque patient context")
    if baseline_source.get("study_id") == followup_source.get("study_id"):
        raise ValueError("visit packets require distinct source studies")
    baseline_modality = baseline_source["modality"]
    followup_modality = followup_source["modality"]
    if baseline_modality not in {"MR", "CT"} or followup_modality != baseline_modality:
        raise ValueError("visit packets require the same MR or CT modality at both timepoints")
    if baseline_source["series_id"] == followup_source["series_id"]:
        raise ValueError("visit packets require distinct source series")
    baseline_date = _parse_dicom_date(baseline_source.get("acquisition_date"))
    followup_date = _parse_dicom_date(followup_source.get("acquisition_date"))
    if baseline_date is None or followup_date is None:
        raise ValueError("visit packets require valid acquisition dates at both timepoints")
    if baseline_date >= followup_date:
        raise ValueError("baseline acquisition date must precede follow-up acquisition date")
    return {
        "method": "explicit_key_image_selection",
        "modality": baseline_modality,
        "baseline_acquisition_date": baseline_source["acquisition_date"],
        "followup_acquisition_date": followup_source["acquisition_date"],
        "elapsed_days": (followup_date - baseline_date).days,
        "same_patient_context": True,
        "distinct_source_studies": True,
        "distinct_source_series": True,
        "registration_status": "not_registered",
        "image_relationship": "side_by_side_only",
    }


def _observation(role: str, bundle: KeyImageBundle) -> dict[str, Any]:
    evidence = bundle.packet["measurement_evidence"]
    return {
        "timepoint": role,
        "source": bundle.packet["source"],
        "display": bundle.packet["display"],
        "key_image_path": f"{role}/key-image.png",
        "key_image_sidecar_path": f"{role}/key-image.json",
        "measurement_path": f"{role}/measurements.json",
        "measurement_count": evidence["measurement_count"],
        "tracking_ids": evidence["tracking_ids"],
        "review_status": "unreviewed",
    }


def _format_date(value: str) -> str:
    parsed = _parse_dicom_date(value)
    return parsed.isoformat() if parsed else value


def _render_review_html(packet: dict[str, Any]) -> bytes:
    observations = {item["timepoint"]: item for item in packet["observations"]}
    pairing = packet["pairing"]

    def card(role: str, heading: str) -> str:
        observation = observations[role]
        source = observation["source"]
        display = observation["display"]
        description = html.escape(str(source["series_description"]))
        modality = html.escape(str(source["modality"]))
        acquisition_date = html.escape(_format_date(source["acquisition_date"]))
        image_path = html.escape(observation["key_image_path"], quote=True)
        return f"""
        <article class="card">
          <header><span>{heading}</span><strong>{acquisition_date}</strong></header>
          <img src="{image_path}" alt="{heading} unreviewed derived display key image">
          <dl>
            <div><dt>Series</dt><dd>{description}</dd></div>
            <div><dt>Modality</dt><dd>{modality}</dd></div>
            <div><dt>Source slice</dt><dd>{display['stack_position']} / {display['stack_count']}</dd></div>
            <div><dt>Visible measurements</dt><dd>{observation['measurement_count']}</dd></div>
          </dl>
        </article>"""

    question_items = "".join(
        f"<li>{html.escape(question)}</li>" for question in packet["questions_for_clinician"]
    )
    document = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="referrer" content="no-referrer">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'">
  <title>ScanView unreviewed clinician visit packet</title>
  <style>
    :root {{ color-scheme: dark; font-family: Inter, system-ui, sans-serif; background: #07110f; color: #e7f3ef; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; padding: 24px; }}
    main {{ max-width: 1500px; margin: auto; }}
    h1 {{ margin: 0 0 8px; font-size: 25px; }}
    .banner {{ border: 1px solid #e8b35c; background: #291d09; color: #ffe4ac; padding: 12px 14px; margin: 16px 0; font-weight: 700; }}
    .context {{ color: #afc2bc; margin-bottom: 18px; }}
    .grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }}
    .card {{ border: 1px solid #29433c; background: #0b1916; padding: 12px; min-width: 0; }}
    .card header {{ display: flex; justify-content: space-between; gap: 12px; margin-bottom: 10px; color: #7de9ca; }}
    img {{ display: block; width: 100%; height: auto; background: #000; border: 1px solid #213a34; }}
    dl {{ margin: 10px 0 0; }}
    dl div {{ display: grid; grid-template-columns: 150px 1fr; gap: 8px; border-top: 1px solid #1c312c; padding: 6px 0; }}
    dt {{ color: #93aaa3; }} dd {{ margin: 0; overflow-wrap: anywhere; }}
    section {{ margin-top: 22px; }}
    .checklist {{ list-style: none; padding: 0; }} .checklist li {{ margin: 10px 0; }}
    .notes {{ min-height: 110px; border: 1px solid #29433c; background: repeating-linear-gradient(#0b1916 0 27px, #29433c 28px); }}
    footer {{ margin-top: 24px; color: #93aaa3; font-size: 12px; }}
    @media (max-width: 850px) {{ .grid {{ grid-template-columns: 1fr; }} }}
    @media print {{ :root {{ color-scheme: light; background: white; color: black; }} body {{ padding: 8mm; }} .card, .notes {{ background: white; border-color: #777; }} .banner {{ color: black; background: #fff4d7; }} .context, dt, footer {{ color: #444; }} }}
  </style>
</head>
<body><main>
  <h1>ScanView clinician visit packet</h1>
  <div class="banner">UNREVIEWED DISPLAY DERIVATIVES · NOT FOR DIAGNOSIS · NO RESPONSE CONCLUSION GENERATED</div>
  <p class="context">Explicitly selected {html.escape(pairing['modality'])} key images · {_format_date(pairing['baseline_acquisition_date'])} to {_format_date(pairing['followup_acquisition_date'])} · {pairing['elapsed_days']} days. Side-by-side only; images are not registered or spatially aligned.</p>
  <div class="grid">{card('baseline', 'BASELINE')}{card('followup', 'FOLLOW-UP')}</div>
  <section><h2>Questions for the clinical team</h2><ul>{question_items}</ul></section>
  <section><h2>Review checklist</h2><ul class="checklist"><li>□ Correct baseline and follow-up exams</li><li>□ Comparable sequence, contrast timing, plane, and tumor component</li><li>□ Measurement placement and units reviewed</li><li>□ Clinical interpretation recorded in the medical record</li></ul></section>
  <section><h2>Clinician notes</h2><div class="notes" aria-label="Blank area for clinician notes"></div></section>
  <footer>Original DICOM instances remain authoritative. Validate this archive locally with scanview-agent before use. This packet may contain sensitive medical imagery.</footer>
</main></body></html>\n"""
    return document.encode()


def _render_readme() -> bytes:
    return (
        "ScanView clinician visit packet\n"
        "\n"
        "1. Extract the entire ZIP into one local folder.\n"
        "2. Open review.html in a browser, or print it for a clinical conversation.\n"
        "3. Keep every file together so integrity validation can succeed.\n"
        "4. Validate locally: scanview-agent validate-visit-packet <archive.zip>\n"
        "\n"
        "UNREVIEWED DISPLAY DERIVATIVES. NOT FOR DIAGNOSIS.\n"
        "No registration, lesion matching, response category, or treatment conclusion is provided.\n"
        "Original DICOM files remain authoritative. Treat this archive as sensitive medical data.\n"
    ).encode()


def _payloads(
    baseline: KeyImageBundle, followup: KeyImageBundle
) -> dict[str, bytes]:
    return {
        "baseline/key-image.json": baseline.packet_bytes,
        "baseline/key-image.png": baseline.png_bytes,
        "baseline/measurements.json": baseline.measurement_bytes,
        "followup/key-image.json": followup.packet_bytes,
        "followup/key-image.png": followup.png_bytes,
        "followup/measurements.json": followup.measurement_bytes,
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


def build_visit_packet(
    baseline_path: Path,
    followup_path: Path,
    *,
    created_at: str | None = None,
) -> tuple[dict[str, Any], dict[str, bytes]]:
    baseline = _read_key_image(baseline_path, "baseline")
    followup = _read_key_image(followup_path, "followup")
    pairing = _pairing_values(baseline, followup)
    created = created_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    if not _valid_datetime(created):
        raise ValueError("created_at must be an ISO 8601 date-time")
    packet: dict[str, Any] = {
        "schema_version": "1.0.0",
        "created_at": created,
        "review_status": "unreviewed",
        "artifact_type": "clinician_visit_packet",
        "pairing": pairing,
        "observations": [
            _observation("baseline", baseline),
            _observation("followup", followup),
        ],
        "computed_results": [],
        "candidate_interpretations": [],
        "limitations": [
            "The two images were explicitly selected and are shown side by side without registration or spatial alignment.",
            "Series descriptions and acquisition metadata do not prove sequence, contrast, or tumor-component comparability.",
            "Measurements are manual, source-linked, and unreviewed; they do not establish lesion identity or treatment response.",
            "Original DICOM instances remain authoritative; all included PNG and JSON files are derived evidence.",
        ],
        "missing_context": [
            "Qualified confirmation that both images depict the same lesion and tumor component on comparable sequences.",
            "Diagnosis-specific response criteria, treatment dates, symptoms, medications, and other clinical context.",
            "Clinician review of measurement placement, acquisition differences, and whether registration or segmentation is needed.",
        ],
        "questions_for_clinician": [
            "Are these the correct baseline and follow-up exams and the intended sequences for comparison?",
            "Do both key images depict the same lesion and tumor component with comparable contrast timing and plane?",
            "Are the visible measurements placed correctly, and which measurement or response criteria should apply?",
            "What conclusions, limitations, and follow-up questions should be recorded after clinical review?",
        ],
        "implementation": {
            "name": "ScanView clinician visit-packet assembler",
            "version": "0.1.0",
        },
        "files": {},
    }
    payloads = _payloads(baseline, followup)
    payloads["review.html"] = _render_review_html(packet)
    payloads["README.txt"] = _render_readme()
    packet["files"] = _file_manifest(payloads)
    return packet, payloads


def write_visit_packet(
    baseline_path: Path,
    followup_path: Path,
    output: Path,
    *,
    created_at: str | None = None,
) -> dict[str, Any]:
    packet, payloads = build_visit_packet(
        baseline_path, followup_path, created_at=created_at
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.{os.getpid()}.tmp")
    try:
        with zipfile.ZipFile(
            temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
        ) as archive:
            archive.writestr("visit-packet.json", _json_bytes(packet))
            for path, content in sorted(payloads.items()):
                archive.writestr(path, content)
        temporary.chmod(0o600)
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    return packet


def _validate_packet_shape(packet: Any) -> list[str]:
    errors: list[str] = []
    required = {
        "schema_version",
        "created_at",
        "review_status",
        "artifact_type",
        "pairing",
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
        return ["visit packet must be a JSON object"]
    if set(packet) != required:
        errors.append("visit packet fields are incomplete or unsupported")
    if packet.get("schema_version") != "1.0.0":
        errors.append("schema_version must be 1.0.0")
    if not _valid_datetime(packet.get("created_at")):
        errors.append("created_at must be an ISO 8601 date-time")
    if packet.get("review_status") != "unreviewed":
        errors.append("review_status must be unreviewed")
    if packet.get("artifact_type") != "clinician_visit_packet":
        errors.append("artifact_type must be clinician_visit_packet")

    pairing = packet.get("pairing")
    pairing_keys = {
        "method",
        "modality",
        "baseline_acquisition_date",
        "followup_acquisition_date",
        "elapsed_days",
        "same_patient_context",
        "distinct_source_studies",
        "distinct_source_series",
        "registration_status",
        "image_relationship",
    }
    if not isinstance(pairing, dict) or set(pairing) != pairing_keys:
        errors.append("pairing is invalid")
    else:
        if pairing.get("method") != "explicit_key_image_selection":
            errors.append("pairing.method is invalid")
        if pairing.get("modality") not in {"MR", "CT"}:
            errors.append("pairing.modality is invalid")
        if _parse_dicom_date(pairing.get("baseline_acquisition_date")) is None:
            errors.append("pairing baseline date is invalid")
        if _parse_dicom_date(pairing.get("followup_acquisition_date")) is None:
            errors.append("pairing follow-up date is invalid")
        if not isinstance(pairing.get("elapsed_days"), int) or isinstance(
            pairing.get("elapsed_days"), bool
        ) or pairing["elapsed_days"] <= 0:
            errors.append("pairing.elapsed_days must be a positive integer")
        if pairing.get("same_patient_context") is not True:
            errors.append("pairing must use one matching patient context")
        if pairing.get("distinct_source_studies") is not True:
            errors.append("pairing must use distinct source studies")
        if pairing.get("distinct_source_series") is not True:
            errors.append("pairing must use distinct source series")
        if pairing.get("registration_status") != "not_registered":
            errors.append("pairing.registration_status must be not_registered")
        if pairing.get("image_relationship") != "side_by_side_only":
            errors.append("pairing.image_relationship must be side_by_side_only")

    observations = packet.get("observations")
    observation_keys = {
        "timepoint",
        "source",
        "display",
        "key_image_path",
        "key_image_sidecar_path",
        "measurement_path",
        "measurement_count",
        "tracking_ids",
        "review_status",
    }
    if not isinstance(observations, list) or len(observations) != 2:
        errors.append("observations must contain baseline and follow-up")
    else:
        for index, role in enumerate(("baseline", "followup")):
            observation = observations[index]
            if not isinstance(observation, dict) or set(observation) != observation_keys:
                errors.append(f"{role} observation is invalid")
                continue
            if observation.get("timepoint") != role:
                errors.append(f"{role} observation has the wrong timepoint")
            if not isinstance(observation.get("source"), dict) or not isinstance(
                observation.get("display"), dict
            ):
                errors.append(f"{role} observation source/display is invalid")
            expected_paths = {
                "key_image_path": f"{role}/key-image.png",
                "key_image_sidecar_path": f"{role}/key-image.json",
                "measurement_path": f"{role}/measurements.json",
            }
            if any(observation.get(key) != value for key, value in expected_paths.items()):
                errors.append(f"{role} observation paths are invalid")
            count = observation.get("measurement_count")
            ids = observation.get("tracking_ids")
            if not isinstance(count, int) or isinstance(count, bool) or count < 0:
                errors.append(f"{role} measurement_count is invalid")
            if not isinstance(ids, list) or not all(
                isinstance(value, str) and value for value in ids
            ) or len(ids) != len(set(ids)):
                errors.append(f"{role} tracking_ids are invalid")
            elif isinstance(count, int) and count != len(ids):
                errors.append(f"{role} measurement count disagrees with tracking_ids")
            if observation.get("review_status") != "unreviewed":
                errors.append(f"{role} review_status must be unreviewed")

    for key in ("computed_results", "candidate_interpretations"):
        if packet.get(key) != []:
            errors.append(f"{key} must remain empty")
    for key in ("limitations", "missing_context", "questions_for_clinician"):
        value = packet.get(key)
        if not isinstance(value, list) or not value or not all(
            isinstance(item, str) and item for item in value
        ):
            errors.append(f"{key} must be a non-empty string array")
    if packet.get("implementation") != {
        "name": "ScanView clinician visit-packet assembler",
        "version": "0.1.0",
    }:
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
            if not isinstance(value.get("byte_count"), int) or isinstance(
                value.get("byte_count"), bool
            ) or value["byte_count"] <= 0:
                errors.append(f"files byte count is invalid: {path}")
            if not isinstance(value.get("sha256"), str) or not SHA256.fullmatch(
                value["sha256"]
            ):
                errors.append(f"files digest is invalid: {path}")
    return errors


def visit_packet_summary(path: Path) -> dict[str, Any]:
    errors: list[str] = []
    packet: Any = None
    payloads: dict[str, bytes] = {}
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            names = {info.filename for info in infos}
            if names != EXPECTED_FILES or len(infos) != len(EXPECTED_FILES):
                errors.append("archive must contain exactly the nine supported files")
            if any(info.flag_bits & 0x1 for info in infos):
                errors.append("encrypted archive members are unsupported")
            if any(info.file_size > MAX_ARCHIVE_MEMBER_BYTES for info in infos):
                errors.append("archive member exceeds the local safety limit")
            if not errors:
                packet = json.loads(archive.read("visit-packet.json"))
                payloads = {name: archive.read(name) for name in PAYLOAD_MEDIA_TYPES}
    except (OSError, zipfile.BadZipFile, KeyError, UnicodeDecodeError, json.JSONDecodeError) as error:
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
        for role in ("baseline", "followup"):
            component_summary = _component_summary(
                payloads[f"{role}/key-image.json"],
                payloads[f"{role}/key-image.png"],
                payloads[f"{role}/measurements.json"],
            )
            if not component_summary["valid"]:
                component_integrity = False
                errors.extend(
                    f"{role} key image: {message}" for message in component_summary["errors"]
                )
            try:
                component_packets[role] = json.loads(payloads[f"{role}/key-image.json"])
            except (UnicodeDecodeError, json.JSONDecodeError):
                component_integrity = False
            component = component_packets.get(role)
            if (
                not isinstance(component, dict)
                or not isinstance(component.get("display"), dict)
                or component["display"].get("viewport_role") != role
            ):
                component_integrity = False
                errors.append(f"{role} key image has the wrong viewport role")

        observations = packet.get("observations")
        if isinstance(observations, list) and len(observations) == 2:
            for index, role in enumerate(("baseline", "followup")):
                component = component_packets.get(role)
                observation = observations[index]
                if not isinstance(component, dict) or not isinstance(observation, dict):
                    component_integrity = False
                    continue
                evidence = component.get("measurement_evidence", {})
                expected = _observation(
                    role,
                    KeyImageBundle(
                        component,
                        payloads[f"{role}/key-image.json"],
                        payloads[f"{role}/key-image.png"],
                        payloads[f"{role}/measurements.json"],
                    ),
                )
                if observation != expected or not isinstance(evidence, dict):
                    component_integrity = False
            if not component_integrity:
                errors.append("visit observations disagree with embedded key-image evidence")

        if len(component_packets) == 2:
            try:
                expected_pairing = _pairing_values(
                    KeyImageBundle(component_packets["baseline"], b"", b"", b""),
                    KeyImageBundle(component_packets["followup"], b"", b"", b""),
                )
                if packet.get("pairing") != expected_pairing:
                    errors.append("pairing metadata disagrees with embedded key images")
                    component_integrity = False
            except (KeyError, TypeError, ValueError) as error:
                errors.append(f"embedded key images are not a valid longitudinal pair: {error}")
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

    pairing = packet.get("pairing") if isinstance(packet, dict) else None
    observations = packet.get("observations") if isinstance(packet, dict) else None
    measurement_counts = {"baseline": 0, "followup": 0}
    if isinstance(observations, list) and len(observations) == 2:
        for observation in observations:
            if isinstance(observation, dict) and observation.get("timepoint") in measurement_counts:
                count = observation.get("measurement_count")
                if isinstance(count, int) and not isinstance(count, bool):
                    measurement_counts[observation["timepoint"]] = count
    return {
        "valid": not errors,
        "schema_version": packet.get("schema_version") if isinstance(packet, dict) else None,
        "review_status": packet.get("review_status") if isinstance(packet, dict) else None,
        "artifact_type": packet.get("artifact_type") if isinstance(packet, dict) else None,
        "modality": pairing.get("modality") if isinstance(pairing, dict) else None,
        "elapsed_days": pairing.get("elapsed_days") if isinstance(pairing, dict) else None,
        "measurement_counts": measurement_counts,
        "file_integrity": file_integrity,
        "component_integrity": component_integrity,
        "presentation_integrity": presentation_integrity,
        "errors": errors,
    }
