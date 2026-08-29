from __future__ import annotations

import hashlib
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from pydicom import dcmread
from pydicom.errors import InvalidDicomError

SCHEMA_VERSION = "1.0.0"

HEADER_TAGS = [
    "PatientID",
    "IssuerOfPatientID",
    "PatientName",
    "PatientBirthDate",
    "SOPClassUID",
    "SOPInstanceUID",
    "StudyInstanceUID",
    "SeriesInstanceUID",
    "StudyDate",
    "SeriesDate",
    "AcquisitionDate",
    "AcquisitionDateTime",
    "Modality",
    "SeriesDescription",
    "ProtocolName",
    "BodyPartExamined",
    "ImageType",
    "InstanceNumber",
    "Rows",
    "Columns",
    "PixelSpacing",
    "SliceThickness",
    "SpacingBetweenSlices",
    "ImagePositionPatient",
    "ImageOrientationPatient",
    "FrameOfReferenceUID",
    "MagneticFieldStrength",
    "Manufacturer",
    "ContrastBolusAgent",
    "RepetitionTime",
    "EchoTime",
    "InversionTime",
    "FlipAngle",
    "ScanningSequence",
    "SequenceVariant",
    "ScanOptions",
    "MRAcquisitionType",
    "EchoTrainLength",
    "NumberOfFrames",
    "PhotometricInterpretation",
    "PixelAspectRatio",
    "RescaleSlope",
    "RescaleIntercept",
    "ModalityLUTSequence",
]


def _text(value: Any) -> str | None:
    if value is None:
        return None
    result = str(value).strip()
    return result or None


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_list(value: Any) -> list[float] | None:
    if value is None:
        return None
    try:
        values = [float(item) for item in value]
    except (TypeError, ValueError):
        return None
    return values or None


def _text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item for item in value.split("\\") if item]
    return [str(item) for item in value]


def opaque_id(kind: str, value: str, salt: str = "scanview-v1") -> str:
    digest = hashlib.sha256(f"{salt}:{kind}:{value}".encode()).hexdigest()
    return f"{kind}_{digest[:20]}"


def hash_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _patient_context_id(dataset: Any, study_uid: str, salt: str) -> str:
    patient_id = _text(getattr(dataset, "PatientID", None))
    issuer = _text(getattr(dataset, "IssuerOfPatientID", None))
    patient_name = _text(getattr(dataset, "PatientName", None))
    birth_date = _text(getattr(dataset, "PatientBirthDate", None))
    if patient_id:
        identity = (
            f"id-demographics:{patient_id}:{patient_name or ''}:{birth_date or ''}"
            if patient_name or birth_date
            else f"id-issuer:{issuer or ''}:{patient_id}"
        )
    elif patient_name or birth_date:
        identity = f"demographics:{patient_name or ''}:{birth_date or ''}"
    else:
        # A study-scoped fallback deliberately cannot join different exams.
        identity = f"study-only:{study_uid}"
    return opaque_id("patient", identity, salt)


def iter_files(root: Path) -> Iterable[Path]:
    for directory, names, files in os.walk(root):
        names.sort()
        files.sort()
        for filename in files:
            path = Path(directory, filename)
            if path.is_file() and not path.is_symlink():
                yield path


