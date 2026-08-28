from __future__ import annotations

import hashlib
import html
import io
import json
import math
import os
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO

from .measurements import measurement_comparison_summary
from .visit_packets import visit_packet_archive_bytes, visit_packet_summary


ArchiveSource = Path | BinaryIO

EXPECTED_FILES = {
    "review-record.json",
    "comparison.json",
    "visit-packet.zip",
    "baseline/key-image.png",
    "followup/key-image.png",
    "review.html",
    "README.txt",
}
PAYLOAD_MEDIA_TYPES = {
    "comparison.json": "application/json",
    "visit-packet.zip": "application/zip",
    "baseline/key-image.png": "image/png",
    "followup/key-image.png": "image/png",
    "review.html": "text/html",
    "README.txt": "text/plain",
}
MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
MAX_MEMBER_BYTES = 128 * 1024 * 1024
MAX_COMPARISON_BYTES = 2 * 1024 * 1024
COMPARISON_REVIEW_TRANSPORT_FILES = {
    "baseline.zip",
    "followup.zip",
    "comparison.json",
}
MAX_COMPARISON_REVIEW_TRANSPORT_BYTES = 196 * 1024 * 1024
MAX_TRANSPORT_KEY_IMAGE_BYTES = 96 * 1024 * 1024
SHA256 = re.compile(r"^[0-9a-f]{64}$")
REVIEW_DECISIONS = {
    "accepted_for_discussion",
    "amendment_requested",
    "rejected",
}
CHECKLIST_VALUES = {
    "same_lesion_identity": {"unreviewed", "confirmed", "uncertain", "not_confirmed"},
    "acquisition_suitability": {"unreviewed", "suitable", "uncertain", "not_suitable"},
    "measurement_placement": {"unreviewed", "accepted", "uncertain", "revision_needed"},
    "response_criteria": {"unreviewed", "selected", "uncertain", "not_applicable"},
}
SELF_ATTESTATION = (
    "I attest that I personally reviewed the linked local evidence within the scope "
    "of my stated role; ScanView has not verified my identity or credentials."
)
AMENDMENT_ATTESTATION = (
    "I attest that I intentionally supplied this amended comparison; ScanView has "
    "not verified my identity or credentials."
)
RECORD_LIMITATIONS = [
    "Reviewer identity and credentials are self-asserted and are not cryptographically verified by ScanView.",
    "The event hash chain detects accidental or partial edits but is not a digital signature and cannot prevent a person from rebuilding an archive.",
    "The source comparison remains an unreviewed arithmetic derivative and never becomes a response category automatically.",
    "Original DICOM instances and the clinical medical record remain authoritative.",
]


@dataclass(frozen=True)
class ReviewComponents:
    visit_bytes: bytes
    visit_packet: dict[str, Any]
    comparison: dict[str, Any]
    comparison_bytes: bytes
    images: dict[str, bytes]
    linkage: dict[str, Any]


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode()


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()


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


