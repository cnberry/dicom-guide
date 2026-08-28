import { strToU8, zipSync } from 'fflate';
import { downloadArchive } from './keyImages';
import type { MeasurementComparisonDraft } from './measurementComparison';

export const COMPARISON_REVIEW_ENDPOINT = '/v1/comparison-reviews';
export const COMPARISON_REVIEW_INPUT_MEDIA_TYPE =
  'application/vnd.scanview.comparison-review-input+zip';

export type ComparisonReviewArchive = {
  filename: string;
  bytes: Uint8Array;
};

export const buildComparisonReviewTransport = (
  baseline: Uint8Array,
  followup: Uint8Array,
  comparison: MeasurementComparisonDraft,
): Uint8Array =>
  zipSync(
    {
      'baseline.zip': [baseline, { level: 0 }],
      'followup.zip': [followup, { level: 0 }],
      'comparison.json': [strToU8(`${JSON.stringify(comparison, null, 2)}\n`), { level: 0 }],
    },
    { level: 0 },
  );

const responseFilename = (header: string | null): string => {
  const candidate = header?.match(/filename="?([A-Za-z0-9._-]+)"?/i)?.[1];
  return candidate?.endsWith('.zip')
    ? candidate
    : `scanview-comparison-review-${new Date().toISOString().slice(0, 10)}.zip`;
};

export const requestComparisonReview = async (
  baseline: Uint8Array,
  followup: Uint8Array,
  comparison: MeasurementComparisonDraft,
): Promise<ComparisonReviewArchive> => {
  const transport = buildComparisonReviewTransport(baseline, followup, comparison);
  const body = transport.buffer.slice(
    transport.byteOffset,
    transport.byteOffset + transport.byteLength,
  ) as ArrayBuffer;
  const response = await fetch(COMPARISON_REVIEW_ENDPOINT, {
    method: 'POST',
    cache: 'no-store',
    credentials: 'same-origin',
    headers: {
      Accept: 'application/zip',
      'Content-Type': COMPARISON_REVIEW_INPUT_MEDIA_TYPE,
    },
    body,
  });
  if (!response.ok) {
    let detail = '';
    try {
      const value = (await response.json()) as { detail?: unknown };
      if (typeof value.detail === 'string') detail = value.detail;
    } catch {
      // The status is sufficient when the local response is not JSON.
    }
    throw new Error(
      detail || `The local comparison-review assembler rejected the evidence (${response.status}).`,
    );
  }
  if (response.headers.get('Content-Type')?.split(';', 1)[0] !== 'application/zip') {
    throw new Error('The local comparison-review assembler returned an unsupported file type.');
  }
  return {
    filename: responseFilename(response.headers.get('Content-Disposition')),
    bytes: new Uint8Array(await response.arrayBuffer()),
  };
};

export const saveComparisonReview = async (
  baseline: Uint8Array,
  followup: Uint8Array,
  comparison: MeasurementComparisonDraft,
): Promise<ComparisonReviewArchive> => {
  const result = await requestComparisonReview(baseline, followup, comparison);
  downloadArchive(result.bytes, result.filename);
  return result;
};
