from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any


SCHEMA_VERSION = "1.0.0"
ARTIFACT_TYPE = "dicom-guide.agent-consultation-plan"
REQUEST_ARTIFACT_TYPE = "dicom-guide.agent-consultation-plan-request"
MEDIA_TYPE = "application/vnd.dicom-guide.agent-consultation-plan+json"
MIN_ITEMS = 2
MAX_ITEMS = 8
MAX_HEADING_CHARACTERS = 80
MAX_PLAN_BYTES = 32 * 1024
OPAQUE_ID = {
    kind: re.compile(rf"^{kind}_[0-9a-f]{{20}}$")
    for kind in ("study", "series", "instance", "patient")
}

REQUIRED_HUMAN_ACTIONS = [
    "confirm_patient_identity_exam_and_source_in_the_clinical_imaging_system",
    "decide_whether_each_proposed_view_is_relevant",
    "review_or_replace_every_discussion_heading",
    "interpret_images_with_a_qualified_clinician",
    "record_clinical_conclusions_only_in_the_authorized_medical_record",
]
LIMITATIONS = [
    "The plan contains unreviewed software-agent proposals, not findings or clinical conclusions.",
    "Exact catalog membership and navigation do not prove that a view is relevant or representative.",
    "MR and CT are cross-modality consultation references and do not form a longitudinal response pair.",
    "A person must deliberately inspect and capture each view; this plan cannot create evidence automatically.",
]


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def load_strict_json(data: str | bytes) -> Any:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON field: {key}")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise ValueError(f"unsupported JSON constant: {value}")

    try:
        text = data.decode("utf-8") if isinstance(data, bytes) else data
        return json.loads(
            text,
            object_pairs_hook=reject_duplicates,
            parse_constant=reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("invalid consultation-plan JSON") from error


def _catalog_content(catalog: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in catalog.items() if key != "generated_at"}


def _strict_keys(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"{label} has unsupported fields")
    return value


def _valid_datetime(value: Any) -> bool:
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _heading(value: Any) -> str:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or not value
        or len(value) > MAX_HEADING_CHARACTERS
    ):
        raise ValueError(
            "discussion heading must be trimmed and contain 1 to "
            f"{MAX_HEADING_CHARACTERS} characters"
        )
    if any(unicodedata.category(character).startswith("C") for character in value):
        raise ValueError("discussion heading contains unsupported control characters")
    return value


def _catalog_index(catalog: Any) -> tuple[str, dict[str, dict[str, Any]]]:
    if (
        not isinstance(catalog, dict)
        or catalog.get("schema_version") != "1.0.0"
        or not isinstance(catalog.get("studies"), list)
    ):
        raise ValueError("consultation plans require a DICOM Guide manifest v1 catalog")
    try:
        catalog_content_sha256 = hashlib.sha256(
            _canonical(_catalog_content(catalog))
        ).hexdigest()
    except (TypeError, ValueError) as error:
        raise ValueError("DICOM Guide catalog contains unsupported values") from error

    study_ids: set[str] = set()
    series_ids: set[str] = set()
    instance_ids: set[str] = set()
    series_by_id: dict[str, dict[str, Any]] = {}
    for study in catalog["studies"]:
        if (
            not isinstance(study, dict)
            or not OPAQUE_ID["study"].fullmatch(str(study.get("id", "")))
            or study["id"] in study_ids
            or not isinstance(study.get("series"), list)
        ):
            raise ValueError("DICOM Guide catalog contains an invalid study")
        study_ids.add(study["id"])
        for series in study["series"]:
            if not isinstance(series, dict) or series.get("modality") not in {"MR", "CT"}:
                continue
            if (
                not OPAQUE_ID["series"].fullmatch(str(series.get("id", "")))
                or series["id"] in series_ids
                or not isinstance(series.get("instances"), list)
            ):
                raise ValueError("DICOM Guide catalog contains an invalid renderable series")
            context = series.get("patient_context_id")
            if not OPAQUE_ID["patient"].fullmatch(str(context or "")):
                raise ValueError(
                    "consultation-plan series require one locally derived opaque patient context"
                )
            selected_instances: set[str] = set()
            for instance in series["instances"]:
                if (
                    not isinstance(instance, dict)
                    or not OPAQUE_ID["instance"].fullmatch(
                        str(instance.get("id", ""))
                    )
                    or instance["id"] in instance_ids
                ):
                    raise ValueError("DICOM Guide catalog contains an invalid instance")
                instance_ids.add(instance["id"])
                selected_instances.add(instance["id"])
            series_ids.add(series["id"])
            series_by_id[series["id"]] = {
                "study_id": study["id"],
                "modality": series["modality"],
                "patient_context_id": context,
                "instance_ids": selected_instances,
            }
    return catalog_content_sha256, series_by_id


