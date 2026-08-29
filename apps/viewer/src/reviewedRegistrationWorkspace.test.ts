import { describe, expect, it } from 'vitest';
import { updateReviewedWindow } from './components/ReviewedRegistrationWorkspace';

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
});
