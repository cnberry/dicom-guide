import type { ViewerTool } from './cornerstone';
import type { DicomSeries, LinkStrategy } from './dicom';

export const VIEWER_STATE_ENDPOINT = '/v1/viewer-state';
export const VIEWER_STATE_MEDIA_TYPE = 'application/vnd.scanview.viewer-state+json';
export const VIEWER_STATE_HEARTBEAT_MS = 10_000;

const publisherPattern = /^publisher_[0-9a-f]{32}$/;
const seriesPattern = /^series_[0-9a-f]{20}$/;
const instancePattern = /^instance_[0-9a-f]{20}$/;

export type ViewerStateTarget = {
  series_id: string;
  instance_id: string;
  stack_position: number;
  stack_count: number;
};

export type ViewerStatePublication = {
  schema_version: '1.0.0';
  sharing: true;
  publisher_id: string;
  review_status: 'unreviewed';
  active_tool: ViewerTool;
  slice_link: 'unpaired' | 'independent' | 'patient_position' | 'approximate_index';
  baseline: ViewerStateTarget | null;
  followup: ViewerStateTarget | null;
  mpr_series_id: string | null;
  measurement_count: number;
  comparison_draft_present: boolean;
  privacy: {
    local_only: true;
    contains_pixels: false;
    contains_direct_identifiers: false;
    persisted: false;
  };
};

type BuildViewerStateInput = {
  publisherId: string;
  activeTool: ViewerTool;
  synchronized: boolean;
  linkStrategy: LinkStrategy;
  baseline?: DicomSeries;
  baselineIndex: number;
  followup?: DicomSeries;
  followupIndex: number;
  mprSeries?: DicomSeries;
  measurementCount: number;
  comparisonDraftPresent: boolean;
};

const targetFor = (series: DicomSeries | undefined, index: number): ViewerStateTarget | null => {
  if (!series) return null;
  if (
    series.sourceKind !== 'loopback-service' ||
    !seriesPattern.test(series.id) ||
    !Number.isInteger(index) ||
    index < 0 ||
    index >= series.instances.length
  ) {
    throw new Error('Viewer state requires an exact local-service source instance.');
  }
  const instance = series.instances[index];
  if (!instancePattern.test(instance.instanceId)) {
    throw new Error('Viewer state requires an exact opaque local instance ID.');
  }
  return {
    series_id: series.id,
    instance_id: instance.instanceId,
    stack_position: index + 1,
    stack_count: series.instances.length,
  };
};

export const buildViewerStatePublication = (
  input: BuildViewerStateInput,
): ViewerStatePublication | undefined => {
  if (!publisherPattern.test(input.publisherId)) return undefined;
  if (
    !Number.isInteger(input.measurementCount) ||
    input.measurementCount < 0 ||
    input.measurementCount > 10_000
  ) {
    return undefined;
  }
  try {
    const baseline = targetFor(input.baseline, input.baselineIndex);
    if (!baseline) return undefined;
    const followup = targetFor(input.followup, input.followupIndex);
    let mprSeriesId: string | null = null;
    if (input.mprSeries) {
      if (
        input.mprSeries.sourceKind !== 'loopback-service' ||
        !seriesPattern.test(input.mprSeries.id)
      ) {
        return undefined;
      }
      mprSeriesId = input.mprSeries.id;
    }
    const sliceLink = !followup
      ? 'unpaired'
      : !input.synchronized
        ? 'independent'
        : input.linkStrategy === 'patient-position'
          ? 'patient_position'
          : 'approximate_index';
    return {
      schema_version: '1.0.0',
      sharing: true,
      publisher_id: input.publisherId,
      review_status: 'unreviewed',
      active_tool: input.activeTool,
      slice_link: sliceLink,
      baseline,
      followup,
      mpr_series_id: mprSeriesId,
      measurement_count: input.measurementCount,
      comparison_draft_present: input.comparisonDraftPresent,
      privacy: {
        local_only: true,
        contains_pixels: false,
        contains_direct_identifiers: false,
        persisted: false,
      },
    };
  } catch {
    return undefined;
  }
};

const postViewerState = async (body: object, keepalive = false): Promise<Record<string, unknown>> => {
  const response = await fetch(VIEWER_STATE_ENDPOINT, {
    method: 'POST',
    cache: 'no-store',
    credentials: 'same-origin',
    keepalive,
    headers: {
      Accept: 'application/json',
      'Content-Type': VIEWER_STATE_MEDIA_TYPE,
    },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(`Local viewer-state bridge rejected the update (${response.status}).`);
  }
  const value = (await response.json()) as Record<string, unknown>;
  if (value.accepted !== true) {
    throw new Error('Local viewer-state bridge returned an invalid acknowledgement.');
  }
  return value;
};

export const publishViewerState = async (publication: ViewerStatePublication): Promise<void> => {
  const response = await postViewerState(publication);
  if (response.sharing !== true) {
    throw new Error('Local viewer-state bridge did not confirm sharing.');
  }
};

export const clearViewerState = async (
  publisherId: string,
  keepalive = false,
): Promise<void> => {
  if (!publisherPattern.test(publisherId)) return;
  const response = await postViewerState(
    { schema_version: '1.0.0', sharing: false, publisher_id: publisherId },
    keepalive,
  );
  if (response.sharing !== false) {
    throw new Error('Local viewer-state bridge did not confirm cleanup.');
  }
};

export const createViewerStatePublisherId = (): string => {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return `publisher_${Array.from(bytes, (value) => value.toString(16).padStart(2, '0')).join('')}`;
};