def _request_items(request: Any) -> list[dict[str, str]]:
    value = _strict_keys(
        request,
        {"schema_version", "artifact_type", "items"},
        "consultation-plan request",
    )
    if (
        value.get("schema_version") != SCHEMA_VERSION
        or value.get("artifact_type") != REQUEST_ARTIFACT_TYPE
        or not isinstance(value.get("items"), list)
        or not MIN_ITEMS <= len(value["items"]) <= MAX_ITEMS
    ):
        raise ValueError(
            f"consultation-plan request must contain {MIN_ITEMS} to {MAX_ITEMS} items"
        )
    items: list[dict[str, str]] = []
    for item in value["items"]:
        record = _strict_keys(
            item,
            {"series_id", "instance_id", "discussion_heading"},
            "consultation-plan request item",
        )
        series_id = record.get("series_id")
        instance_id = record.get("instance_id")
        if not isinstance(series_id, str) or not OPAQUE_ID["series"].fullmatch(
            series_id
        ):
            raise ValueError("consultation-plan request has an invalid series ID")
        if not isinstance(instance_id, str) or not OPAQUE_ID["instance"].fullmatch(
            instance_id
        ):
            raise ValueError("consultation-plan request has an invalid instance ID")
        items.append(
            {
                "series_id": series_id,
                "instance_id": instance_id,
                "discussion_heading": _heading(record.get("discussion_heading")),
            }
        )
    return items


def build_agent_consultation_plan(
    catalog: Any,
    request: Any,
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    catalog_content_sha256, series_by_id = _catalog_index(catalog)
    requested = _request_items(request)
    if generated_at is None:
        generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    if not _valid_datetime(generated_at):
        raise ValueError("consultation-plan generation timestamp is invalid")

    seen_instances: set[str] = set()
    contexts: set[str] = set()
    modalities: set[str] = set()
    study_ids: set[str] = set()
    items: list[dict[str, Any]] = []
    for index, requested_item in enumerate(requested):
        series = series_by_id.get(requested_item["series_id"])
        if series is None:
            raise ValueError("consultation-plan series is not available in the catalog")
        instance_id = requested_item["instance_id"]
        if instance_id not in series["instance_ids"]:
            raise ValueError(
                "consultation-plan instance does not belong to the selected series"
            )
        if instance_id in seen_instances:
            raise ValueError("consultation-plan items require distinct source instances")
        seen_instances.add(instance_id)
        contexts.add(series["patient_context_id"])
        modalities.add(series["modality"])
        study_ids.add(series["study_id"])
        items.append(
            {
                "item_id": f"item_{index + 1:02d}",
                "series_id": requested_item["series_id"],
                "instance_id": instance_id,
                "modality": series["modality"],
                "discussion_heading": requested_item["discussion_heading"],
                "proposal_source": "software_agent_unverified",
                "review_status": "unreviewed",
                "auto_selected": False,
            }
        )
    if len(contexts) != 1:
        raise ValueError("consultation-plan items require one opaque patient context")
    if modalities != {"MR", "CT"}:
        raise ValueError("consultation-plan items require at least one MR and one CT view")
    if len(study_ids) < 2:
        raise ValueError("consultation-plan items require at least two source studies")

    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "generated_at": generated_at,
        "catalog_content_sha256": catalog_content_sha256,
        "local_only": True,
        "privacy": {
            "classification": "sensitive_local_medical_data",
            "direct_identifier_tags_excluded": True,
            "discussion_headings_may_contain_identifiers": True,
            "deidentified": False,
            "contains_pixels": False,
            "contains_paths": False,
        },
        "author": {
            "kind": "software_agent_unverified",
            "identity_authenticated": False,
        },
        "review_status": "unreviewed",
        "items": items,
        "relationship": {
            "selection_method": "agent_proposed_exact_native_sources",
            "item_count": len(items),
            "same_patient_context": True,
            "modalities_present": ["MR", "CT"],
            "distinct_source_study_count": len(study_ids),
            "distinct_source_instances": True,
            "chronology_asserted": False,
            "registration_asserted": False,
            "lesion_identity_asserted": False,
        },
        "clinical_interpretations": [],
        "required_human_actions": list(REQUIRED_HUMAN_ACTIONS),
        "permissions": {
            "exact_source_navigation_authorized": True,
            "automatic_board_capture_authorized": False,
            "source_mutation_authorized": False,
            "chronology_authorized": False,
            "registration_authorized": False,
            "lesion_link_authorized": False,
            "response_classification_authorized": False,
            "treatment_effect_conclusion_authorized": False,
            "diagnosis_authorized": False,
            "clinical_conclusion_authorized": False,
        },
        "limitations": list(LIMITATIONS),
    }


