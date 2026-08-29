from __future__ import annotations

import hashlib
import io
import json
import math
import os
import re
import stat
import unicodedata
from collections.abc import Iterator, Sequence
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Callable

from pydicom import dcmread
from pydicom.errors import InvalidDicomError
from pydicom.tag import Tag
from pydicom.uid import ExplicitVRLittleEndian, ImplicitVRLittleEndian, SegmentationStorage

from .catalog import opaque_id


SCHEMA_VERSION = "1.0.0"
ARTIFACT_TYPE = "scanview.source-segmentation-catalog"
SUMMARY_ARTIFACT_TYPE = "scanview.source-segmentation-summary"
MAX_SEGMENTATION_BYTES = 256 * 1024 * 1024
MAX_SOURCE_INSTANCES = 4096
MAX_SEGMENTS = 32
MAX_FRAMES = 131072
MAX_MASK_VOXELS = 64 * 1024 * 1024
MAX_TOTAL_MASK_BYTES = 128 * 1024 * 1024
MAX_TOTAL_DECODED_FRAME_VOXELS = 64 * 1024 * 1024
MAX_TEXT_CHARACTERS = 256
SHA256 = re.compile(r"^[0-9a-f]{64}$")
OPAQUE_ID = {
    kind: re.compile(rf"^{kind}_[0-9a-f]{{20}}$")
    for kind in ("study", "series", "instance", "frame", "patient")
}

LIMITATIONS = [
    "These are read-only masks extracted from source-carried DICOM Segmentation objects and rejoined to exact local MR/CT source instances.",
    "ScanView does not authenticate the segmentation creator, verify the algorithm, or assess segment labels and coded properties for identifiers, accuracy, or clinical meaning.",
    "Only a conservative native-grid subset is displayed: uncompressed binary SEG, one referenced MR/CT series, single-frame sources, exact matrix/orientation/position/spacing, and one explicit source-image reference with Spatial Locations Preserved YES per frame.",
    "Passing this narrow ScanView import profile is not full DICOM conformance certification; technical marked-voxel counts and native-grid volumes remain unreviewed, unsupported objects fail closed, and original DICOM objects remain authoritative.",
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


def _finite(value: Any, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} is invalid") from error
    if not math.isfinite(result):
        raise ValueError(f"{label} is non-finite")
    return result


def _integer(value: Any, label: str, minimum: int, maximum: int) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} is invalid") from error
    if isinstance(value, float) and not value.is_integer():
        raise ValueError(f"{label} is not an integer")
    if result < minimum or result > maximum:
        raise ValueError(f"{label} is outside the supported range")
    return result


def _numbers(value: Any, length: int, label: str) -> list[float]:
    if value is None:
        raise ValueError(f"{label} is missing")
    try:
        result = [_finite(item, label) for item in value]
    except TypeError as error:
        raise ValueError(f"{label} is invalid") from error
    if len(result) != length:
        raise ValueError(f"{label} has the wrong length")
    return result


def _bounded_text(value: Any, label: str, *, required: bool = True) -> str | None:
    if value is None:
        if required:
            raise ValueError(f"{label} is missing")
        return None
    result = str(value).strip()
    if not result:
        if required:
            raise ValueError(f"{label} is empty")
        return None
    if len(result) > MAX_TEXT_CHARACTERS or any(
        unicodedata.category(character).startswith("C") for character in result
    ):
        raise ValueError(f"{label} is unsupported")
    return result


def _close(left: float, right: float, tolerance: float) -> bool:
    return math.isfinite(left) and math.isfinite(right) and abs(left - right) <= tolerance


def _close_vector(left: Sequence[float], right: Sequence[float], tolerance: float) -> bool:
    return len(left) == len(right) and all(
        _close(float(a), float(b), tolerance) for a, b in zip(left, right, strict=True)
    )


def _cross(left: Sequence[float], right: Sequence[float]) -> list[float]:
    return [
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    ]


def _dot(left: Sequence[float], right: Sequence[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))


def _normal(orientation: Sequence[float]) -> list[float]:
    row = orientation[:3]
    column = orientation[3:]
    row_norm = math.sqrt(_dot(row, row))
    column_norm = math.sqrt(_dot(column, column))
    if (
        not _close(row_norm, 1.0, 1e-4)
        or not _close(column_norm, 1.0, 1e-4)
        or not _close(_dot(row, column), 0.0, 1e-4)
    ):
        raise ValueError("source image orientation is not strictly orthonormal")
    result = _cross(row, column)
    magnitude = math.sqrt(_dot(result, result))
    if not _close(magnitude, 1.0, 1e-4):
        raise ValueError("source image normal is invalid")
    return [value / magnitude for value in result]


