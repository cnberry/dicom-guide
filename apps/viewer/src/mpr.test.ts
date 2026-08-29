import { describe, expect, it } from 'vitest';
import {
  calculateMprCropFit,
  formatMprPatientPoint,
  mprCrosshairConfiguration,
  reorderDenseMaskSlices,
} from './mpr';

describe('MPR crosshair contract', () => {
  it('uses the minimal point-navigation mode without slab-thickness controls', () => {
    expect(mprCrosshairConfiguration.minimal).toEqual({ enabled: true, lineLengthInPx: 48 });
    expect(mprCrosshairConfiguration.getReferenceLineSlabThicknessControlsOn()).toBe(false);
  });

  it('keeps orientation colors stable across generated viewport identifiers', () => {
    expect(mprCrosshairConfiguration.getReferenceLineColor('engine-axial')).toBe(
      'rgb(255, 196, 72)',
    );
    expect(mprCrosshairConfiguration.getReferenceLineColor('engine-coronal')).toBe(
      'rgb(91, 214, 142)',
    );
    expect(mprCrosshairConfiguration.getReferenceLineColor('engine-sagittal')).toBe(
      'rgb(90, 166, 255)',
    );
  });

  it('formats a DICOM LPS patient point without silently changing units', () => {
    expect(formatMprPatientPoint([12.04, -3.55, 100])).toBe('12.0, -3.5, 100.0 mm');
  });

  it('fits a valid display crop to the viewport while preserving aspect ratio', () => {
    expect(
      calculateMprCropFit({
        start: [100, 200],
        end: [300, 500],
        viewportWidth: 800,
        viewportHeight: 600,
        parallelScale: 120,
      }),
    ).toEqual({ center: [200, 350], parallelScale: 60 / 0.94 });
  });

  it('refuses tiny, invalid, and non-zooming crop selections', () => {
    expect(
      calculateMprCropFit({
        start: [10, 10],
        end: [18, 18],
        viewportWidth: 800,
        viewportHeight: 600,
        parallelScale: 120,
      }),
    ).toBeUndefined();
    expect(
      calculateMprCropFit({
        start: [0, 0],
        end: [800, 600],
        viewportWidth: 800,
        viewportHeight: 600,
        parallelScale: 120,
      }),
    ).toBeUndefined();
    expect(
      calculateMprCropFit({
        start: [0, 0],
        end: [100, 100],
        viewportWidth: 0,
        viewportHeight: 600,
        parallelScale: 120,
      }),
    ).toBeUndefined();
  });

  it('aligns dense mask slabs to the volume image order and fails on drift', () => {
    const aligned = reorderDenseMaskSlices({
      mask: new Uint8Array([1, 1, 2, 2, 3, 3]),
      rows: 1,
      columns: 2,
      sourceOrderedInstanceIds: ['slice-a', 'slice-b', 'slice-c'],
      volumeOrderedInstanceIds: ['slice-c', 'slice-b', 'slice-a'],
    });
    expect(Array.from(aligned)).toEqual([3, 3, 2, 2, 1, 1]);
    expect(() => reorderDenseMaskSlices({
      mask: new Uint8Array(6),
      rows: 1,
      columns: 2,
      sourceOrderedInstanceIds: ['slice-a', 'slice-b', 'slice-c'],
      volumeOrderedInstanceIds: ['slice-c', 'slice-b', 'slice-x'],
    })).toThrow(/loaded source volume order/i);
  });
});
