import { describe, expect, it } from 'vitest';
import {
  enforceRegistrationQaCompositeCoverage,
  registrationQaCoverageBoundaryRgba,
  registrationQaRegisteredRgba,
} from './components/RegistrationQaWorkspace';

describe('pending registration QA sampling-support rendering', () => {
  it('mattes unsupported registered-moving pixels without exposing their values', () => {
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

    expect(Array.from(registrationQaRegisteredRgba(slice, coverage))).toEqual([
      25, 25, 25, 255,
      9, 18, 16, 255,
      175, 175, 175, 255,
      9, 18, 16, 255,
    ]);
    expect(() =>
      registrationQaRegisteredRgba(slice, {
        ...coverage,
        pixels: new Uint8Array([1, 2, 1, 0]),
      }),
    ).toThrow(/non-binary/i);
    expect(() =>
      registrationQaRegisteredRgba(slice, { ...coverage, width: 1 }),
    ).toThrow(/does not match/i);
    expect(() => registrationQaRegisteredRgba(slice, undefined)).toThrow(/requires/i);
  });

  it('renders a technical boundary and visually distinct excluded region', () => {
    const fixed = {
      width: 3,
      height: 3,
      pixels: new Uint8ClampedArray([10, 20, 30, 40, 50, 60, 70, 80, 90]),
    };
    const coverage = {
      width: 3,
      height: 3,
      pixels: new Uint8Array([0, 0, 0, 0, 1, 0, 0, 0, 0]),
    };
    const rgba = registrationQaCoverageBoundaryRgba(fixed, coverage);

    expect(Array.from(rgba.slice(0, 4))).toEqual([58, 31, 7, 255]);
    expect(Array.from(rgba.slice(4 * 4, 5 * 4))).toEqual([255, 176, 32, 255]);

    const fullCoverage = {
      width: 3,
      height: 3,
      pixels: new Uint8Array(9).fill(1),
    };
    const fullRgba = registrationQaCoverageBoundaryRgba(fixed, fullCoverage);
    expect(Array.from(fullRgba.slice(4 * 4, 5 * 4))).toEqual([36, 36, 36, 255]);
    expect(Array.from(fullRgba.slice(0, 4))).toEqual([255, 176, 32, 255]);
  });

  it('replaces every unsupported composite pixel with fixed-reference grayscale', () => {
    const fixed = {
      width: 2,
      height: 1,
      pixels: new Uint8ClampedArray([20, 80]),
    };
    const coverage = {
      width: 2,
      height: 1,
      pixels: new Uint8Array([1, 0]),
    };
    const composite = new Uint8ClampedArray([
      1, 2, 3, 255,
      200, 201, 202, 255,
    ]);

    expect(
      Array.from(enforceRegistrationQaCompositeCoverage(composite, fixed, coverage)),
    ).toEqual([
      1, 2, 3, 255,
      80, 80, 80, 255,
    ]);
    expect(Array.from(composite)).toEqual([
      1, 2, 3, 255,
      200, 201, 202, 255,
    ]);
  });
});
