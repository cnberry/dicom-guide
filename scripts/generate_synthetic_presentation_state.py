#!/usr/bin/env python3
"""Generate a patient-free CT + GSPS fixture for local browser/Linux checks."""

from __future__ import annotations

import argparse
import sys
from array import array
from pathlib import Path

from pydicom.dataset import Dataset, FileDataset, FileMetaDataset
from pydicom.uid import (
    CTImageStorage,
    ExplicitVRLittleEndian,
    PYDICOM_IMPLEMENTATION_UID,
    generate_uid,
)


GSPS_SOP_CLASS_UID = "1.2.840.10008.5.1.4.1.1.11.1"
ROWS = 256
COLUMNS = 256


def _dataset(path: Path, sop_class_uid: str, sop_instance_uid: str) -> FileDataset:
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = sop_class_uid
    meta.MediaStorageSOPInstanceUID = sop_instance_uid
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    meta.ImplementationClassUID = PYDICOM_IMPLEMENTATION_UID
    dataset = FileDataset(str(path), {}, file_meta=meta, preamble=b"\0" * 128)
    dataset.SOPClassUID = sop_class_uid
    dataset.SOPInstanceUID = sop_instance_uid
    dataset.SpecificCharacterSet = "ISO_IR 192"
    return dataset


def _pixels(slice_index: int) -> bytes:
    values = array("h")
    for row in range(ROWS):
        for column in range(COLUMNS):
            x = column - COLUMNS / 2
            y = row - ROWS / 2
            radius = (x * x + y * y) ** 0.5
            value = -900
            if radius < 94:
                value = 25 + int(18 * x / COLUMNS) + slice_index * 8
            if (x - 24) ** 2 + (y + 14) ** 2 < (18 + slice_index * 2) ** 2:
                value = 115
            values.append(value)
    if sys.byteorder != "little":
        values.byteswap()
    return values.tobytes()


def generate(output: Path) -> None:
    output = output.expanduser().resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError("output directory must be empty")
    output.mkdir(parents=True, exist_ok=True)

    study_uid = generate_uid()
    image_series_uid = generate_uid()
    presentation_series_uid = generate_uid()
    frame_uid = generate_uid()
    image_uids = [generate_uid() for _ in range(3)]
    for index, instance_uid in enumerate(image_uids, 1):
        path = output / f"synthetic-ct-{index:03d}.dcm"
        dataset = _dataset(path, str(CTImageStorage), instance_uid)
        dataset.PatientName = "SYNTHETIC^GSPS"
        dataset.PatientID = "SYNTHETIC-GSPS"
        dataset.StudyInstanceUID = study_uid
        dataset.SeriesInstanceUID = image_series_uid
        dataset.FrameOfReferenceUID = frame_uid
        dataset.StudyDate = "20260829"
        dataset.SeriesDate = "20260829"
        dataset.AcquisitionDate = "20260829"
        dataset.Modality = "CT"
        dataset.StudyDescription = "SYNTHETIC PRESENTATION STATE TEST"
        dataset.SeriesDescription = "SYNTHETIC CT PHANTOM"
        dataset.InstanceNumber = index
        dataset.Rows = ROWS
        dataset.Columns = COLUMNS
        dataset.PixelSpacing = [0.8, 0.8]
        dataset.SliceThickness = 1.0
        dataset.SpacingBetweenSlices = 1.0
        dataset.ImagePositionPatient = [0.0, 0.0, float(index - 1)]
        dataset.ImageOrientationPatient = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]
        dataset.SamplesPerPixel = 1
        dataset.PhotometricInterpretation = "MONOCHROME2"
        dataset.BitsAllocated = 16
        dataset.BitsStored = 16
        dataset.HighBit = 15
        dataset.PixelRepresentation = 1
        dataset.RescaleIntercept = 0
        dataset.RescaleSlope = 1
        dataset.WindowCenter = 40
        dataset.WindowWidth = 400
        dataset.PixelData = _pixels(index - 1)
        dataset.save_as(path, enforce_file_format=True)

    presentation_uid = generate_uid()
    path = output / "synthetic-gsps.dcm"
    state = _dataset(path, GSPS_SOP_CLASS_UID, presentation_uid)
    state.PatientName = "SYNTHETIC^GSPS"
    state.PatientID = "SYNTHETIC-GSPS"
    state.StudyInstanceUID = study_uid
    state.SeriesInstanceUID = presentation_series_uid
    state.StudyDate = "20260829"
    state.SeriesDate = "20260829"
    state.ContentDate = "20260829"
    state.ContentTime = "120000"
    state.Modality = "PR"
    state.SeriesDescription = "SYNTHETIC READ-ONLY GSPS"
    state.InstanceNumber = 1
    state.ContentLabel = "SYNTHETIC"
    state.ContentDescription = "Patient-free ScanView GSPS fixture"
    state.ImageRotation = 0
    state.ImageHorizontalFlip = "N"
    state.PresentationLUTShape = "IDENTITY"

    referenced_series = Dataset()
    referenced_series.SeriesInstanceUID = image_series_uid
    referenced_series.ReferencedImageSequence = []
    for instance_uid in image_uids:
        reference = Dataset()
        reference.ReferencedSOPClassUID = str(CTImageStorage)
        reference.ReferencedSOPInstanceUID = instance_uid
        referenced_series.ReferencedImageSequence.append(reference)
    state.ReferencedSeriesSequence = [referenced_series]

    voi = Dataset()
    voi.WindowCenter = 40
    voi.WindowWidth = 400
    state.SoftcopyVOILUTSequence = [voi]

    area = Dataset()
    area.DisplayedAreaTopLeftHandCorner = [1, 1]
    area.DisplayedAreaBottomRightHandCorner = [COLUMNS, ROWS]
    area.PresentationSizeMode = "SCALE TO FIT"
    area.PresentationPixelAspectRatio = [1, 1]
    state.DisplayedAreaSelectionSequence = [area]

    layer = Dataset()
    layer.GraphicLayer = "SYNTHETIC"
    layer.GraphicLayerOrder = 1
    state.GraphicLayerSequence = [layer]

    annotation = Dataset()
    annotation.GraphicLayer = "SYNTHETIC"
    reference = Dataset()
    reference.ReferencedSOPClassUID = str(CTImageStorage)
    reference.ReferencedSOPInstanceUID = image_uids[1]
    annotation.ReferencedImageSequence = [reference]

    graphic = Dataset()
    graphic.GraphicAnnotationUnits = "PIXEL"
    graphic.GraphicDimensions = 2
    graphic.NumberOfGraphicPoints = 5
    graphic.GraphicData = [
        132.5,
        92.5,
        184.5,
        92.5,
        184.5,
        144.5,
        132.5,
        144.5,
        132.5,
        92.5,
    ]
    graphic.GraphicType = "POLYLINE"
    graphic.GraphicFilled = "N"
    annotation.GraphicObjectSequence = [graphic]

    text = Dataset()
    text.UnformattedTextValue = "SYNTHETIC 12.3 mm"
    text.AnchorPointAnnotationUnits = "PIXEL"
    text.AnchorPoint = [185.0, 92.0]
    text.AnchorPointVisibility = "Y"
    annotation.TextObjectSequence = [text]
    state.GraphicAnnotationSequence = [annotation]
    state.save_as(path, enforce_file_format=True)

    print(
        "generated patient-free fixture: 3 CT images, 1 supported GSPS state, "
        "1 polyline, 1 text object"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        generate(args.output)
    except (OSError, ValueError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