def _catalog_index(
    catalog: Any,
) -> tuple[str, dict[str, dict[str, Any]], list[str]]:
    if (
        not isinstance(catalog, dict)
        or catalog.get("schema_version") != "1.0.0"
        or not isinstance(catalog.get("studies"), list)
    ):
        raise ValueError("source segmentations require a ScanView manifest v1 catalog")
    try:
        catalog_hash = hashlib.sha256(_canonical(_catalog_content(catalog))).hexdigest()
    except (TypeError, ValueError) as error:
        raise ValueError("ScanView catalog contains unsupported values") from error

    instances: dict[str, dict[str, Any]] = {}
    segmentation_ids: list[str] = []
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
            frame_id = series.get("frame_of_reference_id")
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
                    "frame_of_reference_id": frame_id,
                    "modality": modality,
                    "rows": instance.get("rows"),
                    "columns": instance.get("columns"),
                    "pixel_spacing": instance.get("pixel_spacing"),
                    "slice_thickness": instance.get("slice_thickness"),
                    "orientation": instance.get("image_orientation_patient"),
                    "position": instance.get("image_position_patient"),
                    "number_of_frames": instance.get("number_of_frames", 1),
                    "bytes": instance.get("bytes"),
                    "sha256": instance.get("sha256"),
                    "sop_class_uid": instance.get("sop_class_uid"),
                }
                instances[instance_id] = record
                if str(instance.get("sop_class_uid", "")) == str(SegmentationStorage):
                    segmentation_ids.append(instance_id)
    return catalog_hash, instances, sorted(segmentation_ids)


def read_stable_segmentation_bytes(
    path: Path,
    *,
    expected_bytes: int | None,
    expected_sha256: str | None,
) -> bytes:
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
    except OSError as error:
        raise ValueError("DICOM SEG source cannot be opened safely") from error
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_size < 1
            or before.st_size > MAX_SEGMENTATION_BYTES
            or expected_bytes is not None
            and before.st_size != expected_bytes
        ):
            raise ValueError("DICOM SEG source identity or size changed")
        chunks: list[bytes] = []
        total = 0
        digest = hashlib.sha256()
        while chunk := os.read(descriptor, 1024 * 1024):
            total += len(chunk)
            if total > MAX_SEGMENTATION_BYTES:
                raise ValueError("DICOM SEG source exceeds the size limit")
            chunks.append(chunk)
            digest.update(chunk)
        after = os.fstat(descriptor)
        fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if total != before.st_size or any(
            getattr(before, field) != getattr(after, field) for field in fields
        ):
            raise ValueError("DICOM SEG source changed while it was read")
        observed_sha256 = digest.hexdigest()
        if expected_sha256 is not None and observed_sha256 != expected_sha256:
            raise ValueError("DICOM SEG source hash changed")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def registry_segmentation_source_loader(
    catalog: Any,
    registry: dict[str, Path],
) -> Callable[[str], bytes]:
    _, instances, _ = _catalog_index(catalog)

    def load(instance_id: str) -> bytes:
        source = instances.get(instance_id)
        path = registry.get(instance_id)
        if source is None or path is None:
            raise ValueError("DICOM SEG source is unavailable")
        return read_stable_segmentation_bytes(
            path,
            expected_bytes=source.get("bytes"),
            expected_sha256=source.get("sha256"),
        )

    return load


def _single_item(owner: Any, name: str, label: str) -> Any:
    sequence = list(getattr(owner, name, []))
    if len(sequence) != 1:
        raise ValueError(f"{label} must contain exactly one item")
    return sequence[0]


def _code(owner: Any, name: str, label: str) -> dict[str, str]:
    item = _single_item(owner, name, label)
    return {
        "value": _bounded_text(getattr(item, "CodeValue", None), f"{label} value"),
        "scheme": _bounded_text(
            getattr(item, "CodingSchemeDesignator", None), f"{label} scheme"
        ),
        "meaning": _bounded_text(
            getattr(item, "CodeMeaning", None), f"{label} meaning"
        ),
    }


def _code_matches(owner: Any, name: str, expected: tuple[str, str]) -> bool:
    try:
        observed = _code(owner, name, name)
    except ValueError:
        return False
    return (observed["value"], observed["scheme"]) == expected


def _functional_item(frame: Any, shared: Any, name: str, label: str) -> Any:
    per_frame = list(getattr(frame, name, []))
    shared_items = list(getattr(shared, name, []))
    if len(per_frame) > 1 or len(shared_items) > 1 or per_frame and shared_items:
        raise ValueError(f"DICOM SEG {label} functional group is ambiguous")
    items = per_frame or shared_items
    if len(items) != 1:
        raise ValueError(f"DICOM SEG {label} functional group is missing")
    return items[0]


