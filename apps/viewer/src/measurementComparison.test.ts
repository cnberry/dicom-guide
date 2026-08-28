import { describe, expect, it } from 'vitest';
import { assessMeasurementPairingContext, buildMeasurementComparisonDraft } from './measurementComparison';
import type { DicomSeries } from './dicom';
import type { MeasurementEvidence } from './measurements';

const measurement = (
  overrides: Partial<MeasurementEvidence> & Pick<MeasurementEvidence, 'type' | 'result'>,
): MeasurementEvidence =>
  ({
    tracking_id: 'length:baseline',
    review_status: 'unreviewed',
    source: { series_id: '0123456789abcdef', instance_id: 'fedcba9876543210' },
    geometry: {
      coordinate_system: 'DICOM patient LPS',
      world_points: [[0, 0, 0], [10, 0, 0]],
    },
    method: {
      name: 'manual_two_point_length',
      implementation: 'Cornerstone3D LengthTool',
    },
    limitations: ['Manual and unreviewed.'],
    ...overrides,
  }) as MeasurementEvidence;

describe('explicit measurement comparison draft', () => {
  const series = (id: string, date: string): DicomSeries => ({
    id,
    studyId: `study-${id}`,
    patientContextId: 'patient-a',
    acquisitionDate: date,
    modality: 'MR',
    description: 'T1 POST',
    imageType: ['ORIGINAL', 'PRIMARY'],
    sourceKind: 'loopback-service',
    geometry: {},
    instances: [],
  });

  it('requires strictly chronological compatible series context', () => {
    const earlier = series('baseline', '20260101');
    const later = series('followup', '20260301');
    expect(assessMeasurementPairingContext(earlier, later, 'compatible').ready).toBe(true);
    expect(assessMeasurementPairingContext(later, earlier, 'compatible')).toMatchObject({
      ready: false,
      reason: expect.stringContaining('earlier acquisition date'),
    });
    expect(assessMeasurementPairingContext(earlier, later, 'incompatible').ready).toBe(false);
  });

  it('computes transparent local deltas without a response interpretation', () => {
    const baseline = measurement({ type: 'length', result: { value: 10, unit: 'mm' } });
    const followup = measurement({
      tracking_id: 'length:followup',
      type: 'length',
      source: { series_id: '1111111111111111', instance_id: '2222222222222222' },
      result: { value: 8, unit: 'mm' },
    });

    const draft = buildMeasurementComparisonDraft(
      baseline,
      followup,
      '  Target   lesion A  ',
      '2026-08-28T12:00:00.000Z',
    );

    expect(draft.pairing.lesion_label).toBe('Target lesion A');
    expect(draft.computed_results).toEqual([
      expect.objectContaining({
        metric: 'length',
        baseline: 10,
        followup: 8,
        absolute_change: -2,
        percent_change: -20,
        unit: 'mm',
        review_status: 'unreviewed',
      }),
    ]);
    expect(draft.candidate_interpretations).toEqual([]);
    expect(draft.limitations.join(' ')).toContain('not a treatment-response category');
  });

  it('rejects type mismatch, same-series input, unknown units, and missing labels', () => {
    const baseline = measurement({ type: 'length', result: { value: 10, unit: 'mm' } });
    const sameSeries = measurement({
      tracking_id: 'length:other',
      type: 'length',
      result: { value: 8, unit: 'mm' },
    });
    expect(() => buildMeasurementComparisonDraft(baseline, sameSeries, 'Lesion A')).toThrow(
      'distinct source series',
    );

    const otherSeries = {
      ...sameSeries,
      source: { series_id: '1111111111111111', instance_id: '2222222222222222' },
    } as MeasurementEvidence;
    expect(() => buildMeasurementComparisonDraft(baseline, otherSeries, '   ')).toThrow(
      'working lesion label',
    );
    expect(() =>
      buildMeasurementComparisonDraft(
        baseline,
        { ...otherSeries, result: { value: undefined, unit: 'unknown' } } as MeasurementEvidence,
        'Lesion A',
      ),
    ).toThrow('trusted physical');
  });
});
