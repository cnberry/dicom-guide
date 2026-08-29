export type MprPatientPoint = [number, number, number];

export const reorderDenseMaskSlices = ({
  mask,
  rows,
  columns,
  sourceOrderedInstanceIds,
  volumeOrderedInstanceIds,
}: {
  mask: Uint8Array;
  rows: number;
  columns: number;
  sourceOrderedInstanceIds: string[];
  volumeOrderedInstanceIds: string[];
}): Uint8Array => {
  const sliceVoxels = rows * columns;
  if (
    !Number.isSafeInteger(rows) ||
    !Number.isSafeInteger(columns) ||
    rows < 1 ||
    columns < 1 ||
    !Number.isSafeInteger(sliceVoxels) ||
    sourceOrderedInstanceIds.length < 1 ||
    sourceOrderedInstanceIds.length !== volumeOrderedInstanceIds.length ||
    new Set(sourceOrderedInstanceIds).size !== sourceOrderedInstanceIds.length ||
    new Set(volumeOrderedInstanceIds).size !== volumeOrderedInstanceIds.length ||
    mask.length !== sliceVoxels * sourceOrderedInstanceIds.length
  ) {
    throw new Error('The read-only mask source order is invalid.');
  }
  const sourceIndexes = new Map(
    sourceOrderedInstanceIds.map((instanceId, index) => [instanceId, index]),
  );
  if (volumeOrderedInstanceIds.some((instanceId) => !sourceIndexes.has(instanceId))) {
    throw new Error('The read-only mask does not match the loaded source volume order.');
  }
  const aligned = new Uint8Array(mask.length);
  volumeOrderedInstanceIds.forEach((instanceId, volumeIndex) => {
    const sourceIndex = sourceIndexes.get(instanceId);
    if (sourceIndex === undefined) {
      throw new Error('The read-only mask source slice is unavailable.');
    }
    aligned.set(
      mask.subarray(sourceIndex * sliceVoxels, (sourceIndex + 1) * sliceVoxels),
      volumeIndex * sliceVoxels,
    );
  });
  return aligned;
};

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
