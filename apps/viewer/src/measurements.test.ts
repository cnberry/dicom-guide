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
          type: 'length',
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
          type: 'length',
          referencedImageId: 'dicomfile:2',
          worldPoints: [
            [0, 0, 0],
            [3, 4, 0],
          ],
        },
      ],
      references,
    );

    expect(packet.measurements[0]).toMatchObject({
      type: 'length',
      result: { value: undefined, unit: 'unknown' },
    });
    expect(packet.measurements[0].limitations.join(' ')).toContain('Pixel spacing');
  });

  it('excludes annotations that cannot be traced to an imported source instance', () => {
    const packet = buildMeasurementEvidencePacket(
      [
        {
          annotationId: 'orphan',
          type: 'length',
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

  it('exports perpendicular axes and product for a bidirectional measurement', () => {
    const references = new Map<string, ImageSourceReference>([
      [
        'dicomfile:3',
        {
          seriesId: 'series_0123456789abcdef0123',
          instanceId: 'instance_0123456789abcdef0123',
          frameOfReferenceId: 'frame_0123456789abcdef0123',
          spacingTrusted: true,
        },
      ],
    ]);
    const packet = buildMeasurementEvidencePacket(
      [
        {
          annotationId: 'annotation-2',
          type: 'bidirectional',
          referencedImageId: 'dicomfile:3',
          worldPoints: [
            [0, 0, 0],
            [10, 0, 0],
            [5, -2, 0],
            [5, 2, 0],
          ],
        },
      ],
      references,
    );

    expect(packet.schema_version).toBe('3.0.0');
    expect(packet.measurements[0]).toMatchObject({
      tracking_id: 'bidirectional:annotation-2',
      type: 'bidirectional',
      source: {
        series_id: 'series_0123456789abcdef0123',
        instance_id: 'instance_0123456789abcdef0123',
      },
      result: {
        long_axis: 10,
        short_axis: 4,
        product: 40,
        unit: 'mm',
        product_unit: 'mm2',
      },
    });
    expect(readMeasurementEvidencePacket(packet)).toEqual({ packet, errors: [] });
  });

  it('rejects imported values that disagree with patient-space geometry', () => {
    const packet = {
      schema_version: '2.0.0',
      created_at: '2026-08-28T00:00:00Z',
      review_status: 'unreviewed',
      measurements: [
        {
          tracking_id: 'bidirectional:inconsistent',
          type: 'bidirectional',
          review_status: 'unreviewed',
          source: {
            series_id: '0123456789abcdef',
            instance_id: 'fedcba9876543210',
          },
          geometry: {
            coordinate_system: 'DICOM patient LPS',
            world_points: [
              [0, 0, 0],
              [10, 0, 0],
              [5, -2, 0],
              [5, 2, 0],
            ],
          },
          result: {
            long_axis: 99,
            short_axis: 4,
            product: 396,
            unit: 'mm',
            product_unit: 'mm2',
          },
          method: {
            name: 'manual_perpendicular_bidirectional',
            implementation: 'Cornerstone3D BidirectionalTool',
          },
          limitations: ['Manual and unreviewed.'],
        },
      ],
      limitations: ['Not a response category.'],
    };

    const parsed = readMeasurementEvidencePacket(packet);

    expect(parsed.packet).toBeUndefined();
    expect(parsed.errors.join(' ')).toContain('disagrees with its geometry');
  });

  it('exports an elliptical ROI with patient-space axes and area', () => {
    const references = new Map<string, ImageSourceReference>([
      [
        'dicomfile:4',
        {
          seriesId: 'series_0123456789abcdef0123',
          instanceId: 'instance_0123456789abcdef0123',
          spacingTrusted: true,
        },
      ],
    ]);
    const packet = buildMeasurementEvidencePacket(
      [
        {
          annotationId: 'annotation-3',
          type: 'elliptical_roi',
          referencedImageId: 'dicomfile:4',
          worldPoints: [
            [0, -2, 0],
            [0, 2, 0],
            [-5, 0, 0],
            [5, 0, 0],
          ],
        },
      ],
      references,
      '2026-08-28T00:00:00.000Z',
    );

    expect(packet.schema_version).toBe('3.0.0');
    expect(packet.measurements[0]).toMatchObject({
      tracking_id: 'elliptical_roi:annotation-3',
      type: 'elliptical_roi',
      result: {
        major_axis: 10,
        minor_axis: 4,
        area: Math.PI * 10,
        unit: 'mm',
        area_unit: 'mm2',
      },
      method: {
        name: 'manual_elliptical_roi',
        implementation: 'Cornerstone3D EllipticalROITool',
      },
    });
    expect(packet.measurements[0].limitations.join(' ')).toContain('not a segmentation');
    expect(readMeasurementEvidencePacket(packet)).toEqual({ packet, errors: [] });
  });

  it('rejects an ROI area that disagrees with its geometry', () => {
    const references = new Map<string, ImageSourceReference>([
      [
        'dicomfile:5',
        {
          seriesId: '0123456789abcdef',
          instanceId: 'fedcba9876543210',
          spacingTrusted: true,
        },
      ],
    ]);
    const packet = buildMeasurementEvidencePacket(
      [
        {
          type: 'elliptical_roi',
          referencedImageId: 'dicomfile:5',
          worldPoints: [
            [0, -2, 0],
            [0, 2, 0],
            [-5, 0, 0],
            [5, 0, 0],
          ],
        },
      ],
      references,
    );
    const roi = packet.measurements[0];
    if (roi.type !== 'elliptical_roi') throw new Error('Expected an elliptical ROI fixture.');
    roi.result.area = 999;

    const parsed = readMeasurementEvidencePacket(packet);

    expect(parsed.packet).toBeUndefined();
    expect(parsed.errors.join(' ')).toContain('disagrees with its geometry');
  });
});
