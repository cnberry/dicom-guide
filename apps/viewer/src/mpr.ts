export type MprPatientPoint = [number, number, number];

export const mprCrosshairConfiguration = {
  centerPoint: { enabled: true, color: 'rgba(255, 255, 255, 0.9)', size: 3 },
  getReferenceLineColor: (viewportId: string): string =>
    viewportId.endsWith('-axial')
      ? 'rgb(255, 196, 72)'
      : viewportId.endsWith('-coronal')
        ? 'rgb(91, 214, 142)'
        : 'rgb(90, 166, 255)',
  getReferenceLineControllable: (): boolean => true,
  // Cornerstone requires this capability for point jumps and line translation.
  // Minimal mode below suppresses rotation handles and rotation hit-testing.
  getReferenceLineDraggableRotatable: (): boolean => true,
  getReferenceLineSlabThicknessControlsOn: (): boolean => false,
  minimal: { enabled: true, lineLengthInPx: 48 },
} as const;

export const formatMprPatientPoint = (point: MprPatientPoint): string =>
  `${point.map((value) => value.toFixed(1)).join(', ')} mm`;
