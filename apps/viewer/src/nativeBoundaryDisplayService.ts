export const NATIVE_BOUNDARY_CONTEXT_ENDPOINT =
  '/v1/lesion-volume-comparison-display/context';
export const NATIVE_BOUNDARY_MASK_MEDIA_TYPE =
  'application/vnd.scanview.native-binary-mask';
export const MAX_NATIVE_BOUNDARY_MASK_BYTES = 64 * 1024 * 1024;

export const NATIVE_BOUNDARY_ALWAYS_LOCKED = [
  'spatial_overlay',
  'voxelwise_change_localization',
  'subtraction',
  'mask_propagation',
  'response_classification',
  'causal_treatment_attribution',
  'diagnosis',
  'clinical_conclusion',
  'medical_record_signoff',
] as const;

export const NATIVE_BOUNDARY_LIMITATIONS = [
  'Each accepted boundary is displayed only on its own exact native DICOM grid.',
  'The two native coordinate systems are not registered and must never be overlaid, subtracted, or treated as spatially corresponding.',
  'Optional normalized navigation mirrors fractional grid location only; it is approximate navigation, not anatomical alignment.',
  'Reviewer identity, role, and credentials are self asserted and unauthenticated.',
  'The displayed regions are manually painted boundaries whose uncertainty is not quantified.',
  'The pairing reviewer attested same-lesion and represented-tissue judgments for discussion only.',
  'Volume arithmetic can be affected by acquisition, enhancement, edema, necrosis, treatment effect, motion, and partial-volume differences.',
  'No voxelwise change, biological tumor burden, progression, treatment response, treatment causality, diagnosis, or clinical conclusion is established.',
  'Original DICOM images, radiology reports, pathology, treatment history, and the clinical medical record remain authoritative.',
] as const;

export type NativeBoundaryRole = 'baseline' | 'followup';

export type NativeBoundaryTimepoint = {
  role: NativeBoundaryRole;
  review_id: string;
  evidence_artifact_id: string;
  patient_context_id: string;
  study_id: string;
  series_id: string;
  frame_of_reference_id: string;
  modality: 'MR' | 'CT';
  acquisition_date: string;
  series_description: string;
  protocol_name: string | null;
  source_set_sha256: string;
  ordered_instance_ids: string[];
  dimensions: [number, number, number];
  reviewed_volume_ml: number;
  foreground_voxel_count: number;
  mask: {
    url: string;
    bytes: number;
    sha256: string;
    scalar_type: 'uint8';
    binary_values: [0, 1];
    grid_order: 'source_volume_frame_row_column';
  };
  boundary_review: {
    status: 'accepted_for_discussion';
    self_attested: true;
    represented_tissue: string;
    inclusion_criteria: string;
    exclusion_criteria: string;
    boundary_uncertainty: 'not_quantified';
  };
};

export type NativeBoundaryDisplayContext = {
  schema_version: '1.0.0';
  artifact_type: 'lesion_volume_native_boundary_display_context';
  local_only: true;
  sensitive: true;
  deidentified: false;
  display_status: 'authorized_reviewed_native_boundaries_unregistered';
  display_label: 'REVIEWED NATIVE BOUNDARIES — UNREGISTERED';
  comparison_id: string;
  review: {
    decision: 'accepted_for_volume_change_discussion';
    reviewer_role:
      | 'radiologist'
      | 'neuro_oncologist'
      | 'neurosurgeon'
      | 'medical_physicist'
      | 'other_qualified_clinician';
    identity_status: 'self_attested_unverified';
    same_lesion_identity: 'confirmed';
    same_represented_tissue: 'confirmed';
    acquisition_comparability: 'suitable' | 'suitable_with_limitations';
    boundary_comparability: 'suitable' | 'suitable_with_limitations';
    registration_consideration:
      | 'not_required'
      | 'recommended_before_spatial_comparison'
      | 'required_before_spatial_comparison';
    limitation_note: string;
    treatment_context_note: string;
  };
  comparison: {
    status: 'qualified_pairing_review_for_discussion_only';
    method: 'followup_reviewed_volume_minus_baseline_reviewed_volume';
    baseline_volume_ml: number;
    followup_volume_ml: number;
    absolute_change_ml: number;
    percent_change: number;
    numeric_direction: 'increased' | 'decreased' | 'unchanged';
    elapsed_days: number;
    boundary_uncertainty: 'not_quantified';
    response_assessment: 'not_performed';
    causal_treatment_attribution: false;
    interpretations: [];
  };
  timepoints: {
    baseline: NativeBoundaryTimepoint;
    followup: NativeBoundaryTimepoint;
  };
  navigation_policy: {
    default_linked: false;
    link_mode: 'normalized_native_grid_fraction';
    approximate_navigation_only: true;
    anatomical_correspondence: false;
    registered: false;
    independent_navigation_available: true;
  };
  display_policy: {
    allowed_modes: ['native_side_by_side', 'normalized_navigation_link'];
    always_locked: [...typeof NATIVE_BOUNDARY_ALWAYS_LOCKED];
    masks_read_only: true;
    native_dicom_required: true;
  };
  limitations: [...typeof NATIVE_BOUNDARY_LIMITATIONS];
};

