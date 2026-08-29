#!/usr/bin/env python3
"""Generate a patient-free MR series plus one native-grid binary DICOM SEG."""

from __future__ import annotations

import argparse
import math
import os
from pathlib import Path

from pydicom.dataset import Dataset, FileDataset, FileMetaDataset
from pydicom.sequence import Sequence
from pydicom.tag import Tag
from pydicom.uid import (
    ExplicitVRLittleEndian,
    MRImageStorage,
    PYDICOM_IMPLEMENTATION_UID,
    SegmentationStorage,
    generate_uid,
)


ROWS = 64
COLUMNS = 64
SLICES = 24
ROW_SPACING = 0.8
COLUMN_SPACING = 0.8
SLICE_SPACING = 2.0


def code(value: str, scheme: str, meaning: str) -> Dataset:
    result = Dataset()
    result.CodeValue = value
    result.CodingSchemeDesignator = scheme
    result.CodeMeaning = meaning
    return result


def part10(path: Path, sop_class_uid: str, sop_instance_uid: str) -> FileDataset:
    meta = FileMetaDataset()
    meta.FileMetaInformationVersion = b"\x00\x01"
    meta.MediaStorageSOPClassUID = sop_class_uid
    meta.MediaStorageSOPInstanceUID = sop_instance_uid
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    meta.ImplementationClassUID = PYDICOM_IMPLEMENTATION_UID
    return FileDataset(str(path), {}, file_meta=meta, preamble=b"\0" * 128)


def source_pixels(slice_index: int) -> bytes:
    values = bytearray(ROWS * COLUMNS * 2)
    z = (slice_index - (SLICES - 1) / 2) / 7.0
    for row in range(ROWS):
        y = (row - (ROWS - 1) / 2) / 22.0
        for column in range(COLUMNS):
            x = (column - (COLUMNS - 1) / 2) / 22.0
            radial = math.sqrt(x * x + y * y + z * z)
            value = max(0, min(4095, round(3300 * math.exp(-radial * radial * 1.6))))
            if (x + 0.18) ** 2 + (y - 0.08) ** 2 + z * z < 0.13:
                value = min(4095, value + 650)
            offset = (row * COLUMNS + column) * 2
            values[offset : offset + 2] = value.to_bytes(2, "little")
    return bytes(values)


def segment_frame(slice_index: int) -> bytes:
    result = bytearray(ROWS * COLUMNS)
    z = (slice_index - 12) / 5.2
    for row in range(ROWS):
        y = (row - 34) / 11.0
        for column in range(COLUMNS):
            x = (column - 28) / 13.0
            if x * x + y * y + z * z <= 1:
                result[row * COLUMNS + column] = 1
    return bytes(result)


