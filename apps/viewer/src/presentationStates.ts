import type { DicomSeries } from './dicom';

export const PRESENTATION_STATE_ENDPOINT = '/v1/presentation-states';
export const PRESENTATION_STATE_MAX_BYTES = 32 * 1024 * 1024;
export const PRESENTATION_STATE_LIMITATIONS = [
  'These are read-only display instructions extracted from source-carried DICOM Grayscale Softcopy Presentation State objects.',
  'DICOM Guide preserves supported source text and geometry but does not authenticate the creator or assess text for identifiers or clinical meaning.',
  'Only a conservative subset is displayed: hashed single-frame monochrome sources whose linear modality transform matches the GSPS, LINEAR VOI, identity presentation LUT, matching source/display aspect, unrotated and unflipped full-image SCALE TO FIT, and PIXEL POLYLINE/anchor-text annotations.',
  'Unsupported presentation-state features fail closed and native DICOM images remain authoritative.',
] as const;

const studyIdPattern = /^study_[0-9a-f]{20}$/;
const seriesIdPattern = /^series_[0-9a-f]{20}$/;
const instanceIdPattern = /^instance_[0-9a-f]{20}$/;
const patientIdPattern = /^patient_[0-9a-f]{20}$/;
const sha256Pattern = /^[0-9a-f]{64}$/;

export type PresentationStatePoint = [number, number];

export type PresentationStateGraphic = {
  graphic_id: string;
  type: 'POLYLINE';
  units: 'PIXEL';
  filled: false;
  points: PresentationStatePoint[];
};

export type PresentationStateText = {
  text_id: string;
  units: 'PIXEL';
  anchor_point: PresentationStatePoint;
  anchor_point_visible: boolean;
  unformatted_text: string;
};

export type PresentationStateAnnotation = {
  annotation_id: string;
  graphic_layer: string;
  referenced_instance_ids: string[];
  graphics: PresentationStateGraphic[];
  texts: PresentationStateText[];
};

export type SourcePresentationState = {
  presentation_state_id: string;
  source: {
    study_id: string;
    series_id: string;
    instance_id: string;
    patient_context_id: string;
    bytes: number;
    sha256: string;
  };
  display_status: 'supported_read_only';
  referenced_series: Array<{
    study_id: string;
    series_id: string;
    patient_context_id: string;
    modality: 'MR' | 'CT';
    instance_ids: string[];
  }>;
  referenced_instance_count: number;
  presentation: {
    rotation_degrees: 0;
    horizontal_flip: false;
    modality_transform: 'SOURCE_EQUIVALENT_LINEAR';
    voi_lut_function: 'LINEAR';
    presentation_lut_shape: 'IDENTITY';
    source_pixel_aspect_ratio_verified: true;
    window_center: number;
    window_width: number;
    voi_range: { lower: number; upper: number };
    displayed_area: {
      top_left: PresentationStatePoint;
      bottom_right: PresentationStatePoint;
      presentation_size_mode: 'SCALE TO FIT';
    };
    annotation_style: 'dicom_guide_high_contrast_source_geometry';
  };
  annotations: PresentationStateAnnotation[];
  annotation_count: number;
  graphic_count: number;
  text_count: number;
  author_identity_authenticated: false;
  dicom_guide_interpretation_added: false;
  source_text_clinical_meaning: 'not_assessed';
};

export type PresentationStateCatalog = {
  schema_version: '1.0.0';
  artifact_type: 'dicom-guide.presentation-state-catalog';
  generated_at: string;
  catalog_content_sha256: string;
  local_only: true;
  privacy: {
    classification: 'sensitive_local_medical_data';
    direct_identifier_tags_excluded: true;
    annotation_text_may_contain_identifiers: true;
    deidentified: false;
    contains_pixels: false;
    contains_paths: false;
    contains_annotation_text: boolean;
  };
  state_count: number;
  supported_state_count: number;
  unsupported_state_count: number;
  states: SourcePresentationState[];
  unsupported_states: Array<{
    presentation_state_id: string;
    display_status: 'unsupported';
    reason: string;
  }>;
  permissions: {
    exact_source_navigation_authorized: true;
    apply_saved_voi_authorized: true;
    display_source_annotations_authorized: true;
    edit_source_annotations_authorized: false;
    interpret_annotation_text_as_measurement_authorized: false;
    author_identity_authenticated: false;
    diagnosis_authorized: false;
    response_classification_authorized: false;
    clinical_conclusion_authorized: false;
  };
  limitations: string[];
};

