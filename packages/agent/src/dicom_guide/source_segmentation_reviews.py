from __future__ import annotations

import hashlib
import html
import io
import json
import math
import os
import re
import stat
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO

from .catalog import build_catalog
from .source_segmentations import (
    build_source_segmentation_catalog,
    registry_segmentation_source_loader,
)


SCHEMA_VERSION = "1.0.0"
ARTIFACT_TYPE = "dicom-guide.source-segmentation-review"
REQUEST_ARTIFACT_TYPE = "dicom-guide.source-segmentation-review-request"
SUMMARY_ARTIFACT_TYPE = "dicom-guide.source-segmentation-review-summary"
REQUEST_MEDIA_TYPE = "application/vnd.dicom-guide.source-segmentation-review-request+json"
MAX_REQUEST_BYTES = 32 * 1024
MAX_SEGMENTATION_BYTES = 256 * 1024 * 1024
MAX_MASK_BYTES = 128 * 1024 * 1024
MAX_ARCHIVE_BYTES = 420 * 1024 * 1024
MAX_TEXT_BYTES = 2 * 1024 * 1024
EXPECTED_FILES = {
    "review.json",
    "source-segmentation.dcm",
    "mask.bin",
    "review.html",
    "README.txt",
}
SHA256 = re.compile(r"^[0-9a-f]{64}$")
OPAQUE_ID = re.compile(r"^(?:study|series|instance|frame|patient)_[0-9a-f]{20}$")
REVIEW_ID = re.compile(r"^source_seg_review_[0-9a-f-]{36}$")
ROLES = {
    "radiologist",
    "neuro_oncologist",
    "neurosurgeon",
    "medical_physicist",
    "other_qualified_clinician",
}
DECISIONS = {"accepted_for_discussion", "revision_requested", "rejected"}
SUITABILITY = {"suitable", "uncertain", "not_suitable"}
CHECKLIST_KEYS = {
    "original_images_reviewed",
    "full_source_boundary_reviewed",
    "all_three_planes_reviewed",
    "mask_to_source_alignment_reviewed",
    "source_segment_metadata_treated_as_unverified",
    "creator_and_algorithm_treated_as_unverified",
    "motion_considered",
    "partial_volume_considered",
    "treatment_effect_considered",
    "acquisition_protocol_considered",
}
ATTESTATION = (
    "I attest that I personally reviewed the complete source-carried DICOM SEG boundary "
    "on the original local source images within the scope of my stated role. I treated "
    "the source label, codes, creator, and algorithm as unauthenticated and unverified. "
    "DICOM Guide has not verified my identity or credentials."
)
LIMITATIONS = [
    "Reviewer identity, role, and credentials are self-asserted and are not authenticated by DICOM Guide.",
    "Acceptance means suitable for discussion only; it is not clinical validation, medical-record sign-off, or regulatory clearance.",
    "The boundary originates in a source-carried DICOM SEG object; DICOM Guide does not authenticate its creator or verify its algorithm, label, codes, accuracy, or clinical meaning.",
    "The exact source SEG object and reconstructed native-grid mask are embedded, but boundary uncertainty remains unquantified.",
    "This review applies to one exact source series and does not establish that another scan contains the same lesion or represented tissue.",
    "Differences in acquisition, motion, partial-volume effects, enhancement, edema, necrosis, treatment effect, and boundary choices can alter a mask or volume.",
    "No longitudinal link, volume change, percentage change, treatment-response category, diagnosis, or clinical conclusion is authorized.",
    "Original DICOM images, the original DICOM SEG object, and the clinical medical record remain authoritative.",
]
ArchiveSource = Path | BinaryIO


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _strict_json(value: bytes) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in items:
            if key in result:
                raise ValueError(f"duplicate JSON field: {key}")
            result[key] = item
        return result

    def invalid_constant(value: str) -> None:
        raise ValueError(f"unsupported JSON number: {value}")

    return json.loads(
        value,
        object_pairs_hook=pairs,
        parse_constant=invalid_constant,
    )


