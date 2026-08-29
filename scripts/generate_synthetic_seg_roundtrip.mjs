#!/usr/bin/env node

import { writeFileSync } from 'node:fs';
import { adaptersSEG } from '../apps/viewer/node_modules/@cornerstonejs/adapters/dist/esm/index.js';
import dcmjs from '../apps/viewer/node_modules/dcmjs/build/dcmjs.es.js';
import { repairDicomSegFrameSourceClasses } from '../apps/viewer/src/dicomSeg.ts';

const output = process.argv[2];
if (!output) {
  throw new Error('usage: node --experimental-strip-types generate_synthetic_seg_roundtrip.mjs OUTPUT.dcm');
}

const imageIds = ['synthetic:1', 'synthetic:2', 'synthetic:3'];
const sopInstanceUids = ['1.2.3.1', '1.2.3.2', '1.2.3.3'];
const sourceGeometryByInstance = new Map(
  sopInstanceUids.map((instanceUid, sourceIndex) => [
    instanceUid,
    {
      sopClassUid: '1.2.840.10008.5.1.4.1.1.4',
      imagePositionPatient: [0, 0, sourceIndex * 2],
      imageOrientationPatient: [1, 0, 0, 0, 1, 0],
      pixelSpacing: [1, 1],
      sliceThickness: 1.5,
      sourceIndex,
    },
  ]),
);
const metadata = {
  get: (type, imageId) => {
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
        SOPClassUID: '1.2.840.10008.5.1.4.1.1.4',
        SOPInstanceUID: sopInstanceUids[sourceIndex],
        InstanceNumber: String(sourceIndex + 1),
        ImagePositionPatient: [0, 0, sourceIndex * 2],
        ImageOrientationPatient: [1, 0, 0, 0, 1, 0],
        Rows: 2,
        Columns: 2,
        PixelSpacing: [1, 1],
        SliceThickness: 1.5,
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
        sliceThickness: 1.5,
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
const labelmaps2D = [
  new Uint8Array([1, 0, 0, 0]),
  new Uint8Array(4),
  new Uint8Array([0, 0, 1, 0]),
].map((pixelData) => ({
  rows: 2,
  columns: 2,
  pixelData,
  segmentsOnLabelmap: pixelData.some(Boolean) ? [1] : [],
}));
const artifactId = 'seg_12345678-1234-4abc-8def-1234567890ab';
const trackingUid = '2.25.123456789';
const label = 'Manual region draft';
const targetDefinition =
  'Person-painted synthetic boundary for source and format validation only.';
const segmentMetadata = [];
segmentMetadata[1] = {
  SegmentNumber: '1',
  SegmentLabel: label,
  SegmentDescription: targetDefinition,
  SegmentAlgorithmType: 'MANUAL',
  TrackingID: artifactId,
  TrackingUID: trackingUid,
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
    sopClassUID: '1.2.840.10008.5.1.4.1.1.66.4',
    transferSyntaxUid: '1.2.840.10008.1.2.1',
  },
);
const dataset = generated.dataset;
Object.assign(dataset, {
  SegmentsOverlap: 'NO',
  SpecificCharacterSet: 'ISO_IR 192',
  ContentLabel: 'SCANVIEW_SEG',
  ContentDescription: 'Unreviewed local manual lesion ROI evidence',
  SeriesDescription: 'ScanView unreviewed manual lesion ROI',
  Manufacturer: 'ScanView local',
  ManufacturerModelName: 'ScanView',
  SoftwareVersions: '0.13.0',
});
const segment = Array.isArray(dataset.SegmentSequence)
  ? dataset.SegmentSequence[0]
  : dataset.SegmentSequence;
Object.assign(segment, {
  SegmentNumber: '1',
  SegmentLabel: label,
  SegmentDescription: targetDefinition,
  SegmentAlgorithmType: 'MANUAL',
  TrackingID: artifactId,
  TrackingUID: trackingUid,
});
repairDicomSegFrameSourceClasses(dataset, sourceGeometryByInstance);
const bytes = new Uint8Array(dcmjs.data.datasetToDict(dataset).write());
writeFileSync(output, bytes);
process.stdout.write(
  `${JSON.stringify({ artifactId, trackingUid, label, targetDefinition, bytes: bytes.byteLength })}\n`,
);
