import { describe, expect, it } from 'vitest';
import { formatMprPatientPoint, mprCrosshairConfiguration } from './mpr';

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
});