def _read_instance(path: Path, root: Path, *, include_hashes: bool, salt: str) -> dict[str, Any] | None:
    try:
        dataset = dcmread(
            path,
            stop_before_pixels=True,
            force=False,
            specific_tags=HEADER_TAGS,
        )
    except InvalidDicomError:
        # Some valid datasets omit the Part 10 preamble. Only accept the forced
        # parse below when the required image UIDs are subsequently present.
        try:
            dataset = dcmread(
                path,
                stop_before_pixels=True,
                force=True,
                specific_tags=HEADER_TAGS,
            )
        except (OSError, ValueError):
            return None
    except (OSError, ValueError):
        return None

    study_uid = _text(getattr(dataset, "StudyInstanceUID", None))
    series_uid = _text(getattr(dataset, "SeriesInstanceUID", None))
    sop_uid = _text(getattr(dataset, "SOPInstanceUID", None))
    sop_class_uid = _text(getattr(dataset, "SOPClassUID", None))
    if not all((study_uid, series_uid, sop_uid, sop_class_uid)):
        return None

    stat = path.stat()
    frame_uid = _text(getattr(dataset, "FrameOfReferenceUID", None))
    acquisition_date = (
        _text(getattr(dataset, "AcquisitionDate", None))
        or (_text(getattr(dataset, "AcquisitionDateTime", None)) or "")[:8]
        or _text(getattr(dataset, "SeriesDate", None))
        or _text(getattr(dataset, "StudyDate", None))
    )
    instance = {
        "id": opaque_id("instance", sop_uid, salt),
        "study_id": opaque_id("study", study_uid, salt),
        "series_id": opaque_id("series", series_uid, salt),
        "bytes": stat.st_size,
        "sha256": hash_file(path) if include_hashes else None,
        "instance_number": _int(getattr(dataset, "InstanceNumber", None)),
        "image_position_patient": _float_list(getattr(dataset, "ImagePositionPatient", None)),
        "sop_class_uid": sop_class_uid,
        "rows": _int(getattr(dataset, "Rows", None)),
        "columns": _int(getattr(dataset, "Columns", None)),
        "pixel_spacing": _float_list(getattr(dataset, "PixelSpacing", None)),
        "pixel_aspect_ratio": _float_list(getattr(dataset, "PixelAspectRatio", None)),
        "photometric_interpretation": _text(
            getattr(dataset, "PhotometricInterpretation", None)
        ),
        "rescale_slope": _float(getattr(dataset, "RescaleSlope", None)),
        "rescale_intercept": _float(getattr(dataset, "RescaleIntercept", None)),
        "has_modality_lut_sequence": "ModalityLUTSequence" in dataset,
        "slice_thickness": _float(getattr(dataset, "SliceThickness", None)),
        "image_orientation_patient": _float_list(
            getattr(dataset, "ImageOrientationPatient", None)
        ),
        "number_of_frames": _int(getattr(dataset, "NumberOfFrames", None)) or 1,
        "acquisition_date": acquisition_date,
        "header": {
            "patient_context_id": _patient_context_id(dataset, study_uid, salt),
            "acquisition_date": acquisition_date,
            "modality": _text(getattr(dataset, "Modality", None)) or "Unknown",
            "series_description": _text(getattr(dataset, "SeriesDescription", None)) or "Unnamed series",
            "protocol_name": _text(getattr(dataset, "ProtocolName", None)),
            "body_part": _text(getattr(dataset, "BodyPartExamined", None)),
            "image_type": _text_list(getattr(dataset, "ImageType", None)),
            "frame_of_reference_id": opaque_id("frame", frame_uid, salt) if frame_uid else None,
            "rows": _int(getattr(dataset, "Rows", None)),
            "columns": _int(getattr(dataset, "Columns", None)),
            "pixel_spacing": _float_list(getattr(dataset, "PixelSpacing", None)),
            "slice_thickness": _float(getattr(dataset, "SliceThickness", None)),
            "spacing_between_slices": _float(getattr(dataset, "SpacingBetweenSlices", None)),
            "image_orientation_patient": _float_list(getattr(dataset, "ImageOrientationPatient", None)),
            "magnetic_field_strength": _float(getattr(dataset, "MagneticFieldStrength", None)),
            "manufacturer": _text(getattr(dataset, "Manufacturer", None)),
            "contrast_present": bool(_text(getattr(dataset, "ContrastBolusAgent", None))),
            "transfer_syntax_uid": _text(getattr(dataset.file_meta, "TransferSyntaxUID", None)),
            "repetition_time": _float(getattr(dataset, "RepetitionTime", None)),
            "echo_time": _float(getattr(dataset, "EchoTime", None)),
            "inversion_time": _float(getattr(dataset, "InversionTime", None)),
            "flip_angle": _float(getattr(dataset, "FlipAngle", None)),
            "scanning_sequence": _text_list(getattr(dataset, "ScanningSequence", None)),
            "sequence_variant": _text_list(getattr(dataset, "SequenceVariant", None)),
            "scan_options": _text_list(getattr(dataset, "ScanOptions", None)),
            "mr_acquisition_type": _text(getattr(dataset, "MRAcquisitionType", None)),
            "echo_train_length": _int(getattr(dataset, "EchoTrainLength", None)),
            "number_of_frames": _int(getattr(dataset, "NumberOfFrames", None)) or 1,
        },
        "_path": path,
        "_relative_path": path.relative_to(root).as_posix(),
    }
    return instance


