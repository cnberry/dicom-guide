import { describe, expect, it } from 'vitest';
import {
  buildMeasurementEvidencePacket,
  readMeasurementEvidencePacket,
  type ImageSourceReference,
} from './measurements';

describe('measurement evidence export', () => {
  it('exports physical length with opaque source references and unreviewed state', () => {
    const references = new Map<string, ImageSourceReference>([
      [
        'dicomfile:1',
        {
          seriesId: '0123456789abcdef',
          instanceId: 'fedcba9876543210',
          frameOfReferenceId: '0011223344556677',
          spacingTrusted: true,
        },
      ],
    ]);

    const packet = buildMeasurementEvidencePacket(
      [
        {
          annotationId: 'annotation-1',
          referencedImageId: 'dicomfile:1',
          worldPoints: [
            [0, 0, 0],
            [3, 4, 0],
          ],
        },
      ],
      references,
      '2026-08-28T00:00:00.000Z',
    );

    expect(packet.review_status).toBe('unreviewed');
    expect(packet.measurements[0]).toMatchObject({
      tracking_id: 'length:annotation-1',
      source: { series_id: '0123456789abcdef', instance_id: 'fedcba9876543210' },
      result: { value: 5, unit: 'mm' },
    });
    expect(readMeasurementEvidencePacket(packet)).toEqual({ packet, errors: [] });
  });

  it('withholds a physical value when pixel spacing is unavailable', () => {
    const references = new Map<string, ImageSourceReference>([
      [
        'dicomfile:2',
        {
          seriesId: '0123456789abcdef',
          instanceId: 'fedcba9876543210',
          spacingTrusted: false,
        },
      ],
    ]);

    const packet = buildMeasurementEvidencePacket(
      [
        {
          referencedImageId: 'dicomfile:2',
          worldPoints: [
            [0, 0, 0],
            [3, 4, 0],
          ],
        },
      ],
      references,
    );

    expect(packet.measurements[0].result).toEqual({ value: undefined, unit: 'unknown' });
    expect(packet.measurements[0].limitations.join(' ')).toContain('Pixel spacing');
  });

  it('excludes annotations that cannot be traced to an imported source instance', () => {
    const packet = buildMeasurementEvidencePacket(
      [
        {
          annotationId: 'orphan',
          referencedImageId: 'missing',
          worldPoints: [
            [0, 0, 0],
            [1, 1, 1],
          ],
        },
      ],
      new Map(),
    );

    expect(packet.measurements).toEqual([]);
    expect(packet.limitations.join(' ')).toContain('excluded');
  });

  it('refuses reviewed or untraceable imported measurement packets', () => {
    const parsed = readMeasurementEvidencePacket({
      schema_version: '1.0.0',
      created_at: '2026-08-28T00:00:00Z',
      review_status: 'accepted',
      unexpected_patient_field: 'must not be accepted',
      measurements: [
        {
          tracking_id: 'length:unsafe',
          type: 'length',
          review_status: 'unreviewed',
          source: { series_id: 'not-an-opaque-id', instance_id: 'also-invalid' },
          geometry: { coordinate_system: 'DICOM patient LPS', world_points: [[0, 0, 0], [1, 1, 1]] },
        },
      ],
      limitations: [],
    });

    expect(parsed.packet).toBeUndefined();
    expect(parsed.errors.join(' ')).toContain('unreviewed');
    expect(parsed.errors.join(' ')).toContain('source provenance');
    expect(parsed.errors.join(' ')).toContain('unsupported fields');
  });
});
