import { describe, expect, it } from 'vitest';
import { manifestToDicomSeries } from './localService';

const manifest = {
  schema_version: '1.0.0',
  source: { dicom_instances: 2 },
  studies: [
    {
      id: 'study_0123456789abcdef0123',
      series: [
        {
          id: 'series_0123456789abcdef0123',
          patient_context_id: 'patient_0123456789abcdef0123',
          acquisition_date: '20260828',
          modality: 'MR',
          series_description: 'T1 POST',
          protocol_name: 'Brain',
          body_part: 'BRAIN',
          image_type: ['ORIGINAL', 'PRIMARY'],
          frame_of_reference_id: 'frame_0123456789abcdef0123',
          rows: 512,
          columns: 512,
          pixel_spacing: [0.5, 0.5],
          slice_thickness: 1,
          image_orientation_patient: [1, 0, 0, 0, 1, 0],
          instances: [
            {
              id: 'instance_0123456789abcdef0123',
              instance_number: 1,
              image_position_patient: [0, 0, 0],
            },
            {
              id: 'instance_1123456789abcdef0123',
              instance_number: 2,
              image_position_patient: [0, 0, 1],
            },
          ],
        },
      ],
    },
  ],
};

describe('loopback service manifest', () => {
  it('maps catalog IDs directly into locally streamed DICOM series', () => {
    const result = manifestToDicomSeries(manifest);

    expect(result).toMatchObject({ studyCount: 1, instanceCount: 2 });
    expect(result?.series[0]).toMatchObject({
      id: 'series_0123456789abcdef0123',
      studyId: 'study_0123456789abcdef0123',
      patientContextId: 'patient_0123456789abcdef0123',
      sourceKind: 'loopback-service',
      geometry: { pixelSpacing: [0.5, 0.5] },
    });
    expect(result?.series[0].instances[0]).toMatchObject({
      instanceId: 'instance_0123456789abcdef0123',
      imageUrl: '/v1/instances/instance_0123456789abcdef0123',
    });
  });

  it('excludes non-pixel modalities and malformed opaque identifiers', () => {
    const unsafe = structuredClone(manifest);
    unsafe.studies[0].series.push({
      ...structuredClone(manifest.studies[0].series[0]),
      id: 'not-opaque',
      modality: 'SR',
    });

    const result = manifestToDicomSeries(unsafe);

    expect(result?.series).toHaveLength(1);
  });

  it('rejects an unsupported manifest contract', () => {
    expect(manifestToDicomSeries({ ...manifest, schema_version: '99.0.0' })).toBeUndefined();
  });
});
