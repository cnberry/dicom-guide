import { normalFromOrientation, type DicomSeries } from './dicom';
import type { ViewerTool } from './cornerstone';
import type { MprPatientPoint } from './mpr';
import { parseDiscussionMarks, type DiscussionMark } from './discussionMarkup';

export const VIEWER_CONTROL_ENDPOINT = '/v1/viewer-control';
export const VIEWER_CONTROL_OBSERVATION_ENDPOINT = '/v1/viewer-control/observation';
export const VIEWER_CONTROL_MEDIA_TYPE = 'application/vnd.dicom-guide.viewer-control+json';

export type ViewerControlViewMode = 'native' | 'mpr';
export type ViewerControlTool =
  | 'window'
  | 'pan'
  | 'zoom'
  | 'crosshairs'
  | 'highlight';

export type ViewerControlCommand = {
  schema_version: '1.0.0';
  command_id: string;
  view_mode: ViewerControlViewMode;
  series_id: string;
  instance_id: string;
  tool: ViewerControlTool;
  patient_point_lps_mm: MprPatientPoint | null;
  reset_view: boolean;
  target_viewer_id?: string;
  discussion_marks?: DiscussionMark[];
  revision: number;
  issued_at: string;
};

export type ViewerControlResponse = {
  schema_version: '1.0.0';
  viewer_connected: boolean;
  command: ViewerControlCommand | null;
};

export type ViewerControlObservation = {
  schema_version: '1.0.0';
  viewer_id: string;
  applied_command_id: string | null;
  applied_revision: number;
  interaction_source: 'person' | 'agent';
  render_status: 'loading' | 'ready' | 'error';
  view_mode: ViewerControlViewMode;
  series_id: string;
  instance_id: string;
  stack_position: number;
  stack_count: number;
  tool: ViewerControlTool;
  patient_point_lps_mm: MprPatientPoint | null;
  point_pinned: boolean;
  discussion_marks: DiscussionMark[];
  permissions: {
    agent_view_navigation_authorized: true;
    agent_display_tool_control_authorized: true;
    agent_patient_point_control_authorized: true;
    agent_discussion_overlay_control_authorized: true;
    source_mutation_authorized: false;
    measurement_creation_authorized: false;
    diagnosis_authorized: false;
    response_classification_authorized: false;
    clinical_conclusion_authorized: false;
  };
  privacy: {
    local_only: true;
    sensitive: true;
    contains_pixels: false;
    contains_direct_identifiers: false;
    contains_source_text: false;
    contains_opaque_source_references: true;
    contains_patient_coordinates: true;
    deidentified: false;
    persisted: false;
  };
};

const seriesPattern = /^series_[0-9a-f]{20}$/;
const instancePattern = /^instance_[0-9a-f]{20}$/;
const commandPattern = /^control_[0-9a-f]{32}$/;
const viewerPattern = /^viewer_[0-9a-f]{20}$/;
const toolsByView = {
  native: new Set<ViewerControlTool>(['window', 'pan', 'zoom', 'highlight']),
  mpr: new Set<ViewerControlTool>([
    'crosshairs',
    'window',
    'pan',
    'zoom',
    'highlight',
  ]),
};

const patientPoint = (value: unknown): MprPatientPoint | null | undefined => {
  if (value === null) return null;
  if (
    !Array.isArray(value) ||
    value.length !== 3 ||
    !value.every((item) => typeof item === 'number' && Number.isFinite(item))
  ) {
    return undefined;
  }
  return [value[0], value[1], value[2]];
};

const parseCommand = (value: unknown): ViewerControlCommand | undefined => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return undefined;
  const command = value as Record<string, unknown>;
  if (
    command.schema_version !== '1.0.0' ||
    typeof command.command_id !== 'string' ||
    !commandPattern.test(command.command_id) ||
    (command.view_mode !== 'native' && command.view_mode !== 'mpr') ||
    typeof command.series_id !== 'string' ||
    !seriesPattern.test(command.series_id) ||
    typeof command.instance_id !== 'string' ||
    !instancePattern.test(command.instance_id) ||
    typeof command.tool !== 'string' ||
    !toolsByView[command.view_mode].has(command.tool as ViewerControlTool) ||
    typeof command.reset_view !== 'boolean' ||
    !Number.isSafeInteger(command.revision) ||
    Number(command.revision) < 1 ||
    typeof command.issued_at !== 'string'
  ) {
    return undefined;
  }
  const point = patientPoint(command.patient_point_lps_mm);
  if (point === undefined) return undefined;
  if (
    command.target_viewer_id !== undefined &&
    (typeof command.target_viewer_id !== 'string' ||
      !viewerPattern.test(command.target_viewer_id))
  ) {
    return undefined;
  }
  const marks =
    command.discussion_marks === undefined
      ? undefined
      : parseDiscussionMarks(command.discussion_marks);
  if (
    command.discussion_marks !== undefined &&
    marks === undefined
  ) {
    return undefined;
  }
  return {
    schema_version: '1.0.0',
    command_id: command.command_id,
    view_mode: command.view_mode,
    series_id: command.series_id,
    instance_id: command.instance_id,
    tool: command.tool as ViewerControlTool,
    patient_point_lps_mm: point,
    reset_view: command.reset_view,
    ...(command.target_viewer_id
      ? { target_viewer_id: command.target_viewer_id }
      : {}),
    ...(marks ? { discussion_marks: marks } : {}),
    revision: Number(command.revision),
    issued_at: command.issued_at,
  };
};

