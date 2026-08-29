import {
  assessLesionVolumeEligibility,
  normalFromOrientation,
  type DicomSeries,
} from './dicom';

export const SOURCE_SEGMENTATION_ENDPOINT = '/v1/source-segmentations';
export const SOURCE_SEGMENTATION_MAX_CATALOG_BYTES = 32 * 1024 * 1024;
export const SOURCE_SEGMENTATION_MAX_MASK_BYTES = 64 * 1024 * 1024;
export const SOURCE_SEGMENTATION_LIMITATIONS = [
  'These are read-only masks extracted from source-carried DICOM Segmentation objects and rejoined to exact local MR/CT source instances.',
  'ScanView does not authenticate the segmentation creator, verify the algorithm, or assess segment labels and coded properties for identifiers, accuracy, or clinical meaning.',
  'Only a conservative native-grid subset is displayed: uncompressed binary SEG, one referenced MR/CT series, single-frame sources, exact matrix/orientation/position/spacing, and one exact source-image reference per frame. Spatial Locations Preserved may be YES or absent because DICOM defines it as optional; explicit NO, REORIENTED_ONLY, or any other value is refused.',
  'Passing this narrow ScanView import profile is not full DICOM conformance certification; technical marked-voxel counts and native-grid volumes remain unreviewed, unsupported objects fail closed, and original DICOM objects remain authoritative.',
] as const;

const studyIdPattern = /^study_[0-9a-f]{20}$/;
const seriesIdPattern = /^series_[0-9a-f]{20}$/;
const instanceIdPattern = /^instance_[0-9a-f]{20}$/;
const patientIdPattern = /^patient_[0-9a-f]{20}$/;
const sha256Pattern = /^[0-9a-f]{64}$/;

export type SourceSegmentationCode = {
  value: string;
  scheme: string;
  meaning: string;
};

export type SourceSegment = {
  segment_number: number;
  segment_label: string;
  algorithm_type: 'MANUAL' | 'SEMIAUTOMATIC' | 'AUTOMATIC';
  algorithm_name: string | null;
  property_category: SourceSegmentationCode;
  property_type: SourceSegmentationCode;
  recommended_display_cielab: [number, number, number] | null;
  frame_count: number;
  marked_voxel_count: number;
  computed_volume_mm3: number;
  computed_volume_ml: number;
  mask_sha256: string;
};

export type SourceSegmentation = {
  segmentation_id: string;
  source: {
    study_id: string;
    series_id: string;
    instance_id: string;
    patient_context_id: string;
    bytes: number;
    sha256: string;
  };
  display_status: 'supported_read_only';
  referenced_series: {
    study_id: string;
    series_id: string;
    patient_context_id: string;
    modality: 'MR' | 'CT';
    ordered_instance_ids: string[];
    referenced_instance_ids: string[];
  };
  referenced_instance_count: number;
  spatial_location_evidence:
    | 'explicit_yes_and_exact_native_geometry'
    | 'optional_tag_absent_exact_native_geometry';
  grid: {
    relationship: 'exact_native_source_grid';
    dimensions: [number, number, number];
    pixel_spacing_mm: [number, number];
    projected_slice_spacing_mm: number;
    voxel_volume_mm3: number;
    resampled_by_scanview: false;
  };
  frame_count: number;
  segment_count: number;
  segments: SourceSegment[];
  creator_identity_authenticated: false;
  source_segment_clinical_meaning: 'not_assessed';
  scanview_interpretation_added: false;
};

export type SourceSegmentationCatalog = {
  schema_version: '2.0.0';
  artifact_type: 'scanview.source-segmentation-catalog';
  generated_at: string;
  catalog_content_sha256: string;
  local_only: true;
  privacy: {
    classification: 'sensitive_local_medical_data';
    direct_identifier_tags_excluded: true;
    segment_text_may_contain_identifiers: true;
    deidentified: false;
    contains_pixels: false;
    contains_paths: false;
    contains_segment_text: boolean;
  };
  segmentation_count: number;
  supported_segmentation_count: number;
  unsupported_segmentation_count: number;
  segment_count: number;
  segmentations: SourceSegmentation[];
  unsupported_segmentations: Array<{
    segmentation_id: string;
    display_status: 'unsupported';
    reason: string;
  }>;
  permissions: {
    bearer_agent_sensitive_catalog_read_authorized: true;
    bearer_agent_mask_read_authorized: false;
    browser_session_sensitive_catalog_read_authorized: true;
    browser_session_mask_read_authorized: true;
    browser_session_exact_source_navigation_authorized: true;
    browser_session_read_only_mask_display_authorized: true;
    browser_session_technical_volume_display_authorized: true;
    edit_source_segmentation_authorized: false;
    convert_to_scanview_measurement_authorized: false;
    creator_identity_authenticated: false;
    segment_accuracy_verified: false;
    diagnosis_authorized: false;
    response_classification_authorized: false;
    clinical_conclusion_authorized: false;
  };
  limitations: string[];
};