def _datetime_value(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _created_at(value: str | None) -> str:
    created = value or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    if not _valid_datetime(created):
        raise ValueError("created_at must be an ISO 8601 date-time with a timezone")
    return created


def _read_source(source: ArchiveSource, maximum: int, label: str) -> bytes:
    if isinstance(source, Path):
        if not source.is_file():
            raise ValueError(f"{label} must be a readable file")
        if source.stat().st_size > maximum:
            raise ValueError(f"{label} exceeds the local safety limit")
        return source.read_bytes()
    source.seek(0)
    content = source.read(maximum + 1)
    source.seek(0)
    if len(content) > maximum:
        raise ValueError(f"{label} exceeds the local safety limit")
    return content


def _strict_json_bytes(content: bytes, label: str) -> tuple[dict[str, Any], bytes]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"{label} contains a duplicate JSON field: {key}")
            result[key] = value
        return result

    try:
        value = json.loads(content, object_pairs_hook=reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is not valid JSON") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return value, _json_bytes(value)


def _safe_text(value: str, label: str, maximum: int, *, multiline: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text")
    normalized = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    forbidden = any(
        ord(character) < 32 and (not multiline or character not in "\n\t")
        for character in normalized
    ) or any(ord(character) == 127 for character in normalized)
    if forbidden:
        raise ValueError(f"{label} contains unsupported control characters")
    if not normalized:
        raise ValueError(f"{label} must not be empty")
    if len(normalized) > maximum:
        raise ValueError(f"{label} must not exceed {maximum} characters")
    if not multiline and any(character in "\n\t" for character in normalized):
        raise ValueError(f"{label} must be a single line")
    return normalized


def _read_visit(visit_source: ArchiveSource) -> tuple[bytes, dict[str, Any], dict[str, bytes], dict[str, Any]]:
    visit_bytes = _read_source(visit_source, MAX_ARCHIVE_BYTES, "visit packet")
    summary = visit_packet_summary(io.BytesIO(visit_bytes))
    if not summary["valid"]:
        raise ValueError(f"visit packet is invalid: {'; '.join(summary['errors'])}")
    try:
        with zipfile.ZipFile(io.BytesIO(visit_bytes)) as archive:
            packet = json.loads(archive.read("visit-packet.json"))
            payloads = {
                "baseline_measurements": archive.read("baseline/measurements.json"),
                "followup_measurements": archive.read("followup/measurements.json"),
                "baseline_image": archive.read("baseline/key-image.png"),
                "followup_image": archive.read("followup/key-image.png"),
            }
            measurements = {
                "baseline": json.loads(payloads["baseline_measurements"]),
                "followup": json.loads(payloads["followup_measurements"]),
            }
    except (zipfile.BadZipFile, KeyError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("visit packet components could not be read") from error
    return visit_bytes, packet, payloads, measurements


def _read_comparison(comparison_source: ArchiveSource) -> tuple[dict[str, Any], bytes]:
    content = _read_source(comparison_source, MAX_COMPARISON_BYTES, "comparison")
    comparison, normalized = _strict_json_bytes(content, "comparison")
    summary = measurement_comparison_summary(comparison)
    if not summary["valid"]:
        raise ValueError(f"comparison is invalid: {'; '.join(summary['errors'])}")
    if not _valid_datetime(comparison.get("created_at")):
        raise ValueError("comparison created_at must include a timezone")
    return comparison, normalized


def _find_measurement(packet: dict[str, Any], tracking_id: str, role: str) -> dict[str, Any]:
    measurements = packet.get("measurements")
    if not isinstance(measurements, list):
        raise ValueError(f"{role} visit measurements are invalid")
    matches = [
        measurement
        for measurement in measurements
        if isinstance(measurement, dict) and measurement.get("tracking_id") == tracking_id
    ]
    if len(matches) != 1:
        raise ValueError(
            f"comparison {role} tracking ID must match exactly one visible visit measurement"
        )
    return matches[0]


def _measurement_values(measurement: dict[str, Any]) -> dict[str, tuple[float, str]]:
    result = measurement["result"]
    measurement_type = measurement["type"]
    if measurement_type == "length":
        return {"length": (float(result["value"]), "mm")}
    if measurement_type == "bidirectional":
        return {
            "long_axis": (float(result["long_axis"]), "mm"),
            "short_axis": (float(result["short_axis"]), "mm"),
            "bidimensional_product": (float(result["product"]), "mm2"),
        }
    return {
        "major_axis": (float(result["major_axis"]), "mm"),
        "minor_axis": (float(result["minor_axis"]), "mm"),
        "elliptical_area": (float(result["area"]), "mm2"),
    }


def _derive_linkage(
    visit_packet: dict[str, Any],
    visit_measurements: dict[str, Any],
    comparison: dict[str, Any],
) -> dict[str, Any]:
    observations = comparison["observations"]
    pairing = comparison["pairing"]
    linked: dict[str, dict[str, Any]] = {}
    source_measurements: dict[str, dict[str, Any]] = {}
    for index, role in enumerate(("baseline", "followup")):
        measurement_id = pairing[f"{role}_measurement_id"]
        measurement = _find_measurement(visit_measurements[role], measurement_id, role)
        observation = observations[index]
        if measurement.get("source") != observation.get("source"):
            raise ValueError(f"comparison {role} source disagrees with the visit measurement")
        if measurement.get("type") != observation.get("measurement_type"):
            raise ValueError(f"comparison {role} type disagrees with the visit measurement")
        visit_observation = visit_packet["observations"][index]
        visit_source = visit_observation["source"]
        if (
            measurement["source"].get("series_id") != visit_source.get("series_id")
            or measurement["source"].get("instance_id") != visit_source.get("instance_id")
        ):
            raise ValueError(f"comparison {role} measurement is not on the visit key image")
        source_measurements[role] = measurement
        linked[role] = {
            "series_id": measurement["source"]["series_id"],
            "instance_id": measurement["source"]["instance_id"],
            "measurement_id": measurement_id,
            "measurement_type": measurement["type"],
        }

    baseline_values = _measurement_values(source_measurements["baseline"])
    followup_values = _measurement_values(source_measurements["followup"])
    for result in comparison["computed_results"]:
        metric = result["metric"]
        if metric not in baseline_values or metric not in followup_values:
            raise ValueError("comparison metric set disagrees with linked visit measurements")
        baseline_value, unit = baseline_values[metric]
        followup_value, followup_unit = followup_values[metric]
        if unit != followup_unit or result["unit"] != unit:
            raise ValueError("comparison units disagree with linked visit measurements")
        if not math.isclose(result["baseline"], baseline_value, rel_tol=0.001, abs_tol=0.001):
            raise ValueError("comparison baseline value disagrees with the visit measurement")
        if not math.isclose(result["followup"], followup_value, rel_tol=0.001, abs_tol=0.001):
            raise ValueError("comparison follow-up value disagrees with the visit measurement")

    visit_pairing = visit_packet["pairing"]
    return {
        "method": "exact_visible_measurement_join",
        "patient_context_match": True,
        "modality": visit_pairing["modality"],
        "baseline": linked["baseline"],
        "followup": linked["followup"],
    }


def _components(
    visit_source: ArchiveSource, comparison_source: ArchiveSource
) -> ReviewComponents:
    visit_bytes, visit_packet, visit_payloads, visit_measurements = _read_visit(visit_source)
    comparison, comparison_bytes = _read_comparison(comparison_source)
    linkage = _derive_linkage(visit_packet, visit_measurements, comparison)
    return ReviewComponents(
        visit_bytes=visit_bytes,
        visit_packet=visit_packet,
        comparison=comparison,
        comparison_bytes=comparison_bytes,
        images={
            "baseline/key-image.png": visit_payloads["baseline_image"],
            "followup/key-image.png": visit_payloads["followup_image"],
        },
        linkage=linkage,
    )


def _ensure_after_source_artifacts(created_at: str, components: ReviewComponents) -> None:
    source_times = (
        components.comparison["created_at"],
        components.visit_packet["created_at"],
    )
    if any(
        _datetime_value(created_at) <= _datetime_value(source_time)
        for source_time in source_times
    ):
        raise ValueError("review created_at must be later than both source artifacts")


def _actor(
    display_name: str,
    role: str,
    organization: str | None,
    *,
    identity_verification: str = "self_asserted_unverified",
) -> dict[str, Any]:
    return {
        "display_name": _safe_text(display_name, "actor display name", 120),
        "role": _safe_text(role, "actor role", 120),
        "organization": (
            _safe_text(organization, "actor organization", 160)
            if organization is not None
            else None
        ),
        "identity_verification": identity_verification,
    }


def _empty_checklist() -> dict[str, str]:
    return {key: "unreviewed" for key in CHECKLIST_VALUES}


def _event_hash(event: dict[str, Any]) -> str:
    without_hash = {key: value for key, value in event.items() if key != "event_sha256"}
    return _digest(_canonical_bytes(without_hash))


def _event(
    *,
    sequence: int,
    event_type: str,
    created_at: str,
    actor: dict[str, Any],
    decision: str,
    checklist: dict[str, str],
    note: str,
    attestation: str,
    prior_event_sha256: str | None,
    parent_archive_sha256: str | None,
    source_comparison_sha256: str,
) -> dict[str, Any]:
    value = {
        "sequence": sequence,
        "event_type": event_type,
        "created_at": created_at,
        "actor": actor,
        "decision": decision,
        "checklist": checklist,
        "note": note,
        "attestation": attestation,
        "prior_event_sha256": prior_event_sha256,
        "parent_archive_sha256": parent_archive_sha256,
        "source_comparison_sha256": source_comparison_sha256,
    }
    value["event_sha256"] = _event_hash(value)
    return value


def _initial_record(components: ReviewComponents, created_at: str) -> dict[str, Any]:
    comparison_digest = _digest(components.comparison_bytes)
    initial_event = _event(
        sequence=1,
        event_type="submitted_for_review",
        created_at=created_at,
        actor=_actor(
            "ScanView local workflow",
            "software",
            None,
            identity_verification="software_generated",
        ),
        decision="unreviewed",
        checklist=_empty_checklist(),
        note="The linked visual and numeric evidence was assembled locally for human review.",
        attestation="Not applicable; this event was generated by local software.",
        prior_event_sha256=None,
        parent_archive_sha256=None,
        source_comparison_sha256=comparison_digest,
    )
    return {
        "schema_version": "1.0.0",
        "created_at": created_at,
        "review_status": "unreviewed",
        "artifact_type": "comparison_review_record",
        "parent_archive_sha256": None,
        "source_artifacts": {
            "comparison": {
                "path": "comparison.json",
                "byte_count": len(components.comparison_bytes),
                "sha256": comparison_digest,
            },
            "visit_packet": {
                "path": "visit-packet.zip",
                "byte_count": len(components.visit_bytes),
                "sha256": _digest(components.visit_bytes),
            },
        },
        "linkage": components.linkage,
        "events": [initial_event],
        "limitations": RECORD_LIMITATIONS.copy(),
        "implementation": {
            "name": "ScanView local comparison-review assembler",
            "version": "0.1.0",
        },
        "files": {},
    }


def _format_dicom_date(value: str) -> str:
    return f"{value[:4]}-{value[4:6]}-{value[6:8]}" if len(value) == 8 else value


def _format_metric(value: float, unit: str) -> str:
    return f"{value:.1f} {html.escape(unit)}"


def _format_percent(value: float | None) -> str:
    return "undefined" if value is None else f"{value:.1f}%"


def _render_review_html(
    record: dict[str, Any], comparison: dict[str, Any], visit_packet: dict[str, Any]
) -> bytes:
    observations = visit_packet["observations"]
    pairing = visit_packet["pairing"]
    status = record["review_status"].replace("_", " ").upper()
    metric_rows = "".join(
        "<tr>"
        f"<td>{html.escape(result['metric'].replace('_', ' '))}</td>"
        f"<td>{_format_metric(result['baseline'], result['unit'])}</td>"
        f"<td>{_format_metric(result['followup'], result['unit'])}</td>"
        f"<td>{_format_metric(result['absolute_change'], result['unit'])}</td>"
        f"<td>{_format_percent(result.get('percent_change'))}</td>"
        "</tr>"
        for result in comparison["computed_results"]
    )

    def image_card(index: int, role: str) -> str:
        source = observations[index]["source"]
        return f"""
        <article class="image-card">
          <header><span>{role.upper()}</span><strong>{html.escape(_format_dicom_date(source['acquisition_date']))}</strong></header>
          <img src="{role}/key-image.png" alt="{role} unreviewed derived display key image">
          <p>{html.escape(str(source['series_description']))} · {html.escape(str(source['modality']))} · source slice {observations[index]['display']['stack_position']} / {observations[index]['display']['stack_count']}</p>
        </article>"""

    event_cards = []
    for event in record["events"]:
        actor = event["actor"]
        organization = f" · {html.escape(actor['organization'])}" if actor["organization"] else ""
        checklist = "".join(
            f"<li><span>{html.escape(key.replace('_', ' '))}</span><strong>{html.escape(value.replace('_', ' '))}</strong></li>"
            for key, value in event["checklist"].items()
        )
        note_label = (
            "Local workflow note"
            if event["event_type"] == "submitted_for_review"
            else "Person-entered note"
        )
        event_cards.append(
            f"""
            <article class="event">
              <header><strong>#{event['sequence']} · {html.escape(event['event_type'].replace('_', ' '))}</strong><time>{html.escape(event['created_at'])}</time></header>
              <p class="actor">{html.escape(actor['display_name'])} · {html.escape(actor['role'])}{organization} · {html.escape(actor['identity_verification'].replace('_', ' '))}</p>
              <p><strong>Decision:</strong> {html.escape(event['decision'].replace('_', ' '))}</p>
              <ul>{checklist}</ul>
              <p class="note"><strong>{note_label}:</strong><br>{html.escape(event['note']).replace(chr(10), '<br>')}</p>
              <p class="attestation">{html.escape(event['attestation'])}</p>
            </article>"""
        )

    lesion_label = comparison["pairing"].get("lesion_label", "Working lesion pair")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="referrer" content="no-referrer">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'self'; style-src 'unsafe-inline'">
  <title>ScanView local comparison review</title>
  <style>
    :root {{ color-scheme: dark; font-family: Inter, system-ui, sans-serif; background: #07110f; color: #e7f3ef; }}
    * {{ box-sizing: border-box; }} body {{ margin: 0; padding: 24px; }} main {{ max-width: 1500px; margin: auto; }}
    h1 {{ margin: 0 0 8px; font-size: 26px; }} h2 {{ margin-top: 26px; }}
    .banner {{ border: 1px solid #e8b35c; background: #291d09; color: #ffe4ac; padding: 12px 14px; margin: 16px 0; font-weight: 700; }}
    .context, .safety, .actor, .attestation {{ color: #a9bdb7; line-height: 1.5; }}
    .grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }}
    .image-card, .event, .metrics {{ border: 1px solid #29433c; background: #0b1916; padding: 12px; min-width: 0; }}
    .image-card header, .event header {{ display: flex; justify-content: space-between; gap: 12px; color: #7de9ca; }}
    img {{ display: block; width: 100%; height: auto; margin-top: 10px; background: #000; border: 1px solid #213a34; }}
    table {{ width: 100%; border-collapse: collapse; }} th, td {{ border-bottom: 1px solid #29433c; padding: 8px; text-align: left; }} th {{ color: #8ba49d; }}
    .events {{ display: grid; gap: 12px; }} .event ul {{ list-style: none; padding: 0; display: grid; grid-template-columns: repeat(2, 1fr); gap: 6px 16px; }} .event li {{ display: flex; justify-content: space-between; gap: 10px; }}
    .note {{ white-space: normal; }} .attestation {{ font-size: 12px; border-top: 1px solid #29433c; padding-top: 8px; }}
    footer {{ margin-top: 28px; color: #93aaa3; font-size: 12px; }}
    @media (max-width: 850px) {{ .grid {{ grid-template-columns: 1fr; }} .event ul {{ grid-template-columns: 1fr; }} }}
    @media print {{ :root {{ color-scheme: light; background: white; color: black; }} body {{ padding: 8mm; }} .image-card, .event, .metrics {{ background: white; border-color: #777; }} .banner {{ color: black; background: #fff4d7; }} .context, .safety, .actor, .attestation, footer {{ color: #444; }} }}
  </style>
</head>
<body><main>
  <h1>ScanView local comparison review</h1>
  <div class="banner">{status} · SELF-ATTESTED IDENTITY IS NOT CRYPTOGRAPHICALLY VERIFIED · NO RESPONSE CONCLUSION GENERATED BY SCANVIEW</div>
  <p class="context">{html.escape(str(lesion_label))} · explicitly linked {html.escape(pairing['modality'])} evidence · {_format_dicom_date(pairing['baseline_acquisition_date'])} to {_format_dicom_date(pairing['followup_acquisition_date'])} · {pairing['elapsed_days']} days.</p>
  <div class="grid">{image_card(0, 'baseline')}{image_card(1, 'followup')}</div>
  <h2>Source-linked arithmetic</h2>
  <div class="metrics"><table><thead><tr><th>Metric</th><th>Baseline</th><th>Follow-up</th><th>Absolute change</th><th>Percent change</th></tr></thead><tbody>{metric_rows}</tbody></table></div>
  <p class="safety">The arithmetic comparison remains an unreviewed derivative. It does not prove same-lesion identity, acquisition suitability, treatment response, progression, or clinical meaning.</p>
  <h2>Review and amendment history</h2>
  <div class="events">{''.join(event_cards)}</div>
  <footer>Original DICOM instances and the clinical medical record remain authoritative. Keep ancestor review archives to preserve parent-archive verification. Validate locally with scanview-agent before use.</footer>
</main></body></html>\n""".encode()


def _render_readme() -> bytes:
    return (
        "ScanView local comparison review packet\n"
        "\n"
        "1. Extract the entire ZIP into one local folder.\n"
        "2. Open review.html locally, or print it for a clinical conversation.\n"
        "3. Keep all files and ancestor review archives together.\n"
        "4. Validate locally: scanview-agent validate-comparison-review <archive.zip>\n"
        "\n"
        "Reviewer names, roles, organizations, checklist choices, and notes are self-asserted.\n"
        "ScanView does not authenticate clinical credentials or create a digital signature.\n"
        "The numeric comparison remains unreviewed and ScanView generates no response conclusion.\n"
        "Original DICOM and the clinical medical record remain authoritative.\n"
        "Treat this archive as sensitive medical data. No external service is required.\n"
    ).encode()


def _file_manifest(payloads: dict[str, bytes]) -> dict[str, dict[str, Any]]:
    return {
        path: {
            "media_type": PAYLOAD_MEDIA_TYPES[path],
            "byte_count": len(content),
            "sha256": _digest(content),
        }
        for path, content in sorted(payloads.items())
    }


def _payloads(record: dict[str, Any], components: ReviewComponents) -> dict[str, bytes]:
    payloads = {
        "comparison.json": components.comparison_bytes,
        "visit-packet.zip": components.visit_bytes,
        **components.images,
        "README.txt": _render_readme(),
    }
    payloads["review.html"] = _render_review_html(
        record, components.comparison, components.visit_packet
    )
    return payloads


def _archive_bytes(record: dict[str, Any], components: ReviewComponents) -> bytes:
    payloads = _payloads(record, components)
    record["files"] = _file_manifest(payloads)
    output = io.BytesIO()
    with zipfile.ZipFile(
        output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
    ) as archive:
        archive.writestr("review-record.json", _json_bytes(record))
        for path, content in sorted(payloads.items()):
            archive.writestr(path, content)
    return output.getvalue()


def comparison_review_archive_bytes(
    visit_source: ArchiveSource,
    comparison_source: ArchiveSource,
    *,
    created_at: str | None = None,
) -> bytes:
    components = _components(visit_source, comparison_source)
    created = _created_at(created_at)
    _ensure_after_source_artifacts(created, components)
    record = _initial_record(components, created)
    return _archive_bytes(record, components)


def comparison_review_from_transport(
    transport_bytes: bytes,
    *,
    visit_created_at: str | None = None,
    review_created_at: str | None = None,
) -> bytes:
    if (
        not transport_bytes
        or len(transport_bytes) > MAX_COMPARISON_REVIEW_TRANSPORT_BYTES
    ):
        raise ValueError("comparison-review request exceeds the local safety limit")
    try:
        with zipfile.ZipFile(io.BytesIO(transport_bytes)) as archive:
            infos = archive.infolist()
            names = {info.filename for info in infos}
            if names != COMPARISON_REVIEW_TRANSPORT_FILES or len(infos) != 3:
                raise ValueError(
                    "comparison-review request must contain exactly baseline.zip, "
                    "followup.zip, and comparison.json"
                )
            if any(info.flag_bits & 0x1 for info in infos):
                raise ValueError("encrypted comparison-review request members are unsupported")
            info_by_name = {info.filename: info for info in infos}
            if any(
                info_by_name[path].file_size > MAX_TRANSPORT_KEY_IMAGE_BYTES
                for path in ("baseline.zip", "followup.zip")
            ) or info_by_name["comparison.json"].file_size > MAX_COMPARISON_BYTES:
                raise ValueError(
                    "comparison-review request member exceeds the local safety limit"
                )
            if (
                sum(info.file_size for info in infos)
                > MAX_COMPARISON_REVIEW_TRANSPORT_BYTES
            ):
                raise ValueError(
                    "expanded comparison-review request exceeds the local safety limit"
                )
            baseline_bytes = archive.read("baseline.zip")
            followup_bytes = archive.read("followup.zip")
            comparison_bytes = archive.read("comparison.json")
    except (OSError, zipfile.BadZipFile, KeyError) as error:
        raise ValueError(
            f"comparison-review request could not be read: {type(error).__name__}"
        ) from error

    visit_bytes = visit_packet_archive_bytes(
        io.BytesIO(baseline_bytes),
        io.BytesIO(followup_bytes),
        created_at=visit_created_at,
    )
    payload = comparison_review_archive_bytes(
        io.BytesIO(visit_bytes),
        io.BytesIO(comparison_bytes),
        created_at=review_created_at,
    )
    summary = comparison_review_summary(io.BytesIO(payload))
    if not summary["valid"]:
        raise ValueError("assembled comparison review failed local integrity validation")
    return payload


def _write_new_archive(output: Path, archive_bytes: bytes) -> None:
    if output.exists():
        raise ValueError("review output already exists; use a new path to preserve history")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.{os.getpid()}.tmp")
    try:
        temporary.write_bytes(archive_bytes)
        temporary.chmod(0o600)
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)


def write_comparison_review(
    visit_path: Path,
    comparison_path: Path,
    output: Path,
    *,
    created_at: str | None = None,
) -> dict[str, Any]:
    archive_bytes = comparison_review_archive_bytes(
        visit_path, comparison_path, created_at=created_at
    )
    _write_new_archive(output, archive_bytes)
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        return json.loads(archive.read("review-record.json"))


def _validate_actor(actor: Any, prefix: str, errors: list[str]) -> None:
    expected = {"display_name", "role", "organization", "identity_verification"}
    if not isinstance(actor, dict) or set(actor) != expected:
        errors.append(f"{prefix}.actor is invalid")
        return
    for key, maximum in (("display_name", 120), ("role", 120)):
        try:
            if _safe_text(actor.get(key), f"{prefix}.actor.{key}", maximum) != actor.get(key):
                errors.append(f"{prefix}.actor.{key} must already be normalized")
        except ValueError as error:
            errors.append(str(error))
    organization = actor.get("organization")
    if organization is not None:
        try:
            if _safe_text(organization, f"{prefix}.actor.organization", 160) != organization:
                errors.append(f"{prefix}.actor.organization must already be normalized")
        except ValueError as error:
            errors.append(str(error))
    if actor.get("identity_verification") not in {
        "software_generated",
        "self_asserted_unverified",
    }:
        errors.append(f"{prefix}.actor.identity_verification is invalid")


def _validate_events(record: dict[str, Any]) -> tuple[list[str], bool]:
    errors: list[str] = []
    events = record.get("events")
    if not isinstance(events, list) or not events:
        return ["events must be a non-empty array"], False
    expected_keys = {
        "sequence",
        "event_type",
        "created_at",
        "actor",
        "decision",
        "checklist",
        "note",
        "attestation",
        "prior_event_sha256",
        "parent_archive_sha256",
        "source_comparison_sha256",
        "event_sha256",
    }
    prior_hash: str | None = None
    prior_time: datetime | None = None
    for index, event in enumerate(events):
        prefix = f"events[{index}]"
        if not isinstance(event, dict) or set(event) != expected_keys:
            errors.append(f"{prefix} is invalid")
            continue
        if event.get("sequence") != index + 1:
            errors.append(f"{prefix}.sequence is invalid")
        created = event.get("created_at")
        if not _valid_datetime(created):
            errors.append(f"{prefix}.created_at is invalid")
        else:
            current_time = _datetime_value(created)
            if prior_time is not None and current_time <= prior_time:
                errors.append("review event times must be strictly increasing")
            prior_time = current_time
        _validate_actor(event.get("actor"), prefix, errors)
        checklist = event.get("checklist")
        if not isinstance(checklist, dict) or set(checklist) != set(CHECKLIST_VALUES):
            errors.append(f"{prefix}.checklist is invalid")
        else:
            for key, allowed in CHECKLIST_VALUES.items():
                if checklist.get(key) not in allowed:
                    errors.append(f"{prefix}.checklist.{key} is invalid")
        event_type = event.get("event_type")
        decision = event.get("decision")
        actor = event.get("actor")
        if index == 0:
            if event_type != "submitted_for_review" or decision != "unreviewed":
                errors.append("the first event must submit an unreviewed artifact")
            if checklist != _empty_checklist():
                errors.append("the first event checklist must remain unreviewed")
            if not isinstance(actor, dict) or actor.get("identity_verification") != "software_generated":
                errors.append("the first event must be software generated")
        elif event_type == "clinician_review":
            if decision not in REVIEW_DECISIONS:
                errors.append(f"{prefix}.decision is invalid")
            if not isinstance(actor, dict) or actor.get("identity_verification") != "self_asserted_unverified":
                errors.append(f"{prefix} reviewer identity must be self asserted")
            if event.get("attestation") != SELF_ATTESTATION:
                errors.append(f"{prefix}.attestation is invalid")
            if checklist == _empty_checklist():
                errors.append(f"{prefix}.checklist must record human choices")
            if decision == "accepted_for_discussion" and isinstance(checklist, dict):
                required = {
                    "same_lesion_identity": "confirmed",
                    "acquisition_suitability": "suitable",
                    "measurement_placement": "accepted",
                }
                if any(checklist.get(key) != value for key, value in required.items()):
                    errors.append(
                        "accepted_for_discussion requires confirmed lesion identity, suitable acquisition, and accepted placement"
                    )
        elif event_type == "comparison_amended":
            if decision != "unreviewed" or checklist != _empty_checklist():
                errors.append(f"{prefix} amendment must reset review state")
            if not isinstance(actor, dict) or actor.get("identity_verification") != "self_asserted_unverified":
                errors.append(f"{prefix} amendment identity must be self asserted")
            if event.get("attestation") != AMENDMENT_ATTESTATION:
                errors.append(f"{prefix}.attestation is invalid")
        elif index != 0:
            errors.append(f"{prefix}.event_type is invalid")
        try:
            _safe_text(event.get("note"), f"{prefix}.note", 4000, multiline=True)
        except ValueError as error:
            errors.append(str(error))
        if event.get("prior_event_sha256") != prior_hash:
            errors.append(f"{prefix}.prior_event_sha256 is invalid")
        event_parent = event.get("parent_archive_sha256")
        if index == 0:
            if event_parent is not None:
                errors.append("the first event cannot identify a parent archive")
        elif not isinstance(event_parent, str) or not SHA256.fullmatch(event_parent):
            errors.append(f"{prefix}.parent_archive_sha256 is invalid")
        source_digest = event.get("source_comparison_sha256")
        if not isinstance(source_digest, str) or not SHA256.fullmatch(source_digest):
            errors.append(f"{prefix}.source_comparison_sha256 is invalid")
        expected_hash = _event_hash(event)
        if event.get("event_sha256") != expected_hash:
            errors.append(f"{prefix}.event_sha256 is invalid")
        prior_hash = event.get("event_sha256")
    return errors, not errors


def _derived_review_status(events: list[dict[str, Any]]) -> str:
    latest = events[-1]
    return latest["decision"] if latest["event_type"] == "clinician_review" else "unreviewed"


def _validate_record_shape(record: Any) -> tuple[list[str], bool]:
    errors: list[str] = []
    required = {
        "schema_version",
        "created_at",
        "review_status",
        "artifact_type",
        "parent_archive_sha256",
        "source_artifacts",
        "linkage",
        "events",
        "limitations",
        "implementation",
        "files",
    }
    if not isinstance(record, dict):
        return ["review record must be a JSON object"], False
    if set(record) != required:
        errors.append("review record fields are incomplete or unsupported")
    if record.get("schema_version") != "1.0.0":
        errors.append("schema_version must be 1.0.0")
    if not _valid_datetime(record.get("created_at")):
        errors.append("created_at must be an ISO 8601 date-time")
    if record.get("artifact_type") != "comparison_review_record":
        errors.append("artifact_type must be comparison_review_record")
    parent = record.get("parent_archive_sha256")
    if parent is not None and (not isinstance(parent, str) or not SHA256.fullmatch(parent)):
        errors.append("parent_archive_sha256 is invalid")

    source_artifacts = record.get("source_artifacts")
    if not isinstance(source_artifacts, dict) or set(source_artifacts) != {
        "comparison",
        "visit_packet",
    }:
        errors.append("source_artifacts is invalid")
    else:
        for key, expected_path in (
            ("comparison", "comparison.json"),
            ("visit_packet", "visit-packet.zip"),
        ):
            artifact = source_artifacts.get(key)
            if not isinstance(artifact, dict) or set(artifact) != {
                "path",
                "byte_count",
                "sha256",
            }:
                errors.append(f"source_artifacts.{key} is invalid")
                continue
            if artifact.get("path") != expected_path:
                errors.append(f"source_artifacts.{key}.path is invalid")
            byte_count = artifact.get("byte_count")
            if not isinstance(byte_count, int) or isinstance(byte_count, bool) or byte_count <= 0:
                errors.append(f"source_artifacts.{key}.byte_count is invalid")
            digest = artifact.get("sha256")
            if not isinstance(digest, str) or not SHA256.fullmatch(digest):
                errors.append(f"source_artifacts.{key}.sha256 is invalid")

    linkage = record.get("linkage")
    if not isinstance(linkage, dict) or set(linkage) != {
        "method",
        "patient_context_match",
        "modality",
        "baseline",
        "followup",
    }:
        errors.append("linkage is invalid")
    else:
        if linkage.get("method") != "exact_visible_measurement_join":
            errors.append("linkage.method is invalid")
        if linkage.get("patient_context_match") is not True:
            errors.append("linkage must use a matching patient context")
        if linkage.get("modality") not in {"MR", "CT"}:
            errors.append("linkage.modality is invalid")
        for role in ("baseline", "followup"):
            value = linkage.get(role)
            if not isinstance(value, dict) or set(value) != {
                "series_id",
                "instance_id",
                "measurement_id",
                "measurement_type",
            }:
                errors.append(f"linkage.{role} is invalid")

    event_errors, event_integrity = _validate_events(record)
    errors.extend(event_errors)
    events = record.get("events")
    if isinstance(events, list) and events:
        if record.get("created_at") != events[0].get("created_at"):
            errors.append("created_at must match the first event")
        try:
            expected_status = _derived_review_status(events)
            if record.get("review_status") != expected_status:
                errors.append("review_status disagrees with the latest event")
        except (KeyError, TypeError):
            pass
        if len(events) == 1 and parent is not None:
            errors.append("an initial review packet cannot have a parent archive")
        if len(events) > 1 and parent is None:
            errors.append("a derived review packet must identify its parent archive")
        if record.get("parent_archive_sha256") != events[-1].get(
            "parent_archive_sha256"
        ):
            errors.append("parent_archive_sha256 disagrees with the latest event")
    if record.get("review_status") not in {"unreviewed", *REVIEW_DECISIONS}:
        errors.append("review_status is invalid")
    if record.get("limitations") != RECORD_LIMITATIONS:
        errors.append("limitations are incomplete or unsupported")
    if record.get("implementation") != {
        "name": "ScanView local comparison-review assembler",
        "version": "0.1.0",
    }:
        errors.append("implementation is unsupported")
    files = record.get("files")
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
            count = value.get("byte_count")
            if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
                errors.append(f"files byte count is invalid: {path}")
            digest = value.get("sha256")
            if not isinstance(digest, str) or not SHA256.fullmatch(digest):
                errors.append(f"files digest is invalid: {path}")
    return errors, event_integrity


def comparison_review_summary(source: ArchiveSource) -> dict[str, Any]:
    errors: list[str] = []
    record: Any = None
    comparison: Any = None
    visit_packet: Any = None
    payloads: dict[str, bytes] = {}
    file_integrity = False
    source_integrity = False
    linkage_integrity = False
    presentation_integrity = False
    event_integrity = False
    try:
        archive_bytes = _read_source(source, MAX_ARCHIVE_BYTES, "comparison review packet")
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            infos = archive.infolist()
            names = {info.filename for info in infos}
            if names != EXPECTED_FILES or len(infos) != len(EXPECTED_FILES):
                errors.append("archive must contain exactly the seven supported files")
            if any(info.flag_bits & 0x1 for info in infos):
                errors.append("encrypted archive members are unsupported")
            if any(info.file_size > MAX_MEMBER_BYTES for info in infos):
                errors.append("archive member exceeds the local safety limit")
            if sum(info.file_size for info in infos) > MAX_ARCHIVE_BYTES:
                errors.append("expanded archive exceeds the local safety limit")
            if not errors:
                record, _ = _strict_json_bytes(
                    archive.read("review-record.json"), "review record"
                )
                comparison, _ = _strict_json_bytes(
                    archive.read("comparison.json"), "comparison"
                )
                payloads = {path: archive.read(path) for path in PAYLOAD_MEDIA_TYPES}
                with zipfile.ZipFile(io.BytesIO(payloads["visit-packet.zip"])) as visit_archive:
                    visit_packet = json.loads(visit_archive.read("visit-packet.json"))
    except (
        OSError,
        ValueError,
        zipfile.BadZipFile,
        KeyError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as error:
        errors.append(f"archive could not be read: {type(error).__name__}")

    if record is not None:
        shape_errors, event_integrity = _validate_record_shape(record)
        errors.extend(shape_errors)
    if isinstance(record, dict) and payloads:
        files = record.get("files")
        if isinstance(files, dict):
            file_integrity = all(
                isinstance(files.get(path), dict)
                and files[path].get("byte_count") == len(content)
                and files[path].get("sha256") == _digest(content)
                for path, content in payloads.items()
            )
        if not file_integrity:
            errors.append("one or more payload digests or byte counts disagree")
        source_artifacts = record.get("source_artifacts")
        if isinstance(source_artifacts, dict):
            source_integrity = all(
                isinstance(source_artifacts.get(key), dict)
                and source_artifacts[key].get("byte_count") == len(payloads[path])
                and source_artifacts[key].get("sha256") == _digest(payloads[path])
                for key, path in (
                    ("comparison", "comparison.json"),
                    ("visit_packet", "visit-packet.zip"),
                )
            )
        if not source_integrity:
            errors.append("source artifact anchors disagree with embedded files")

        comparison_summary = measurement_comparison_summary(comparison)
        visit_summary = visit_packet_summary(io.BytesIO(payloads["visit-packet.zip"]))
        if not comparison_summary["valid"]:
            errors.extend(
                f"comparison: {message}" for message in comparison_summary["errors"]
            )
        elif not _valid_datetime(comparison.get("created_at")):
            errors.append("comparison created_at must include a timezone")
        if not visit_summary["valid"]:
            errors.extend(f"visit packet: {message}" for message in visit_summary["errors"])
        if comparison_summary["valid"] and visit_summary["valid"]:
            try:
                with zipfile.ZipFile(io.BytesIO(payloads["visit-packet.zip"])) as visit_archive:
                    visit_measurements = {
                        role: json.loads(visit_archive.read(f"{role}/measurements.json"))
                        for role in ("baseline", "followup")
                    }
                    nested_images = {
                        f"{role}/key-image.png": visit_archive.read(f"{role}/key-image.png")
                        for role in ("baseline", "followup")
                    }
                expected_linkage = _derive_linkage(
                    visit_packet, visit_measurements, comparison
                )
                linkage_integrity = record.get("linkage") == expected_linkage and all(
                    payloads[path] == content for path, content in nested_images.items()
                )
            except (KeyError, TypeError, ValueError, zipfile.BadZipFile, json.JSONDecodeError) as error:
                errors.append(f"source linkage could not be verified: {error}")
            if not linkage_integrity:
                errors.append("review linkage or displayed images disagree with embedded evidence")
        try:
            presentation_integrity = (
                payloads["review.html"]
                == _render_review_html(record, comparison, visit_packet)
                and payloads["README.txt"] == _render_readme()
            )
        except (KeyError, TypeError, IndexError):
            presentation_integrity = False
        if not presentation_integrity:
            errors.append("review presentation does not match the local static template")
        events = record.get("events")
        current_digest = _digest(payloads["comparison.json"])
        if (
            not isinstance(events, list)
            or not events
            or events[-1].get("source_comparison_sha256") != current_digest
        ):
            event_integrity = False
            errors.append("latest review event does not anchor the embedded comparison")
        if (
            isinstance(events, list)
            and events
            and _valid_datetime(events[-1].get("created_at"))
            and _valid_datetime(comparison.get("created_at"))
            and _datetime_value(events[-1]["created_at"])
            <= _datetime_value(comparison["created_at"])
        ):
            event_integrity = False
            errors.append("latest review event must be later than the embedded comparison")
        if (
            isinstance(events, list)
            and events
            and _valid_datetime(events[0].get("created_at"))
            and _valid_datetime(visit_packet.get("created_at"))
            and _datetime_value(events[0]["created_at"])
            <= _datetime_value(visit_packet["created_at"])
        ):
            event_integrity = False
            errors.append("initial review event must be later than the embedded visit packet")

    events = record.get("events") if isinstance(record, dict) else None
    linkage = record.get("linkage") if isinstance(record, dict) else None
    return {
        "valid": not errors,
        "schema_version": record.get("schema_version") if isinstance(record, dict) else None,
        "review_status": record.get("review_status") if isinstance(record, dict) else None,
        "artifact_type": record.get("artifact_type") if isinstance(record, dict) else None,
        "event_count": len(events) if isinstance(events, list) else 0,
        "latest_event_type": (
            events[-1].get("event_type")
            if isinstance(events, list) and events and isinstance(events[-1], dict)
            else None
        ),
        "modality": linkage.get("modality") if isinstance(linkage, dict) else None,
        "parent_archive_link_present": isinstance(record, dict)
        and record.get("parent_archive_sha256") is not None,
        "file_integrity": file_integrity,
        "source_integrity": source_integrity,
        "linkage_integrity": linkage_integrity,
        "event_integrity": event_integrity,
        "presentation_integrity": presentation_integrity,
        "errors": errors,
    }


def _load_valid_review(path: Path) -> tuple[bytes, dict[str, Any], ReviewComponents]:
    archive_bytes = _read_source(path, MAX_ARCHIVE_BYTES, "comparison review packet")
    summary = comparison_review_summary(io.BytesIO(archive_bytes))
    if not summary["valid"]:
        raise ValueError(f"comparison review packet is invalid: {'; '.join(summary['errors'])}")
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        record = json.loads(archive.read("review-record.json"))
        visit_bytes = archive.read("visit-packet.zip")
        comparison_bytes = archive.read("comparison.json")
    components = _components(io.BytesIO(visit_bytes), io.BytesIO(comparison_bytes))
    return archive_bytes, record, components


def _next_time(record: dict[str, Any], created_at: str | None) -> str:
    created = _created_at(created_at)
    if _datetime_value(created) <= _datetime_value(record["events"][-1]["created_at"]):
        raise ValueError("new review events must have a later created_at time")
    return created


def append_comparison_review(
    source: Path,
    output: Path,
    *,
    reviewer_name: str,
    reviewer_role: str,
    organization: str | None,
    decision: str,
    same_lesion_identity: str,
    acquisition_suitability: str,
    measurement_placement: str,
    response_criteria: str,
    note: str,
    attest: bool,
    created_at: str | None = None,
) -> dict[str, Any]:
    if not attest:
        raise ValueError("--attest is required for a self-asserted review event")
    if decision not in REVIEW_DECISIONS:
        raise ValueError("review decision is unsupported")
    checklist = {
        "same_lesion_identity": same_lesion_identity,
        "acquisition_suitability": acquisition_suitability,
        "measurement_placement": measurement_placement,
        "response_criteria": response_criteria,
    }
    for key, value in checklist.items():
        if value not in CHECKLIST_VALUES[key] - {"unreviewed"}:
            raise ValueError(f"{key} review choice is unsupported")
    if decision == "accepted_for_discussion":
        required = {
            "same_lesion_identity": "confirmed",
            "acquisition_suitability": "suitable",
            "measurement_placement": "accepted",
        }
        if any(checklist[key] != value for key, value in required.items()):
            raise ValueError(
                "accepted_for_discussion requires confirmed lesion identity, suitable acquisition, and accepted placement"
            )
    archive_bytes, record, components = _load_valid_review(source)
    created = _next_time(record, created_at)
    actor = _actor(reviewer_name, reviewer_role, organization)
    parent_digest = _digest(archive_bytes)
    event = _event(
        sequence=len(record["events"]) + 1,
        event_type="clinician_review",
        created_at=created,
        actor=actor,
        decision=decision,
        checklist=checklist,
        note=_safe_text(note, "review note", 4000, multiline=True),
        attestation=SELF_ATTESTATION,
        prior_event_sha256=record["events"][-1]["event_sha256"],
        parent_archive_sha256=parent_digest,
        source_comparison_sha256=_digest(components.comparison_bytes),
    )
    record["events"].append(event)
    record["review_status"] = decision
    record["parent_archive_sha256"] = parent_digest
    output_bytes = _archive_bytes(record, components)
    _write_new_archive(output, output_bytes)
    return record


def amend_comparison_review(
    source: Path,
    comparison_path: Path,
    output: Path,
    *,
    actor_name: str,
    actor_role: str,
    organization: str | None,
    reason: str,
    attest: bool,
    created_at: str | None = None,
) -> dict[str, Any]:
    if not attest:
        raise ValueError("--attest is required for a self-asserted amendment")
    archive_bytes, record, existing_components = _load_valid_review(source)
    comparison, comparison_bytes = _read_comparison(comparison_path)
    with zipfile.ZipFile(io.BytesIO(existing_components.visit_bytes)) as visit_archive:
        visit_measurements = {
            role: json.loads(visit_archive.read(f"{role}/measurements.json"))
            for role in ("baseline", "followup")
        }
    linkage = _derive_linkage(
        existing_components.visit_packet, visit_measurements, comparison
    )
    if comparison_bytes == existing_components.comparison_bytes:
        raise ValueError("amended comparison must differ from the current comparison")
    components = ReviewComponents(
        visit_bytes=existing_components.visit_bytes,
        visit_packet=existing_components.visit_packet,
        comparison=comparison,
        comparison_bytes=comparison_bytes,
        images=existing_components.images,
        linkage=linkage,
    )
    created = _next_time(record, created_at)
    if _datetime_value(created) <= _datetime_value(comparison["created_at"]):
        raise ValueError("amendment event must be later than the amended comparison")
    parent_digest = _digest(archive_bytes)
    event = _event(
        sequence=len(record["events"]) + 1,
        event_type="comparison_amended",
        created_at=created,
        actor=_actor(actor_name, actor_role, organization),
        decision="unreviewed",
        checklist=_empty_checklist(),
        note=_safe_text(reason, "amendment reason", 4000, multiline=True),
        attestation=AMENDMENT_ATTESTATION,
        prior_event_sha256=record["events"][-1]["event_sha256"],
        parent_archive_sha256=parent_digest,
        source_comparison_sha256=_digest(comparison_bytes),
    )
    record["events"].append(event)
    record["review_status"] = "unreviewed"
    record["parent_archive_sha256"] = parent_digest
    record["source_artifacts"]["comparison"] = {
        "path": "comparison.json",
        "byte_count": len(comparison_bytes),
        "sha256": _digest(comparison_bytes),
    }
    record["linkage"] = linkage
    output_bytes = _archive_bytes(record, components)
    _write_new_archive(output, output_bytes)
    return record
