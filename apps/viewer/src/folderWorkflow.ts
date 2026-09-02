import { assessMprEligibility, type DicomSeries } from './dicom';

export type FolderLoadState =
  | { phase: 'collecting'; fileCount: number; restoring: boolean }
  | { phase: 'reading'; processed: number; total: number; restoring: boolean };

export const defaultFolderSeries = (items: DicomSeries[]): DicomSeries | undefined =>
  [...items]
    .filter((item) => assessMprEligibility(item).eligible)
    .sort((left, right) => right.instances.length - left.instances.length)[0] ?? items[0];

export const folderViewSelection = (
  items: DicomSeries[],
  preserveMpr: boolean,
): { series?: DicomSeries; instanceIndex: number; mprSeriesId?: string } => {
  const series = defaultFolderSeries(items);
  return {
    series,
    instanceIndex: Math.floor((series?.instances.length ?? 1) / 2),
    mprSeriesId:
      preserveMpr && assessMprEligibility(series).eligible ? series?.id : undefined,
  };
};

export const folderLoadMessage = (state: FolderLoadState): string => {
  if (state.phase === 'collecting') {
    return state.fileCount
      ? `Preparing ${state.fileCount.toLocaleString()} local files…`
      : state.restoring
        ? 'Restoring the current local folder…'
        : 'Opening the local folder…';
  }
  return `Reading ${state.processed.toLocaleString()} of ${state.total.toLocaleString()} local files…`;
};
