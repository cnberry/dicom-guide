import { describe, expect, it } from 'vitest';
import {
  buildKeyImageEvidencePacket,
  scopeMeasurementPacketToInstance,
} from './keyImages';
import type { MeasurementEvidencePacket } from './measurements';

const measurementPacket: MeasurementEvidencePacket = {
  schema_version: '3.0.0',
  created_at: '2026-08-28T00:00:00.000Z',
  review_status: 'unreviewed',
  measurements: [
    {
      tracking_id: 'length:visible',
      type: 'length',
      review_status: 'unreviewed',
      source: {
        series_id: '0123456789abcdef',
        instance_id: 'fedcba9876543210',
      },
      geometry: {
        coordinate_system: 'DICOM patient LPS',
        world_points: [
          [0, 0, 0],
          [3, 4, 0],
        ],
      },
      result: { value: 5, unit: 'mm' },
      method: {
        name: 'manual_two_point_length',
        implementation: 'Cornerstone3D LengthTool',
      },
      limitations: ['Manual and unreviewed.'],
    },
    {
      tracking_id: 'length:other-instance',
      type: 'length',
      review_status: 'unreviewed',
      source: {
        series_id: '0123456789abcdef',
        instance_id: '0011223344556677',
      },
      geometry: {
        coordinate_system: 'DICOM patient LPS',
        world_points: [
          [0, 0, 0],
          [0, 1, 0],
        ],
      },
      result: { value: 1, unit: 'mm' },
      method: {
        name: 'manual_two_point_length',
        implementation: 'Cornerstone3D LengthTool',
      },
      limitations: ['Manual and unreviewed.'],
    },
  ],
  limitations: ['Not a diagnosis.'],
};

describe('key-image evidence', () => {
  it('scopes embedded measurement evidence to the displayed source instance', () => {
    const scoped = scopeMeasurementPacketToInstance(
      measurementPacket,
      '0123456789abcdef',
      'fedcba9876543210',
      '2026-08-28T01:02:03.000Z',
    );

    expect(scoped.schema_version).toBe('3.0.0');
    expect(scoped.created_at).toBe('2026-08-28T01:02:03.000Z');
    expect(scoped.measurements.map((measurement) => measurement.tracking_id)).toEqual([
      'length:visible',
    ]);
    expect(scoped.limitations.join(' ')).toContain('single displayed source instance');
  });

  it('cross-hashes the PNG and measurement packet without exposing source UIDs', async () => {
    const scoped = scopeMeasurementPacketToInstance(
      measurementPacket,
      '0123456789abcdef',
      'fedcba9876543210',
      '2026-08-28T01:02:03.000Z',
    );
    const measurementBytes = new TextEncoder().encode(`${JSON.stringify(scoped)}\n`);
    const packet = await buildKeyImageEvidencePacket({
      createdAt: '2026-08-28T01:02:03.000Z',
      source: {
        study_id: 'abcdef0123456789',
        series_id: '0123456789abcdef',
        instance_id: 'fedcba9876543210',
        patient_context_id: '1234567890abcdef',
        modality: 'MR',
        acquisition_date: '20260828',
        series_description: 'Synthetic axial',
        instance_number: 2,
      },
      display: {
        viewport_role: 'baseline',
        stack_position: 2,
        stack_count: 3,
        source_kind: 'loopback-service',
        viewport_width_px: 512,
        viewport_height_px: 512,
        patient_orientation: { left: 'R', right: 'L', top: 'A', bottom: 'P' },
        presentation: { invert: false, zoom: 1, pan: [0, 0] },
      },
      imageWidth: 512,
      imageHeight: 560,
      pngBytes: new Uint8Array([1, 2, 3]),
      measurementPacket: scoped,
      measurementBytes,
    });

    expect(packet).toMatchObject({
      schema_version: '2.0.0',
      review_status: 'unreviewed',
      artifact_type: 'derived_display_key_image',
      measurement_evidence: {
        measurement_count: 1,
        tracking_ids: ['length:visible'],
      },
      image: { filename: 'key-image.png', width_px: 512, height_px: 560 },
    });
    expect(packet.image.sha256).toMatch(/^[0-9a-f]{64}$/);
    expect(packet.measurement_evidence.sha256).toMatch(/^[0-9a-f]{64}$/);
    expect(packet.image.sha256).not.toBe(packet.measurement_evidence.sha256);
    expect(JSON.stringify(packet)).not.toContain('1.2.840.');
  });
});
