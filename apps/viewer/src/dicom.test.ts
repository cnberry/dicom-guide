import { describe, expect, it } from 'vitest';
import {
  assessCompatibility,
  formatDicomDate,
  mapNormalizedIndex,
  type DicomSeries,
} from './dicom';

const series = (overrides: Partial<DicomSeries> = {}): DicomSeries => ({
  id: 'series-a',
  studyId: 'study-a',
  acquisitionDate: '20260101',
  modality: 'MR',
  description: 'T1 POST CONTRAST',
  imageType: ['ORIGINAL', 'PRIMARY'],
  geometry: { rows: 512, columns: 512 },
  frameOfReferenceId: 'frame-a',
  instances: [],
  ...overrides,
});

describe('comparison safety', () => {
  it('never treats CT and MR as intensity-compatible', () => {
    const result = assessCompatibility(series(), series({ modality: 'CT' }));
    expect(result.level).toBe('incompatible');
    expect(result.reasons.join(' ')).toContain('not directly comparable');
  });

  it('warns when a spatial registration is needed', () => {
    const result = assessCompatibility(series(), series({ id: 'series-b', frameOfReferenceId: 'frame-b' }));
    expect(result.reasons.join(' ')).toContain('registration');
  });
});

describe('display formatting', () => {
  it('formats DICOM dates without guessing malformed values', () => {
    expect(formatDicomDate('20260828')).toBe('2026-08-28');
    expect(formatDicomDate('unknown')).toBe('unknown');
  });

  it('maps normalized stack position for linked native views', () => {
    expect(mapNormalizedIndex(0, 5, 11)).toBe(0);
    expect(mapNormalizedIndex(2, 5, 11)).toBe(5);
    expect(mapNormalizedIndex(4, 5, 11)).toBe(10);
  });
});
