from __future__ import annotations

import hashlib
import io
import json
import math
import os
import re
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any, BinaryIO, Iterable

from pydicom import dcmread
from pydicom.errors import InvalidDicomError
from pydicom.uid import ExplicitVRLittleEndian, SegmentationStorage


EXPECTED_FILES = {"evidence.json", "segmentation.dcm", "README.txt"}
MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_SEG_BYTES = 512 * 1024 * 1024
SHA256 = re.compile(r"^[0-9a-f]{64}$")
UID = re.compile(r"^[0-9]+(?:\.[0-9]+)+$")
ARTIFACT_ID = re.compile(r"^seg_[0-9a-f-]{36}$")
OPAQUE_ID = re.compile(
    r"^(?:[0-9a-f]{16}|(?:study|series|instance|frame|patient)_[0-9a-f]{20})$"
)
SOURCE_TAGS = [
    "SOPClassUID",
    "SOPInstanceUID",
    "StudyInstanceUID",
    "SeriesInstanceUID",
    "FrameOfReferenceUID",
    "Modality",
    "Rows",
    "Columns",
    "PixelSpacing",
    "SliceThickness",
    "ImageOrientationPatient",
    "ImagePositionPatient",
    "NumberOfFrames",
]
ArchiveSource = Path | BinaryIO


