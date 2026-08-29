import { adaptersSEG } from '@cornerstonejs/adapters';
import { describe, expect, it } from 'vitest';
import {
  repairDicomSegFrameSourceClasses,
  type DicomSegSourceGeometry,
} from './dicomSeg';

const MR_IMAGE_STORAGE = '1.2.840.10008.5.1.4.1.1.4';
const SEGMENTATION_STORAGE = '1.2.840.10008.5.1.4.1.1.66.4';

type DicomItem = Record<string, unknown>;

const sequenceItems = (value: unknown): DicomItem[] =>
  Array.isArray(value) ? (value as DicomItem[]) : value ? [value as DicomItem] : [];

describe('Cornerstone DICOM SEG adapter integration', () => {
  it('keeps sparse first/last source UIDs aligned with their patient positions after repair', () => {
    const imageIds = ['synthetic:1', 'synthetic:2', 'synthetic:3'];
    const sopInstanceUids = ['1.2.3.1', '1.2.3.2', '1.2.3.3'];
    const sourceGeometryByInstance = new Map<string, DicomSegSourceGeometry>(
      sopInstanceUids.map((instanceUid, sourceIndex) => [
        instanceUid,
        {
          sopClassUid: MR_IMAGE_STORAGE,
          imagePositionPatient: [0, 0, sourceIndex * 2],
          imageOrientationPatient: [1, 0, 0, 0, 1, 0],
          pixelSpacing: [1, 1],
          sliceThickness: 1.5,
          sourceIndex,
        },
      ]),
    );
    const metadata = {
      get: (type: string, imageId: string) => {
        const sourceIndex = imageIds.indexOf(imageId);
        if (type === 'StudyData') {
          return {
            StudyInstanceUID: '1.2.10',
            StudyID: 'SYNTHETIC',
            PatientName: 'SYNTHETIC',
            PatientID: 'SYNTHETIC',
          };
        }
        if (type === 'SeriesData') {
          return {
            SeriesInstanceUID: '1.2.20',
            SeriesNumber: '1',
            Modality: 'MR',
            FrameOfReferenceUID: '1.2.30',
          };
        }
        if (type === 'ImageData') {
          return {
            SOPClassUID: MR_IMAGE_STORAGE,
            SOPInstanceUID: sopInstanceUids[sourceIndex],
            InstanceNumber: String(sourceIndex + 1),
            ImagePositionPatient: [0, 0, sourceIndex * 2],
            ImageOrientationPatient: [1, 0, 0, 0, 1, 0],
            Rows: 2,
            Columns: 2,
            PixelSpacing: [1, 1],
            SliceThickness: 2,
            SamplesPerPixel: 1,
            PhotometricInterpretation: 'MONOCHROME2',
            BitsAllocated: 16,
            BitsStored: 12,
            HighBit: 11,
            PixelRepresentation: 0,
          };
        }
        if (type === 'imagePlaneModule') {
          return {
            rows: 2,
            columns: 2,
            rowCosines: [1, 0, 0],
            columnCosines: [0, 1, 0],
            imagePositionPatient: [0, 0, sourceIndex * 2],
            pixelSpacing: [1, 1],
            sliceThickness: 2,
            frameOfReferenceUID: '1.2.30',
          };
        }
        return undefined;
      },
    };
    const images = imageIds.map((imageId) => ({
      imageId,
      voxelManager: { getScalarData: () => new Uint16Array(4) },
    }));
    const first = new Uint8Array([1, 0, 0, 0]);
    const middle = new Uint8Array(4);
    const last = new Uint8Array([0, 0, 1, 0]);
    const labelmaps2D = [first, middle, last].map((pixelData) => ({
      rows: 2,
      columns: 2,
      pixelData,
      segmentsOnLabelmap: pixelData.some(Boolean) ? [1] : [],
    }));
    const segmentMetadata: Array<DicomItem | undefined> = [];
    segmentMetadata[1] = {
      SegmentNumber: '1',
      SegmentLabel: 'Synthetic ROI',
      SegmentAlgorithmType: 'MANUAL',
      SegmentedPropertyCategoryCodeSequence: {
        CodeValue: '49755003',
        CodingSchemeDesignator: 'SCT',
        CodeMeaning: 'Morphologically Abnormal Structure',
      },
      SegmentedPropertyTypeCodeSequence: {
        CodeValue: '52988006',
        CodingSchemeDesignator: 'SCT',
        CodeMeaning: 'Lesion',
      },
    };

    const generated = adaptersSEG.Cornerstone3D.Segmentation.generateSegmentation(
      images,
      { segmentsOnLabelmap: [1], metadata: segmentMetadata, labelmaps2D },
      metadata,
      {
        sopClassUID: SEGMENTATION_STORAGE,
        transferSyntaxUid: '1.2.840.10008.1.2.1',
      },
    );
    const dataset = generated.dataset as DicomItem;

    repairDicomSegFrameSourceClasses(dataset, sourceGeometryByInstance);

    const observed = sequenceItems(dataset.PerFrameFunctionalGroupsSequence).map((frame) => {
      const derivation = sequenceItems(frame.DerivationImageSequence)[0];
      const source = sequenceItems(derivation.SourceImageSequence)[0];
      const plane = sequenceItems(frame.PlanePositionSequence)[0];
      const frameContent = sequenceItems(frame.FrameContentSequence)[0];
      return {
        instanceUid: source.ReferencedSOPInstanceUID,
        imagePositionPatient: plane.ImagePositionPatient,
        dimensionIndexValues: frameContent.DimensionIndexValues,
      };
    });

    expect(observed).toHaveLength(2);
    expect(new Set(observed.map((frame) => frame.instanceUid))).toEqual(
      new Set([sopInstanceUids[0], sopInstanceUids[2]]),
    );
    for (const frame of observed) {
      const source = sourceGeometryByInstance.get(String(frame.instanceUid));
      expect(source).toBeDefined();
      expect(frame.imagePositionPatient).toEqual(source?.imagePositionPatient);
      expect(frame.dimensionIndexValues).toEqual([1, (source?.sourceIndex ?? -1) + 1]);
    }
    const pixelData = dataset.PixelData as ArrayBuffer;
    expect(Array.from(new Uint8Array(pixelData))).toEqual([0x41, 0]);
  });
});