export type PresentationStateTarget = {
  seriesId: string;
  instanceId: string;
  instanceIndex: number;
  stackPosition: number;
  stackCount: number;
  modality: 'MR' | 'CT';
  seriesDescription: string;
  basis: 'source_annotation' | 'first_referenced_image';
};

export type ResolvedPresentationState = {
  state: SourcePresentationState;
  targets: PresentationStateTarget[];
};

export type ResolvedPresentationStateCatalog = {
  catalog: PresentationStateCatalog;
  states: ResolvedPresentationState[];
};

export type AppliedPresentationState = {
  state: SourcePresentationState;
  target: PresentationStateTarget;
};

export const presentationPixelPointToImageIndex = (
  point: PresentationStatePoint,
): [number, number, number] => [point[0] - 0.5, point[1] - 0.5, 0];

const isRecord = (value: unknown): value is Record<string, unknown> =>
  Boolean(value) && typeof value === 'object' && !Array.isArray(value);

const exactKeys = (value: Record<string, unknown>, expected: string[]): boolean => {
  const expectedKeys = [...expected].sort();
  const keys = Object.keys(value).sort();
  return keys.length === expectedKeys.length &&
    keys.every((key, index) => key === expectedKeys[index]);
};

const finite = (value: unknown): value is number =>
  typeof value === 'number' && Number.isFinite(value);

const safeInteger = (value: unknown, minimum = 0, maximum = Number.MAX_SAFE_INTEGER): value is number =>
  Number.isSafeInteger(value) && Number(value) >= minimum && Number(value) <= maximum;

const point = (value: unknown): value is PresentationStatePoint =>
  Array.isArray(value) && value.length === 2 && value.every(finite);

const boundedText = (
  value: unknown,
  maximum: number,
  allowLineBreaks = false,
): value is string =>
  typeof value === 'string' &&
  value.length >= 1 &&
  [...value].length <= maximum &&
  ![...value].some((character) => {
    if (allowLineBreaks && (character === '\r' || character === '\n')) return false;
    return /\p{C}/u.test(character);
  });

const uniqueStrings = (value: unknown, pattern: RegExp, maximum: number): value is string[] =>
  Array.isArray(value) &&
  value.length >= 1 &&
  value.length <= maximum &&
  value.every((item) => typeof item === 'string' && pattern.test(item)) &&
  new Set(value).size === value.length;

const fixedPrivacy = (value: unknown): boolean =>
  isRecord(value) &&
  exactKeys(value, [
    'classification',
    'direct_identifier_tags_excluded',
    'annotation_text_may_contain_identifiers',
    'deidentified',
    'contains_pixels',
    'contains_paths',
    'contains_annotation_text',
  ]) &&
  value.classification === 'sensitive_local_medical_data' &&
  value.direct_identifier_tags_excluded === true &&
  value.annotation_text_may_contain_identifiers === true &&
  value.deidentified === false &&
  value.contains_pixels === false &&
  value.contains_paths === false &&
  typeof value.contains_annotation_text === 'boolean';

const fixedPermissions = (value: unknown): boolean => {
  if (!isRecord(value)) return false;
  const keys = [
    'exact_source_navigation_authorized',
    'apply_saved_voi_authorized',
    'display_source_annotations_authorized',
    'edit_source_annotations_authorized',
    'interpret_annotation_text_as_measurement_authorized',
    'author_identity_authenticated',
    'diagnosis_authorized',
    'response_classification_authorized',
    'clinical_conclusion_authorized',
  ];
  const trueKeys = new Set([
    'exact_source_navigation_authorized',
    'apply_saved_voi_authorized',
    'display_source_annotations_authorized',
  ]);
  return exactKeys(value, keys) &&
    keys.every((key) => value[key] === trueKeys.has(key));
};

