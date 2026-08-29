from __future__ import annotations

import hashlib
import io
import json
import math
import os
import re
import stat
import unicodedata
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from pydicom import dcmread
from pydicom.errors import InvalidDicomError

from .catalog import opaque_id


SCHEMA_VERSION = "1.0.0"
ARTIFACT_TYPE = "scanview.presentation-state-catalog"
SUMMARY_ARTIFACT_TYPE = "scanview.presentation-state-summary"
GSPS_SOP_CLASS_UID = "1.2.840.10008.5.1.4.1.1.11.1"
MAX_PRESENTATION_STATE_BYTES = 16 * 1024 * 1024
MAX_REFERENCED_INSTANCES = 4096
MAX_ANNOTATIONS = 512
MAX_GRAPHICS_PER_ANNOTATION = 64
MAX_TEXTS_PER_ANNOTATION = 64
MAX_POINTS_PER_GRAPHIC = 2048
MAX_TEXT_CHARACTERS = 512
MAX_LAYER_CHARACTERS = 64
SHA256 = re.compile(r"^[0-9a-f]{64}$")
OPAQUE_ID = {
    kind: re.compile(rf"^{kind}_[0-9a-f]{{20}}$")
    for kind in ("study", "series", "instance", "patient")
}

LIMITATIONS = [
    "These are read-only display instructions extracted from source-carried DICOM Grayscale Softcopy Presentation State objects.",
    "ScanView preserves supported source text and geometry but does not authenticate the creator or assess text for identifiers or clinical meaning.",
    "Only a conservative subset is displayed: hashed single-frame monochrome sources whose linear modality transform matches the GSPS, LINEAR VOI, identity presentation LUT, matching source/display aspect, unrotated and unflipped full-image SCALE TO FIT, and PIXEL POLYLINE/anchor-text annotations.",
    "Unsupported presentation-state features fail closed and native DICOM images remain authoritative.",
]


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _catalog_content(catalog: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in catalog.items() if key != "generated_at"}


def _valid_datetime(value: Any) -> bool:
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _finite(value: Any) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError("presentation-state numeric value is invalid") from error
    if not math.isfinite(result):
        raise ValueError("presentation-state numeric value is non-finite")
    return result


def _single_number(value: Any, label: str) -> float:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        if len(value) != 1:
            raise ValueError(f"{label} must contain exactly one value")
        value = value[0]
    return _finite(value)


def _number_pair(value: Any, label: str) -> list[float]:
    if value is None:
        raise ValueError(f"{label} is missing")
    try:
        result = [_finite(item) for item in value]
    except TypeError as error:
        raise ValueError(f"{label} is invalid") from error
    if len(result) != 2:
        raise ValueError(f"{label} must contain two values")
    return result


def _bounded_text(value: Any, label: str, maximum: int) -> str:
    result = str(value or "")
    if not result or len(result) > maximum:
        raise ValueError(f"{label} is missing or too long")
    if any(
        unicodedata.category(character).startswith("C")
        and character not in {"\r", "\n"}
        for character in result
    ):
        raise ValueError(f"{label} contains unsupported control characters")
    return result