def pack_frames(frames: list[bytes]) -> bytes:
    bit_count = sum(len(frame) for frame in frames)
    payload = bytearray((bit_count + 7) // 8)
    bit_index = 0
    for frame in frames:
        for value in frame:
            if value:
                payload[bit_index // 8] |= 1 << (bit_index % 8)
            bit_index += 1
    if len(payload) % 2:
        payload.append(0)
    return bytes(payload)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    output = args.output.expanduser().resolve()
    output.mkdir(mode=0o700, parents=True, exist_ok=False)

    patient_id = "SCANVIEW-SYNTHETIC-SEG"
    study_uid = generate_uid()
    source_series_uid = generate_uid()
    segmentation_series_uid = generate_uid()
    frame_uid = generate_uid()
    source_uids = [generate_uid() for _ in range(SLICES)]

    for index, sop_uid in enumerate(source_uids):
        path = output / f"mr-{index + 1:03d}.dcm"
        dataset = part10(path, str(MRImageStorage), sop_uid)
        dataset.SOPClassUID = MRImageStorage
        dataset.SOPInstanceUID = sop_uid
        dataset.PatientID = patient_id
        dataset.PatientName = "ScanView^SyntheticSeg"
        dataset.StudyInstanceUID = study_uid
        dataset.SeriesInstanceUID = source_series_uid
        dataset.FrameOfReferenceUID = frame_uid
        dataset.Modality = "MR"
        dataset.StudyDate = "20260101"
        dataset.SeriesDate = "20260101"
        dataset.AcquisitionDate = "20260101"
        dataset.SeriesNumber = 1
        dataset.SeriesDescription = "Synthetic source SEG validation MR"
        dataset.InstanceNumber = index + 1
        dataset.ImageType = ["ORIGINAL", "PRIMARY", "OTHER"]
        dataset.Rows = ROWS
        dataset.Columns = COLUMNS
        dataset.PixelSpacing = [ROW_SPACING, COLUMN_SPACING]
        dataset.SliceThickness = SLICE_SPACING
        dataset.SpacingBetweenSlices = SLICE_SPACING
        dataset.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
        dataset.ImagePositionPatient = [0, 0, index * SLICE_SPACING]
        dataset.SamplesPerPixel = 1
        dataset.PhotometricInterpretation = "MONOCHROME2"
        dataset.BitsAllocated = 16
        dataset.BitsStored = 12
        dataset.HighBit = 11
        dataset.PixelRepresentation = 0
        dataset.WindowCenter = 1500
        dataset.WindowWidth = 2600
        dataset.PixelData = source_pixels(index)
        dataset.save_as(path, enforce_file_format=True)
        os.chmod(path, 0o600)

    nonempty: list[tuple[int, bytes]] = []
    for index in range(SLICES):
        frame = segment_frame(index)
        if any(frame):
            nonempty.append((index, frame))

    segmentation_path = output / "source-segmentation.dcm"
    segmentation_uid = generate_uid()
    segmentation = part10(
        segmentation_path, str(SegmentationStorage), segmentation_uid
    )
    segmentation.SOPClassUID = SegmentationStorage
    segmentation.SOPInstanceUID = segmentation_uid
    segmentation.PatientID = patient_id
    segmentation.PatientName = "ScanView^SyntheticSeg"
    segmentation.StudyInstanceUID = study_uid
    segmentation.SeriesInstanceUID = segmentation_series_uid
    segmentation.FrameOfReferenceUID = frame_uid
    segmentation.Modality = "SEG"
    segmentation.SeriesNumber = 90
    segmentation.InstanceNumber = 1
    segmentation.SeriesDescription = "Synthetic source-carried DICOM SEG"
    segmentation.ImageType = ["DERIVED", "PRIMARY"]
    segmentation.ContentLabel = "SYNTHETIC_SEG"
    segmentation.ContentDescription = "Patient-free local source SEG validation"
    segmentation.Manufacturer = "ScanView local"
    segmentation.ManufacturerModelName = "ScanView synthetic generator"
    segmentation.SoftwareVersions = "0.12.0"
    segmentation.Rows = ROWS
    segmentation.Columns = COLUMNS
    segmentation.NumberOfFrames = len(nonempty)
    segmentation.SamplesPerPixel = 1
    segmentation.PhotometricInterpretation = "MONOCHROME2"
    segmentation.BitsAllocated = 1
    segmentation.BitsStored = 1
    segmentation.HighBit = 0
    segmentation.PixelRepresentation = 0
    segmentation.SegmentationType = "BINARY"
    segmentation.SegmentsOverlap = "NO"

    segment = Dataset()
    segment.SegmentNumber = 1
    segment.SegmentLabel = "Synthetic test region"
    segment.SegmentDescription = "Patient-free shape for local display validation only"
    segment.SegmentAlgorithmType = "MANUAL"
    segment.SegmentedPropertyCategoryCodeSequence = Sequence(
        [code("49755003", "SCT", "Morphologically Abnormal Structure")]
    )
    segment.SegmentedPropertyTypeCodeSequence = Sequence(
        [code("52988006", "SCT", "Lesion")]
    )
    segment.RecommendedDisplayCIELabValue = [50000, 30000, 45000]
    segmentation.SegmentSequence = Sequence([segment])

    dimension_uid = generate_uid()
    dimension_organization = Dataset()
    dimension_organization.DimensionOrganizationUID = dimension_uid
    segmentation.DimensionOrganizationSequence = Sequence([dimension_organization])
    segment_dimension = Dataset()
    segment_dimension.DimensionOrganizationUID = dimension_uid
    segment_dimension.DimensionIndexPointer = Tag(0x0062000B)
    segment_dimension.FunctionalGroupPointer = Tag(0x0062000A)
    position_dimension = Dataset()
    position_dimension.DimensionOrganizationUID = dimension_uid
    position_dimension.DimensionIndexPointer = Tag(0x00200032)
    position_dimension.FunctionalGroupPointer = Tag(0x00209113)
    segmentation.DimensionIndexSequence = Sequence(
        [segment_dimension, position_dimension]
    )

    referenced_series = Dataset()
    referenced_series.SeriesInstanceUID = source_series_uid
    referenced_series.ReferencedInstanceSequence = Sequence([])
    for index, _ in nonempty:
        reference = Dataset()
        reference.ReferencedSOPClassUID = MRImageStorage
        reference.ReferencedSOPInstanceUID = source_uids[index]
        referenced_series.ReferencedInstanceSequence.append(reference)
    segmentation.ReferencedSeriesSequence = Sequence([referenced_series])

    shared = Dataset()
    measures = Dataset()
    measures.PixelSpacing = [ROW_SPACING, COLUMN_SPACING]
    measures.SliceThickness = SLICE_SPACING
    measures.SpacingBetweenSlices = SLICE_SPACING
    shared.PixelMeasuresSequence = Sequence([measures])
    orientation = Dataset()
    orientation.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
    shared.PlaneOrientationSequence = Sequence([orientation])
    segmentation.SharedFunctionalGroupsSequence = Sequence([shared])

    segmentation.PerFrameFunctionalGroupsSequence = Sequence([])
    for frame_number, (source_index, _) in enumerate(nonempty, 1):
        group = Dataset()
        identification = Dataset()
        identification.ReferencedSegmentNumber = 1
        group.SegmentIdentificationSequence = Sequence([identification])
        derivation = Dataset()
        derivation.DerivationCodeSequence = Sequence(
            [code("113076", "DCM", "Segmentation")]
        )
        source = Dataset()
        source.ReferencedSOPClassUID = MRImageStorage
        source.ReferencedSOPInstanceUID = source_uids[source_index]
        source.SpatialLocationsPreserved = "YES"
        source.PurposeOfReferenceCodeSequence = Sequence(
            [code("121322", "DCM", "Source Image for Image Processing Operation")]
        )
        derivation.SourceImageSequence = Sequence([source])
        group.DerivationImageSequence = Sequence([derivation])
        position = Dataset()
        position.ImagePositionPatient = [0, 0, source_index * SLICE_SPACING]
        group.PlanePositionSequence = Sequence([position])
        frame_content = Dataset()
        frame_content.DimensionIndexValues = [1, frame_number]
        frame_content.StackID = "1"
        frame_content.InStackPositionNumber = source_index + 1
        frame_content.TemporalPositionIndex = 1
        frame_content.FrameAcquisitionNumber = frame_number
        group.FrameContentSequence = Sequence([frame_content])
        segmentation.PerFrameFunctionalGroupsSequence.append(group)
    segmentation.PixelData = pack_frames([frame for _, frame in nonempty])
    segmentation.save_as(segmentation_path, enforce_file_format=True)
    os.chmod(segmentation_path, 0o600)

    foreground = sum(sum(frame) for _, frame in nonempty)
    volume_ml = foreground * ROW_SPACING * COLUMN_SPACING * SLICE_SPACING / 1000
    print(
        f"generated {SLICES} source images + 1 DICOM SEG; "
        f"{len(nonempty)} SEG frames; {foreground} marked voxels; {volume_ml:.6f} mL"
    )


if __name__ == "__main__":
    main()