export type ResolvedSourceSegmentation = {
  state: SourceSegmentation;
  series: DicomSeries;
};

export type ResolvedSourceSegmentationCatalog = {
  catalog: SourceSegmentationCatalog;
  segmentations: ResolvedSourceSegmentation[];
};

export type LoadedSourceSegmentation = {
  state: SourceSegmentation;
  segment: SourceSegment;
  series: DicomSeries;
  mask: Uint8Array;
};

const isRecord = (value: unknown): value is Record<string, unknown> =>
  Boolean(value) && typeof value === 'object' && !Array.isArray(value);

const exactKeys = (value: Record<string, unknown>, expected: string[]): boolean => {
  const observed = Object.keys(value).sort();
  const wanted = [...expected].sort();
  return observed.length === wanted.length &&
    observed.every((item, index) => item === wanted[index]);
};

const finite = (value: unknown): value is number =>
  typeof value === 'number' && Number.isFinite(value);

const safeInteger = (
  value: unknown,
  minimum: number,
  maximum: number,
): value is number => Number.isSafeInteger(value) && Number(value) >= minimum && Number(value) <= maximum;

const close = (left: number, right: number, tolerance: number): boolean =>
  Number.isFinite(left) && Number.isFinite(right) && Math.abs(left - right) <= tolerance;

const boundedText = (value: unknown, maximum = 256): value is string =>
  typeof value === 'string' &&
  value.length >= 1 &&
  [...value].length <= maximum &&
  ![...value].some((character) => /\p{C}/u.test(character));

const stringIds = (
  value: unknown,
  pattern: RegExp,
  minimum: number,
  maximum: number,
): value is string[] =>
  Array.isArray(value) &&
  value.length >= minimum &&
  value.length <= maximum &&
  value.every((item) => typeof item === 'string' && pattern.test(item)) &&
  new Set(value).size === value.length;

const finiteTuple = <Length extends number>(
  value: unknown,
  length: Length,
): value is number[] & { length: Length } =>
  Array.isArray(value) && value.length === length && value.every(finite);

const readCode = (value: unknown): value is SourceSegmentationCode =>
  isRecord(value) &&
  exactKeys(value, ['value', 'scheme', 'meaning']) &&
  boundedText(value.value) &&
  boundedText(value.scheme) &&
  boundedText(value.meaning);

const readSegment = (
  value: unknown,
  depth: number,
  voxelCount: number,
  voxelVolumeMm3: number,
): value is SourceSegment => {
  if (
    !isRecord(value) ||
    !exactKeys(value, [
      'segment_number',
      'segment_label',
      'algorithm_type',
      'algorithm_name',
      'property_category',
      'property_type',
      'recommended_display_cielab',
      'frame_count',
      'marked_voxel_count',
      'computed_volume_mm3',
      'computed_volume_ml',
      'mask_sha256',
    ]) ||
    !safeInteger(value.segment_number, 1, 65535) ||
    !boundedText(value.segment_label) ||
    !['MANUAL', 'SEMIAUTOMATIC', 'AUTOMATIC'].includes(String(value.algorithm_type)) ||
    !(
      value.algorithm_name === null ||
      boundedText(value.algorithm_name)
    ) ||
    (value.algorithm_type !== 'MANUAL' && value.algorithm_name === null) ||
    !readCode(value.property_category) ||
    !readCode(value.property_type) ||
    !(
      value.recommended_display_cielab === null ||
      (finiteTuple(value.recommended_display_cielab, 3) &&
        value.recommended_display_cielab.every((item) =>
          safeInteger(item, 0, 65535)))
    ) ||
    !safeInteger(value.frame_count, 1, Math.min(depth, 131072)) ||
    !safeInteger(value.marked_voxel_count, 1, voxelCount) ||
    !finite(value.computed_volume_mm3) ||
    value.computed_volume_mm3 <= 0 ||
    !finite(value.computed_volume_ml) ||
    value.computed_volume_ml <= 0 ||
    typeof value.mask_sha256 !== 'string' ||
    !sha256Pattern.test(value.mask_sha256)
  ) {
    return false;
  }
  const expectedVolume = value.marked_voxel_count * voxelVolumeMm3;
  return close(
    value.computed_volume_mm3,
    expectedVolume,
    Math.max(1e-6, expectedVolume * 1e-6),
  ) && close(
    value.computed_volume_ml,
    expectedVolume / 1000,
    Math.max(1e-9, expectedVolume * 1e-9),
  );
};