def _catalog_index(catalog: Any) -> tuple[str, dict[str, dict[str, Any]], list[str]]:
    if (
        not isinstance(catalog, dict)
        or catalog.get("schema_version") != "1.0.0"
        or not isinstance(catalog.get("studies"), list)
    ):
        raise ValueError("presentation states require a ScanView manifest v1 catalog")
    try:
        catalog_hash = hashlib.sha256(_canonical(_catalog_content(catalog))).hexdigest()
    except (TypeError, ValueError) as error:
        raise ValueError("ScanView catalog contains unsupported values") from error

    instances: dict[str, dict[str, Any]] = {}
    presentation_state_ids: list[str] = []
    for study in catalog["studies"]:
        if (
            not isinstance(study, dict)
            or not OPAQUE_ID["study"].fullmatch(str(study.get("id", "")))
            or not isinstance(study.get("series"), list)
        ):
            raise ValueError("ScanView catalog contains an invalid study")
        for series in study["series"]:
            if (
                not isinstance(series, dict)
                or not OPAQUE_ID["series"].fullmatch(str(series.get("id", "")))
                or not isinstance(series.get("instances"), list)
            ):
                raise ValueError("ScanView catalog contains an invalid series")
            modality = str(series.get("modality", ""))
            patient_context_id = series.get("patient_context_id")
            if modality == "PR" and not OPAQUE_ID["patient"].fullmatch(
                str(patient_context_id or "")
            ):
                raise ValueError("presentation-state catalog requires opaque patient context")
            for instance in series["instances"]:
                instance_id = instance.get("id") if isinstance(instance, dict) else None
                if (
                    not isinstance(instance, dict)
                    or not OPAQUE_ID["instance"].fullmatch(str(instance_id or ""))
                    or instance_id in instances
                ):
                    raise ValueError("ScanView catalog contains an invalid instance")
                record = {
                    "study_id": study["id"],
                    "series_id": series["id"],
                    "patient_context_id": patient_context_id,
                    "modality": modality,
                    "rows": instance.get("rows") or series.get("geometry", {}).get("rows"),
                    "columns": instance.get("columns")
                    or series.get("geometry", {}).get("columns"),
                    "pixel_spacing": instance.get("pixel_spacing"),
                    "pixel_aspect_ratio": instance.get("pixel_aspect_ratio"),
                    "photometric_interpretation": instance.get(
                        "photometric_interpretation"
                    ),
                    "rescale_slope": instance.get("rescale_slope"),
                    "rescale_intercept": instance.get("rescale_intercept"),
                    "has_modality_lut_sequence": instance.get(
                        "has_modality_lut_sequence", False
                    ),
                    "number_of_frames": instance.get("number_of_frames", 1),
                    "bytes": instance.get("bytes"),
                    "sha256": instance.get("sha256"),
                    "sop_class_uid": instance.get("sop_class_uid"),
                }
                instances[instance_id] = record
                if modality == "PR":
                    presentation_state_ids.append(instance_id)
    return catalog_hash, instances, sorted(presentation_state_ids)


def read_stable_source_bytes(
    path: Path,
    *,
    expected_bytes: int | None,
    expected_sha256: str | None,
) -> bytes:
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_size < 1
            or before.st_size > MAX_PRESENTATION_STATE_BYTES
            or expected_bytes is not None
            and before.st_size != expected_bytes
        ):
            raise ValueError("presentation-state source identity or size changed")
        chunks: list[bytes] = []
        total = 0
        digest = hashlib.sha256()
        while chunk := os.read(descriptor, 1024 * 1024):
            total += len(chunk)
            if total > MAX_PRESENTATION_STATE_BYTES:
                raise ValueError("presentation-state source exceeds the size limit")
            chunks.append(chunk)
            digest.update(chunk)
        after = os.fstat(descriptor)
        fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if total != before.st_size or any(
            getattr(before, field) != getattr(after, field) for field in fields
        ):
            raise ValueError("presentation-state source changed while it was read")
        observed_sha256 = digest.hexdigest()
        if expected_sha256 is not None and observed_sha256 != expected_sha256:
            raise ValueError("presentation-state source hash changed")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def registry_source_loader(
    catalog: Any,
    registry: dict[str, Path],
) -> Callable[[str], bytes]:
    _, instances, _ = _catalog_index(catalog)

    def load(instance_id: str) -> bytes:
        source = instances.get(instance_id)
        path = registry.get(instance_id)
        if source is None or path is None:
            raise ValueError("presentation-state source is unavailable")
        return read_stable_source_bytes(
            path,
            expected_bytes=source.get("bytes"),
            expected_sha256=source.get("sha256"),
        )

    return load