export const fetchViewerControl = async (): Promise<ViewerControlResponse> => {
  const response = await fetch(VIEWER_CONTROL_ENDPOINT, {
    cache: 'no-store',
    credentials: 'same-origin',
    headers: { Accept: 'application/json' },
  });
  if (!response.ok) throw new Error(`Viewer control is unavailable (${response.status}).`);
  const value = (await response.json()) as Record<string, unknown>;
  if (value.schema_version !== '1.0.0' || typeof value.viewer_connected !== 'boolean') {
    throw new Error('Viewer control returned an invalid response.');
  }
  const command = value.command === null ? null : parseCommand(value.command);
  if (command === undefined) throw new Error('Viewer control returned an invalid command.');
  return { schema_version: '1.0.0', viewer_connected: value.viewer_connected, command };
};

export const publishViewerControlObservation = async (
  observation: ViewerControlObservation,
): Promise<void> => {
  const response = await fetch(VIEWER_CONTROL_OBSERVATION_ENDPOINT, {
    method: 'POST',
    cache: 'no-store',
    credentials: 'same-origin',
    headers: {
      Accept: 'application/json',
      'Content-Type': VIEWER_CONTROL_MEDIA_TYPE,
    },
    body: JSON.stringify(observation),
  });
  if (!response.ok) {
    let detail = '';
    try {
      const value = (await response.json()) as Record<string, unknown>;
      if (typeof value.detail === 'string' && value.detail.trim()) {
        detail = ` ${value.detail.trim()}`;
      }
    } catch {
      // The status remains useful when the local service cannot return JSON.
    }
    throw new Error(`Viewer observation was rejected (${response.status}).${detail}`);
  }
};

export const sourceIndexForPatientPoint = (
  series: DicomSeries,
  fallbackIndex: number,
  point?: MprPatientPoint,
): number => {
  if (!point) return fallbackIndex;
  const normal = normalFromOrientation(series.geometry.orientation);
  if (!normal || series.instances.some((item) => item.imagePosition?.length !== 3)) {
    return fallbackIndex;
  }
  const projection = (value: number[]) =>
    value.reduce((sum, coordinate, axis) => sum + coordinate * normal[axis], 0);
  const target = projection(point);
  return series.instances.reduce((closest, item, index) =>
    Math.abs(projection(item.imagePosition!) - target) <
    Math.abs(projection(series.instances[closest].imagePosition!) - target)
      ? index
      : closest,
  0);
};

export const buildViewerControlObservation = ({
  series,
  index,
  viewMode,
  nativeTool,
  mprTool,
  patientPoint: value,
  renderStatus,
  appliedCommand,
  discussionMarks = [],
  viewerId,
}: {
  series?: DicomSeries;
  index: number;
  viewMode: ViewerControlViewMode;
  nativeTool: ViewerTool;
  mprTool: ViewerControlTool;
  patientPoint?: MprPatientPoint;
  renderStatus: ViewerControlObservation['render_status'];
  appliedCommand?: { commandId: string; revision: number };
  discussionMarks?: DiscussionMark[];
  viewerId: string;
}): ViewerControlObservation | undefined => {
  if (!series || series.sourceKind !== 'loopback-service') return undefined;
  if (!viewerPattern.test(viewerId)) return undefined;
  const resolvedIndex =
    viewMode === 'mpr' ? sourceIndexForPatientPoint(series, index, value) : index;
  if (!Number.isInteger(resolvedIndex) || !series.instances[resolvedIndex]) return undefined;
  const point = value?.length === 3 && value.every(Number.isFinite) ? [...value] as MprPatientPoint : null;
  const selectedTool = viewMode === 'mpr' ? mprTool : nativeTool;
  if (!toolsByView[viewMode].has(selectedTool as ViewerControlTool)) return undefined;
  const tool = selectedTool as ViewerControlTool;
  return {
    schema_version: '1.0.0',
    viewer_id: viewerId,
    applied_command_id: appliedCommand?.commandId ?? null,
    applied_revision: appliedCommand?.revision ?? 0,
    interaction_source: appliedCommand ? 'agent' : 'person',
    render_status: renderStatus,
    view_mode: viewMode,
    series_id: series.id,
    instance_id: series.instances[resolvedIndex].instanceId,
    stack_position: resolvedIndex + 1,
    stack_count: series.instances.length,
    tool,
    patient_point_lps_mm: point,
    point_pinned: point !== null,
    discussion_marks: discussionMarks ?? [],
    permissions: {
      agent_view_navigation_authorized: true,
      agent_display_tool_control_authorized: true,
      agent_patient_point_control_authorized: true,
      agent_discussion_overlay_control_authorized: true,
      source_mutation_authorized: false,
      measurement_creation_authorized: false,
      diagnosis_authorized: false,
      response_classification_authorized: false,
      clinical_conclusion_authorized: false,
    },
    privacy: {
      local_only: true,
      sensitive: true,
      contains_pixels: false,
      contains_direct_identifiers: false,
      contains_source_text: false,
      contains_opaque_source_references: true,
      contains_patient_coordinates: true,
      deidentified: false,
      persisted: false,
    },
  };
};