const readSource = (value: unknown, segmentationId: string): boolean =>
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
  value.instance_id === segmentationId &&
  typeof value.patient_context_id === 'string' &&
  patientIdPattern.test(value.patient_context_id) &&
  safeInteger(value.bytes, 1, 256 * 1024 * 1024) &&
  typeof value.sha256 === 'string' &&
  sha256Pattern.test(value.sha256);

const readState = (
  value: unknown,
  seriesById: Map<string, DicomSeries>,
): value is SourceSegmentation => {
  if (
    !isRecord(value) ||
    !exactKeys(value, [
      'segmentation_id',
      'source',
      'display_status',
      'referenced_series',
      'referenced_instance_count',
      'spatial_location_evidence',
      'grid',
      'frame_count',
      'segment_count',
      'segments',
      'creator_identity_authenticated',
      'source_segment_clinical_meaning',
      'scanview_interpretation_added',
    ]) ||
    typeof value.segmentation_id !== 'string' ||
    !instanceIdPattern.test(value.segmentation_id) ||
    !readSource(value.source, value.segmentation_id) ||
    value.display_status !== 'supported_read_only' ||
    !isRecord(value.referenced_series) ||
    !exactKeys(value.referenced_series, [
      'study_id',
      'series_id',
      'patient_context_id',
      'modality',
      'ordered_instance_ids',
      'referenced_instance_ids',
    ]) ||
    typeof value.referenced_series.study_id !== 'string' ||
    !studyIdPattern.test(value.referenced_series.study_id) ||
    typeof value.referenced_series.series_id !== 'string' ||
    !seriesIdPattern.test(value.referenced_series.series_id) ||
    typeof value.referenced_series.patient_context_id !== 'string' ||
    !patientIdPattern.test(value.referenced_series.patient_context_id) ||
    !['MR', 'CT'].includes(String(value.referenced_series.modality)) ||
    !stringIds(value.referenced_series.ordered_instance_ids, instanceIdPattern, 3, 4096) ||
    !stringIds(value.referenced_series.referenced_instance_ids, instanceIdPattern, 1, 4096) ||
    !safeInteger(value.referenced_instance_count, 1, 4096) ||
    value.referenced_instance_count !== value.referenced_series.referenced_instance_ids.length ||
    ![
      'explicit_yes_and_exact_native_geometry',
      'optional_tag_absent_exact_native_geometry',
    ].includes(String(value.spatial_location_evidence)) ||
    !isRecord(value.grid) ||
    !exactKeys(value.grid, [
      'relationship',
      'dimensions',
      'pixel_spacing_mm',
      'projected_slice_spacing_mm',
      'voxel_volume_mm3',
      'resampled_by_scanview',
    ]) ||
    value.grid.relationship !== 'exact_native_source_grid' ||
    !finiteTuple(value.grid.dimensions, 3) ||
    !value.grid.dimensions.every((item, index) =>
      safeInteger(item, index === 0 ? 3 : 2, index === 0 ? 4096 : 65535)) ||
    !finiteTuple(value.grid.pixel_spacing_mm, 2) ||
    !value.grid.pixel_spacing_mm.every((item) => item > 0) ||
    !finite(value.grid.projected_slice_spacing_mm) ||
    value.grid.projected_slice_spacing_mm <= 0 ||
    !finite(value.grid.voxel_volume_mm3) ||
    value.grid.voxel_volume_mm3 <= 0 ||
    value.grid.resampled_by_scanview !== false ||
    !safeInteger(value.frame_count, 1, 131072) ||
    !safeInteger(value.segment_count, 1, 32) ||
    !Array.isArray(value.segments) ||
    value.segments.length !== value.segment_count ||
    value.creator_identity_authenticated !== false ||
    value.source_segment_clinical_meaning !== 'not_assessed' ||
    value.scanview_interpretation_added !== false
  ) {
    return false;
  }

  const referenced = value.referenced_series as SourceSegmentation['referenced_series'];
  const grid = value.grid as SourceSegmentation['grid'];
  const segments = value.segments as unknown[];
  const source = value.source as Record<string, unknown>;
  const series = seriesById.get(referenced.series_id as string);
  const eligibility = assessLesionVolumeEligibility(series);
  const normal = normalFromOrientation(series?.geometry.orientation);
  const projectionOrderedInstanceIds = normal && series
    ? [...series.instances]
      .sort((left, right) => {
        const leftProjection = left.imagePosition!.reduce(
          (sum, coordinate, index) => sum + coordinate * normal[index],
          0,
        );
        const rightProjection = right.imagePosition!.reduce(
          (sum, coordinate, index) => sum + coordinate * normal[index],
          0,
        );
        return leftProjection - rightProjection || left.instanceId.localeCompare(right.instanceId);
      })
      .map((item) => item.instanceId)
    : [];
  if (
    !series ||
    series.sourceKind !== 'loopback-service' ||
    !eligibility.eligible ||
    series.studyId !== referenced.study_id ||
    series.studyId !== source.study_id ||
    series.patientContextId !== referenced.patient_context_id ||
    series.patientContextId !== source.patient_context_id ||
    series.modality !== referenced.modality ||
    referenced.ordered_instance_ids.length !== series.instances.length ||
    !referenced.ordered_instance_ids.every(
      (instanceId, index) => instanceId === projectionOrderedInstanceIds[index],
    ) ||
    !referenced.referenced_instance_ids.every((instanceId) =>
      referenced.ordered_instance_ids.includes(instanceId))
  ) {
    return false;
  }
  const [depth, rows, columns] = grid.dimensions;
  const voxelCount = depth * rows * columns;
  const pixelSpacing = series.geometry.pixelSpacing;
  if (
    depth !== series.instances.length ||
    rows !== series.geometry.rows ||
    columns !== series.geometry.columns ||
    !Number.isSafeInteger(voxelCount) ||
    voxelCount < 1 ||
    voxelCount > SOURCE_SEGMENTATION_MAX_MASK_BYTES ||
    !pixelSpacing ||
    !close(grid.pixel_spacing_mm[0], pixelSpacing[0], 1e-4) ||
    !close(grid.pixel_spacing_mm[1], pixelSpacing[1], 1e-4) ||
    !close(
      grid.projected_slice_spacing_mm,
      eligibility.sliceSpacingMm ?? Number.NaN,
      Math.max(0.01, grid.projected_slice_spacing_mm * 0.001),
    ) ||
    !close(
      grid.voxel_volume_mm3,
      grid.pixel_spacing_mm[0] *
        grid.pixel_spacing_mm[1] *
        grid.projected_slice_spacing_mm,
      Math.max(1e-6, grid.voxel_volume_mm3 * 1e-6),
    ) ||
    !segments.every((item) =>
      readSegment(item, depth, voxelCount, grid.voxel_volume_mm3))
  ) {
    return false;
  }
  const typedSegments = segments as SourceSegment[];
  const segmentNumbers = typedSegments.map((item) => item.segment_number);
  return new Set(segmentNumbers).size === segmentNumbers.length &&
    segmentNumbers.every((number, index) => index === 0 || number > segmentNumbers[index - 1]) &&
    value.frame_count <= depth * value.segment_count &&
    typedSegments.reduce((sum, item) => sum + item.frame_count, 0) === value.frame_count;
};