const readSource = (value: unknown, stateId: string): boolean =>
  isRecord(value) &&
  exactKeys(value, [
    'study_id',
    'series_id',
    'instance_id',
    'patient_context_id',
    'bytes',
    'sha256',
  ]) &&
  typeof value.study_id === 'string' &&
  studyIdPattern.test(value.study_id) &&
  typeof value.series_id === 'string' &&
  seriesIdPattern.test(value.series_id) &&
  value.instance_id === stateId &&
  typeof value.patient_context_id === 'string' &&
  patientIdPattern.test(value.patient_context_id) &&
  safeInteger(value.bytes, 1, 16 * 1024 * 1024) &&
  typeof value.sha256 === 'string' &&
  sha256Pattern.test(value.sha256);

const readGraphic = (
  value: unknown,
  index: number,
  rows: number,
  columns: number,
): value is PresentationStateGraphic =>
  isRecord(value) &&
  exactKeys(value, ['graphic_id', 'type', 'units', 'filled', 'points']) &&
  value.graphic_id === `graphic_${String(index + 1).padStart(2, '0')}` &&
  value.type === 'POLYLINE' &&
  value.units === 'PIXEL' &&
  value.filled === false &&
  Array.isArray(value.points) &&
  value.points.length >= 2 &&
  value.points.length <= 2048 &&
  value.points.every(
    (candidate) =>
      point(candidate) &&
      candidate[0] >= 0 &&
      candidate[0] <= columns &&
      candidate[1] >= 0 &&
      candidate[1] <= rows,
  );

const readText = (
  value: unknown,
  index: number,
  rows: number,
  columns: number,
): value is PresentationStateText =>
  isRecord(value) &&
  exactKeys(value, [
    'text_id',
    'units',
    'anchor_point',
    'anchor_point_visible',
    'unformatted_text',
  ]) &&
  value.text_id === `text_${String(index + 1).padStart(2, '0')}` &&
  value.units === 'PIXEL' &&
  point(value.anchor_point) &&
  value.anchor_point[0] >= 0 &&
  value.anchor_point[0] <= columns &&
  value.anchor_point[1] >= 0 &&
  value.anchor_point[1] <= rows &&
  typeof value.anchor_point_visible === 'boolean' &&
  boundedText(value.unformatted_text, 512, true);

const seriesDimensions = (series: DicomSeries): [number, number] | undefined => {
  const rows = series.geometry.rows;
  const columns = series.geometry.columns;
  return safeInteger(rows, 1) && safeInteger(columns, 1) ? [rows, columns] : undefined;
};