@dataclass(frozen=True)
class SourceRecord:
    path: Path
    size: int
    sha256: str
    sop_class_uid: str
    sop_instance_uid: str
    study_instance_uid: str
    series_instance_uid: str
    frame_of_reference_uid: str
    modality: str
    rows: int
    columns: int
    pixel_spacing: tuple[float, float]
    slice_thickness: float
    orientation: tuple[float, float, float, float, float, float]
    position: tuple[float, float, float]


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _finite(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _numbers(value: Any, length: int) -> tuple[float, ...] | None:
    if not isinstance(value, (list, tuple)) or len(value) != length:
        return None
    if not all(_finite(item) for item in value):
        return None
    return tuple(float(item) for item in value)


def _dot(left: Iterable[float], right: Iterable[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))


def _subtract(left: Iterable[float], right: Iterable[float]) -> tuple[float, ...]:
    return tuple(a - b for a, b in zip(left, right, strict=True))


def _magnitude(vector: Iterable[float]) -> float:
    return math.sqrt(_dot(vector, vector))


def _cross(
    left: tuple[float, float, float], right: tuple[float, float, float]
) -> tuple[float, float, float]:
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


def _close(left: float, right: float, tolerance: float) -> bool:
    return math.isclose(left, right, rel_tol=0.0, abs_tol=tolerance)


def _close_vector(
    left: Iterable[float], right: Iterable[float], tolerance: float
) -> bool:
    return all(_close(a, b, tolerance) for a, b in zip(left, right, strict=True))


def _source_set_sha256(instances: list[dict[str, Any]]) -> str:
    lines = [
        f"{item.get('frame_index')}:{item.get('instance_id')}:{item.get('bytes')}:{item.get('sha256')}"
        for item in instances
    ]
    return _sha256_bytes(("\n".join(lines) + "\n").encode())


def _strict_json(data: bytes) -> Any:
    def pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in values:
            if key in result:
                raise ValueError(f"duplicate JSON field: {key}")
            result[key] = value
        return result

    def invalid_constant(value: str) -> None:
        raise ValueError(f"unsupported JSON number: {value}")

    return json.loads(data, object_pairs_hook=pairs, parse_constant=invalid_constant)


def _archive_members(archive: ArchiveSource) -> tuple[dict[str, bytes], list[str]]:
    errors: list[str] = []
    members: dict[str, bytes] = {}
    try:
        with zipfile.ZipFile(archive) as bundle:
            infos = bundle.infolist()
            names = [item.filename for item in infos]
            if set(names) != EXPECTED_FILES or len(names) != len(EXPECTED_FILES):
                errors.append("archive must contain exactly evidence.json, segmentation.dcm, and README.txt")
                return {}, errors
            for info in infos:
                mode = info.external_attr >> 16
                if info.flag_bits & 0x1:
                    errors.append("archive members must not be encrypted")
                    continue
                if stat.S_ISLNK(mode) or info.filename.startswith(("/", "\\")) or ".." in Path(info.filename).parts:
                    errors.append("archive contains an unsafe member")
                    continue
                limit = MAX_SEG_BYTES if info.filename == "segmentation.dcm" else MAX_JSON_BYTES
                if info.file_size > limit:
                    errors.append(f"{info.filename} exceeds its local evidence size limit")
                    continue
                members[info.filename] = bundle.read(info)
    except (OSError, zipfile.BadZipFile, RuntimeError):
        errors.append("archive is not a readable ZIP file")
    return members, errors


def validate_lesion_volume_evidence(evidence: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(evidence, dict):
        return ["evidence.json must contain one JSON object"]
    expected = {
        "schema_version",
        "artifact_type",
        "artifact_id",
        "created_at",
        "state",
        "local_only",
        "sensitive",
        "deidentified",
        "source",
        "segment",
        "geometry",
        "measurement",
        "files",
        "review",
        "permitted_uses",
        "limitations",
    }
    if set(evidence) != expected:
        errors.append("evidence.json fields do not match the v1 contract")
    constants = {
        "schema_version": "1.0.0",
        "artifact_type": "scanview.lesion-volume-evidence",
        "state": "draft_unreviewed",
        "local_only": True,
        "sensitive": True,
        "deidentified": False,
    }
    for key, value in constants.items():
        if evidence.get(key) != value:
            errors.append(f"{key} must be {value!r}")
    if not isinstance(evidence.get("artifact_id"), str) or not ARTIFACT_ID.fullmatch(
        evidence["artifact_id"]
    ):
        errors.append("artifact_id is invalid")

    source = evidence.get("source")
    instances: list[dict[str, Any]] = []
    if not isinstance(source, dict):
        errors.append("source must be an object")
    else:
        required = {
            "study_id",
            "series_id",
            "frame_of_reference_id",
            "modality",
            "instance_count",
            "instances",
            "source_set_sha256",
        }
        if not required.issubset(source) or set(source) - (required | {"patient_context_id"}):
            errors.append("source fields do not match the v1 contract")
        for key in ("study_id", "series_id", "frame_of_reference_id"):
            if not isinstance(source.get(key), str) or not OPAQUE_ID.fullmatch(source[key]):
                errors.append(f"source.{key} must be an opaque ID")
        patient_context = source.get("patient_context_id")
        if patient_context is not None and (
            not isinstance(patient_context, str) or not OPAQUE_ID.fullmatch(patient_context)
        ):
            errors.append("source.patient_context_id must be an opaque ID")
        if source.get("modality") not in {"MR", "CT"}:
            errors.append("source.modality must be MR or CT")
        if isinstance(source.get("instances"), list):
            instances = source["instances"]
        if len(instances) < 3 or source.get("instance_count") != len(instances):
            errors.append("source instance_count must match at least three source instances")
        seen_ids: set[str] = set()
        for index, item in enumerate(instances):
            if not isinstance(item, dict):
                errors.append(f"source.instances[{index}] must be an object")
                continue
            if item.get("frame_index") != index:
                errors.append("source frame indexes must be contiguous from zero")
            instance_id = item.get("instance_id")
            if not isinstance(instance_id, str) or not OPAQUE_ID.fullmatch(instance_id):
                errors.append("source instance IDs must be opaque")
            elif instance_id in seen_ids:
                errors.append("source instance IDs must be unique")
            else:
                seen_ids.add(instance_id)
            if not isinstance(item.get("bytes"), int) or isinstance(item.get("bytes"), bool) or item["bytes"] < 132:
                errors.append("source instance byte counts must be positive integers")
            if not isinstance(item.get("sha256"), str) or not SHA256.fullmatch(item["sha256"]):
                errors.append("source instance SHA-256 values are invalid")
            if not isinstance(item.get("rows"), int) or item["rows"] < 2:
                errors.append("source instance rows are invalid")
            if not isinstance(item.get("columns"), int) or item["columns"] < 2:
                errors.append("source instance columns are invalid")
            spacing = _numbers(item.get("pixel_spacing_mm"), 2)
            if spacing is None or any(value <= 0 for value in spacing):
                errors.append("source instance pixel spacing is invalid")
            if _numbers(item.get("image_orientation_patient"), 6) is None:
                errors.append("source instance orientation is invalid")
            if _numbers(item.get("image_position_patient"), 3) is None:
                errors.append("source instance position is invalid")
        if isinstance(source.get("source_set_sha256"), str) and SHA256.fullmatch(source["source_set_sha256"]):
            if instances and _source_set_sha256(instances) != source["source_set_sha256"]:
                errors.append("source_set_sha256 does not match the ordered source list")
        else:
            errors.append("source.source_set_sha256 is invalid")

    segment = evidence.get("segment")
    if not isinstance(segment, dict):
        errors.append("segment must be an object")
    else:
        if segment.get("segment_number") != 1 or segment.get("algorithm_type") != "MANUAL":
            errors.append("v1 supports exactly one manually painted segment")
        if segment.get("tracking_id") != evidence.get("artifact_id"):
            errors.append("segment tracking_id must equal artifact_id")
        tracking_uid = segment.get("tracking_uid")
        if not isinstance(tracking_uid, str) or len(tracking_uid) > 64 or not UID.fullmatch(tracking_uid):
            errors.append("segment tracking_uid is invalid")
        for key, maximum in (("label", 64), ("target_definition", 300)):
            if not isinstance(segment.get(key), str) or not segment[key].strip() or len(segment[key]) > maximum:
                errors.append(f"segment.{key} is invalid")
        expected_codes = {
            "property_category": ("49755003", "SCT", "Morphologically Abnormal Structure"),
            "property_type": ("52988006", "SCT", "Lesion"),
        }
        for key, values in expected_codes.items():
            code = segment.get(key)
            if not isinstance(code, dict) or (
                code.get("value"), code.get("scheme"), code.get("meaning")
            ) != values:
                errors.append(f"segment.{key} must use the neutral v1 lesion code")

    geometry = evidence.get("geometry")
    if not isinstance(geometry, dict):
        errors.append("geometry must be an object")
    else:
        if geometry.get("grid_order") != "source_volume_frame_row_column":
            errors.append("geometry.grid_order is invalid")
        dimensions = _numbers(geometry.get("dimensions"), 3)
        if dimensions is None or any(value < 2 or not value.is_integer() for value in dimensions):
            errors.append("geometry.dimensions are invalid")
        spacing = _numbers(geometry.get("pixel_spacing_mm"), 2)
        if spacing is None or any(value <= 0 for value in spacing):
            errors.append("geometry.pixel_spacing_mm is invalid")
        for key in ("projected_slice_spacing_mm", "voxel_volume_mm3"):
            if not _finite(geometry.get(key)) or geometry[key] <= 0:
                errors.append(f"geometry.{key} must be positive")
        for key in ("row_direction", "column_direction", "normal_direction"):
            if _numbers(geometry.get(key), 3) is None:
                errors.append(f"geometry.{key} is invalid")
        if geometry.get("geometry_matches_source") is not True or geometry.get("resampled") is not False:
            errors.append("v1 geometry must be native and source-matched")

    measurement = evidence.get("measurement")
    if not isinstance(measurement, dict):
        errors.append("measurement must be an object")
    else:
        if measurement.get("status") != "computed_unreviewed":
            errors.append("measurement.status must be computed_unreviewed")
        if measurement.get("method") != "binary_voxel_count_times_native_voxel_determinant":
            errors.append("measurement.method is invalid")
        count = measurement.get("foreground_voxel_count")
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            errors.append("measurement foreground voxel count must be non-zero")
        for key in ("volume_mm3", "volume_ml"):
            if not _finite(measurement.get(key)) or measurement[key] <= 0:
                errors.append(f"measurement.{key} must be positive")
        if not isinstance(measurement.get("mask_pixel_sha256"), str) or not SHA256.fullmatch(
            measurement["mask_pixel_sha256"]
        ):
            errors.append("measurement.mask_pixel_sha256 is invalid")
        if measurement.get("boundary_uncertainty") != "not_quantified":
            errors.append("measurement boundary uncertainty must remain not_quantified")

    files = evidence.get("files")
    dicom_file = files.get("dicom_seg") if isinstance(files, dict) else None
    if not isinstance(dicom_file, dict) or set(dicom_file) != {"filename", "bytes", "sha256"}:
        errors.append("files.dicom_seg is invalid")
    elif (
        dicom_file.get("filename") != "segmentation.dcm"
        or not isinstance(dicom_file.get("bytes"), int)
        or not isinstance(dicom_file.get("sha256"), str)
        or not SHA256.fullmatch(dicom_file["sha256"])
    ):
        errors.append("files.dicom_seg metadata is invalid")

    review = evidence.get("review")
    if review != {"status": "unreviewed"}:
        errors.append("review must remain unreviewed in an exported v1 draft")
    permissions = evidence.get("permitted_uses")
    if permissions != {
        "source_overlay": True,
        "mask_overlay": True,
        "exact_timepoint_volume": "computed_unreviewed_only",
        "longitudinal_link": False,
        "percent_change": False,
        "response_classification": False,
        "diagnosis": False,
        "clinical_conclusion": False,
    }:
        errors.append("permitted_uses must preserve every v1 safety lock")
    limitations = evidence.get("limitations")
    if not isinstance(limitations, list) or not 5 <= len(limitations) <= 12 or not all(
        isinstance(item, str) and item.strip() and len(item) <= 300 for item in limitations
    ):
        errors.append("limitations must contain 5-12 bounded statements")
    return errors


def _read_source_record(path: Path) -> SourceRecord | None:
    descriptor = -1
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            return None
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            try:
                dataset = dcmread(
                    stream,
                    stop_before_pixels=True,
                    force=False,
                    specific_tags=SOURCE_TAGS,
                )
            except InvalidDicomError:
                stream.seek(0)
                dataset = dcmread(
                    stream,
                    stop_before_pixels=True,
                    force=True,
                    specific_tags=SOURCE_TAGS,
                )
            stream.seek(0)
            digest = hashlib.sha256()
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
        after = os.fstat(descriptor)
        identity_before = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        identity_after = (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        if identity_before != identity_after:
            return None
    except (InvalidDicomError, OSError, ValueError):
        return None
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    values = {
        "sop_class_uid": str(getattr(dataset, "SOPClassUID", "")),
        "sop_instance_uid": str(getattr(dataset, "SOPInstanceUID", "")),
        "study_instance_uid": str(getattr(dataset, "StudyInstanceUID", "")),
        "series_instance_uid": str(getattr(dataset, "SeriesInstanceUID", "")),
        "frame_of_reference_uid": str(getattr(dataset, "FrameOfReferenceUID", "")),
        "modality": str(getattr(dataset, "Modality", "")),
    }
    try:
        rows = int(dataset.Rows)
        columns = int(dataset.Columns)
        spacing = tuple(float(item) for item in dataset.PixelSpacing)
        slice_thickness = float(dataset.SliceThickness)
        orientation = tuple(float(item) for item in dataset.ImageOrientationPatient)
        position = tuple(float(item) for item in dataset.ImagePositionPatient)
        frames = int(getattr(dataset, "NumberOfFrames", 1))
    except (AttributeError, TypeError, ValueError):
        return None
    if (
        not all(values.values())
        or values["modality"] not in {"MR", "CT"}
        or len(spacing) != 2
        or not math.isfinite(slice_thickness)
        or slice_thickness <= 0
        or len(orientation) != 6
        or len(position) != 3
        or frames != 1
    ):
        return None
    return SourceRecord(
        path=path,
        size=before.st_size,
        sha256=digest.hexdigest(),
        rows=rows,
        columns=columns,
        pixel_spacing=(spacing[0], spacing[1]),
        slice_thickness=slice_thickness,
        orientation=orientation,  # type: ignore[arg-type]
        position=position,  # type: ignore[arg-type]
        **values,
    )


def _iter_source_records(root: Path) -> Iterable[SourceRecord]:
    root = root.expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError("source root must be a directory")
    for directory, names, files in os.walk(root):
        names.sort()
        files.sort()
        for filename in files:
            path = Path(directory, filename)
            if path.is_symlink() or not path.is_file():
                continue
            record = _read_source_record(path)
            if record:
                yield record


def _match_sources(
    instances: list[dict[str, Any]], source_root: Path
) -> tuple[list[SourceRecord], list[str]]:
    errors: list[str] = []
    expected = {(item.get("sha256"), item.get("bytes")) for item in instances}
    matches: dict[tuple[str, int], SourceRecord] = {}
    try:
        for record in _iter_source_records(source_root):
            key = (record.sha256, record.size)
            if key in expected:
                if key in matches:
                    errors.append("a source byte identity is duplicated in the source directory")
                matches[key] = record
    except (OSError, ValueError):
        return [], ["source directory could not be read"]
    ordered: list[SourceRecord] = []
    for item in instances:
        match = matches.get((item.get("sha256"), item.get("bytes")))
        if match is None:
            errors.append("an exact source instance is missing or its bytes changed")
        else:
            ordered.append(match)
    if len(ordered) == len(instances):
        series_uids = {item.series_instance_uid for item in ordered}
        study_uids = {item.study_instance_uid for item in ordered}
        frame_uids = {item.frame_of_reference_uid for item in ordered}
        if len(series_uids) != 1 or len(study_uids) != 1 or len(frame_uids) != 1:
            errors.append("source instances do not belong to one study, series, and frame of reference")
    return ordered, errors


def _validate_source_geometry(
    evidence: dict[str, Any], sources: list[SourceRecord]
) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    if len(sources) < 3:
        return None, ["at least three exact source planes are required"]
    first = sources[0]
    row = first.orientation[:3]
    column = first.orientation[3:]
    normal = _cross(row, column)
    if (
        abs(_magnitude(row) - 1.0) > 1e-4
        or abs(_magnitude(column) - 1.0) > 1e-4
        or abs(_dot(row, column)) > 1e-4
        or abs(_magnitude(normal) - 1.0) > 1e-4
    ):
        errors.append("source orientation is not an orthonormal native grid")
    for source in sources:
        if source.modality != first.modality:
            errors.append("source modality is inconsistent")
        if source.rows != first.rows or source.columns != first.columns:
            errors.append("source matrix dimensions are inconsistent")
        if not _close_vector(source.pixel_spacing, first.pixel_spacing, 1e-4):
            errors.append("source pixel spacing is inconsistent")
        if not _close(source.slice_thickness, first.slice_thickness, 0.01):
            errors.append("source slice thickness is inconsistent")
        if not _close_vector(source.orientation, first.orientation, 1e-4):
            errors.append("source orientation is inconsistent")
    projections = [_dot(source.position, normal) for source in sources]
    gaps = [abs(right - left) for left, right in zip(projections, projections[1:])]
    if not gaps or any(gap < 0.01 for gap in gaps):
        errors.append("source slice positions overlap or are missing")
        slice_spacing = 0.0
    else:
        slice_spacing = median(gaps)
        tolerance = max(0.01, slice_spacing * 0.001)
        if any(abs(gap - slice_spacing) > tolerance for gap in gaps):
            errors.append("source slice spacing is irregular or contains a gap")
    origin = first.position
    for source, projection in zip(sources, projections, strict=True):
        displacement = _subtract(source.position, origin)
        normal_displacement = tuple(normal[index] * (projection - projections[0]) for index in range(3))
        in_plane = _subtract(displacement, normal_displacement)
        if _magnitude(in_plane) > 0.01:
            errors.append("source planes contain in-plane drift or gantry tilt")
            break
    if errors:
        return None, errors
    voxel_volume = first.pixel_spacing[0] * first.pixel_spacing[1] * slice_spacing
    expected_geometry = evidence.get("geometry", {})
    comparisons = [
        (expected_geometry.get("dimensions"), [first.columns, first.rows, len(sources)], 0.0, "dimensions"),
        (expected_geometry.get("pixel_spacing_mm"), list(first.pixel_spacing), 1e-4, "pixel spacing"),
        (expected_geometry.get("row_direction"), list(row), 1e-4, "row direction"),
        (expected_geometry.get("column_direction"), list(column), 1e-4, "column direction"),
        (expected_geometry.get("normal_direction"), list(normal), 1e-4, "normal direction"),
    ]
    for observed, expected, tolerance, label in comparisons:
        values = _numbers(observed, len(expected))
        if values is None or not _close_vector(values, expected, tolerance):
            errors.append(f"evidence geometry {label} does not match the live source")
    if not _finite(expected_geometry.get("projected_slice_spacing_mm")) or not _close(
        float(expected_geometry["projected_slice_spacing_mm"]), slice_spacing, 0.01
    ):
        errors.append("evidence slice spacing does not match the live source")
    if not _finite(expected_geometry.get("voxel_volume_mm3")) or not _close(
        float(expected_geometry["voxel_volume_mm3"]), voxel_volume, max(1e-6, voxel_volume * 1e-6)
    ):
        errors.append("evidence voxel volume does not match source geometry")
    return {
        "rows": first.rows,
        "columns": first.columns,
        "slice_spacing": slice_spacing,
        "voxel_volume": voxel_volume,
        "normal": normal,
    }, errors


def _frame_source_reference(frame_group: Any) -> tuple[str, str] | None:
    try:
        source = frame_group.DerivationImageSequence[0].SourceImageSequence[0]
        return (
            str(source.ReferencedSOPClassUID),
            str(source.ReferencedSOPInstanceUID),
        )
    except (AttributeError, IndexError, TypeError):
        try:
            source = frame_group.SourceImageSequence[0]
            return (
                str(source.ReferencedSOPClassUID),
                str(source.ReferencedSOPInstanceUID),
            )
        except (AttributeError, IndexError, TypeError):
            return None


def _code_sequence_matches(
    owner: Any,
    name: str,
    expected: tuple[str, str, str],
) -> bool:
    sequence = list(getattr(owner, name, []))
    if len(sequence) != 1:
        return False
    item = sequence[0]
    observed = (
        str(getattr(item, "CodeValue", "")),
        str(getattr(item, "CodingSchemeDesignator", "")),
        str(getattr(item, "CodeMeaning", "")),
    )
    return observed == expected


def _decode_binary_frames(dataset: Any) -> tuple[list[bytes], list[str]]:
    errors: list[str] = []
    try:
        rows = int(dataset.Rows)
        columns = int(dataset.Columns)
        frame_count = int(dataset.NumberOfFrames)
        pixel_data = bytes(dataset.PixelData)
    except (AttributeError, TypeError, ValueError):
        return [], ["DICOM SEG pixel dimensions are missing"]
    bits_per_frame = rows * columns
    total_bits = bits_per_frame * frame_count
    required_bytes = (total_bits + 7) // 8
    if len(pixel_data) < required_bytes or len(pixel_data) > required_bytes + 1:
        return [], ["DICOM SEG Pixel Data length is inconsistent"]
    if len(pixel_data) == required_bytes + 1 and pixel_data[-1] != 0:
        errors.append("DICOM SEG has a non-zero trailing pad byte")
    frames: list[bytes] = []
    for frame_index in range(frame_count):
        output = bytearray(bits_per_frame)
        start = frame_index * bits_per_frame
        for index in range(bits_per_frame):
            bit_offset = start + index
            output[index] = (pixel_data[bit_offset // 8] >> (bit_offset % 8)) & 1
        frames.append(bytes(output))
    return frames, errors


def _validate_dicom_seg(
    seg_bytes: bytes,
    evidence: dict[str, Any],
    sources: list[SourceRecord],
    geometry: dict[str, Any],
) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    try:
        dataset = dcmread(io.BytesIO(seg_bytes), force=False)
    except (InvalidDicomError, OSError, ValueError):
        return None, ["segmentation.dcm is not a readable DICOM Part 10 file"]
    if str(getattr(dataset, "SOPClassUID", "")) != str(SegmentationStorage):
        errors.append("DICOM object is not the binary Segmentation Storage SOP class")
    if str(getattr(dataset.file_meta, "TransferSyntaxUID", "")) != str(ExplicitVRLittleEndian):
        errors.append("DICOM SEG must use uncompressed Explicit VR Little Endian")
    expected_values = {
        "Modality": "SEG",
        "SegmentationType": "BINARY",
        "SamplesPerPixel": 1,
        "PhotometricInterpretation": "MONOCHROME2",
        "BitsAllocated": 1,
        "BitsStored": 1,
        "HighBit": 0,
        "PixelRepresentation": 0,
        "SegmentsOverlap": "NO",
    }
    for key, value in expected_values.items():
        if getattr(dataset, key, None) != value:
            errors.append(f"DICOM SEG {key} does not match the v1 binary profile")
    first_source = sources[0]
    if str(getattr(dataset, "StudyInstanceUID", "")) != first_source.study_instance_uid:
        errors.append("DICOM SEG study does not match the exact source series")
    if str(getattr(dataset, "FrameOfReferenceUID", "")) != first_source.frame_of_reference_uid:
        errors.append("DICOM SEG Frame of Reference does not match the exact source series")
    referenced_series = list(getattr(dataset, "ReferencedSeriesSequence", []))
    if len(referenced_series) != 1:
        errors.append("DICOM SEG must reference exactly one source series")
    else:
        series_reference = referenced_series[0]
        if str(getattr(series_reference, "SeriesInstanceUID", "")) != first_source.series_instance_uid:
            errors.append("DICOM SEG referenced series does not match the exact source series")
        expected_references = {
            (source.sop_class_uid, source.sop_instance_uid) for source in sources
        }
        referenced_instances = list(
            getattr(series_reference, "ReferencedInstanceSequence", [])
        )
        observed_references = {
            (
                str(getattr(item, "ReferencedSOPClassUID", "")),
                str(getattr(item, "ReferencedSOPInstanceUID", "")),
            )
            for item in referenced_instances
        }
        if (
            len(referenced_instances) != len(expected_references)
            or observed_references != expected_references
        ):
            errors.append("DICOM SEG referenced instances do not match the exact source set")
    if len(getattr(dataset, "SegmentSequence", [])) != 1:
        errors.append("DICOM SEG must contain exactly one segment")
    else:
        segment = dataset.SegmentSequence[0]
        sidecar = evidence["segment"]
        if int(getattr(segment, "SegmentNumber", 0)) != 1:
            errors.append("DICOM SEG Segment Number must be 1")
        if str(getattr(segment, "SegmentLabel", "")) != sidecar["label"]:
            errors.append("DICOM SEG label does not match evidence.json")
        if str(getattr(segment, "SegmentAlgorithmType", "")) != "MANUAL":
            errors.append("DICOM SEG algorithm type must be MANUAL")
        if str(getattr(segment, "TrackingID", "")) != sidecar["tracking_id"]:
            errors.append("DICOM SEG Tracking ID does not match evidence.json")
        if str(getattr(segment, "TrackingUID", "")) != sidecar["tracking_uid"]:
            errors.append("DICOM SEG Tracking UID does not match evidence.json")
        for key, expected in (
            (
                "SegmentedPropertyCategoryCodeSequence",
                ("49755003", "SCT", "Morphologically Abnormal Structure"),
            ),
            ("SegmentedPropertyTypeCodeSequence", ("52988006", "SCT", "Lesion")),
        ):
            sequence = getattr(segment, key, [])
            observed = (
                str(getattr(sequence[0], "CodeValue", "")),
                str(getattr(sequence[0], "CodingSchemeDesignator", "")),
                str(getattr(sequence[0], "CodeMeaning", "")),
            ) if len(sequence) == 1 else None
            if observed != expected:
                errors.append(f"DICOM SEG {key} does not use the neutral v1 lesion code")

    if int(getattr(dataset, "Rows", 0)) != geometry["rows"] or int(
        getattr(dataset, "Columns", 0)
    ) != geometry["columns"]:
        errors.append("DICOM SEG matrix does not match the source grid")
    shared_groups = list(getattr(dataset, "SharedFunctionalGroupsSequence", []))
    if len(shared_groups) != 1:
        errors.append("DICOM SEG must contain one shared native-grid functional group")
    else:
        shared = shared_groups[0]
        pixel_measures = list(getattr(shared, "PixelMeasuresSequence", []))
        try:
            pixel_spacing = tuple(
                float(item) for item in pixel_measures[0].PixelSpacing
            )
            slice_thickness = float(pixel_measures[0].SliceThickness)
        except (AttributeError, IndexError, TypeError, ValueError):
            pixel_spacing = ()
            slice_thickness = 0.0
        if (
            len(pixel_measures) != 1
            or len(pixel_spacing) != 2
            or not _close_vector(pixel_spacing, first_source.pixel_spacing, 1e-4)
            or not _close(slice_thickness, first_source.slice_thickness, 0.01)
        ):
            errors.append("DICOM SEG pixel measures do not match the native source grid")
        plane_orientations = list(getattr(shared, "PlaneOrientationSequence", []))
        try:
            orientation = tuple(
                float(item) for item in plane_orientations[0].ImageOrientationPatient
            )
        except (AttributeError, IndexError, TypeError, ValueError):
            orientation = ()
        if (
            len(plane_orientations) != 1
            or len(orientation) != 6
            or not _close_vector(orientation, first_source.orientation, 1e-4)
        ):
            errors.append("DICOM SEG plane orientation does not match the native source grid")
    source_by_reference = {
        (source.sop_class_uid, source.sop_instance_uid): (index, source)
        for index, source in enumerate(sources)
    }
    frames, frame_errors = _decode_binary_frames(dataset)
    errors.extend(frame_errors)
    frame_groups = list(getattr(dataset, "PerFrameFunctionalGroupsSequence", []))
    if len(frame_groups) != len(frames):
        errors.append("DICOM SEG functional groups do not match its frame count")
    dense = bytearray(geometry["rows"] * geometry["columns"] * len(sources))
    used_source_indexes: set[int] = set()
    for frame_index, (frame, group) in enumerate(zip(frames, frame_groups, strict=False)):
        source_reference = _frame_source_reference(group)
        source_match = source_by_reference.get(source_reference or ("", ""))
        if source_match is None:
            errors.append("a DICOM SEG frame does not reference an exact source instance")
            continue
        source_index, source = source_match
        if source_index in used_source_indexes:
            errors.append("multiple DICOM SEG frames reference the same source plane")
            continue
        used_source_indexes.add(source_index)
        derivations = list(getattr(group, "DerivationImageSequence", []))
        if len(derivations) != 1 or not _code_sequence_matches(
            derivations[0],
            "DerivationCodeSequence",
            ("113076", "DCM", "Segmentation"),
        ):
            errors.append("a DICOM SEG frame does not declare the Segmentation derivation code")
        sources_for_purpose = (
            list(getattr(derivations[0], "SourceImageSequence", []))
            if len(derivations) == 1
            else []
        )
        if len(sources_for_purpose) != 1 or not _code_sequence_matches(
            sources_for_purpose[0],
            "PurposeOfReferenceCodeSequence",
            ("121322", "DCM", "Source Image for Image Processing Operation"),
        ):
            errors.append("a DICOM SEG frame does not declare the source-image processing purpose code")
        try:
            segment_number = int(
                group.SegmentIdentificationSequence[0].ReferencedSegmentNumber
            )
            if segment_number != 1:
                errors.append("a DICOM SEG frame references an unsupported segment number")
        except (AttributeError, IndexError, TypeError, ValueError):
            errors.append("a DICOM SEG frame is missing its segment identification")
        try:
            dimension_indexes = [
                int(item)
                for item in group.FrameContentSequence[0].DimensionIndexValues
            ]
            if dimension_indexes != [1, source_index + 1]:
                errors.append("a DICOM SEG frame dimension index does not match its source plane")
        except (AttributeError, IndexError, TypeError, ValueError):
            errors.append("a DICOM SEG frame is missing its source-plane dimension index")
        offset = source_index * len(frame)
        dense[offset : offset + len(frame)] = frame
        try:
            plane_position = group.PlanePositionSequence[0].ImagePositionPatient
            if not _close_vector(tuple(float(item) for item in plane_position), source.position, 0.001):
                errors.append("a DICOM SEG frame position does not match its source plane")
        except (AttributeError, IndexError, TypeError, ValueError):
            errors.append("a DICOM SEG frame is missing its native plane position")
    foreground = sum(dense)
    if foreground < 1:
        errors.append("DICOM SEG mask is empty")
    measurement = evidence["measurement"]
    volume_mm3 = foreground * geometry["voxel_volume"]
    if foreground != measurement["foreground_voxel_count"]:
        errors.append("foreground voxel count does not match evidence.json")
    if _sha256_bytes(bytes(dense)) != measurement["mask_pixel_sha256"]:
        errors.append("dense binary mask hash does not match evidence.json")
    if not _close(volume_mm3, float(measurement["volume_mm3"]), max(1e-6, volume_mm3 * 1e-6)):
        errors.append("recomputed volume_mm3 does not match evidence.json")
    if not _close(volume_mm3 / 1000.0, float(measurement["volume_ml"]), max(1e-9, volume_mm3 * 1e-9)):
        errors.append("recomputed volume_ml does not match evidence.json")
    return {"foreground": foreground, "volume_mm3": volume_mm3}, errors


def lesion_volume_archive_summary(archive: ArchiveSource, source_root: Path) -> dict[str, Any]:
    members, errors = _archive_members(archive)
    evidence: dict[str, Any] = {}
    if "evidence.json" in members:
        try:
            parsed = _strict_json(members["evidence.json"])
            if isinstance(parsed, dict):
                evidence = parsed
            else:
                errors.append("evidence.json must contain one JSON object")
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            errors.append("evidence.json is not strict valid UTF-8 JSON")
    if evidence:
        errors.extend(validate_lesion_volume_evidence(evidence))
    if evidence and "segmentation.dcm" in members:
        file_contract = evidence.get("files", {}).get("dicom_seg", {})
        seg_bytes = members["segmentation.dcm"]
        if file_contract.get("bytes") != len(seg_bytes):
            errors.append("segmentation.dcm byte count does not match evidence.json")
        if file_contract.get("sha256") != _sha256_bytes(seg_bytes):
            errors.append("segmentation.dcm SHA-256 does not match evidence.json")

    sources: list[SourceRecord] = []
    geometry: dict[str, Any] | None = None
    if evidence and not validate_lesion_volume_evidence(evidence):
        sources, source_errors = _match_sources(evidence["source"]["instances"], source_root)
        errors.extend(source_errors)
        if len(sources) == len(evidence["source"]["instances"]):
            geometry, geometry_errors = _validate_source_geometry(evidence, sources)
            errors.extend(geometry_errors)
    result: dict[str, Any] | None = None
    if geometry is not None and "segmentation.dcm" in members:
        result, dicom_errors = _validate_dicom_seg(
            members["segmentation.dcm"], evidence, sources, geometry
        )
        errors.extend(dicom_errors)
    errors = list(dict.fromkeys(errors))
    valid = not errors and result is not None
    return {
        "valid": valid,
        "errors": errors,
        "schema_version": evidence.get("schema_version") if evidence else None,
        "artifact_type": evidence.get("artifact_type") if evidence else None,
        "artifact_id": evidence.get("artifact_id") if evidence else None,
        "artifact_state": evidence.get("state") if evidence else None,
        "validation_state": "source_validated_pending_review" if valid else "invalid",
        "review_status": evidence.get("review", {}).get("status") if evidence else None,
        "source_validated": valid,
        "modality": evidence.get("source", {}).get("modality") if evidence else None,
        "segment_count": 1 if valid else 0,
        "computed_unreviewed_foreground_voxels": result["foreground"] if valid else None,
        "computed_unreviewed_volume_mm3": result["volume_mm3"] if valid else None,
        "computed_unreviewed_volume_ml": result["volume_mm3"] / 1000.0 if valid else None,
        "boundary_uncertainty": "not_quantified" if valid else None,
        "evidence_use": "exact_timepoint_unreviewed_only" if valid else "none",
        "longitudinal_link": False,
        "percent_change": False,
        "response_classification": False,
        "diagnosis": False,
        "clinical_conclusion": False,
    }