export type NativeBoundaryProbeResult =
  | { status: 'available'; context: NativeBoundaryDisplayContext }
  | { status: 'none' }
  | { status: 'error'; message: string };

const isRecord = (value: unknown): value is Record<string, unknown> =>
  Boolean(value && typeof value === 'object' && !Array.isArray(value));

const exactKeys = (value: Record<string, unknown>, keys: readonly string[]): boolean =>
  Object.keys(value).sort().join('|') === [...keys].sort().join('|');

const sameSequence = (value: unknown, expected: readonly unknown[]): boolean =>
  Array.isArray(value) &&
  value.length === expected.length &&
  value.every((item, index) => item === expected[index]);

const isSha256 = (value: unknown): value is string =>
  typeof value === 'string' && /^[0-9a-f]{64}$/.test(value);

const isOpaque = (value: unknown, prefix: string): value is string =>
  typeof value === 'string' && new RegExp(`^${prefix}_[0-9a-f]{20}$`).test(value);

const isUuidId = (value: unknown, prefix: string): value is string =>
  typeof value === 'string' &&
  new RegExp(`^${prefix}_[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$`).test(
    value,
  );

const finite = (value: unknown): value is number =>
  typeof value === 'number' && Number.isFinite(value);

const close = (left: number, right: number): boolean =>
  Math.abs(left - right) <= Math.max(1e-12, Math.abs(right) * 1e-12);

const validDate = (value: unknown): value is string => {
  if (typeof value !== 'string' || !/^\d{8}$/.test(value)) return false;
  const year = Number(value.slice(0, 4));
  const month = Number(value.slice(4, 6));
  const day = Number(value.slice(6, 8));
  const parsed = new Date(Date.UTC(year, month - 1, day));
  return (
    parsed.getUTCFullYear() === year &&
    parsed.getUTCMonth() === month - 1 &&
    parsed.getUTCDate() === day
  );
};

const dateEpochDay = (value: string): number =>
  Date.UTC(Number(value.slice(0, 4)), Number(value.slice(4, 6)) - 1, Number(value.slice(6, 8))) /
  86_400_000;

const validText = (value: unknown, maximum: number, optional = false): value is string =>
  typeof value === 'string' &&
  value.length <= maximum &&
  (optional || value.trim().length > 0) &&
  !/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/u.test(value);