def _strict_object(value: bytes, label: str) -> dict[str, Any]:
    try:
        result = _strict_json(value)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"{label} is not strict valid UTF-8 JSON") from error
    if not isinstance(result, dict):
        raise ValueError(f"{label} must contain one JSON object")
    return result


def _created_at(value: str | None) -> str:
    result = value or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    if not isinstance(result, str) or "T" not in result:
        raise ValueError("created_at must be an ISO 8601 date-time with a timezone")
    try:
        parsed = datetime.fromisoformat(result.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("created_at must be an ISO 8601 date-time with a timezone") from error
    if parsed.tzinfo is None:
        raise ValueError("created_at must include a timezone")
    return result


def _safe_text(
    value: Any,
    label: str,
    maximum: int,
    *,
    optional: bool = False,
    multiline: bool = False,
) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text")
    result = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not result and not optional:
        raise ValueError(f"{label} must not be empty")
    if len(result) > maximum:
        raise ValueError(f"{label} exceeds {maximum} characters")
    if any(
        (ord(character) < 32 and not (multiline and character in "\n\t"))
        or ord(character) == 127
        for character in result
    ):
        raise ValueError(f"{label} contains unsupported control characters")
    if not multiline and any(character in "\n\t" for character in result):
        raise ValueError(f"{label} must be one line")
    return result


def validate_source_segmentation_review_request(value: Any) -> dict[str, Any]:
    expected = {
        "schema_version",
        "artifact_type",
        "source",
        "reviewer",
        "decision",
        "acquisition_suitability",
        "represented_tissue",
        "inclusion_criteria",
        "exclusion_criteria",
        "note",
        "checklist",
        "attestation",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError("source-SEG review request fields do not match the v1 contract")
    if value.get("schema_version") != SCHEMA_VERSION or value.get("artifact_type") != REQUEST_ARTIFACT_TYPE:
        raise ValueError("source-SEG review request type or version is invalid")
    source = value.get("source")
    if not isinstance(source, dict) or set(source) != {
        "catalog_content_sha256",
        "segmentation_id",
        "segment_number",
    }:
        raise ValueError("source-SEG review source reference is invalid")
    if not isinstance(source.get("catalog_content_sha256"), str) or not SHA256.fullmatch(
        source["catalog_content_sha256"]
    ):
        raise ValueError("source-SEG review catalog binding is invalid")
    if not isinstance(source.get("segmentation_id"), str) or not re.fullmatch(
        r"instance_[0-9a-f]{20}", source["segmentation_id"]
    ):
        raise ValueError("source-SEG review object ID is invalid")
    if (
        type(source.get("segment_number")) is not int
        or not 1 <= source["segment_number"] <= 65535
    ):
        raise ValueError("source-SEG review segment number is invalid")

    reviewer = value.get("reviewer")
    if not isinstance(reviewer, dict) or set(reviewer) != {
        "name",
        "role",
        "organization",
        "identity_verification",
    }:
        raise ValueError("source-SEG reviewer is invalid")
    name = _safe_text(reviewer.get("name"), "reviewer.name", 120)
    if reviewer.get("role") not in ROLES:
        raise ValueError("reviewer.role is invalid")
    organization = reviewer.get("organization")
    if organization is not None:
        organization = _safe_text(organization, "reviewer.organization", 160)
    if reviewer.get("identity_verification") != "self_asserted_unverified":
        raise ValueError("reviewer identity must remain self asserted and unverified")

    decision = value.get("decision")
    suitability = value.get("acquisition_suitability")
    if decision not in DECISIONS:
        raise ValueError("source-SEG review decision is invalid")
    if suitability not in SUITABILITY:
        raise ValueError("source-SEG acquisition suitability is invalid")
    checklist = value.get("checklist")
    if not isinstance(checklist, dict) or set(checklist) != CHECKLIST_KEYS:
        raise ValueError("source-SEG review checklist is invalid")
    if any(type(item) is not bool for item in checklist.values()):
        raise ValueError("source-SEG review checklist values must be boolean")
    if decision == "accepted_for_discussion":
        if suitability != "suitable":
            raise ValueError("acceptance for discussion requires suitable acquisition")
        if not all(checklist.values()):
            raise ValueError("acceptance for discussion requires every source-SEG checklist item")
    if value.get("attestation") != ATTESTATION:
        raise ValueError("source-SEG review attestation is invalid")

    return {
        **value,
        "reviewer": {
            **reviewer,
            "name": name,
            "organization": organization,
        },
        "represented_tissue": _safe_text(
            value.get("represented_tissue"),
            "represented_tissue",
            500,
            multiline=True,
        ),
        "inclusion_criteria": _safe_text(
            value.get("inclusion_criteria"),
            "inclusion_criteria",
            1000,
            multiline=True,
        ),
        "exclusion_criteria": _safe_text(
            value.get("exclusion_criteria"),
            "exclusion_criteria",
            1000,
            multiline=True,
        ),
        "note": _safe_text(
            value.get("note"),
            "note",
            2000,
            optional=True,
            multiline=True,
        ),
        "checklist": dict(checklist),
    }


def _catalog_series(catalog: dict[str, Any], series_id: str) -> dict[str, Any]:
    matches = [
        series
        for study in catalog.get("studies", [])
        if isinstance(study, dict)
        for series in study.get("series", [])
        if isinstance(series, dict) and series.get("id") == series_id
    ]
    if len(matches) != 1:
        raise ValueError("source-SEG referenced series is not an exact catalog member")
    return matches[0]


def _source_set(catalog: dict[str, Any], state: dict[str, Any]) -> tuple[dict[str, Any], str]:
    referenced = state["referenced_series"]
    series = _catalog_series(catalog, referenced["series_id"])
    instances = {
        item.get("id"): item
        for item in series.get("instances", [])
        if isinstance(item, dict)
    }
    ordered = []
    for index, instance_id in enumerate(referenced["ordered_instance_ids"]):
        instance = instances.get(instance_id)
        if (
            not isinstance(instance, dict)
            or type(instance.get("bytes")) is not int
            or instance["bytes"] < 132
            or not isinstance(instance.get("sha256"), str)
            or not SHA256.fullmatch(instance["sha256"])
        ):
            raise ValueError("source-SEG referenced source provenance is incomplete")
        ordered.append(
            {
                "frame_index": index,
                "instance_id": instance_id,
                "bytes": instance["bytes"],
                "sha256": instance["sha256"],
            }
        )
    lines = [
        f"{item['frame_index']}:{item['instance_id']}:{item['bytes']}:{item['sha256']}"
        for item in ordered
    ]
    return series, _sha256(("\n".join(lines) + "\n").encode())


def _resolve_source(
    request: dict[str, Any],
    catalog: dict[str, Any],
    registry: dict[str, Path],
    *,
    source_segmentation_catalog: dict[str, Any] | None = None,
    source_segmentation_masks: dict[tuple[str, int], bytes] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], bytes, bytes, str]:
    loader = registry_segmentation_source_loader(catalog, registry)
    if source_segmentation_catalog is None or source_segmentation_masks is None:
        source_segmentation_catalog, source_segmentation_masks, _ = (
            build_source_segmentation_catalog(catalog, loader)
        )
    source = request["source"]
    if source_segmentation_catalog.get("catalog_content_sha256") != source["catalog_content_sha256"]:
        raise ValueError("source-SEG catalog binding is unavailable or changed")
    states = [
        item
        for item in source_segmentation_catalog.get("segmentations", [])
        if isinstance(item, dict) and item.get("segmentation_id") == source["segmentation_id"]
    ]
    if len(states) != 1 or states[0].get("display_status") != "supported_read_only":
        raise ValueError("source-SEG object is unavailable or unsupported")
    state = states[0]
    segments = [
        item
        for item in state.get("segments", [])
        if isinstance(item, dict) and item.get("segment_number") == source["segment_number"]
    ]
    if len(segments) != 1:
        raise ValueError("source-SEG segment is unavailable")
    segment = segments[0]
    mask = source_segmentation_masks.get((state["segmentation_id"], segment["segment_number"]))
    if (
        not isinstance(mask, bytes)
        or len(mask) < 1
        or len(mask) > MAX_MASK_BYTES
        or _sha256(mask) != segment.get("mask_sha256")
        or sum(mask) != segment.get("marked_voxel_count")
        or any(value not in (0, 1) for value in mask)
    ):
        raise ValueError("source-SEG reconstructed mask is unavailable or changed")
    segmentation_bytes = loader(state["segmentation_id"])
    if (
        len(segmentation_bytes) != state["source"]["bytes"]
        or _sha256(segmentation_bytes) != state["source"]["sha256"]
    ):
        raise ValueError("source DICOM SEG bytes are unavailable or changed")
    series, source_set_sha256 = _source_set(catalog, state)
    return state, segment, series, segmentation_bytes, mask, source_set_sha256


def _permissions(accepted: bool) -> dict[str, Any]:
    return {
        "source_boundary_discussion": True,
        "reviewed_volume_for_discussion": accepted,
        "eligible_for_future_pairing_review": accepted,
        "source_segmentation_edit": False,
        "source_label_as_clinical_finding": False,
        "source_creator_authenticated": False,
        "longitudinal_link": False,
        "percent_change": False,
        "response_classification": False,
        "diagnosis": False,
        "clinical_conclusion": False,
    }


def _record_without_files(
    request: dict[str, Any],
    state: dict[str, Any],
    segment: dict[str, Any],
    series: dict[str, Any],
    source_set_sha256: str,
    *,
    review_id: str,
    created_at: str,
) -> dict[str, Any]:
    if not REVIEW_ID.fullmatch(review_id):
        raise ValueError("source-SEG review ID is invalid")
    accepted = request["decision"] == "accepted_for_discussion"
    frame_id = series.get("frame_of_reference_id")
    patient_id = series.get("patient_context_id")
    if not isinstance(frame_id, str) or not OPAQUE_ID.fullmatch(frame_id):
        raise ValueError("source-SEG referenced frame of reference is unavailable")
    if accepted and (
        not isinstance(patient_id, str) or not re.fullmatch(r"patient_[0-9a-f]{20}", patient_id)
    ):
        raise ValueError("accepted source-SEG review requires one opaque patient context")
    volume_mm3 = float(segment["computed_volume_mm3"])
    volume_ml = float(segment["computed_volume_ml"])
    if not all(math.isfinite(value) and value > 0 for value in (volume_mm3, volume_ml)):
        raise ValueError("source-SEG technical volume is invalid")
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "review_id": review_id,
        "created_at": _created_at(created_at),
        "review_status": request["decision"],
        "local_only": True,
        "sensitive": True,
        "deidentified": False,
        "privacy": {
            "classification": "sensitive_local_medical_data",
            "contains_original_dicom": True,
            "contains_source_text": True,
            "contains_segmentation_mask_pixels": True,
            "may_contain_direct_identifiers": True,
            "deidentified": False,
        },
        "source_snapshot": {
            "source_kind": "source_carried_dicom_seg",
            "source_segmentation_catalog_sha256": request["source"]["catalog_content_sha256"],
            "segmentation_id": state["segmentation_id"],
            "segment_number": segment["segment_number"],
            "source_segmentation_study_id": state["source"]["study_id"],
            "source_segmentation_series_id": state["source"]["series_id"],
            "source_segmentation_instance_id": state["source"]["instance_id"],
            "source_segmentation_bytes": state["source"]["bytes"],
            "source_segmentation_sha256": state["source"]["sha256"],
            "source_segment_metadata_sha256": _sha256(_canonical(segment)),
            "patient_context_id": patient_id,
            "study_id": state["referenced_series"]["study_id"],
            "series_id": state["referenced_series"]["series_id"],
            "frame_of_reference_id": frame_id,
            "modality": state["referenced_series"]["modality"],
            "source_set_sha256": source_set_sha256,
            "mask_pixel_sha256": segment["mask_sha256"],
            "foreground_voxel_count": segment["marked_voxel_count"],
            "volume_mm3": volume_mm3,
            "volume_ml": volume_ml,
            "boundary_uncertainty": "not_quantified",
            "geometry_relationship": "exact_native_source_grid",
            "source_creator_identity_authenticated": False,
            "source_algorithm_verified": False,
            "source_segment_accuracy_verified": False,
            "source_segment_clinical_meaning": "not_assessed",
            "dicom_guide_interpretation_added": False,
        },
        "reviewer": request["reviewer"],
        "review": {
            "decision": request["decision"],
            "acquisition_suitability": request["acquisition_suitability"],
            "planes_reviewed": ["axial", "coronal", "sagittal"],
            "represented_tissue": request["represented_tissue"],
            "inclusion_criteria": request["inclusion_criteria"],
            "exclusion_criteria": request["exclusion_criteria"],
            "note": request["note"],
            "checklist": request["checklist"],
        },
        "attestation": ATTESTATION,
        "permitted_uses": _permissions(accepted),
        "limitations": LIMITATIONS.copy(),
    }


