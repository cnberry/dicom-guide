import { describe, expect, it } from 'vitest';
import { repairDicomSegFrameSourceClasses } from './dicomSeg';

type AdapterSource = {
  ReferencedSOPInstanceUID: string;
  ReferencedSOPClassUID?: string;
  PurposeOfReferenceCodeSequence?: unknown;
};

type AdapterFrame = {
  DerivationImageSequence: {
    SourceImageSequence: AdapterSource;
    DerivationCodeSequence?: unknown;
  };
  FrameContentSequence: { DimensionIndexValues: number[] };
  PlanePositionSequence?: { ImagePositionPatient: number[] };
};

type AdapterDataset = Record<string, unknown> & {
  PerFrameFunctionalGroupsSequence: AdapterFrame[];
};

const adapterStyleDataset = (): AdapterDataset => ({
  ReferencedSeriesSequence: {
    SeriesInstanceUID: '1.2.3',
    ReferencedInstanceSequence: [
      {
        ReferencedSOPClassUID: '1.2.840.10008.5.1.4.1.1.4',
        ReferencedSOPInstanceUID: '1.2.3.1',
      },
      {
        ReferencedSOPClassUID: '1.2.840.10008.5.1.4.1.1.4',
        ReferencedSOPInstanceUID: '1.2.3.2',
      },
      {
        ReferencedSOPClassUID: '1.2.840.10008.5.1.4.1.1.4',
        ReferencedSOPInstanceUID: '1.2.3.3',
      },
    ],
  },
  PerFrameFunctionalGroupsSequence: [
    {
      DerivationImageSequence: {
        SourceImageSequence: { ReferencedSOPInstanceUID: '1.2.3.1' },
      },
      FrameContentSequence: { DimensionIndexValues: [1, 1] },
    },
    {
      DerivationImageSequence: {
        SourceImageSequence: { ReferencedSOPInstanceUID: '1.2.3.3' },
      },
      FrameContentSequence: { DimensionIndexValues: [1, 3] },
    },
  ],
  SharedFunctionalGroupsSequence: {},
  Rows: 2,
  Columns: 2,
  NumberOfFrames: 2,
  PixelData: new Uint8Array([0x01, 0x04]).buffer,
});

const sourceGeometry = new Map([
  [
    '1.2.3.1',
    {
      sopClassUid: '1.2.840.10008.5.1.4.1.1.4',
      imagePositionPatient: [0, 0, 0] as [number, number, number],
      imageOrientationPatient: [1, 0, 0, 0, 1, 0] as [number, number, number, number, number, number],
      pixelSpacing: [1, 1] as [number, number],
      sliceThickness: 1.5,
      sourceIndex: 0,
    },
  ],
  [
    '1.2.3.2',
    {
      sopClassUid: '1.2.840.10008.5.1.4.1.1.4',
      imagePositionPatient: [0, 0, 2] as [number, number, number],
      imageOrientationPatient: [1, 0, 0, 0, 1, 0] as [number, number, number, number, number, number],
      pixelSpacing: [1, 1] as [number, number],
      sliceThickness: 1.5,
      sourceIndex: 1,
    },
  ],
  [
    '1.2.3.3',
    {
      sopClassUid: '1.2.840.10008.5.1.4.1.1.4',
      imagePositionPatient: [0, 0, 4] as [number, number, number],
      imageOrientationPatient: [1, 0, 0, 0, 1, 0] as [number, number, number, number, number, number],
      pixelSpacing: [1, 1] as [number, number],
      sliceThickness: 1.5,
      sourceIndex: 2,
    },
  ],
]);

describe('DICOM SEG source-reference repair', () => {
  it('restores the mandatory SOP class on sparse adapter-generated frame references', () => {
    const dataset = adapterStyleDataset();

    repairDicomSegFrameSourceClasses(dataset, sourceGeometry);

    expect(
      dataset.PerFrameFunctionalGroupsSequence.map(
        (frame) => frame.DerivationImageSequence.SourceImageSequence.ReferencedSOPClassUID,
      ),
    ).toEqual([
      '1.2.840.10008.5.1.4.1.1.4',
      '1.2.840.10008.5.1.4.1.1.4',
    ]);
    for (const frame of dataset.PerFrameFunctionalGroupsSequence) {
      expect(frame.DerivationImageSequence.DerivationCodeSequence).toMatchObject({
        CodeValue: '113076',
        CodingSchemeDesignator: 'DCM',
      });
      expect(
        frame.DerivationImageSequence.SourceImageSequence.PurposeOfReferenceCodeSequence,
      ).toMatchObject({ CodeValue: '121322', CodingSchemeDesignator: 'DCM' });
    }
    expect(
      dataset.PerFrameFunctionalGroupsSequence.map(
        (frame) => frame.PlanePositionSequence?.ImagePositionPatient,
      ),
    ).toEqual([
      [0, 0, 0],
      [0, 0, 4],
    ]);
  });

  it('fails closed when a sparse frame is absent from or conflicts with the source set', () => {
    const absent = adapterStyleDataset();
    absent.PerFrameFunctionalGroupsSequence[1].DerivationImageSequence.SourceImageSequence.ReferencedSOPInstanceUID =
      '1.2.3.9';
    expect(() => repairDicomSegFrameSourceClasses(absent, sourceGeometry)).toThrow(
      /complete source reference set/i,
    );

    const conflicting = adapterStyleDataset();
    conflicting.PerFrameFunctionalGroupsSequence[0].DerivationImageSequence.SourceImageSequence.ReferencedSOPClassUID =
      '1.2.840.10008.5.1.4.1.1.2';
    expect(() => repairDicomSegFrameSourceClasses(conflicting, sourceGeometry)).toThrow(
      /wrong source SOP class/i,
    );

    const wrongPurpose = adapterStyleDataset();
    wrongPurpose.PerFrameFunctionalGroupsSequence[0].DerivationImageSequence.SourceImageSequence.PurposeOfReferenceCodeSequence =
      { CodeValue: 'wrong', CodingSchemeDesignator: 'DCM', CodeMeaning: 'wrong' };
    expect(() => repairDicomSegFrameSourceClasses(wrongPurpose, sourceGeometry)).toThrow(
      /conflicting PurposeOfReferenceCodeSequence/i,
    );
  });
});
