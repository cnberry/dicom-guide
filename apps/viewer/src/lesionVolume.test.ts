import { unzipSync } from 'fflate';
import { describe, expect, it } from 'vitest';
import type { DicomSeries } from './dicom';
import {
  MAX_MANUAL_LABELMAP_VOXELS,
  buildLesionVolumeArchive,
  calculateManualSegmentationStats,
} from './lesionVolume';

const series = (): DicomSeries => ({
  id: '0000000000000002',
  studyId: '0000000000000001',
  patientContextId: '0000000000000004',
  frameOfReferenceId: '0000000000000003',
  modality: 'MR',
  description: 'Synthetic series',
  imageType: ['ORIGINAL', 'PRIMARY'],
  sourceKind: 'browser-folder',
  geometry: {
    rows: 2,
    columns: 2,
    pixelSpacing: [0.5, 0.75],
    sliceThickness: 2,
    orientation: [1, 0, 0, 0, 1, 0],
  },
  instances: [0, 1, 2].map((index) => ({
    instanceId: `${index + 1}`.padStart(16, '0'),
    instanceNumber: index + 1,
    imagePosition: [0, 0, index * 2],
    rows: 2,
    columns: 2,
    pixelSpacing: [0.5, 0.75],
    sliceThickness: 2,
    orientation: [1, 0, 0, 0, 1, 0],
    numberOfFrames: 1,
    file: new File([new Uint8Array([index, 1, 2, 3])], `source-${index}.dcm`),
  })),
});

describe('manual lesion ROI volume evidence', () => {
  it('computes native anisotropic volume without rounding the evidence', () => {
    const stats = calculateManualSegmentationStats(
      new Uint8Array([1, 0, 1, 0, 0, 1, 0, 0, 1, 0, 0, 0]),
      [2, 2, 3],
      [0.5, 0.75],
      2,
    );
    expect(stats).toEqual({
      foregroundVoxels: 4,
      voxelVolumeMm3: 0.75,
      volumeMm3: 3,
      volumeMl: 0.003,
    });
  });

  it('exports one source-bound sensitive ZIP with every clinical inference locked', async () => {
    const source = series();
    const archive = await buildLesionVolumeArchive({
      series: source,
      orderedInstanceIds: source.instances.map((instance) => instance.instanceId),
      dimensions: [2, 2, 3],
      sliceSpacingMm: 2,
      maskValues: new Uint8Array([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0]),
      dicomSegBytes: new Uint8Array(132).fill(7),
      artifactId: 'seg_12345678-1234-4abc-8def-1234567890ab',
      trackingUid: '2.25.123456789',
      label: 'Reviewer-defined region',
      targetDefinition: 'Manual discussion boundary; tissue identity is unreviewed.',
      createdAt: '2026-08-28T12:00:00.000Z',
    });
    const files = unzipSync(archive.bytes);
    expect(Object.keys(files).sort()).toEqual([
      'README.txt',
      'evidence.json',
      'segmentation.dcm',
    ]);
    const evidence = JSON.parse(new TextDecoder().decode(files['evidence.json']));
    expect(evidence.source.instances).toHaveLength(3);
    expect(evidence.source.instances.map((item: { frame_index: number }) => item.frame_index)).toEqual([
      0, 1, 2,
    ]);
    expect(evidence.source.instances[0].sha256).toMatch(/^[0-9a-f]{64}$/);
    expect(evidence.source.source_set_sha256).toMatch(/^[0-9a-f]{64}$/);
    expect(evidence.measurement).toMatchObject({
      status: 'computed_unreviewed',
      foreground_voxel_count: 3,
      volume_mm3: 2.25,
      volume_ml: 0.00225,
      boundary_uncertainty: 'not_quantified',
    });
    expect(evidence.permitted_uses).toEqual({
      source_overlay: true,
      mask_overlay: true,
      exact_timepoint_volume: 'computed_unreviewed_only',
      longitudinal_link: false,
      percent_change: false,
      response_classification: false,
      diagnosis: false,
      clinical_conclusion: false,
    });
    expect(JSON.stringify(evidence)).not.toMatch(/StudyInstanceUID|SeriesInstanceUID|SOPInstanceUID/);
  });

  it('rejects empty, non-binary, mismatched, and over-budget labelmaps', () => {
    expect(() =>
      calculateManualSegmentationStats(new Uint8Array(12), [2, 2, 3], [1, 1], 1),
    ).toThrow(/at least one voxel/i);
    expect(() =>
      calculateManualSegmentationStats(
        new Uint8Array([2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]),
        [2, 2, 3],
        [1, 1],
        1,
      ),
    ).toThrow(/strictly binary/i);
    expect(() =>
      calculateManualSegmentationStats(new Uint8Array([1]), [2, 2, 3], [1, 1], 1),
    ).toThrow(/does not match/i);
    expect(() =>
      calculateManualSegmentationStats(
        new Uint8Array([1]),
        [MAX_MANUAL_LABELMAP_VOXELS + 1, 1, 1],
        [1, 1],
        1,
      ),
    ).toThrow(/64 Mi-voxel/i);
  });
});
