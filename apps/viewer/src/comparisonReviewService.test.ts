import { afterEach, describe, expect, it, vi } from 'vitest';
import { unzipSync } from 'fflate';
import {
  buildComparisonReviewTransport,
  COMPARISON_REVIEW_ENDPOINT,
  COMPARISON_REVIEW_INPUT_MEDIA_TYPE,
  requestComparisonReview,
} from './comparisonReviewService';
import type { MeasurementComparisonDraft } from './measurementComparison';

afterEach(() => vi.unstubAllGlobals());

const comparison: MeasurementComparisonDraft = {
  schema_version: '1.0.0',
  created_at: '2026-08-28T01:00:00Z',
  review_status: 'unreviewed',
  pairing: {
    method: 'explicit_tracking_id_selection',
    lesion_label: 'Target lesion A',
    baseline_measurement_id: 'length:baseline',
    followup_measurement_id: 'length:followup',
  },
  observations: [
    {
      timepoint: 'baseline',
      measurement_type: 'length',
      source: { series_id: '0123456789abcdef', instance_id: 'fedcba9876543210' },
      review_status: 'unreviewed',
    },
    {
      timepoint: 'followup',
      measurement_type: 'length',
      source: { series_id: '1123456789abcdef', instance_id: '0011223344556677' },
      review_status: 'unreviewed',
    },
  ],
  computed_results: [
    {
      metric: 'length',
      baseline: 10,
      followup: 8,
      absolute_change: -2,
      percent_change: -20,
      unit: 'mm',
      source_measurement_ids: ['length:baseline', 'length:followup'],
      review_status: 'unreviewed',
    },
  ],
  candidate_interpretations: [],
  limitations: ['Synthetic arithmetic only.'],
  missing_context: ['Clinician review.'],
  questions_for_clinician: ['Is this the same lesion?'],
};

describe('local comparison-review service', () => {
  it('wraps exactly two key images and the current numeric comparison', () => {
    const baseline = new Uint8Array([1, 2, 3]);
    const followup = new Uint8Array([4, 5]);

    const files = unzipSync(buildComparisonReviewTransport(baseline, followup, comparison));

    expect(Object.keys(files).sort()).toEqual([
      'baseline.zip',
      'comparison.json',
      'followup.zip',
    ]);
    expect(files['baseline.zip']).toEqual(baseline);
    expect(files['followup.zip']).toEqual(followup);
    expect(JSON.parse(new TextDecoder().decode(files['comparison.json']))).toEqual(comparison);
  });

  it('posts only to the same-origin relative endpoint and accepts a local ZIP response', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(new Uint8Array([9, 8, 7]), {
        status: 200,
        headers: {
          'Content-Type': 'application/zip',
          'Content-Disposition':
            'attachment; filename="dicom-guide-comparison-review-test.zip"',
        },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const result = await requestComparisonReview(
      new Uint8Array([1]),
      new Uint8Array([2]),
      comparison,
    );

    expect(COMPARISON_REVIEW_ENDPOINT).toBe('/v1/comparison-reviews');
    expect(result).toEqual({
      filename: 'dicom-guide-comparison-review-test.zip',
      bytes: new Uint8Array([9, 8, 7]),
    });
    const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/v1/comparison-reviews');
    expect(options).toMatchObject({
      method: 'POST',
      cache: 'no-store',
      credentials: 'same-origin',
      headers: {
        Accept: 'application/zip',
        'Content-Type': COMPARISON_REVIEW_INPUT_MEDIA_TYPE,
      },
    });
    expect(Object.keys(unzipSync(new Uint8Array(options.body as ArrayBuffer))).sort()).toEqual([
      'baseline.zip',
      'comparison.json',
      'followup.zip',
    ]);
  });

  it('surfaces exact visual/numeric join failures from the local assembler', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: 'invalid_comparison_review_input',
            detail: 'comparison baseline measurement is not on the visit key image',
          }),
          { status: 422, headers: { 'Content-Type': 'application/json' } },
        ),
      ),
    );

    await expect(
      requestComparisonReview(new Uint8Array([1]), new Uint8Array([2]), comparison),
    ).rejects.toThrow('not on the visit key image');
  });
});
