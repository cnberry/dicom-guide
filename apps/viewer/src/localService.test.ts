import { afterEach, describe, expect, it, vi } from 'vitest';
import { manifestToDicomSeries, selectLocalServiceFolder } from './localService';

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
              rows: 512,
              columns: 512,
              pixel_spacing: [0.5, 0.5],
              slice_thickness: 1,
              image_orientation_patient: [1, 0, 0, 0, 1, 0],
              number_of_frames: 1,
            },
            {
              id: 'instance_1123456789abcdef0123',
              instance_number: 2,
              image_position_patient: [0, 0, 1],
              rows: 512,
              columns: 512,
              pixel_spacing: [0.5, 0.5],
              slice_thickness: 1,
              image_orientation_patient: [1, 0, 0, 0, 1, 0],
              number_of_frames: 1,
            },
          ],
        },
      ],
    },
  ],
};

describe('loopback service manifest', () => {
  afterEach(() => vi.unstubAllGlobals());

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
      pixelSpacing: [0.5, 0.5],
      orientation: [1, 0, 0, 0, 1, 0],
      numberOfFrames: 1,
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

  it('asks the local service to select and index a folder without browser files', async () => {
    const fetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          status: 'selected',
          source_revision: 2,
          study_count: 1,
          renderable_series: 3,
          dicom_instances: 240,
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    );
    vi.stubGlobal('fetch', fetch);

    await expect(selectLocalServiceFolder()).resolves.toEqual({
      status: 'selected',
      sourceRevision: 2,
      studyCount: 1,
      seriesCount: 3,
      instanceCount: 240,
    });
    expect(fetch).toHaveBeenCalledWith(
      '/v1/local-folders/select',
      expect.objectContaining({
        method: 'POST',
        credentials: 'same-origin',
        body: '{}',
      }),
    );
  });

  it('preserves the current folder after cancellation or an invalid selection', async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ status: 'cancelled' }), { status: 200 }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ error: 'no_renderable_dicom' }), { status: 422 }),
      );
    vi.stubGlobal('fetch', fetch);

    await expect(selectLocalServiceFolder()).resolves.toEqual({ status: 'cancelled' });
    await expect(selectLocalServiceFolder()).rejects.toThrow(
      'No readable MR or CT image series were found',
    );
  });

  it('falls back to browser-only folder support when no local service endpoint exists', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('', { status: 404 })));

    await expect(selectLocalServiceFolder()).resolves.toBeUndefined();
  });

  it('does not fall back to browser folder materialization after a service failure', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('connection closed')));

    await expect(selectLocalServiceFolder()).rejects.toThrow(
      'The local folder service is unavailable',
    );
  });
});