def _instance_sort_key(instance: dict[str, Any]) -> tuple[float, int, str]:
    position = instance.get("image_position_patient")
    z = float(position[2]) if position and len(position) >= 3 else float("inf")
    number = instance.get("instance_number")
    return z, number if number is not None else 2**31, instance["id"]


def build_catalog(
    root: Path,
    *,
    include_hashes: bool = True,
    include_relative_paths: bool = False,
    salt: str = "scanview-v1",
    progress: Callable[[int], None] | None = None,
) -> tuple[dict[str, Any], dict[str, Path]]:
    root = root.expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError(f"DICOM root must be a directory: {root}")

    parsed: list[dict[str, Any]] = []
    skipped = 0
    for count, path in enumerate(iter_files(root), start=1):
        instance = _read_instance(path, root, include_hashes=include_hashes, salt=salt)
        if instance:
            parsed.append(instance)
        else:
            skipped += 1
        if progress and count % 100 == 0:
            progress(count)

    by_study: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    registry: dict[str, Path] = {}
    for instance in parsed:
        by_study[instance["study_id"]][instance["series_id"]].append(instance)
        registry[instance["id"]] = instance.pop("_path")

    studies = []
    for study_id, series_groups in by_study.items():
        series_items = []
        study_dates: list[str] = []
        for series_id, instances in series_groups.items():
            instances.sort(key=_instance_sort_key)
            header = instances[0].pop("header")
            for item in instances[1:]:
                item.pop("header")
            if not include_relative_paths:
                for item in instances:
                    item.pop("_relative_path")
            else:
                for item in instances:
                    item["relative_path"] = item.pop("_relative_path")
            if header["acquisition_date"]:
                study_dates.append(header["acquisition_date"])
            series_items.append(
                {
                    "id": series_id,
                    **header,
                    "instance_count": len(instances),
                    "total_bytes": sum(item["bytes"] for item in instances),
                    "instances": instances,
                    "review_status": "unreviewed",
                }
            )
        series_items.sort(key=lambda item: (item.get("acquisition_date") or "", item["series_description"]))
        studies.append(
            {
                "id": study_id,
                "acquisition_date": min(study_dates) if study_dates else None,
                "series": series_items,
                "review_status": "unreviewed",
            }
        )
    studies.sort(key=lambda item: item.get("acquisition_date") or "")

    catalog = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "privacy": {
            "classification": "sensitive_local_medical_data",
            "direct_identifier_tags_excluded": True,
            "deidentified": False,
            "warning": "This catalog remains sensitive and must not be uploaded or committed.",
        },
        "source": {
            "root_label": root.name,
            "immutable": True,
            "dicom_instances": len(parsed),
            "skipped_non_image_files": skipped,
        },
        "studies": studies,
        "agent_contract": {
            "review_status": "unreviewed",
            "observations": [],
            "computed_results": [],
            "candidate_interpretations": [],
            "limitations": [
                "No clinical interpretation has been performed.",
                "Series pairing and registration require human review.",
                "Header filtering is not DICOM de-identification; pixels and private tags may identify a patient.",
            ],
            "missing_context": ["diagnosis", "treatment_timeline", "clinical_status", "response_criteria"],
            "questions_for_clinician": [],
        },
    }
    return catalog, registry