const fixedPrivacy = (value: unknown): boolean =>
  isRecord(value) &&
  exactKeys(value, [
    'classification',
    'direct_identifier_tags_excluded',
    'segment_text_may_contain_identifiers',
    'deidentified',
    'contains_pixels',
    'contains_paths',
    'contains_segment_text',
  ]) &&
  value.classification === 'sensitive_local_medical_data' &&
  value.direct_identifier_tags_excluded === true &&
  value.segment_text_may_contain_identifiers === true &&
  value.deidentified === false &&
  value.contains_pixels === false &&
  value.contains_paths === false &&
  typeof value.contains_segment_text === 'boolean';

const fixedPermissions = (value: unknown): boolean => {
  if (!isRecord(value)) return false;
  const keys = [
    'bearer_agent_sensitive_catalog_read_authorized',
    'bearer_agent_mask_read_authorized',
    'browser_session_sensitive_catalog_read_authorized',
    'browser_session_mask_read_authorized',
    'browser_session_exact_source_navigation_authorized',
    'browser_session_read_only_mask_display_authorized',
    'browser_session_technical_volume_display_authorized',
    'edit_source_segmentation_authorized',
    'convert_to_scanview_measurement_authorized',
    'creator_identity_authenticated',
    'segment_accuracy_verified',
    'diagnosis_authorized',
    'response_classification_authorized',
    'clinical_conclusion_authorized',
  ];
  const allowed = new Set([
    'bearer_agent_sensitive_catalog_read_authorized',
    'browser_session_sensitive_catalog_read_authorized',
    'browser_session_mask_read_authorized',
    'browser_session_exact_source_navigation_authorized',
    'browser_session_read_only_mask_display_authorized',
    'browser_session_technical_volume_display_authorized',
  ]);
  return exactKeys(value, keys) && keys.every((key) => value[key] === allowed.has(key));
};