const readState = (
  value: unknown,
  seriesById: Map<string, DicomSeries>,
): value is SourcePresentationState => {
  const keys = [
    'presentation_state_id',
    'source',
    'display_status',
    'referenced_series',
    'referenced_instance_count',
    'presentation',
    'annotations',
    'annotation_count',
    'graphic_count',
    'text_count',
    'author_identity_authenticated',
    'dicom_guide_interpretation_added',
    'source_text_clinical_meaning',
  ];
  if (
    !isRecord(value) ||
    !exactKeys(value, keys) ||
    typeof value.presentation_state_id !== 'string' ||
    !instanceIdPattern.test(value.presentation_state_id) ||
    !readSource(value.source, value.presentation_state_id) ||
    value.display_status !== 'supported_read_only' ||
    !Array.isArray(value.referenced_series) ||
    value.referenced_series.length < 1 ||
    !safeInteger(value.referenced_instance_count, 1, 4096) ||
    !Array.isArray(value.annotations) ||
    value.annotations.length > 512 ||
    value.annotation_count !== value.annotations.length ||
    !safeInteger(value.graphic_count, 0) ||
    !safeInteger(value.text_count, 0) ||
    value.author_identity_authenticated !== false ||
    value.dicom_guide_interpretation_added !== false ||
    value.source_text_clinical_meaning !== 'not_assessed'
  ) {
    return false;
  }

  const source = value.source as Record<string, unknown>;
  const referencedIds = new Set<string>();
  const referencedSeriesIds = new Set<string>();
  let commonDimensions: [number, number] | undefined;
  for (const referenced of value.referenced_series) {
    if (
      !isRecord(referenced) ||
      !exactKeys(referenced, [
        'study_id',
        'series_id',
        'patient_context_id',
        'modality',
        'instance_ids',
      ]) ||
      typeof referenced.study_id !== 'string' ||
      !studyIdPattern.test(referenced.study_id) ||
      typeof referenced.series_id !== 'string' ||
      !seriesIdPattern.test(referenced.series_id) ||
      typeof referenced.patient_context_id !== 'string' ||
      !patientIdPattern.test(referenced.patient_context_id) ||
      referenced.patient_context_id !== source.patient_context_id ||
      referenced.study_id !== source.study_id ||
      !['MR', 'CT'].includes(String(referenced.modality)) ||
      !uniqueStrings(referenced.instance_ids, instanceIdPattern, 4096)
    ) {
      return false;
    }
    if (referencedSeriesIds.has(referenced.series_id)) return false;
    referencedSeriesIds.add(referenced.series_id);
    const localSeries = seriesById.get(referenced.series_id);
    const dimensions = localSeries ? seriesDimensions(localSeries) : undefined;
    if (
      !localSeries ||
      localSeries.sourceKind !== 'loopback-service' ||
      localSeries.studyId !== referenced.study_id ||
      localSeries.patientContextId !== referenced.patient_context_id ||
      localSeries.modality !== referenced.modality ||
      !dimensions
    ) {
      return false;
    }
    if (
      commonDimensions &&
      (commonDimensions[0] !== dimensions[0] || commonDimensions[1] !== dimensions[1])
    ) {
      return false;
    }
    commonDimensions = dimensions;
    const localInstanceIds = new Set(localSeries.instances.map((item) => item.instanceId));
    for (const instanceId of referenced.instance_ids) {
      if (referencedIds.has(instanceId) || !localInstanceIds.has(instanceId)) return false;
      referencedIds.add(instanceId);
    }
  }
  if (referencedIds.size !== value.referenced_instance_count || !commonDimensions) return false;
  const [rows, columns] = commonDimensions;

  const presentation = value.presentation;
  if (
    !isRecord(presentation) ||
    !exactKeys(presentation, [
      'rotation_degrees',
      'horizontal_flip',
      'modality_transform',
      'voi_lut_function',
      'presentation_lut_shape',
      'source_pixel_aspect_ratio_verified',
      'window_center',
      'window_width',
      'voi_range',
      'displayed_area',
      'annotation_style',
    ]) ||
    presentation.rotation_degrees !== 0 ||
    presentation.horizontal_flip !== false ||
    presentation.modality_transform !== 'SOURCE_EQUIVALENT_LINEAR' ||
    presentation.voi_lut_function !== 'LINEAR' ||
    presentation.presentation_lut_shape !== 'IDENTITY' ||
    presentation.source_pixel_aspect_ratio_verified !== true ||
    !finite(presentation.window_center) ||
    !finite(presentation.window_width) ||
    presentation.window_width < 1 ||
    presentation.annotation_style !== 'dicom_guide_high_contrast_source_geometry' ||
    !isRecord(presentation.voi_range) ||
    !exactKeys(presentation.voi_range, ['lower', 'upper']) ||
    !finite(presentation.voi_range.lower) ||
    !finite(presentation.voi_range.upper) ||
    presentation.voi_range.upper < presentation.voi_range.lower ||
    Math.abs(
      presentation.voi_range.lower -
        (presentation.window_center - 0.5 - (presentation.window_width - 1) / 2),
    ) > 1e-9 ||
    Math.abs(
      presentation.voi_range.upper -
        (presentation.window_center - 0.5 + (presentation.window_width - 1) / 2),
    ) > 1e-9 ||
    !isRecord(presentation.displayed_area) ||
    !exactKeys(presentation.displayed_area, [
      'top_left',
      'bottom_right',
      'presentation_size_mode',
    ]) ||
    !point(presentation.displayed_area.top_left) ||
    presentation.displayed_area.top_left[0] !== 1 ||
    presentation.displayed_area.top_left[1] !== 1 ||
    !point(presentation.displayed_area.bottom_right) ||
    presentation.displayed_area.bottom_right[0] !== columns ||
    presentation.displayed_area.bottom_right[1] !== rows ||
    presentation.displayed_area.presentation_size_mode !== 'SCALE TO FIT'
  ) {
    return false;
  }

  let graphicCount = 0;
  let textCount = 0;
  for (const [annotationIndex, annotation] of value.annotations.entries()) {
    if (
      !isRecord(annotation) ||
      !exactKeys(annotation, [
        'annotation_id',
        'graphic_layer',
        'referenced_instance_ids',
        'graphics',
        'texts',
      ]) ||
      annotation.annotation_id !==
        `annotation_${String(annotationIndex + 1).padStart(3, '0')}` ||
      !boundedText(annotation.graphic_layer, 64) ||
      !uniqueStrings(annotation.referenced_instance_ids, instanceIdPattern, 4096) ||
      !annotation.referenced_instance_ids.every((item) => referencedIds.has(item)) ||
      !Array.isArray(annotation.graphics) ||
      annotation.graphics.length > 64 ||
      !Array.isArray(annotation.texts) ||
      annotation.texts.length > 64 ||
      annotation.graphics.length + annotation.texts.length === 0 ||
      !annotation.graphics.every((item, index) =>
        readGraphic(item, index, rows, columns),
      ) ||
      !annotation.texts.every((item, index) => readText(item, index, rows, columns))
    ) {
      return false;
    }
    graphicCount += annotation.graphics.length;
    textCount += annotation.texts.length;
  }
  return graphicCount === value.graphic_count && textCount === value.text_count;
};