def validate_agent_consultation_plan(
    catalog: Any,
    plan: Any,
) -> dict[str, Any]:
    value = _strict_keys(
        plan,
        {
            "schema_version",
            "artifact_type",
            "generated_at",
            "catalog_content_sha256",
            "local_only",
            "privacy",
            "author",
            "review_status",
            "items",
            "relationship",
            "clinical_interpretations",
            "required_human_actions",
            "permissions",
            "limitations",
        },
        "consultation plan",
    )
    if (
        value.get("schema_version") != SCHEMA_VERSION
        or value.get("artifact_type") != ARTIFACT_TYPE
        or not isinstance(value.get("items"), list)
    ):
        raise ValueError("consultation plan contract is invalid")
    request_items: list[dict[str, Any]] = []
    for item in value["items"]:
        record = _strict_keys(
            item,
            {
                "item_id",
                "series_id",
                "instance_id",
                "modality",
                "discussion_heading",
                "proposal_source",
                "review_status",
                "auto_selected",
            },
            "consultation-plan item",
        )
        request_items.append(
            {
                "series_id": record.get("series_id"),
                "instance_id": record.get("instance_id"),
                "discussion_heading": record.get("discussion_heading"),
            }
        )
    rebuilt = build_agent_consultation_plan(
        catalog,
        {
            "schema_version": SCHEMA_VERSION,
            "artifact_type": REQUEST_ARTIFACT_TYPE,
            "items": request_items,
        },
        generated_at=value.get("generated_at"),
    )
    if value != rebuilt:
        raise ValueError("consultation plan does not match its exact local catalog")
    return value


def agent_consultation_plan_summary(
    catalog: Any,
    plan: Any,
) -> dict[str, Any]:
    try:
        validated = validate_agent_consultation_plan(catalog, plan)
    except (TypeError, ValueError):
        return {
            "valid": False,
            "errors": ["consultation plan is invalid or does not match the local catalog"],
            "schema_version": SCHEMA_VERSION,
            "artifact_type": "dicom-guide.agent-consultation-plan-summary",
            "item_count": 0,
            "modalities_present": [],
            "distinct_source_study_count": 0,
            "review_status": "invalid",
            "agent_identity_authenticated": False,
            "exact_source_navigation_authorized": False,
            "automatic_board_capture_authorized": False,
            "clinical_conclusion_authorized": False,
            "contains_prompts": False,
            "contains_source_ids": False,
            "local_only": True,
        }
    return {
        "valid": True,
        "errors": [],
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "dicom-guide.agent-consultation-plan-summary",
        "item_count": len(validated["items"]),
        "modalities_present": validated["relationship"]["modalities_present"],
        "distinct_source_study_count": validated["relationship"][
            "distinct_source_study_count"
        ],
        "review_status": "unreviewed",
        "agent_identity_authenticated": False,
        "exact_source_navigation_authorized": True,
        "automatic_board_capture_authorized": False,
        "clinical_conclusion_authorized": False,
        "contains_prompts": False,
        "contains_source_ids": False,
        "local_only": True,
    }