const readTimepoint = (
  value: unknown,
  role: NativeBoundaryRole,
): NativeBoundaryTimepoint | undefined => {
  if (
    !isRecord(value) ||
    !exactKeys(value, [
      'role',
      'review_id',
      'evidence_artifact_id',
      'patient_context_id',
      'study_id',
      'series_id',
      'frame_of_reference_id',
      'modality',
      'acquisition_date',
      'series_description',
      'protocol_name',
      'source_set_sha256',
      'ordered_instance_ids',
      'dimensions',
      'reviewed_volume_ml',
      'foreground_voxel_count',
      'mask',
      'boundary_review',
    ]) ||
    value.role !== role ||
    !isUuidId(value.review_id, 'review') ||
    !isUuidId(value.evidence_artifact_id, 'seg') ||
    !isOpaque(value.patient_context_id, 'patient') ||
    !isOpaque(value.study_id, 'study') ||
    !isOpaque(value.series_id, 'series') ||
    !isOpaque(value.frame_of_reference_id, 'frame') ||
    !['MR', 'CT'].includes(String(value.modality)) ||
    !validDate(value.acquisition_date) ||
    !validText(value.series_description, 300) ||
    !(value.protocol_name === null || validText(value.protocol_name, 300)) ||
    !isSha256(value.source_set_sha256) ||
    !Array.isArray(value.dimensions) ||
    value.dimensions.length !== 3 ||
    !value.dimensions.every(
      (item) => Number.isSafeInteger(item) && item >= 2 && item <= MAX_NATIVE_BOUNDARY_MASK_BYTES,
    ) ||
    !Array.isArray(value.ordered_instance_ids) ||
    value.ordered_instance_ids.length !== value.dimensions[2] ||
    new Set(value.ordered_instance_ids).size !== value.ordered_instance_ids.length ||
    !value.ordered_instance_ids.every((item) => isOpaque(item, 'instance')) ||
    !finite(value.reviewed_volume_ml) ||
    value.reviewed_volume_ml <= 0 ||
    typeof value.foreground_voxel_count !== 'number' ||
    !Number.isSafeInteger(value.foreground_voxel_count) ||
    value.foreground_voxel_count < 1 ||
    !isRecord(value.mask) ||
    !isRecord(value.boundary_review)
  ) {
    return undefined;
  }
  const voxelCount = value.dimensions[0] * value.dimensions[1] * value.dimensions[2];
  const expectedUrl = `/v1/lesion-volume-comparison-display/masks/${role}`;
  if (
    !Number.isSafeInteger(voxelCount) ||
    voxelCount > MAX_NATIVE_BOUNDARY_MASK_BYTES ||
    value.foreground_voxel_count > voxelCount ||
    !exactKeys(value.mask, [
      'url',
      'bytes',
      'sha256',
      'scalar_type',
      'binary_values',
      'grid_order',
    ]) ||
    value.mask.url !== expectedUrl ||
    value.mask.bytes !== voxelCount ||
    !isSha256(value.mask.sha256) ||
    value.mask.scalar_type !== 'uint8' ||
    !sameSequence(value.mask.binary_values, [0, 1]) ||
    value.mask.grid_order !== 'source_volume_frame_row_column' ||
    !exactKeys(value.boundary_review, [
      'status',
      'self_attested',
      'represented_tissue',
      'inclusion_criteria',
      'exclusion_criteria',
      'boundary_uncertainty',
    ]) ||
    value.boundary_review.status !== 'accepted_for_discussion' ||
    value.boundary_review.self_attested !== true ||
    !validText(value.boundary_review.represented_tissue, 500) ||
    !validText(value.boundary_review.inclusion_criteria, 2000) ||
    !validText(value.boundary_review.exclusion_criteria, 2000) ||
    value.boundary_review.boundary_uncertainty !== 'not_quantified'
  ) {
    return undefined;
  }
  return value as NativeBoundaryTimepoint;
};