export const parsePresentationStateCatalog = (
  value: unknown,
  series: DicomSeries[],
): ResolvedPresentationStateCatalog => {
  const topKeys = [
    'schema_version',
    'artifact_type',
    'generated_at',
    'catalog_content_sha256',
    'local_only',
    'privacy',
    'state_count',
    'supported_state_count',
    'unsupported_state_count',
    'states',
    'unsupported_states',
    'permissions',
    'limitations',
  ];
  if (
    !isRecord(value) ||
    !exactKeys(value, topKeys) ||
    value.schema_version !== '1.0.0' ||
    value.artifact_type !== 'dicom-guide.presentation-state-catalog' ||
    typeof value.generated_at !== 'string' ||
    !value.generated_at.endsWith('Z') ||
    Number.isNaN(Date.parse(value.generated_at)) ||
    typeof value.catalog_content_sha256 !== 'string' ||
    !sha256Pattern.test(value.catalog_content_sha256) ||
    value.local_only !== true ||
    !fixedPrivacy(value.privacy) ||
    !safeInteger(value.state_count, 0) ||
    !safeInteger(value.supported_state_count, 0) ||
    !safeInteger(value.unsupported_state_count, 0) ||
    !Array.isArray(value.states) ||
    !Array.isArray(value.unsupported_states) ||
    value.state_count !== value.states.length + value.unsupported_states.length ||
    value.supported_state_count !== value.states.length ||
    value.unsupported_state_count !== value.unsupported_states.length ||
    !fixedPermissions(value.permissions) ||
    !Array.isArray(value.limitations) ||
    value.limitations.length !== PRESENTATION_STATE_LIMITATIONS.length ||
    !value.limitations.every(
      (item, index) => item === PRESENTATION_STATE_LIMITATIONS[index],
    )
  ) {
    throw new Error('Local presentation-state contract is invalid. Nothing was displayed.');
  }

  const seriesById = new Map(series.map((item) => [item.id, item]));
  if (!value.states.every((item) => readState(item, seriesById))) {
    throw new Error(
      'A source-carried GSPS state does not match the exact local MR/CT sources. Nothing was displayed.',
    );
  }
  if (
    !value.unsupported_states.every(
      (item) =>
        isRecord(item) &&
        exactKeys(item, ['presentation_state_id', 'display_status', 'reason']) &&
        typeof item.presentation_state_id === 'string' &&
        instanceIdPattern.test(item.presentation_state_id) &&
        item.display_status === 'unsupported' &&
        boundedText(item.reason, 240),
    )
  ) {
    throw new Error('Local presentation-state contract is invalid. Nothing was displayed.');
  }
  const typed = value as PresentationStateCatalog;
  if (
    (typed.privacy.contains_annotation_text !==
      typed.states.some((state) => state.text_count > 0)) ||
    new Set([
      ...typed.states.map((state) => state.presentation_state_id),
      ...typed.unsupported_states.map((state) => state.presentation_state_id),
    ]).size !== typed.state_count
  ) {
    throw new Error('Local presentation-state counts are inconsistent. Nothing was displayed.');
  }

  const states = typed.states.map((state): ResolvedPresentationState => {
    const annotatedIds = state.annotations.flatMap(
      (annotation) => annotation.referenced_instance_ids,
    );
    const targetIds = [...new Set(annotatedIds)];
    const basis: PresentationStateTarget['basis'] = targetIds.length
      ? 'source_annotation'
      : 'first_referenced_image';
    if (targetIds.length === 0) {
      targetIds.push(state.referenced_series[0].instance_ids[0]);
    }
    const targets = targetIds.map((instanceId): PresentationStateTarget => {
      const referenced = state.referenced_series.find((candidate) =>
        candidate.instance_ids.includes(instanceId),
      );
      const localSeries = referenced ? seriesById.get(referenced.series_id) : undefined;
      const instanceIndex = localSeries?.instances.findIndex(
        (candidate) => candidate.instanceId === instanceId,
      );
      if (!referenced || !localSeries || instanceIndex === undefined || instanceIndex < 0) {
        throw new Error(
          'A source-carried GSPS target is unavailable locally. Nothing was displayed.',
        );
      }
      return {
        seriesId: localSeries.id,
        instanceId,
        instanceIndex,
        stackPosition: instanceIndex + 1,
        stackCount: localSeries.instances.length,
        modality: referenced.modality,
        seriesDescription: localSeries.description,
        basis,
      };
    });
    return { state, targets };
  });
  return { catalog: typed, states };
};

