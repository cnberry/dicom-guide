export type MprPatientPoint = [number, number, number];
export type MprCanvasPoint = [number, number];

export type MprCropFit = {
  center: MprCanvasPoint;
  parallelScale: number;
};

export const calculateMprCropFit = ({
  start,
  end,
  viewportWidth,
  viewportHeight,
  parallelScale,
  padding = 0.94,
}: {
  start: MprCanvasPoint;
  end: MprCanvasPoint;
  viewportWidth: number;
  viewportHeight: number;
  parallelScale: number;
  padding?: number;
}): MprCropFit | undefined => {
  if (
    ![...start, ...end, viewportWidth, viewportHeight, parallelScale, padding].every(
      Number.isFinite,
    ) ||
    viewportWidth <= 0 ||
    viewportHeight <= 0 ||
    parallelScale <= 0 ||
    padding <= 0 ||
    padding > 1
  ) {
    return undefined;
  }
  const width = Math.abs(end[0] - start[0]);
  const height = Math.abs(end[1] - start[1]);
  if (width < 12 || height < 12) return undefined;
  const scaleFactor = Math.min(viewportWidth / width, viewportHeight / height) * padding;
  if (!Number.isFinite(scaleFactor) || scaleFactor <= 1) return undefined;
  return {
    center: [(start[0] + end[0]) / 2, (start[1] + end[1]) / 2],
    parallelScale: parallelScale / Math.min(scaleFactor, 50),
  };
};

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