def _render_page(record: dict[str, Any]) -> bytes:
    review = record["review"]
    reviewer = record["reviewer"]
    source = record["source_snapshot"]
    checks = "".join(
        f"<li>{'Yes' if checked else 'No'} · {html.escape(key.replace('_', ' '))}</li>"
        for key, checked in review["checklist"].items()
    )
    organization = (
        f" · {html.escape(reviewer['organization'])}" if reviewer["organization"] else ""
    )
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>DICOM Guide source DICOM SEG boundary review</title><style>
body{{font:16px/1.5 system-ui,sans-serif;margin:0;background:#f5f7f6;color:#17201e}}main{{max-width:920px;margin:auto;padding:32px}}.warning{{border:3px solid #a23d35;background:#fff2f0;padding:16px;font-weight:700}}section{{background:white;border:1px solid #cbd5d1;border-radius:10px;padding:20px;margin:18px 0}}dt{{font-weight:700}}dd{{margin:0 0 12px}}code{{overflow-wrap:anywhere}}footer{{font-size:13px;color:#4b5c57}}@media print{{body{{background:white}}main{{padding:0}}section{{break-inside:avoid}}}}
</style></head><body><main><h1>Source DICOM SEG boundary review</h1><p class="warning">SELF-ATTESTED REVIEW FOR DISCUSSION ONLY · SOURCE CREATOR AND ALGORITHM NOT VERIFIED · SOURCE LABEL MEANING NOT ASSESSED · NOT A DIAGNOSIS · NO LONGITUDINAL OR RESPONSE CONCLUSION</p>
<section><h2>Decision</h2><dl><dt>Status</dt><dd>{html.escape(record['review_status'].replace('_', ' '))}</dd><dt>Reviewer</dt><dd>{html.escape(reviewer['name'])} · {html.escape(reviewer['role'].replace('_', ' '))}{organization}</dd><dt>Acquisition suitability</dt><dd>{html.escape(review['acquisition_suitability'].replace('_', ' '))}</dd><dt>Reviewed technical volume</dt><dd>{source['volume_ml']:.6f} mL · {source['foreground_voxel_count']:,} native voxels</dd></dl></section>
<section><h2>Reviewer-defined boundary meaning</h2><dl><dt>Represented tissue</dt><dd>{html.escape(review['represented_tissue'])}</dd><dt>Inclusion criteria</dt><dd>{html.escape(review['inclusion_criteria'])}</dd><dt>Exclusion criteria</dt><dd>{html.escape(review['exclusion_criteria'])}</dd><dt>Note</dt><dd>{html.escape(review['note'] or 'None recorded.')}</dd></dl><p>The reviewer-defined description is separate from the source-carried segment label and codes, whose clinical meaning remains not assessed by DICOM Guide.</p></section>
<section><h2>Checklist</h2><ul>{checks}</ul><p>Planes reviewed: axial, coronal, sagittal.</p></section>
<section><h2>Source anchors</h2><p>Review <code>{html.escape(record['review_id'])}</code> · segment {source['segment_number']} · {source['modality']} · exact source-set, original SEG, source-metadata, and mask hashes are retained in <code>review.json</code>.</p></section>
<section><h2>Attestation</h2><p>{html.escape(record['attestation'])}</p></section>
<footer>{''.join(f'<p>{html.escape(item)}</p>' for item in record['limitations'])}</footer></main></body></html>\n"""
    return page.encode("utf-8")


def _readme() -> bytes:
    return (
        "DICOM Guide source DICOM SEG boundary review\n\n"
        "This sensitive local archive contains review.json, the exact original source-segmentation.dcm, the independently reconstructed native-grid mask.bin, review.html, and README.txt.\n"
        "Validate it against the original local DICOM root before discussion:\n"
        "  dicom-guide validate-source-segmentation-review review.zip '/path/to/DICOM-root'\n\n"
        "A valid accepted record is self-attested and suitable for discussion only. It does not authenticate the source creator or reviewer, verify the source algorithm or segment label, establish a longitudinal lesion link, calculate change, classify response, diagnose, or create a clinical conclusion.\n"
    ).encode("utf-8")


def _file(filename: str, content: bytes) -> dict[str, Any]:
    return {"filename": filename, "bytes": len(content), "sha256": _sha256(content)}


def source_segmentation_review_archive_bytes(
    request_source: bytes,
    catalog: dict[str, Any],
    registry: dict[str, Path],
    *,
    source_segmentation_catalog: dict[str, Any] | None = None,
    source_segmentation_masks: dict[tuple[str, int], bytes] | None = None,
    review_id: str | None = None,
    created_at: str | None = None,
) -> bytes:
    if not request_source or len(request_source) > MAX_REQUEST_BYTES:
        raise ValueError("source-SEG review request exceeds the local safety limit")
    request = validate_source_segmentation_review_request(
        _strict_object(request_source, "source-SEG review request")
    )
    state, segment, series, segmentation_bytes, mask, source_set_sha256 = _resolve_source(
        request,
        catalog,
        registry,
        source_segmentation_catalog=source_segmentation_catalog,
        source_segmentation_masks=source_segmentation_masks,
    )
    identifier = review_id or f"source_seg_review_{uuid.uuid4()}"
    record_without_files = _record_without_files(
        request,
        state,
        segment,
        series,
        source_set_sha256,
        review_id=identifier,
        created_at=_created_at(created_at),
    )
    page = _render_page(record_without_files)
    readme = _readme()
    record = {
        **record_without_files,
        "files": {
            "source_segmentation": _file("source-segmentation.dcm", segmentation_bytes),
            "mask": _file("mask.bin", mask),
            "review_page": _file("review.html", page),
            "readme": _file("README.txt", readme),
        },
    }
    output = io.BytesIO()
    with zipfile.ZipFile(
        output,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=6,
    ) as archive:
        archive.writestr("review.json", _json_bytes(record))
        archive.writestr("source-segmentation.dcm", segmentation_bytes)
        archive.writestr("mask.bin", mask)
        archive.writestr("review.html", page)
        archive.writestr("README.txt", readme)
    return output.getvalue()


def _read_archive(source: ArchiveSource) -> tuple[dict[str, bytes], list[str]]:
    errors: list[str] = []
    members: dict[str, bytes] = {}
    try:
        if isinstance(source, Path):
            if source.is_symlink() or not source.is_file() or source.stat().st_size > MAX_ARCHIVE_BYTES:
                return {}, ["source-SEG review must be one bounded regular non-symlink file"]
        with zipfile.ZipFile(source) as archive:
            infos = archive.infolist()
            names = [item.filename for item in infos]
            if set(names) != EXPECTED_FILES or len(names) != len(EXPECTED_FILES):
                return {}, ["source-SEG review archive has unsupported or duplicate members"]
            limits = {
                "review.json": MAX_TEXT_BYTES,
                "source-segmentation.dcm": MAX_SEGMENTATION_BYTES,
                "mask.bin": MAX_MASK_BYTES,
                "review.html": MAX_TEXT_BYTES,
                "README.txt": MAX_TEXT_BYTES,
            }
            for info in infos:
                mode = info.external_attr >> 16
                if (
                    info.flag_bits & 0x1
                    or stat.S_ISLNK(mode)
                    or info.filename.startswith(("/", "\\"))
                    or ".." in Path(info.filename).parts
                    or info.file_size < 1
                    or info.file_size > limits[info.filename]
                ):
                    errors.append("source-SEG review archive contains an unsafe member")
                    continue
                members[info.filename] = archive.read(info)
    except (OSError, RuntimeError, zipfile.BadZipFile):
        errors.append("source-SEG review archive is not a readable ZIP")
    return members, list(dict.fromkeys(errors))


def _record_request(record: dict[str, Any]) -> dict[str, Any]:
    source = record["source_snapshot"]
    review = record["review"]
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": REQUEST_ARTIFACT_TYPE,
        "source": {
            "catalog_content_sha256": source["source_segmentation_catalog_sha256"],
            "segmentation_id": source["segmentation_id"],
            "segment_number": source["segment_number"],
        },
        "reviewer": record["reviewer"],
        "decision": record["review_status"],
        "acquisition_suitability": review["acquisition_suitability"],
        "represented_tissue": review["represented_tissue"],
        "inclusion_criteria": review["inclusion_criteria"],
        "exclusion_criteria": review["exclusion_criteria"],
        "note": review["note"],
        "checklist": review["checklist"],
        "attestation": record["attestation"],
    }


def source_segmentation_review_summary(
    source: ArchiveSource,
    *,
    source_root: Path | None = None,
    catalog: dict[str, Any] | None = None,
    registry: dict[str, Path] | None = None,
) -> dict[str, Any]:
    members, errors = _read_archive(source)
    record: dict[str, Any] = {}
    if not errors:
        try:
            record = _strict_object(members["review.json"], "review.json")
            live_catalog, live_registry = (
                (catalog, registry)
                if catalog is not None and registry is not None
                else build_catalog(source_root, include_hashes=True)
                if source_root is not None
                else (None, None)
            )
            if live_catalog is None or live_registry is None:
                raise ValueError("exact local DICOM catalog and registry are required")
            request = validate_source_segmentation_review_request(_record_request(record))
            state, segment, series, segmentation_bytes, mask, source_set_sha256 = _resolve_source(
                request,
                live_catalog,
                live_registry,
            )
            expected = _record_without_files(
                request,
                state,
                segment,
                series,
                source_set_sha256,
                review_id=record["review_id"],
                created_at=record["created_at"],
            )
            observed_without_files = {key: value for key, value in record.items() if key != "files"}
            if observed_without_files != expected:
                raise ValueError("review record does not match the exact live source SEG and request")
            files = record.get("files")
            expected_files = {
                "source_segmentation": _file("source-segmentation.dcm", segmentation_bytes),
                "mask": _file("mask.bin", mask),
                "review_page": _file("review.html", _render_page(expected)),
                "readme": _file("README.txt", _readme()),
            }
            if files != expected_files:
                raise ValueError("review file contracts do not match the exact validated content")
            if members["source-segmentation.dcm"] != segmentation_bytes:
                raise ValueError("embedded source DICOM SEG does not match the exact live source")
            if members["mask.bin"] != mask:
                raise ValueError("embedded source-SEG mask does not match local reconstruction")
            if members["review.html"] != _render_page(expected):
                raise ValueError("review.html does not exactly present the validated record")
            if members["README.txt"] != _readme():
                raise ValueError("README.txt does not match the v1 local instructions")
        except (KeyError, OSError, TypeError, ValueError) as error:
            errors.append(str(error)[:500])
    errors = list(dict.fromkeys(errors))
    valid = not errors and bool(record)
    accepted = bool(valid and record.get("review_status") == "accepted_for_discussion")
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": SUMMARY_ARTIFACT_TYPE,
        "valid": valid,
        "errors": errors,
        "review_status": record.get("review_status") if valid else None,
        "identity_verification": "self_asserted_unverified" if valid else None,
        "source_validated": valid,
        "source_creator_authenticated": False,
        "source_algorithm_verified": False,
        "source_segment_clinical_meaning": "not_assessed",
        "reviewed_volume_for_discussion": accepted,
        "eligible_for_future_pairing_review": accepted,
        "longitudinal_link": False,
        "percent_change": False,
        "response_classification": False,
        "diagnosis": False,
        "clinical_conclusion": False,
        "contains_identifiers": False,
        "contains_source_text": False,
        "contains_pixels": False,
        "contains_measurement_values": False,
        "contains_paths": False,
        "local_only": True,
        "external_api_required": False,
    }


def write_source_segmentation_review(
    source_root: Path,
    request_path: Path,
    output: Path,
    *,
    created_at: str | None = None,
) -> dict[str, Any]:
    if output.exists() or output.is_symlink():
        raise ValueError("source-SEG review output already exists")
    try:
        request_descriptor = os.open(
            request_path,
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NONBLOCK", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
    except OSError as error:
        raise ValueError("source-SEG review request cannot be opened safely") from error
    try:
        request_stat = os.fstat(request_descriptor)
        if (
            not stat.S_ISREG(request_stat.st_mode)
            or request_stat.st_size < 1
            or request_stat.st_size > MAX_REQUEST_BYTES
        ):
            raise ValueError("source-SEG review request must be one bounded regular file")
        chunks: list[bytes] = []
        remaining = request_stat.st_size
        while remaining:
            chunk = os.read(request_descriptor, min(remaining, 64 * 1024))
            if not chunk:
                raise ValueError("source-SEG review request changed while being read")
            chunks.append(chunk)
            remaining -= len(chunk)
        completed_stat = os.fstat(request_descriptor)
        identity_fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if any(
            getattr(request_stat, field) != getattr(completed_stat, field)
            for field in identity_fields
        ):
            raise ValueError("source-SEG review request changed while being read")
        request_source = b"".join(chunks)
    finally:
        os.close(request_descriptor)
    catalog, registry = build_catalog(source_root, include_hashes=True)
    payload = source_segmentation_review_archive_bytes(
        request_source,
        catalog,
        registry,
        created_at=created_at,
    )
    descriptor = os.open(
        output,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    incomplete = True
    try:
        written = 0
        while written < len(payload):
            count = os.write(descriptor, payload[written:])
            if count <= 0:
                raise OSError("source-SEG review output write did not make progress")
            written += count
        os.fsync(descriptor)
        incomplete = False
    finally:
        os.close(descriptor)
        if incomplete:
            output.unlink(missing_ok=True)
    return source_segmentation_review_summary(output, source_root=source_root)