export const loadPresentationStateCatalog = async (
  series: DicomSeries[],
  signal?: AbortSignal,
): Promise<ResolvedPresentationStateCatalog> => {
  const response = await fetch(PRESENTATION_STATE_ENDPOINT, {
    cache: 'no-store',
    credentials: 'same-origin',
    headers: { Accept: 'application/json' },
    signal,
  });
  if (!response.ok) {
    if (response.status === 409) {
      throw new Error(
        'Source-carried GSPS states were locked because local DICOM source bytes changed after startup.',
      );
    }
    throw new Error(
      response.status === 401 || response.status === 403
        ? 'Source-carried GSPS states require the authenticated local browser workspace.'
        : `Source-carried GSPS states are unavailable from the local service (${response.status}).`,
    );
  }
  const declaredLength = Number(response.headers.get('Content-Length'));
  if (Number.isFinite(declaredLength) && declaredLength > PRESENTATION_STATE_MAX_BYTES) {
    throw new Error('GSPS presentation-state response exceeds the 32 MiB browser limit.');
  }
  const text = await response.text();
  if (new TextEncoder().encode(text).byteLength > PRESENTATION_STATE_MAX_BYTES) {
    throw new Error('GSPS presentation-state response exceeds the 32 MiB browser limit.');
  }
  let value: unknown;
  try {
    value = JSON.parse(text);
  } catch {
    throw new Error('GSPS presentation-state response is not valid JSON.');
  }
  return parsePresentationStateCatalog(value, series);
};