export const readNativeBoundaryDisplayContext = (
  value: unknown,
): NativeBoundaryDisplayContext | undefined => {
  if (
    !isRecord(value) ||
    !exactKeys(value, [
      'schema_version',
      'artifact_type',
      'local_only',
      'sensitive',
      'deidentified',
      'display_status',
      'display_label',
      'comparison_id',
      'review',
      'comparison',
      'timepoints',
      'navigation_policy',
      'display_policy',
      'limitations',
    ]) ||
    value.schema_version !== '1.0.0' ||
    value.artifact_type !== 'lesion_volume_native_boundary_display_context' ||
    value.local_only !== true ||
    value.sensitive !== true ||
    value.deidentified !== false ||
    value.display_status !== 'authorized_reviewed_native_boundaries_unregistered' ||
    value.display_label !== 'REVIEWED NATIVE BOUNDARIES — UNREGISTERED' ||
    !isUuidId(value.comparison_id, 'volume_pair') ||
    !isRecord(value.review) ||
    !isRecord(value.comparison) ||
    !isRecord(value.timepoints) ||
    !isRecord(value.navigation_policy) ||
    !isRecord(value.display_policy)
  ) {
    return undefined;
  }
  if (
    !exactKeys(value.review, [
      'decision',
      'reviewer_role',
      'identity_status',
      'same_lesion_identity',
      'same_represented_tissue',
      'acquisition_comparability',
      'boundary_comparability',
      'registration_consideration',
      'limitation_note',
      'treatment_context_note',
    ]) ||
    value.review.decision !== 'accepted_for_volume_change_discussion' ||
    ![
      'radiologist',
      'neuro_oncologist',
      'neurosurgeon',
      'medical_physicist',
      'other_qualified_clinician',
    ].includes(String(value.review.reviewer_role)) ||
    value.review.identity_status !== 'self_attested_unverified' ||
    value.review.same_lesion_identity !== 'confirmed' ||
    value.review.same_represented_tissue !== 'confirmed' ||
    !['suitable', 'suitable_with_limitations'].includes(
      String(value.review.acquisition_comparability),
    ) ||
    !['suitable', 'suitable_with_limitations'].includes(
      String(value.review.boundary_comparability),
    ) ||
    ![
      'not_required',
      'recommended_before_spatial_comparison',
      'required_before_spatial_comparison',
    ].includes(String(value.review.registration_consideration)) ||
    !validText(value.review.limitation_note, 2000, true) ||
    !validText(value.review.treatment_context_note, 2000, true)
  ) {
    return undefined;
  }
  const baseline = readTimepoint(value.timepoints.baseline, 'baseline');
  const followup = readTimepoint(value.timepoints.followup, 'followup');
  if (
    !exactKeys(value.timepoints, ['baseline', 'followup']) ||
    !baseline ||
    !followup ||
    baseline.patient_context_id !== followup.patient_context_id ||
    baseline.modality !== followup.modality ||
    baseline.acquisition_date >= followup.acquisition_date ||
    baseline.study_id === followup.study_id ||
    baseline.series_id === followup.series_id ||
    baseline.review_id === followup.review_id ||
    baseline.evidence_artifact_id === followup.evidence_artifact_id
  ) {
    return undefined;
  }
  const expectedChange = followup.reviewed_volume_ml - baseline.reviewed_volume_ml;
  const expectedElapsedDays =
    dateEpochDay(followup.acquisition_date) - dateEpochDay(baseline.acquisition_date);
  const expectedDirection =
    expectedChange > 0 ? 'increased' : expectedChange < 0 ? 'decreased' : 'unchanged';
  if (
    !exactKeys(value.comparison, [
      'status',
      'method',
      'baseline_volume_ml',
      'followup_volume_ml',
      'absolute_change_ml',
      'percent_change',
      'numeric_direction',
      'elapsed_days',
      'boundary_uncertainty',
      'response_assessment',
      'causal_treatment_attribution',
      'interpretations',
    ]) ||
    value.comparison.status !== 'qualified_pairing_review_for_discussion_only' ||
    value.comparison.method !==
      'followup_reviewed_volume_minus_baseline_reviewed_volume' ||
    !finite(value.comparison.baseline_volume_ml) ||
    !finite(value.comparison.followup_volume_ml) ||
    !finite(value.comparison.absolute_change_ml) ||
    !finite(value.comparison.percent_change) ||
    !close(value.comparison.baseline_volume_ml, baseline.reviewed_volume_ml) ||
    !close(value.comparison.followup_volume_ml, followup.reviewed_volume_ml) ||
    !close(value.comparison.absolute_change_ml, expectedChange) ||
    !close(
      value.comparison.percent_change,
      (expectedChange / baseline.reviewed_volume_ml) * 100,
    ) ||
    value.comparison.numeric_direction !== expectedDirection ||
    typeof value.comparison.elapsed_days !== 'number' ||
    !Number.isSafeInteger(value.comparison.elapsed_days) ||
    value.comparison.elapsed_days !== expectedElapsedDays ||
    value.comparison.boundary_uncertainty !== 'not_quantified' ||
    value.comparison.response_assessment !== 'not_performed' ||
    value.comparison.causal_treatment_attribution !== false ||
    !sameSequence(value.comparison.interpretations, [])
  ) {
    return undefined;
  }
  if (
    !exactKeys(value.navigation_policy, [
      'default_linked',
      'link_mode',
      'approximate_navigation_only',
      'anatomical_correspondence',
      'registered',
      'independent_navigation_available',
    ]) ||
    value.navigation_policy.default_linked !== false ||
    value.navigation_policy.link_mode !== 'normalized_native_grid_fraction' ||
    value.navigation_policy.approximate_navigation_only !== true ||
    value.navigation_policy.anatomical_correspondence !== false ||
    value.navigation_policy.registered !== false ||
    value.navigation_policy.independent_navigation_available !== true ||
    !exactKeys(value.display_policy, [
      'allowed_modes',
      'always_locked',
      'masks_read_only',
      'native_dicom_required',
    ]) ||
    !sameSequence(value.display_policy.allowed_modes, [
      'native_side_by_side',
      'normalized_navigation_link',
    ]) ||
    !sameSequence(value.display_policy.always_locked, NATIVE_BOUNDARY_ALWAYS_LOCKED) ||
    value.display_policy.masks_read_only !== true ||
    value.display_policy.native_dicom_required !== true ||
    !sameSequence(value.limitations, NATIVE_BOUNDARY_LIMITATIONS)
  ) {
    return undefined;
  }
  return value as NativeBoundaryDisplayContext;
};