export const readSourceSegmentationCatalog = (
  value: unknown,
  series: DicomSeries[],
): ResolvedSourceSegmentationCatalog | undefined => {
  const keys = [
    'schema_version',
    'artifact_type',
    'generated_at',
    'catalog_content_sha256',
    'local_only',
    'privacy',
    'segmentation_count',
    'supported_segmentation_count',
    'unsupported_segmentation_count',
    'segment_count',
    'segmentations',
    'unsupported_segmentations',
    'permissions',
    'limitations',
  ];
  if (
    !isRecord(value) ||
    !exactKeys(value, keys) ||
    value.schema_version !== '2.0.0' ||
    value.artifact_type !== 'scanview.source-segmentation-catalog' ||
    typeof value.generated_at !== 'string' ||
    !value.generated_at.endsWith('Z') ||
    !Number.isFinite(Date.parse(value.generated_at)) ||
    typeof value.catalog_content_sha256 !== 'string' ||
    !sha256Pattern.test(value.catalog_content_sha256) ||
    value.local_only !== true ||
    !fixedPrivacy(value.privacy) ||
    !safeInteger(value.segmentation_count, 0, 100000) ||
    !safeInteger(value.supported_segmentation_count, 0, 100000) ||
    !safeInteger(value.unsupported_segmentation_count, 0, 100000) ||
    !safeInteger(value.segment_count, 0, 3200000) ||
    !Array.isArray(value.segmentations) ||
    !Array.isArray(value.unsupported_segmentations) ||
    !fixedPermissions(value.permissions) ||
    !Array.isArray(value.limitations) ||
    value.limitations.length !== SOURCE_SEGMENTATION_LIMITATIONS.length ||
    !value.limitations.every(
      (item, index) => item === SOURCE_SEGMENTATION_LIMITATIONS[index])
  ) {
    return undefined;
  }
  const seriesById = new Map(series.map((item) => [item.id, item]));
  if (!value.segmentations.every((item) => readState(item, seriesById))) {
    return undefined;
  }
  const supportedIds = (value.segmentations as SourceSegmentation[]).map(
    (item) => item.segmentation_id,
  );
  const unsupportedIds: string[] = [];
  for (const unsupported of value.unsupported_segmentations) {
    if (
      !isRecord(unsupported) ||
      !exactKeys(unsupported, ['segmentation_id', 'display_status', 'reason']) ||
      typeof unsupported.segmentation_id !== 'string' ||
      !instanceIdPattern.test(unsupported.segmentation_id) ||
      unsupported.display_status !== 'unsupported' ||
      !boundedText(unsupported.reason, 300)
    ) {
      return undefined;
    }
    unsupportedIds.push(unsupported.segmentation_id);
  }
  const allIds = [...supportedIds, ...unsupportedIds];
  const typedStates = value.segmentations as SourceSegmentation[];
  if (
    new Set(allIds).size !== allIds.length ||
    value.supported_segmentation_count !== typedStates.length ||
    value.unsupported_segmentation_count !== unsupportedIds.length ||
    value.segmentation_count !== allIds.length ||
    value.segment_count !== typedStates.reduce((sum, item) => sum + item.segment_count, 0) ||
    (value.privacy as SourceSegmentationCatalog['privacy']).contains_segment_text !==
      (typedStates.length > 0)
  ) {
    return undefined;
  }
  return {
    catalog: value as SourceSegmentationCatalog,
    segmentations: typedStates.map((state) => ({
      state,
      series: seriesById.get(state.referenced_series.series_id)!,
    })),
  };
};