def _source_geometry(
    source_series_id: str,
    instances: dict[str, dict[str, Any]],
) -> tuple[list[str], dict[str, int], dict[str, Any]]:
    source_ids = [
        instance_id
        for instance_id, source in instances.items()
        if source["series_id"] == source_series_id and source["modality"] in {"MR", "CT"}
    ]
    if not 3 <= len(source_ids) <= MAX_SOURCE_INSTANCES:
        raise ValueError("DICOM SEG native source series has an unsupported image count")
    first = instances[source_ids[0]]
    rows = _integer(first.get("rows"), "source rows", 2, 65535)
    columns = _integer(first.get("columns"), "source columns", 2, 65535)
    pixel_spacing = _numbers(first.get("pixel_spacing"), 2, "source pixel spacing")
    slice_thickness = _finite(first.get("slice_thickness"), "source slice thickness")
    orientation = _numbers(first.get("orientation"), 6, "source orientation")
    normal = _normal(orientation)
    if any(value <= 0 for value in pixel_spacing) or slice_thickness <= 0:
        raise ValueError("source pixel measures are not positive")
    planes: list[tuple[float, str, list[float]]] = []
    for instance_id in source_ids:
        source = instances[instance_id]
        if (
            source["modality"] != first["modality"]
            or source["study_id"] != first["study_id"]
            or source["patient_context_id"] != first["patient_context_id"]
            or source["frame_of_reference_id"] != first["frame_of_reference_id"]
            or _integer(source.get("number_of_frames"), "source frame count", 1, 1) != 1
            or _integer(source.get("rows"), "source rows", 2, 65535) != rows
            or _integer(source.get("columns"), "source columns", 2, 65535) != columns
            or not _close_vector(
                _numbers(source.get("pixel_spacing"), 2, "source pixel spacing"),
                pixel_spacing,
                1e-4,
            )
            or not _close_vector(
                _numbers(source.get("orientation"), 6, "source orientation"),
                orientation,
                1e-4,
            )
            or not _close(
                _finite(source.get("slice_thickness"), "source slice thickness"),
                slice_thickness,
                0.01,
            )
        ):
            raise ValueError("DICOM SEG source series does not have one exact native grid")
        position = _numbers(source.get("position"), 3, "source position")
        planes.append((_dot(position, normal), instance_id, position))
    planes.sort(key=lambda item: (item[0], item[1]))
    coordinates = [coordinate for coordinate, _, _ in planes]
    ordered_ids = [instance_id for _, instance_id, _ in planes]
    positions = [position for _, _, position in planes]
    gaps = [
        coordinates[index] - coordinates[index - 1]
        for index in range(1, len(coordinates))
    ]
    if any(gap < 0.01 for gap in gaps):
        raise ValueError("DICOM SEG source planes overlap or are duplicated")
    slice_spacing = median(gaps)
    tolerance = max(0.01, slice_spacing * 0.001)
    if any(abs(gap - slice_spacing) > tolerance for gap in gaps):
        raise ValueError("DICOM SEG source slice spacing is irregular")
    origin = positions[0]
    origin_projection = coordinates[0]
    for position, projection in zip(positions, coordinates, strict=True):
        displacement = [value - origin[axis] for axis, value in enumerate(position)]
        normal_displacement = [
            value * (projection - origin_projection) for value in normal
        ]
        in_plane = [
            value - normal_displacement[axis]
            for axis, value in enumerate(displacement)
        ]
        if math.sqrt(_dot(in_plane, in_plane)) > 0.01:
            raise ValueError("DICOM SEG source planes have in-plane drift or tilt")
    voxel_count = rows * columns * len(ordered_ids)
    if not 1 <= voxel_count <= MAX_MASK_VOXELS:
        raise ValueError("DICOM SEG source grid exceeds the local mask safety bound")
    return ordered_ids, {value: index for index, value in enumerate(ordered_ids)}, {
        "rows": rows,
        "columns": columns,
        "pixel_spacing": pixel_spacing,
        "slice_spacing": slice_spacing,
        "slice_thickness": slice_thickness,
        "orientation": orientation,
        "normal": normal,
        "voxel_volume_mm3": pixel_spacing[0] * pixel_spacing[1] * slice_spacing,
    }