export const loadNativeBoundaryDisplayContext = async (
  signal?: AbortSignal,
): Promise<NativeBoundaryProbeResult> => {
  try {
    const response = await fetch(NATIVE_BOUNDARY_CONTEXT_ENDPOINT, {
      cache: 'no-store',
      credentials: 'same-origin',
      headers: { Accept: 'application/json' },
      signal,
    });
    if (response.status === 404) return { status: 'none' };
    if (!response.ok) {
      return {
        status: 'error',
        message: `Reviewed native-boundary display is locked or unavailable (${response.status}).`,
      };
    }
    if (response.headers.get('Content-Type')?.split(';', 1)[0] !== 'application/json') {
      return {
        status: 'error',
        message: 'Reviewed native-boundary context has an unexpected media type.',
      };
    }
    const context = readNativeBoundaryDisplayContext(await response.json());
    return context
      ? { status: 'available', context }
      : {
          status: 'error',
          message: 'Reviewed native-boundary context failed strict validation.',
        };
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      return { status: 'none' };
    }
    return {
      status: 'error',
      message: 'Reviewed native-boundary display probe could not complete.',
    };
  }
};

const sha256Hex = async (buffer: ArrayBuffer): Promise<string> => {
  const digest = await crypto.subtle.digest('SHA-256', buffer);
  return Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, '0'),
  ).join('');
};

export const fetchNativeBoundaryMask = async (
  timepoint: NativeBoundaryTimepoint,
  signal?: AbortSignal,
): Promise<Uint8Array> => {
  const validated = readTimepoint(timepoint, timepoint.role);
  if (!validated) throw new Error('Native-boundary mask descriptor failed validation.');
  const response = await fetch(validated.mask.url, {
    cache: 'no-store',
    credentials: 'same-origin',
    headers: { Accept: NATIVE_BOUNDARY_MASK_MEDIA_TYPE },
    signal,
  });
  if (!response.ok) throw new Error('Reviewed native-boundary mask could not be loaded.');
  if (
    response.headers.get('Content-Type')?.split(';', 1)[0] !==
    NATIVE_BOUNDARY_MASK_MEDIA_TYPE
  ) {
    throw new Error('Reviewed native-boundary mask has an unexpected media type.');
  }
  const declaredLength = Number(response.headers.get('Content-Length'));
  if (declaredLength !== validated.mask.bytes) {
    throw new Error('Reviewed native-boundary mask response byte count changed.');
  }
  if (response.headers.get('X-Content-SHA256') !== validated.mask.sha256) {
    throw new Error('Reviewed native-boundary mask response digest changed.');
  }
  const buffer = await response.arrayBuffer();
  if (
    buffer.byteLength !== validated.mask.bytes ||
    (await sha256Hex(buffer)) !== validated.mask.sha256
  ) {
    throw new Error('Reviewed native-boundary mask integrity check failed.');
  }
  const mask = new Uint8Array(buffer);
  let foreground = 0;
  for (const value of mask) {
    if (value !== 0 && value !== 1) {
      throw new Error('Reviewed native-boundary mask is not strictly binary.');
    }
    foreground += value;
  }
  if (foreground !== validated.foreground_voxel_count) {
    throw new Error('Reviewed native-boundary foreground count changed.');
  }
  return mask;
};

export const nativeBoundaryMaskCentroid = (
  mask: Uint8Array,
  dimensions: [number, number, number],
): [number, number, number] => {
  const [columns, rows, slices] = dimensions;
  if (
    !dimensions.every((value) => Number.isSafeInteger(value) && value >= 2) ||
    mask.length !== columns * rows * slices
  ) {
    throw new Error('Reviewed native-boundary centroid requires the exact source grid.');
  }
  let foreground = 0;
  let sumColumn = 0;
  let sumRow = 0;
  let sumSlice = 0;
  const frameSize = columns * rows;
  for (let index = 0; index < mask.length; index += 1) {
    const value = mask[index];
    if (value !== 0 && value !== 1) {
      throw new Error('Reviewed native-boundary centroid requires a binary mask.');
    }
    if (value === 0) continue;
    const slice = Math.floor(index / frameSize);
    const inFrame = index - slice * frameSize;
    foreground += 1;
    sumColumn += inFrame % columns;
    sumRow += Math.floor(inFrame / columns);
    sumSlice += slice;
  }
  if (foreground === 0) throw new Error('Reviewed native boundary is empty.');
  return [
    sumColumn / foreground / (columns - 1),
    sumRow / foreground / (rows - 1),
    sumSlice / foreground / (slices - 1),
  ];
};