export const loadSourceSegmentationCatalog = async (
  series: DicomSeries[],
  signal?: AbortSignal,
): Promise<ResolvedSourceSegmentationCatalog> => {
  const response = await fetch(SOURCE_SEGMENTATION_ENDPOINT, {
    cache: 'no-store',
    credentials: 'same-origin',
    headers: { Accept: 'application/json' },
    signal,
  });
  if (!response.ok) {
    throw new Error(
      response.status === 409
        ? 'DICOM SEG inputs changed after startup; source masks remain locked.'
        : 'Source-carried DICOM segmentations are unavailable.',
    );
  }
  const contentLength = Number(response.headers.get('Content-Length'));
  if (Number.isFinite(contentLength) && contentLength > SOURCE_SEGMENTATION_MAX_CATALOG_BYTES) {
    throw new Error('Source-carried DICOM segmentation catalog exceeds the local safety limit.');
  }
  const bytes = new Uint8Array(await response.arrayBuffer());
  if (bytes.byteLength > SOURCE_SEGMENTATION_MAX_CATALOG_BYTES) {
    throw new Error('Source-carried DICOM segmentation catalog exceeds the local safety limit.');
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes));
  } catch {
    throw new Error('Source-carried DICOM segmentation catalog is not strict UTF-8 JSON.');
  }
  const resolved = readSourceSegmentationCatalog(parsed, series);
  if (!resolved) {
    throw new Error('Source-carried DICOM segmentation catalog failed strict local validation.');
  }
  return resolved;
};

const sha256 = async (value: Uint8Array): Promise<string> => {
  const owned = new Uint8Array(value.byteLength);
  owned.set(value);
  const digest = await crypto.subtle.digest('SHA-256', owned.buffer);
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, '0'))
    .join('');
};

export const loadSourceSegmentationMask = async (
  resolved: ResolvedSourceSegmentation,
  segment: SourceSegment,
  signal?: AbortSignal,
): Promise<LoadedSourceSegmentation> => {
  const [depth, rows, columns] = resolved.state.grid.dimensions;
  const expectedBytes = depth * rows * columns;
  const catalogSegment = resolved.state.segments.find(
    (candidate) => candidate.segment_number === segment.segment_number,
  );
  if (
    !Number.isSafeInteger(expectedBytes) ||
    expectedBytes < 1 ||
    expectedBytes > SOURCE_SEGMENTATION_MAX_MASK_BYTES ||
    !catalogSegment
  ) {
    throw new Error('Source-carried DICOM segmentation mask request is invalid.');
  }
  const response = await fetch(
    `${SOURCE_SEGMENTATION_ENDPOINT}/${encodeURIComponent(resolved.state.segmentation_id)}` +
      `/masks/${segment.segment_number}`,
    {
      cache: 'no-store',
      credentials: 'same-origin',
      headers: { Accept: 'application/vnd.scanview.source-binary-mask' },
      signal,
    },
  );
  if (!response.ok) {
    throw new Error(
      response.status === 409 || response.status === 423
        ? 'DICOM SEG inputs changed or failed integrity checks; no mask was displayed.'
        : 'Source-carried DICOM segmentation mask is unavailable.',
    );
  }
  if (
    response.headers.get('Content-Type')?.split(';', 1)[0].trim().toLowerCase() !==
      'application/vnd.scanview.source-binary-mask' ||
    Number(response.headers.get('Content-Length')) !== expectedBytes ||
    response.headers.get('X-Content-SHA256') !== catalogSegment.mask_sha256
  ) {
    throw new Error('Source-carried DICOM segmentation mask headers failed validation.');
  }
  const mask = new Uint8Array(await response.arrayBuffer());
  if (
    mask.byteLength !== expectedBytes ||
    mask.some((value) => value !== 0 && value !== 1) ||
    mask.reduce((sum, value) => sum + value, 0) !== catalogSegment.marked_voxel_count ||
    await sha256(mask) !== catalogSegment.mask_sha256
  ) {
    throw new Error('Source-carried DICOM segmentation mask failed exact local validation.');
  }
  return { state: resolved.state, segment: catalogSegment, series: resolved.series, mask };
};