def _decode_binary_frames(
    dataset: Any,
    rows: int,
    columns: int,
    count: int,
) -> Iterator[bytes]:
    try:
        pixel_data = bytes(dataset.PixelData)
    except (AttributeError, TypeError, ValueError) as error:
        raise ValueError("DICOM SEG Pixel Data is missing") from error
    bits_per_frame = rows * columns
    total_bits = bits_per_frame * count
    if total_bits > MAX_TOTAL_MASK_BYTES:
        raise ValueError("DICOM SEG decoded frames exceed the local processing bound")
    required_bytes = (total_bits + 7) // 8
    if len(pixel_data) not in {required_bytes, required_bytes + (required_bytes % 2)}:
        raise ValueError("DICOM SEG Pixel Data length is inconsistent")
    if len(pixel_data) > required_bytes and any(pixel_data[required_bytes:]):
        raise ValueError("DICOM SEG has a non-zero trailing pad byte")
    for frame_index in range(count):
        start = frame_index * bits_per_frame
        frame = bytearray(bits_per_frame)
        for pixel_index in range(bits_per_frame):
            bit_offset = start + pixel_index
            frame[pixel_index] = (
                pixel_data[bit_offset // 8] >> (bit_offset % 8)
            ) & 1
        yield bytes(frame)


def _parse_segmentation(
    segmentation_id: str,
    segmentation_bytes: bytes,
    source: dict[str, Any],
    instances: dict[str, dict[str, Any]],
    mask_budget: int,
    decoded_voxel_budget: list[int],
) -> tuple[dict[str, Any], dict[tuple[str, int], bytes], set[str]]:
    try:
        dataset = dcmread(io.BytesIO(segmentation_bytes), force=False)
    except (InvalidDicomError, OSError, ValueError) as error:
        raise ValueError("DICOM SEG is not a readable Part 10 object") from error
    transfer_syntax = str(getattr(dataset.file_meta, "TransferSyntaxUID", ""))
    if transfer_syntax not in {
        str(ExplicitVRLittleEndian),
        str(ImplicitVRLittleEndian),
    }:
        raise ValueError("DICOM SEG uses an unsupported compressed or non-little-endian syntax")
    required = {
        "SOPClassUID": str(SegmentationStorage),
        "Modality": "SEG",
        "SegmentationType": "BINARY",
        "SamplesPerPixel": 1,
        "PhotometricInterpretation": "MONOCHROME2",
        "BitsAllocated": 1,
        "BitsStored": 1,
        "HighBit": 0,
        "PixelRepresentation": 0,
    }
    for name, expected in required.items():
        if getattr(dataset, name, None) != expected:
            raise ValueError(f"DICOM SEG {name} is outside the supported binary profile")
    image_type = [str(item) for item in getattr(dataset, "ImageType", [])]
    if image_type != ["DERIVED", "PRIMARY"]:
        raise ValueError("DICOM SEG Image Type is outside the supported profile")
    _bounded_text(getattr(dataset, "ContentLabel", None), "DICOM SEG content label")
    rows = _integer(getattr(dataset, "Rows", None), "DICOM SEG rows", 2, 65535)
    columns = _integer(
        getattr(dataset, "Columns", None), "DICOM SEG columns", 2, 65535
    )
    frame_count = _integer(
        getattr(dataset, "NumberOfFrames", None),
        "DICOM SEG frame count",
        1,
        MAX_FRAMES,
    )
    decoded_voxels = rows * columns * frame_count
    if decoded_voxels > decoded_voxel_budget[0]:
        raise ValueError("DICOM SEG frames exceed the catalog-wide local processing bound")
    decoded_voxel_budget[0] -= decoded_voxels
    if len(segmentation_bytes) != source["bytes"] or hashlib.sha256(
        segmentation_bytes
    ).hexdigest() != source["sha256"]:
        raise ValueError("DICOM SEG source bytes do not match the indexed catalog")
    if str(getattr(dataset, "StudyInstanceUID", "")) == "":
        raise ValueError("DICOM SEG study identity is missing")
    if opaque_id("study", str(dataset.StudyInstanceUID)) != source["study_id"]:
        raise ValueError("DICOM SEG study does not match its indexed source")
    frame_uid = str(getattr(dataset, "FrameOfReferenceUID", ""))
    if not frame_uid or opaque_id("frame", frame_uid) != source["frame_of_reference_id"]:
        raise ValueError("DICOM SEG Frame of Reference does not match its catalog record")

    referenced_series = list(getattr(dataset, "ReferencedSeriesSequence", []))
    if len(referenced_series) != 1:
        raise ValueError("DICOM SEG must reference exactly one source series")
    series_reference = referenced_series[0]
    source_series_id = opaque_id(
        "series", str(getattr(series_reference, "SeriesInstanceUID", ""))
    )
    ordered_ids, source_indexes, geometry = _source_geometry(source_series_id, instances)
    first_source = instances[ordered_ids[0]]
    if (
        first_source["study_id"] != source["study_id"]
        or first_source["patient_context_id"] != source["patient_context_id"]
        or first_source["frame_of_reference_id"] != source["frame_of_reference_id"]
    ):
        raise ValueError("DICOM SEG and referenced images do not share one source context")
    if rows != geometry["rows"] or columns != geometry["columns"]:
        raise ValueError("DICOM SEG matrix does not match the native source grid")
    referenced_instance_ids: list[str] = []
    for item in getattr(series_reference, "ReferencedInstanceSequence", []):
        instance_id = opaque_id(
            "instance", str(getattr(item, "ReferencedSOPInstanceUID", ""))
        )
        referenced_source = instances.get(instance_id)
        if (
            instance_id not in source_indexes
            or referenced_source is None
            or str(getattr(item, "ReferencedSOPClassUID", ""))
            != referenced_source["sop_class_uid"]
            or instance_id in referenced_instance_ids
        ):
            raise ValueError("DICOM SEG contains an unavailable source reference")
        referenced_instance_ids.append(instance_id)
    if not referenced_instance_ids:
        raise ValueError("DICOM SEG source reference set is empty")

    segment_items = list(getattr(dataset, "SegmentSequence", []))
    if not 1 <= len(segment_items) <= MAX_SEGMENTS:
        raise ValueError("DICOM SEG has an unsupported segment count")
    segments: dict[int, dict[str, Any]] = {}
    for segment_item in segment_items:
        number = _integer(
            getattr(segment_item, "SegmentNumber", None),
            "DICOM SEG Segment Number",
            1,
            65535,
        )
        if number in segments:
            raise ValueError("DICOM SEG contains duplicate Segment Numbers")
        algorithm_type = str(getattr(segment_item, "SegmentAlgorithmType", ""))
        if algorithm_type not in {"MANUAL", "SEMIAUTOMATIC", "AUTOMATIC"}:
            raise ValueError("DICOM SEG Segment Algorithm Type is unsupported")
        algorithm_name = _bounded_text(
            getattr(segment_item, "SegmentAlgorithmName", None),
            "segment algorithm name",
            required=algorithm_type != "MANUAL",
        )
        display_cielab = getattr(segment_item, "RecommendedDisplayCIELabValue", None)
        recommended = None
        if display_cielab is not None:
            recommended = [
                _integer(value, "recommended display CIELab value", 0, 65535)
                for value in display_cielab
            ]
            if len(recommended) != 3:
                raise ValueError("recommended display CIELab value has the wrong length")
        segments[number] = {
            "segment_number": number,
            "segment_label": _bounded_text(
                getattr(segment_item, "SegmentLabel", None), "segment label"
            ),
            "algorithm_type": algorithm_type,
            "algorithm_name": algorithm_name,
            "property_category": _code(
                segment_item,
                "SegmentedPropertyCategoryCodeSequence",
                "segmented property category",
            ),
            "property_type": _code(
                segment_item,
                "SegmentedPropertyTypeCodeSequence",
                "segmented property type",
            ),
            "recommended_display_cielab": recommended,
            "frame_count": 0,
            "marked_voxel_count": 0,
            "computed_volume_mm3": 0.0,
            "computed_volume_ml": 0.0,
            "mask_sha256": "",
        }

    dimension_organization = _single_item(
        dataset,
        "DimensionOrganizationSequence",
        "dimension organization",
    )
    dimension_uid = _bounded_text(
        getattr(dimension_organization, "DimensionOrganizationUID", None),
        "dimension organization UID",
    )
    expected_dimension_pointers = {
        int(Tag(0x0062000B)): int(Tag(0x0062000A)),
        int(Tag(0x00200032)): int(Tag(0x00209113)),
    }
    dimension_pointers: list[int] = []
    for item in list(getattr(dataset, "DimensionIndexSequence", [])):
        try:
            pointer = int(item.DimensionIndexPointer)
            functional_group_pointer = int(item.FunctionalGroupPointer)
        except (AttributeError, TypeError, ValueError) as error:
            raise ValueError("DICOM SEG dimension index is incomplete") from error
        if (
            pointer not in expected_dimension_pointers
            or functional_group_pointer != expected_dimension_pointers[pointer]
            or str(getattr(item, "DimensionOrganizationUID", "")) != dimension_uid
            or pointer in dimension_pointers
        ):
            raise ValueError("DICOM SEG dimension index is outside the supported profile")
        dimension_pointers.append(pointer)
    if set(dimension_pointers) != set(expected_dimension_pointers):
        raise ValueError("DICOM SEG requires segment and plane-position dimensions")
    dimension_ordinals_by_value: dict[int, dict[Any, int]] = {
        pointer: {} for pointer in dimension_pointers
    }
    dimension_values_by_ordinal: dict[int, dict[int, Any]] = {
        pointer: {} for pointer in dimension_pointers
    }

    frame_groups = list(getattr(dataset, "PerFrameFunctionalGroupsSequence", []))
    if len(frame_groups) != frame_count:
        raise ValueError("DICOM SEG functional groups do not match the frame count")
    shared = _single_item(
        dataset, "SharedFunctionalGroupsSequence", "shared functional groups"
    )
    required_mask_bytes = rows * columns * len(ordered_ids) * len(segments)
    if required_mask_bytes > mask_budget:
        raise ValueError("DICOM SEG masks exceed the aggregate local safety bound")
    masks = {
        number: bytearray(rows * columns * len(ordered_ids)) for number in segments
    }
    frames = _decode_binary_frames(dataset, rows, columns, frame_count)
    used: set[tuple[int, int]] = set()
    frame_source_ids: set[str] = set()
    for frame, group in zip(frames, frame_groups, strict=True):
        segment_identification = _functional_item(
            group,
            shared,
            "SegmentIdentificationSequence",
            "segment identification",
        )
        segment_number = _integer(
            getattr(segment_identification, "ReferencedSegmentNumber", None),
            "referenced segment number",
            1,
            65535,
        )
        if segment_number not in segments:
            raise ValueError("DICOM SEG frame references an unavailable segment")
        derivation = _functional_item(
            group, shared, "DerivationImageSequence", "derivation image"
        )
        if not _code_matches(
            derivation,
            "DerivationCodeSequence",
            ("113076", "DCM"),
        ):
            raise ValueError("DICOM SEG frame lacks the standard segmentation derivation code")
        source_image = _single_item(
            derivation, "SourceImageSequence", "frame source image"
        )
        if str(getattr(source_image, "SpatialLocationsPreserved", "")) != "YES":
            raise ValueError(
                "DICOM SEG frame does not explicitly preserve source spatial locations"
            )
        if not _code_matches(
            source_image,
            "PurposeOfReferenceCodeSequence",
            ("121322", "DCM"),
        ):
            raise ValueError("DICOM SEG frame lacks the standard source-image purpose code")
        if "ReferencedFrameNumber" in source_image:
            raise ValueError("DICOM SEG references an unsupported multiframe source")
        source_instance_id = opaque_id(
            "instance", str(getattr(source_image, "ReferencedSOPInstanceUID", ""))
        )
        source_record = instances.get(source_instance_id)
        if (
            source_instance_id not in source_indexes
            or source_instance_id not in referenced_instance_ids
            or source_record is None
            or str(getattr(source_image, "ReferencedSOPClassUID", ""))
            != source_record["sop_class_uid"]
        ):
            raise ValueError("DICOM SEG frame does not reference an exact source image")
        source_index = source_indexes[source_instance_id]
        if (segment_number, source_index) in used:
            raise ValueError("DICOM SEG repeats one segment on one source plane")
        used.add((segment_number, source_index))
        frame_source_ids.add(source_instance_id)

        frame_content = _single_item(
            group,
            "FrameContentSequence",
            "frame content",
        )
        dimension_values = [
            _integer(value, "dimension index value", 1, 65535)
            for value in getattr(frame_content, "DimensionIndexValues", [])
        ]
        indexed_values: dict[int, Any] = {
            int(Tag(0x0062000B)): segment_number,
            int(Tag(0x00200032)): source_instance_id,
        }
        if len(dimension_values) != len(dimension_pointers):
            raise ValueError("DICOM SEG frame dimension indexes are incomplete")
        for pointer, ordinal in zip(
            dimension_pointers, dimension_values, strict=True
        ):
            indexed_value = indexed_values[pointer]
            known_ordinal = dimension_ordinals_by_value[pointer].get(indexed_value)
            known_value = dimension_values_by_ordinal[pointer].get(ordinal)
            if (
                (known_ordinal is not None and known_ordinal != ordinal)
                or (known_value is not None and known_value != indexed_value)
            ):
                raise ValueError(
                    "DICOM SEG frame dimension indexes contradict its source mapping"
                )
            dimension_ordinals_by_value[pointer][indexed_value] = ordinal
            dimension_values_by_ordinal[pointer][ordinal] = indexed_value

        pixel_measures = _functional_item(
            group, shared, "PixelMeasuresSequence", "pixel measures"
        )
        observed_spacing = _numbers(
            getattr(pixel_measures, "PixelSpacing", None),
            2,
            "DICOM SEG pixel spacing",
        )
        if not _close_vector(observed_spacing, geometry["pixel_spacing"], 1e-4):
            raise ValueError("DICOM SEG pixel spacing does not match the source grid")
        if not _close(
            _finite(
                getattr(pixel_measures, "SliceThickness", None),
                "DICOM SEG slice thickness",
            ),
            geometry["slice_thickness"],
            0.01,
        ):
            raise ValueError("DICOM SEG slice thickness does not match the source grid")
        if hasattr(pixel_measures, "SpacingBetweenSlices") and not _close(
            _finite(pixel_measures.SpacingBetweenSlices, "DICOM SEG slice spacing"),
            geometry["slice_spacing"],
            max(0.01, geometry["slice_spacing"] * 0.001),
        ):
            raise ValueError("DICOM SEG slice spacing does not match the source grid")
        orientation_item = _functional_item(
            group, shared, "PlaneOrientationSequence", "plane orientation"
        )
        observed_orientation = _numbers(
            getattr(orientation_item, "ImageOrientationPatient", None),
            6,
            "DICOM SEG plane orientation",
        )
        if not _close_vector(observed_orientation, geometry["orientation"], 1e-4):
            raise ValueError("DICOM SEG orientation does not match the source grid")
        position_item = _functional_item(
            group, shared, "PlanePositionSequence", "plane position"
        )
        observed_position = _numbers(
            getattr(position_item, "ImagePositionPatient", None),
            3,
            "DICOM SEG plane position",
        )
        source_position = _numbers(
            source_record["position"], 3, "source image position"
        )
        if not _close_vector(observed_position, source_position, 0.001):
            raise ValueError("DICOM SEG frame position does not match the source image")
        offset = source_index * rows * columns
        masks[segment_number][offset : offset + rows * columns] = frame
        segments[segment_number]["frame_count"] += 1

    if any(
        set(values) != set(range(1, len(values) + 1))
        for values in dimension_values_by_ordinal.values()
    ):
        raise ValueError("DICOM SEG frame dimension indexes are not contiguous")
    if frame_source_ids != set(referenced_instance_ids):
        raise ValueError("DICOM SEG top-level and per-frame source references disagree")
    output_masks: dict[tuple[str, int], bytes] = {}
    for number, mask in masks.items():
        foreground = sum(mask)
        if foreground < 1:
            raise ValueError("DICOM SEG contains an empty segment")
        payload = bytes(mask)
        volume_mm3 = foreground * geometry["voxel_volume_mm3"]
        segments[number].update(
            {
                "marked_voxel_count": foreground,
                "computed_volume_mm3": volume_mm3,
                "computed_volume_ml": volume_mm3 / 1000.0,
                "mask_sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
        output_masks[(segmentation_id, number)] = payload

    referenced_ids_in_source_order = [
        instance_id for instance_id in ordered_ids if instance_id in frame_source_ids
    ]
    return {
        "segmentation_id": segmentation_id,
        "source": {
            "study_id": source["study_id"],
            "series_id": source["series_id"],
            "instance_id": segmentation_id,
            "patient_context_id": source["patient_context_id"],
            "bytes": source["bytes"],
            "sha256": source["sha256"],
        },
        "display_status": "supported_read_only",
        "referenced_series": {
            "study_id": first_source["study_id"],
            "series_id": source_series_id,
            "patient_context_id": first_source["patient_context_id"],
            "modality": first_source["modality"],
            "ordered_instance_ids": ordered_ids,
            "referenced_instance_ids": referenced_ids_in_source_order,
        },
        "referenced_instance_count": len(referenced_ids_in_source_order),
        "grid": {
            "relationship": "exact_native_source_grid",
            "dimensions": [len(ordered_ids), rows, columns],
            "pixel_spacing_mm": geometry["pixel_spacing"],
            "projected_slice_spacing_mm": geometry["slice_spacing"],
            "voxel_volume_mm3": geometry["voxel_volume_mm3"],
            "resampled_by_scanview": False,
        },
        "frame_count": frame_count,
        "segment_count": len(segments),
        "segments": [segments[number] for number in sorted(segments)],
        "creator_identity_authenticated": False,
        "source_segment_clinical_meaning": "not_assessed",
        "scanview_interpretation_added": False,
    }, output_masks, {segmentation_id, *ordered_ids}


def build_source_segmentation_catalog(
    catalog: Any,
    load_source: Callable[[str], bytes],
) -> tuple[dict[str, Any], dict[tuple[str, int], bytes], set[str]]:
    catalog_hash, instances, segmentation_ids = _catalog_index(catalog)
    states: list[dict[str, Any]] = []
    unsupported: list[dict[str, Any]] = []
    masks: dict[tuple[str, int], bytes] = {}
    cached_mask_bytes = 0
    decoded_voxel_budget = [MAX_TOTAL_DECODED_FRAME_VOXELS]
    guarded_ids: set[str] = set(segmentation_ids)
    for segmentation_id in segmentation_ids:
        source = instances[segmentation_id]
        try:
            if (
                source["modality"] != "SEG"
                or not OPAQUE_ID["patient"].fullmatch(
                    str(source.get("patient_context_id") or "")
                )
                or not OPAQUE_ID["frame"].fullmatch(
                    str(source.get("frame_of_reference_id") or "")
                )
                or type(source.get("bytes")) is not int
                or not 1 <= source["bytes"] <= MAX_SEGMENTATION_BYTES
                or not isinstance(source.get("sha256"), str)
                or not SHA256.fullmatch(source["sha256"])
            ):
                raise ValueError("DICOM SEG indexed provenance is incomplete")
            parsed, parsed_masks, parsed_guards = _parse_segmentation(
                segmentation_id,
                load_source(segmentation_id),
                source,
                instances,
                MAX_TOTAL_MASK_BYTES - cached_mask_bytes,
                decoded_voxel_budget,
            )
            # Re-read every referenced source through the guarded loader. Geometry
            # metadata alone cannot prove that the live source bytes still match the
            # catalog used to authorize the mask.
            for referenced_instance_id in parsed["referenced_series"][
                "ordered_instance_ids"
            ]:
                load_source(referenced_instance_id)
            states.append(parsed)
            cached_mask_bytes += sum(len(payload) for payload in parsed_masks.values())
            masks.update(parsed_masks)
            guarded_ids.update(parsed_guards)
        except (AttributeError, IndexError, KeyError, OSError, TypeError, ValueError) as error:
            unsupported.append(
                {
                    "segmentation_id": segmentation_id,
                    "display_status": "unsupported",
                    "reason": str(error)[:300] or "DICOM SEG validation failed",
                }
            )
    states.sort(key=lambda item: item["segmentation_id"])
    unsupported.sort(key=lambda item: item["segmentation_id"])
    result = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "catalog_content_sha256": catalog_hash,
        "local_only": True,
        "privacy": {
            "classification": "sensitive_local_medical_data",
            "direct_identifier_tags_excluded": True,
            "segment_text_may_contain_identifiers": True,
            "deidentified": False,
            "contains_pixels": False,
            "contains_paths": False,
            "contains_segment_text": any(item["segments"] for item in states),
        },
        "segmentation_count": len(segmentation_ids),
        "supported_segmentation_count": len(states),
        "unsupported_segmentation_count": len(unsupported),
        "segment_count": sum(item["segment_count"] for item in states),
        "segmentations": states,
        "unsupported_segmentations": unsupported,
        "permissions": {
            "bearer_agent_sensitive_catalog_read_authorized": True,
            "bearer_agent_mask_read_authorized": False,
            "browser_session_sensitive_catalog_read_authorized": True,
            "browser_session_mask_read_authorized": True,
            "browser_session_exact_source_navigation_authorized": True,
            "browser_session_read_only_mask_display_authorized": True,
            "browser_session_technical_volume_display_authorized": True,
            "edit_source_segmentation_authorized": False,
            "convert_to_scanview_measurement_authorized": False,
            "creator_identity_authenticated": False,
            "segment_accuracy_verified": False,
            "diagnosis_authorized": False,
            "response_classification_authorized": False,
            "clinical_conclusion_authorized": False,
        },
        "limitations": list(LIMITATIONS),
    }
    return result, masks, guarded_ids


def source_segmentation_summary(
    artifact: Any,
    *,
    catalog: Any | None = None,
    load_source: Callable[[str], bytes] | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    if not isinstance(artifact, dict):
        errors.append("source-segmentation artifact must be a JSON object")
    elif catalog is None or load_source is None:
        errors.append("exact local catalog and source loader are required")
    else:
        try:
            rebuilt, _, _ = build_source_segmentation_catalog(catalog, load_source)
            if _catalog_content(artifact) != _catalog_content(rebuilt):
                errors.append("source-segmentation artifact does not match exact local DICOM inputs")
        except (OSError, TypeError, ValueError) as error:
            errors.append(str(error)[:300])
    supported = (
        artifact.get("supported_segmentation_count")
        if isinstance(artifact, dict)
        and type(artifact.get("supported_segmentation_count")) is int
        else 0
    )
    unsupported = (
        artifact.get("unsupported_segmentation_count")
        if isinstance(artifact, dict)
        and type(artifact.get("unsupported_segmentation_count")) is int
        else 0
    )
    segments = (
        artifact.get("segment_count")
        if isinstance(artifact, dict) and type(artifact.get("segment_count")) is int
        else 0
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": SUMMARY_ARTIFACT_TYPE,
        "valid": not errors,
        "errors": list(dict.fromkeys(errors)),
        "supported_segmentation_count": supported if not errors else 0,
        "unsupported_segmentation_count": unsupported,
        "segment_count": segments if not errors else 0,
        "contains_segment_text": False,
        "contains_identifiers": False,
        "contains_paths": False,
        "contains_pixels": False,
        "contains_geometry": False,
        "contains_computed_volumes": False,
        "local_only": True,
        "external_api_required": False,
    }
