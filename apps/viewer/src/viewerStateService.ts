import type { ViewerTool } from './cornerstone';
import type { DicomSeries, LinkStrategy } from './dicom';

export const VIEWER_STATE_ENDPOINT = '/v1/viewer-state';
export const VIEWER_STATE_MEDIA_TYPE = 'application/vnd.dicom-guide.viewer-state+json';
export const VIEWER_STATE_HEARTBEAT_MS = 10_000;

const publisherPattern = /^publisher_[0-9a-f]{32}$/;
const seriesPattern = /^series_[0-9a-f]{20}$/;
const instancePattern = /^instance_[0-9a-f]{20}$/;
const sha256Pattern = /^[0-9a-f]{64}$/;

export type ViewerStateTarget = {
  series_id: string;
  instance_id: string;
  stack_position: number;
  stack_count: number;
};

export type ViewerStatePublication = {
  schema_version: '2.0.0';
  sharing: true;
  publisher_id: string;
  workspace_mode: 'consult_prep' | 'longitudinal_review';
  view_roles:
    | { view_a: 'reference'; view_b: 'reference' }
    | { view_a: 'baseline'; view_b: 'followup' };
  review_status: 'unreviewed';
  active_tool: ViewerTool;
  slice_link: 'unpaired' | 'independent' | 'patient_position' | 'approximate_index';
  view_a: ViewerStateTarget | null;
  view_b: ViewerStateTarget | null;
  mpr_series_id: string | null;
  source_segmentation_display: {
    segmentation_id: string;
    segment_number: number;
    referenced_series_id: string;
    catalog_content_sha256: string;
    display_status: 'read_only_native_grid';
    mask_pixels_shared: false;
    creator_identity_authenticated: false;
    segment_accuracy_verified: false;
    source_segment_clinical_meaning: 'not_assessed';
    dicom_guide_interpretation_added: false;
  } | null;
  measurement_count: number;
  comparison_draft_present: boolean;
  permissions: {
    agent_navigation_from_state_authorized: false;
    source_mutation_authorized: false;
    source_segmentation_mask_read_authorized: false;
    source_segmentation_interpretation_authorized: false;
    diagnosis_authorized: false;
    response_classification_authorized: false;
    clinical_conclusion_authorized: false;
  };
  privacy: {
    local_only: true;
    contains_pixels: false;
    contains_direct_identifiers: false;
    contains_source_text: false;
    contains_measurement_values: false;
    contains_segmentation_mask: false;
    contains_opaque_source_references: true;
    contains_sensitive_segmentation_reference: boolean;
    contains_hashes: boolean;
    deidentified: false;
    persisted: false;
  };
};

type BuildViewerStateInput = {
  publisherId: string;
  workspaceMode: 'consult_prep' | 'longitudinal_review';
  activeTool: ViewerTool;
  synchronized: boolean;
  linkStrategy: LinkStrategy;
  viewA?: DicomSeries;
  viewAIndex: number;
  viewB?: DicomSeries;
  viewBIndex: number;
  mprSeries?: DicomSeries;
  sourceSegmentation?: {
    segmentationId: string;
    segmentNumber: number;
    referencedSeriesId: string;
    catalogContentSha256: string;
  };
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
  if (!['consult_prep', 'longitudinal_review'].includes(input.workspaceMode)) {
    return undefined;
  }
  if (
    !Number.isInteger(input.measurementCount) ||
    input.measurementCount < 0 ||
    input.measurementCount > 10_000
  ) {
    return undefined;
  }
  try {
    const viewA = targetFor(input.viewA, input.viewAIndex);
    if (!viewA) return undefined;
    const viewB = targetFor(input.viewB, input.viewBIndex);
    if (input.workspaceMode === 'consult_prep' && input.comparisonDraftPresent) {
      return undefined;
    }
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
    let sourceSegmentationDisplay: ViewerStatePublication['source_segmentation_display'] = null;
    if (input.sourceSegmentation) {
      const source = input.sourceSegmentation;
      if (
        !instancePattern.test(source.segmentationId) ||
        !Number.isSafeInteger(source.segmentNumber) ||
        source.segmentNumber < 1 ||
        source.segmentNumber > 65535 ||
        !seriesPattern.test(source.referencedSeriesId) ||
        !sha256Pattern.test(source.catalogContentSha256) ||
        mprSeriesId !== source.referencedSeriesId
      ) {
        return undefined;
      }
      sourceSegmentationDisplay = {
        segmentation_id: source.segmentationId,
        segment_number: source.segmentNumber,
        referenced_series_id: source.referencedSeriesId,
        catalog_content_sha256: source.catalogContentSha256,
        display_status: 'read_only_native_grid',
        mask_pixels_shared: false,
        creator_identity_authenticated: false,
        segment_accuracy_verified: false,
        source_segment_clinical_meaning: 'not_assessed',
        dicom_guide_interpretation_added: false,
      };
    }
    const sliceLink = !viewB
      ? 'unpaired'
      : !input.synchronized
        ? 'independent'
        : input.linkStrategy === 'patient-position'
          ? 'patient_position'
          : 'approximate_index';
    return {
      schema_version: '2.0.0',
      sharing: true,
      publisher_id: input.publisherId,
      workspace_mode: input.workspaceMode,
      view_roles:
        input.workspaceMode === 'consult_prep'
          ? { view_a: 'reference', view_b: 'reference' }
          : { view_a: 'baseline', view_b: 'followup' },
      review_status: 'unreviewed',
      active_tool: input.activeTool,
      slice_link: sliceLink,
      view_a: viewA,
      view_b: viewB,
      mpr_series_id: mprSeriesId,
      source_segmentation_display: sourceSegmentationDisplay,
      measurement_count: input.measurementCount,
      comparison_draft_present: input.comparisonDraftPresent,
      permissions: {
        agent_navigation_from_state_authorized: false,
        source_mutation_authorized: false,
        source_segmentation_mask_read_authorized: false,
        source_segmentation_interpretation_authorized: false,
        diagnosis_authorized: false,
        response_classification_authorized: false,
        clinical_conclusion_authorized: false,
      },
      privacy: {
        local_only: true,
        contains_pixels: false,
        contains_direct_identifiers: false,
        contains_source_text: false,
        contains_measurement_values: false,
        contains_segmentation_mask: false,
        contains_opaque_source_references: true,
        contains_sensitive_segmentation_reference: sourceSegmentationDisplay !== null,
        contains_hashes: sourceSegmentationDisplay !== null,
        deidentified: false,
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
    { schema_version: '2.0.0', sharing: false, publisher_id: publisherId },
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
