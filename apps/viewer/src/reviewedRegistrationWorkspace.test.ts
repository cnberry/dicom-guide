import { describe, expect, it } from 'vitest';
import {
  reviewedSliceRgba,
  updateReviewedWindow,
} from './components/ReviewedRegistrationWorkspace';

describe('reviewed registration display controls', () => {
  it('keeps percentile windows ordered when either boundary is dragged across the other', () => {
    expect(updateReviewedWindow([1, 99], 'lower', 100)).toEqual([98, 99]);
    expect(updateReviewedWindow([1, 99], 'upper', 0)).toEqual([1, 2]);
    expect(updateReviewedWindow([25, 75], 'lower', 40)).toEqual([40, 75]);
    expect(updateReviewedWindow([25, 75], 'upper', 60)).toEqual([25, 60]);
  });

  it('clamps non-finite and out-of-range window input without reversing bounds', () => {
    expect(updateReviewedWindow([0, 100], 'lower', Number.NaN)).toEqual([0, 100]);
    expect(updateReviewedWindow([0, 100], 'upper', Number.POSITIVE_INFINITY)).toEqual([
      0,
      100,
    ]);
    expect(updateReviewedWindow([20, 80], 'lower', -10)).toEqual([0, 80]);
    expect(updateReviewedWindow([20, 80], 'upper', 110)).toEqual([20, 100]);
  });

  it('mattes every unsupported registered pixel instead of rendering its value', () => {
    const slice = {
      width: 2,
      height: 2,
      pixels: new Uint8ClampedArray([25, 100, 175, 250]),
    };
    const coverage = {
      width: 2,
      height: 2,
      pixels: new Uint8Array([1, 0, 1, 0]),
    };
    expect(Array.from(reviewedSliceRgba(slice, coverage))).toEqual([
      25, 25, 25, 255,
      9, 18, 16, 255,
      175, 175, 175, 255,
      9, 18, 16, 255,
    ]);
    expect(() =>
      reviewedSliceRgba(slice, { ...coverage, pixels: new Uint8Array([1, 2, 1, 0]) }),
    ).toThrow(/non-binary/i);
    expect(() =>
      reviewedSliceRgba(slice, { ...coverage, width: 1 }),
    ).toThrow(/does not match/i);
    expect(() => reviewedSliceRgba(slice, undefined, true)).toThrow(/requires/i);
  });
});