def _referenced_instances(
    dataset: Any,
    instances: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    by_series: dict[str, list[str]] = {}
    all_ids: list[str] = []
    for referenced_series in dataset.get("ReferencedSeriesSequence", []):
        series_uid = str(referenced_series.get("SeriesInstanceUID", ""))
        series_id = opaque_id("series", series_uid)
        image_ids: list[str] = []
        for referenced_image in referenced_series.get("ReferencedImageSequence", []):
            if (
                "ReferencedFrameNumber" in referenced_image
                or "ReferencedSegmentNumber" in referenced_image
            ):
                raise ValueError("presentation state uses frame-scoped image references")
            referenced_sop_class_uid = str(
                referenced_image.get("ReferencedSOPClassUID", "")
            )
            if referenced_sop_class_uid == GSPS_SOP_CLASS_UID:
                raise ValueError("presentation state cannot reference another GSPS as an image")
            instance_uid = str(referenced_image.get("ReferencedSOPInstanceUID", ""))
            instance_id = opaque_id("instance", instance_uid)
            source = instances.get(instance_id)
            if (
                source is None
                or source["series_id"] != series_id
                or source["modality"] not in {"MR", "CT"}
                or referenced_sop_class_uid != source["sop_class_uid"]
            ):
                raise ValueError("presentation state references an unavailable MR/CT image")
            if instance_id in all_ids:
                raise ValueError("presentation state contains a duplicate image reference")
            image_ids.append(instance_id)
            all_ids.append(instance_id)
        if not image_ids or series_id in by_series:
            raise ValueError("presentation state has an empty or duplicate referenced series")
        by_series[series_id] = image_ids
    if not all_ids or len(all_ids) > MAX_REFERENCED_INSTANCES:
        raise ValueError("presentation state has an unsupported referenced-image count")
    referenced = []
    for series_id, image_ids in by_series.items():
        source = instances[image_ids[0]]
        if any(
            instances[instance_id]["study_id"] != source["study_id"]
            or instances[instance_id]["patient_context_id"]
            != source["patient_context_id"]
            or instances[instance_id]["modality"] != source["modality"]
            for instance_id in image_ids
        ):
            raise ValueError("presentation-state referenced series is internally inconsistent")
        referenced.append(
            {
                "study_id": source["study_id"],
                "series_id": series_id,
                "patient_context_id": source["patient_context_id"],
                "modality": source["modality"],
                "instance_ids": image_ids,
            }
        )
    return referenced, all_ids


def _image_reference_ids(
    sequence: Any,
    allowed: set[str],
    instances: dict[str, dict[str, Any]],
) -> list[str]:
    result: list[str] = []
    for reference in sequence or []:
        if "ReferencedFrameNumber" in reference or "ReferencedSegmentNumber" in reference:
            raise ValueError("annotation uses frame-scoped image references")
        instance_id = opaque_id(
            "instance", str(reference.get("ReferencedSOPInstanceUID", ""))
        )
        source = instances.get(instance_id)
        if (
            instance_id not in allowed
            or instance_id in result
            or source is None
            or str(reference.get("ReferencedSOPClassUID", ""))
            != source["sop_class_uid"]
        ):
            raise ValueError("annotation references an unavailable or duplicate source image")
        result.append(instance_id)
    if not result:
        raise ValueError("supported annotations require explicit image references")
    return result


def _validate_point(point: list[float], sources: list[dict[str, Any]]) -> None:
    for source in sources:
        rows = source.get("rows")
        columns = source.get("columns")
        if (
            type(rows) is not int
            or type(columns) is not int
            or rows < 1
            or columns < 1
            or not 0 <= point[0] <= columns
            or not 0 <= point[1] <= rows
        ):
            raise ValueError("presentation-state annotation point is outside source pixels")


def _annotations(
    dataset: Any,
    referenced_instance_ids: list[str],
    instances: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    raw_annotations = list(dataset.get("GraphicAnnotationSequence", []))
    if len(raw_annotations) > MAX_ANNOTATIONS:
        raise ValueError("presentation state contains too many annotations")
    allowed = set(referenced_instance_ids)
    graphic_layers: set[str] = set()
    raw_layers = list(dataset.get("GraphicLayerSequence", []))
    if len(raw_layers) > MAX_ANNOTATIONS:
        raise ValueError("presentation state contains too many graphic layers")
    for raw_layer in raw_layers:
        layer = _bounded_text(
            raw_layer.get("GraphicLayer"), "graphic layer", MAX_LAYER_CHARACTERS
        )
        if layer in graphic_layers:
            raise ValueError("presentation state contains a duplicate graphic layer")
        graphic_layers.add(layer)
    result = []
    for annotation_index, annotation in enumerate(raw_annotations, 1):
        instance_ids = _image_reference_ids(
            annotation.get("ReferencedImageSequence", []), allowed, instances
        )
        sources = [instances[instance_id] for instance_id in instance_ids]
        layer = _bounded_text(
            annotation.get("GraphicLayer"), "graphic layer", MAX_LAYER_CHARACTERS
        )
        if layer not in graphic_layers:
            raise ValueError("presentation state annotation uses an unavailable graphic layer")
        raw_graphics = list(annotation.get("GraphicObjectSequence", []))
        raw_texts = list(annotation.get("TextObjectSequence", []))
        if (
            not raw_graphics
            and not raw_texts
            or len(raw_graphics) > MAX_GRAPHICS_PER_ANNOTATION
            or len(raw_texts) > MAX_TEXTS_PER_ANNOTATION
        ):
            raise ValueError("presentation state annotation has unsupported object counts")
        graphics = []
        for graphic_index, graphic in enumerate(raw_graphics, 1):
            if (
                str(graphic.get("GraphicAnnotationUnits", "")) != "PIXEL"
                or int(graphic.get("GraphicDimensions", 0) or 0) != 2
                or str(graphic.get("GraphicType", "")) != "POLYLINE"
                or str(graphic.get("GraphicFilled", "N")) != "N"
            ):
                raise ValueError("presentation state uses an unsupported graphic object")
            point_count = int(graphic.get("NumberOfGraphicPoints", 0) or 0)
            data = [_finite(value) for value in graphic.get("GraphicData", [])]
            if (
                point_count < 2
                or point_count > MAX_POINTS_PER_GRAPHIC
                or len(data) != point_count * 2
            ):
                raise ValueError("presentation-state polyline coordinates are invalid")
            points = [data[index : index + 2] for index in range(0, len(data), 2)]
            for point in points:
                _validate_point(point, sources)
            graphics.append(
                {
                    "graphic_id": f"graphic_{graphic_index:02d}",
                    "type": "POLYLINE",
                    "units": "PIXEL",
                    "filled": False,
                    "points": points,
                }
            )
        texts = []
        for text_index, text in enumerate(raw_texts, 1):
            anchor_visibility = str(text.get("AnchorPointVisibility", ""))
            if (
                "BoundingBoxTopLeftHandCorner" in text
                or "BoundingBoxBottomRightHandCorner" in text
                or str(text.get("AnchorPointAnnotationUnits", "")) != "PIXEL"
                or "AnchorPoint" not in text
                or anchor_visibility not in {"Y", "N"}
            ):
                raise ValueError("presentation state uses an unsupported text layout")
            anchor = _number_pair(text.get("AnchorPoint"), "text anchor point")
            _validate_point(anchor, sources)
            texts.append(
                {
                    "text_id": f"text_{text_index:02d}",
                    "units": "PIXEL",
                    "anchor_point": anchor,
                    "anchor_point_visible": anchor_visibility == "Y",
                    "unformatted_text": _bounded_text(
                        text.get("UnformattedTextValue"),
                        "presentation-state annotation text",
                        MAX_TEXT_CHARACTERS,
                    ),
                }
            )
        result.append(
            {
                "annotation_id": f"annotation_{annotation_index:03d}",
                "graphic_layer": layer,
                "referenced_instance_ids": instance_ids,
                "graphics": graphics,
                "texts": texts,
            }
        )
    return result


def _presentation(
    dataset: Any,
    referenced_instance_ids: list[str],
    instances: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    unsupported_keywords = {
        "MaskSubtractionSequence",
        "MaskOperation",
        "ApplicableFrameRange",
        "MaskFrameNumbers",
        "ContrastFrameAveraging",
        "RecommendedViewingMode",
    }
    if any(
        element.tag.group in range(0x6000, 0x6100)
        or element.keyword in unsupported_keywords
        for element in dataset.iterall()
    ):
        raise ValueError("presentation state uses unsupported mask or overlay features")
    if (
        int(dataset.get("ImageRotation", 0) or 0) != 0
        or str(dataset.get("ImageHorizontalFlip", "N")) != "N"
        or str(dataset.get("PresentationLUTShape", "IDENTITY")) != "IDENTITY"
        or "PresentationLUTSequence" in dataset
        or "ModalityLUTSequence" in dataset
        or dataset.get("ShutterShape")
    ):
        raise ValueError("presentation state uses unsupported spatial/LUT/shutter features")
    presentation_slope = dataset.get("RescaleSlope")
    presentation_intercept = dataset.get("RescaleIntercept")
    if (presentation_slope is None) != (presentation_intercept is None):
        raise ValueError("presentation state has an incomplete modality transform")
    if presentation_slope is None:
        presentation_slope_value = 1.0
        presentation_intercept_value = 0.0
    else:
        presentation_slope_value = _finite(presentation_slope)
        presentation_intercept_value = _finite(presentation_intercept)
        if presentation_slope_value == 0:
            raise ValueError("presentation state modality slope is zero")
    voi_items = list(dataset.get("SoftcopyVOILUTSequence", []))
    if len(voi_items) != 1:
        raise ValueError("presentation state requires one linear VOI item")
    voi = voi_items[0]
    if voi.get("ReferencedImageSequence") or "VOILUTSequence" in voi:
        raise ValueError("presentation state uses a scoped or lookup-table VOI")
    if "VOILUTFunction" in voi and str(voi.get("VOILUTFunction")) != "LINEAR":
        raise ValueError("presentation state uses an unsupported VOI LUT function")
    center = _single_number(voi.get("WindowCenter"), "window center")
    width = _single_number(voi.get("WindowWidth"), "window width")
    if width < 1:
        raise ValueError("presentation-state window width must be at least one")
    lower = center - 0.5 - (width - 1) / 2
    upper = center - 0.5 + (width - 1) / 2

    area_items = list(dataset.get("DisplayedAreaSelectionSequence", []))
    if len(area_items) != 1:
        raise ValueError("presentation state requires one displayed area")
    area = area_items[0]
    if (
        area.get("ReferencedImageSequence")
        or str(area.get("PresentationSizeMode", "")) != "SCALE TO FIT"
    ):
        raise ValueError("presentation state uses a scoped or unsupported displayed area")
    top_left = [_finite(value) for value in area.get("DisplayedAreaTopLeftHandCorner", [])]
    bottom_right = [
        _finite(value) for value in area.get("DisplayedAreaBottomRightHandCorner", [])
    ]
    if top_left != [1.0, 1.0] or len(bottom_right) != 2:
        raise ValueError("presentation state crops the source image")
    dimensions = {
        (instances[instance_id].get("columns"), instances[instance_id].get("rows"))
        for instance_id in referenced_instance_ids
    }
    if len(dimensions) != 1:
        raise ValueError("presentation state references mixed source dimensions")
    columns, rows = next(iter(dimensions))
    if (
        type(columns) is not int
        or type(rows) is not int
        or bottom_right != [float(columns), float(rows)]
    ):
        raise ValueError("presentation state displayed area is not the full source image")
    presentation_spacing = area.get("PresentationPixelSpacing")
    presentation_aspect = area.get("PresentationPixelAspectRatio")
    if presentation_spacing is not None and presentation_aspect is not None:
        raise ValueError("presentation state has ambiguous displayed-area aspect")
    if presentation_spacing is not None:
        aspect_values = [_finite(value) for value in presentation_spacing]
    elif presentation_aspect is not None:
        aspect_values = [_finite(value) for value in presentation_aspect]
    else:
        raise ValueError("presentation state displayed-area aspect is missing")
    if len(aspect_values) != 2 or any(value <= 0 for value in aspect_values):
        raise ValueError("presentation state displayed-area aspect is invalid")
    presentation_ratio = aspect_values[0] / aspect_values[1]
    for instance_id in referenced_instance_ids:
        source = instances[instance_id]
        source_spacing = source.get("pixel_spacing")
        source_aspect = source.get("pixel_aspect_ratio")
        if source_spacing is not None:
            source_values = [_finite(value) for value in source_spacing]
        elif source_aspect is not None:
            source_values = [_finite(value) for value in source_aspect]
        else:
            raise ValueError("source image pixel aspect is unavailable")
        if (
            len(source_values) != 2
            or any(value <= 0 for value in source_values)
            or not math.isclose(
                source_values[0] / source_values[1],
                presentation_ratio,
                rel_tol=1e-9,
                abs_tol=1e-12,
            )
        ):
            raise ValueError("presentation state pixel aspect differs from source display")
        if (
            source.get("number_of_frames") != 1
            or source.get("photometric_interpretation")
            not in {"MONOCHROME1", "MONOCHROME2"}
            or source.get("has_modality_lut_sequence") is not False
        ):
            raise ValueError("source image grayscale pipeline is unsupported")
        slope = source.get("rescale_slope")
        intercept = source.get("rescale_intercept")
        if (slope is None) != (intercept is None):
            raise ValueError("source image modality transform is incomplete")
        source_slope = 1.0 if slope is None else _finite(slope)
        source_intercept = 0.0 if intercept is None else _finite(intercept)
        if not math.isclose(source_slope, presentation_slope_value) or not math.isclose(
            source_intercept, presentation_intercept_value
        ):
            raise ValueError(
                "presentation-state modality transform differs from source display"
            )
    return {
        "rotation_degrees": 0,
        "horizontal_flip": False,
        "modality_transform": "SOURCE_EQUIVALENT_LINEAR",
        "voi_lut_function": "LINEAR",
        "presentation_lut_shape": "IDENTITY",
        "source_pixel_aspect_ratio_verified": True,
        "window_center": center,
        "window_width": width,
        "voi_range": {"lower": lower, "upper": upper},
        "displayed_area": {
            "top_left": top_left,
            "bottom_right": bottom_right,
            "presentation_size_mode": "SCALE TO FIT",
        },
        "annotation_style": "scanview_high_contrast_source_geometry",
    }


def _build_state(
    presentation_state_id: str,
    source: dict[str, Any],
    payload: bytes,
    instances: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if not payload or len(payload) > MAX_PRESENTATION_STATE_BYTES:
        raise ValueError("presentation-state source size is unsupported")
    dataset = dcmread(io.BytesIO(payload), stop_before_pixels=True, force=False)
    if (
        str(dataset.get("SOPClassUID", "")) != GSPS_SOP_CLASS_UID
        or str(dataset.get("Modality", "")) != "PR"
        or source.get("sop_class_uid") != GSPS_SOP_CLASS_UID
        or opaque_id("instance", str(dataset.get("SOPInstanceUID", "")))
        != presentation_state_id
    ):
        raise ValueError("presentation-state source identity is invalid")
    referenced_series, referenced_instance_ids = _referenced_instances(
        dataset, instances
    )
    if not SHA256.fullmatch(str(source.get("sha256") or "")) or any(
        not SHA256.fullmatch(str(instances[instance_id].get("sha256") or ""))
        for instance_id in referenced_instance_ids
    ):
        raise ValueError("presentation state requires hashed exact source instances")
    if hashlib.sha256(payload).hexdigest() != source["sha256"]:
        raise ValueError("presentation-state source hash changed")
    patient_contexts = {
        item["patient_context_id"] for item in referenced_series
    } | {source["patient_context_id"]}
    if len(patient_contexts) != 1:
        raise ValueError("presentation state crosses opaque patient contexts")
    if any(item["study_id"] != source["study_id"] for item in referenced_series):
        raise ValueError("presentation state references images from another study")
    presentation = _presentation(dataset, referenced_instance_ids, instances)
    annotations = _annotations(dataset, referenced_instance_ids, instances)
    graphic_count = sum(len(item["graphics"]) for item in annotations)
    text_count = sum(len(item["texts"]) for item in annotations)
    return {
        "presentation_state_id": presentation_state_id,
        "source": {
            "study_id": source["study_id"],
            "series_id": source["series_id"],
            "instance_id": presentation_state_id,
            "patient_context_id": source["patient_context_id"],
            "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        },
        "display_status": "supported_read_only",
        "referenced_series": referenced_series,
        "referenced_instance_count": len(referenced_instance_ids),
        "presentation": presentation,
        "annotations": annotations,
        "annotation_count": len(annotations),
        "graphic_count": graphic_count,
        "text_count": text_count,
        "author_identity_authenticated": False,
        "scanview_interpretation_added": False,
        "source_text_clinical_meaning": "not_assessed",
    }


def build_presentation_state_catalog(
    catalog: Any,
    source_loader: Callable[[str], bytes],
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    catalog_hash, instances, presentation_state_ids = _catalog_index(catalog)
    if generated_at is None:
        generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    if not _valid_datetime(generated_at):
        raise ValueError("presentation-state catalog timestamp is invalid")
    states: list[dict[str, Any]] = []
    unsupported_states: list[dict[str, Any]] = []
    for state_id in presentation_state_ids:
        source = instances[state_id]
        try:
            payload = source_loader(state_id)
        except (KeyError, OSError, TypeError, ValueError) as error:
            raise ValueError("presentation-state source is unavailable or changed") from error
        if not isinstance(payload, bytes):
            raise ValueError("presentation-state loader must return bytes")
        try:
            states.append(_build_state(state_id, source, payload, instances))
        except (
            EOFError,
            InvalidDicomError,
            KeyError,
            OverflowError,
            TypeError,
            ValueError,
        ) as error:
            reason = str(error)
            allowed_prefixes = (
                "annotation ",
                "graphic layer ",
                "presentation state ",
                "presentation-state ",
                "supported annotations ",
                "text anchor point ",
                "window center ",
                "window width ",
            )
            if not reason.startswith(allowed_prefixes):
                reason = "presentation-state DICOM structure is invalid"
            unsupported_states.append(
                {
                    "presentation_state_id": state_id,
                    "display_status": "unsupported",
                    "reason": reason[:240] or "presentation-state validation failed",
                }
            )
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "generated_at": generated_at,
        "catalog_content_sha256": catalog_hash,
        "local_only": True,
        "privacy": {
            "classification": "sensitive_local_medical_data",
            "direct_identifier_tags_excluded": True,
            "annotation_text_may_contain_identifiers": True,
            "deidentified": False,
            "contains_pixels": False,
            "contains_paths": False,
            "contains_annotation_text": any(state["text_count"] for state in states),
        },
        "state_count": len(states) + len(unsupported_states),
        "supported_state_count": len(states),
        "unsupported_state_count": len(unsupported_states),
        "states": states,
        "unsupported_states": unsupported_states,
        "permissions": {
            "exact_source_navigation_authorized": True,
            "apply_saved_voi_authorized": True,
            "display_source_annotations_authorized": True,
            "edit_source_annotations_authorized": False,
            "interpret_annotation_text_as_measurement_authorized": False,
            "author_identity_authenticated": False,
            "diagnosis_authorized": False,
            "response_classification_authorized": False,
            "clinical_conclusion_authorized": False,
        },
        "limitations": list(LIMITATIONS),
    }


def validate_presentation_state_catalog(
    catalog: Any,
    source_loader: Callable[[str], bytes],
    artifact: Any,
) -> dict[str, Any]:
    if not isinstance(artifact, dict):
        raise ValueError("presentation-state catalog must be an object")
    rebuilt = build_presentation_state_catalog(
        catalog,
        source_loader,
        generated_at=artifact.get("generated_at"),
    )
    if artifact != rebuilt:
        raise ValueError("presentation-state catalog does not match local DICOM sources")
    return artifact


def presentation_state_summary(
    catalog: Any,
    source_loader: Callable[[str], bytes],
    artifact: Any,
) -> dict[str, Any]:
    try:
        validated = validate_presentation_state_catalog(catalog, source_loader, artifact)
    except (KeyError, OSError, TypeError, ValueError):
        return {
            "schema_version": SCHEMA_VERSION,
            "artifact_type": SUMMARY_ARTIFACT_TYPE,
            "valid": False,
            "errors": ["presentation-state catalog is invalid or source bytes changed"],
            "state_count": 0,
            "supported_state_count": 0,
            "unsupported_state_count": 0,
            "annotation_count": 0,
            "graphic_count": 0,
            "text_count": 0,
            "contains_annotation_text": False,
            "contains_source_ids": False,
            "contains_annotation_geometry": False,
            "exact_source_navigation_authorized": False,
            "clinical_conclusion_authorized": False,
            "local_only": True,
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": SUMMARY_ARTIFACT_TYPE,
        "valid": True,
        "errors": [],
        "state_count": validated["state_count"],
        "supported_state_count": validated["supported_state_count"],
        "unsupported_state_count": validated["unsupported_state_count"],
        "annotation_count": sum(
            state["annotation_count"] for state in validated["states"]
        ),
        "graphic_count": sum(state["graphic_count"] for state in validated["states"]),
        "text_count": sum(state["text_count"] for state in validated["states"]),
        "contains_annotation_text": False,
        "contains_source_ids": False,
        "contains_annotation_geometry": False,
        "exact_source_navigation_authorized": True,
        "clinical_conclusion_authorized": False,
        "local_only": True,
    }
