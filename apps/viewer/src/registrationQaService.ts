export const REGISTRATION_QA_PREVIEW_ENDPOINT = '/v1/registration-qa/preview';
export const REGISTRATION_REVIEW_ENDPOINT = '/v1/registration-reviews';
export const REGISTRATION_REVIEW_INPUT_MEDIA_TYPE =
  'application/vnd.scanview.registration-review-input+json';
export const REGISTRATION_REVIEW_MEDIA_TYPE =
  'application/vnd.scanview.registration-review+json';
export const MAX_REGISTRATION_QA_ENCODED_VOLUME_BYTES = 512 * 1024 * 1024;
export const MAX_REGISTRATION_QA_ENCODED_MASK_BYTES = 512 * 1024 * 1024;
export const MAX_REGISTRATION_QA_ENCODED_TOTAL_BYTES = 1024 * 1024 * 1024;
export const MAX_REGISTRATION_QA_DECODED_TOTAL_BYTES = 384 * 1024 * 1024;
export const REGISTRATION_QA_COVERAGE_MASK_URL =
  '/v1/registration-qa/files/registered-moving-coverage.nrrd';

export const REGISTRATION_QA_PREVIEW_MODES = [
  'reference_volume_side_by_side',
  'registered_side_by_side',
  'opacity_overlay',
  'swipe_or_flicker',
  'checkerboard',
  'edge_overlay',
  'coverage_mask_boundary',
  'landmark_residuals',
] as const;

export const REGISTRATION_QA_ALWAYS_LOCKED = [
  'subtraction',
  'mask_propagation',
  'segmentation',
  'resampled_image_measurements',
  'response_conclusions',
] as const;

export const REGISTRATION_QA_QUALITATIVE_CHECKS = [
  ['correct_series_roles_and_intended_use_confirmed', 'Correct series, chronological roles, and shared-coverage exploratory use confirmed.'],
  ['full_shared_volume_axial_reviewed', 'Full shared volume reviewed axially.'],
  ['full_shared_volume_coronal_reviewed', 'Full shared volume reviewed coronally.'],
  ['full_shared_volume_sagittal_reviewed', 'Full shared volume reviewed sagittally.'],
  ['native_and_registered_side_by_side_reviewed', 'Native and registered-moving views reviewed side by side.'],
  ['opacity_overlay_reviewed', 'Adjustable opacity overlay reviewed.'],
  ['swipe_or_flicker_reviewed', 'Swipe or flicker comparison reviewed.'],
  ['checkerboard_reviewed', 'Checkerboard comparison reviewed.'],
  ['edge_alignment_reviewed', 'Fixed and registered-moving edge agreement reviewed.'],
  [
    'coverage_mask_boundary_and_excluded_region_reviewed',
    'Moving-image sampling-support mask boundary and excluded regions reviewed; the mask was not interpreted as anatomy, tumor, segmentation, or registration quality.',
  ],
  ['region_of_importance_reviewed', 'Region of greatest importance reviewed.'],
  ['distant_anatomy_reviewed', 'Distant stable anatomy reviewed for global error.'],
  [
    'artifacts_coverage_and_anatomical_change_reviewed',
    'Artifacts, shared coverage, surgery, edema, mass effect, and anatomical change reviewed.',
  ],
  [
    'laterality_and_orientation_reviewed',
    'Laterality, orientation, and gross translation or rotation reviewed.',
  ],
  [
    'no_reject_condition_identified',
    'No global mismatch, material regional mismatch, laterality error, unusable coverage, or rigid-model failure was identified.',
  ],
] as const;

export const REGISTRATION_QA_LIMITATIONS = [
  'Acceptance means only spatially acceptable for exploratory overlay and swipe where the required sampling-support mask is one and shared anatomy was visually reviewed.',
  'The coverage mask identifies transformed moving-image sampling support only; it is not anatomy, tumor, segmentation, registration quality, or clinical comparability.',
  'The sampling-support mask excludes default-filled registered-moving pixels but does not establish shared anatomy.',
  'Reviewer identity, role, training, and organization are self asserted and unauthenticated.',
  'Registration QA does not establish patient identity, clinical baseline, lesion identity, tumor boundary, or response.',
  'Registered-moving pixels are resampled and must remain distinguishable from native DICOM.',
  'Tumor, edema, surgery, artifacts, distortion, mass effect, and coverage changes can make rigid alignment misleading.',
  'Subtraction, segmentation, mask propagation, resampled-image measurements, and response conclusions remain locked.',
  'Landmark residuals depend on point-selection uncertainty and do not replace full-volume qualitative inspection.',
  'This investigational workflow is not validated or cleared for primary diagnosis or treatment planning.',
  'The event SHA-256 and any previous-review reference are tamper evidence only, not a digital signature or reviewer authentication.',
] as const;

export type RegistrationVolumeGeometry = {
  sizes: [number, number, number];
  voxel_spacing_mm: [number, number, number];
  coordinate_system: 'left-posterior-superior' | 'right-anterior-superior';
  space_directions: [
    [number, number, number],
    [number, number, number],
    [number, number, number],
  ];
  space_origin: [number, number, number];
};

export type RegistrationQaVolume = {
  role: string;
  filename: 'fixed.nrrd' | 'moving.nrrd' | 'registered-moving.nrrd';
  url: string;
  bytes: number;
  sha256: string;
  resampled: boolean;
  geometry: RegistrationVolumeGeometry;
};

export type RegistrationQaCoverageMask = {
  role: 'registered_moving_sampling_support_in_fixed_geometry';
  filename: 'registered-moving-coverage.nrrd';
  url: typeof REGISTRATION_QA_COVERAGE_MASK_URL;
  bytes: number;
  sha256: string;
  derived: true;
  scalar_type: 'uint8';
  binary_values: [0, 1];
  semantics: 'technical_sampling_support_not_anatomy_or_segmentation';
  geometry: RegistrationVolumeGeometry;
};

export type RegistrationQaContext = {
  schema_version: '2.0.0';
  artifact_type: 'registration_qa_context';
  mode: 'human_qa_preview';
  qa_preview_only: true;
  watermark: 'UNAPPROVED REGISTRATION — QA ONLY';
  job_id: string;
  artifact_state: 'generated_pending_qa';
  review_status: 'unreviewed';
  source: {
    manifest_sha256: string;
    transform_direction: 'moving_later_to_fixed_earlier';
    modality: 'MR' | 'CT';
    fixed: {
      role: 'fixed_earlier';
      study_id: string;
      series_id: string;
      acquisition_date: string;
    };
    moving: {
      role: 'moving_later';
      study_id: string;
      series_id: string;
      acquisition_date: string;
    };
  };
  volumes: {
    fixed: RegistrationQaVolume;
    moving: RegistrationQaVolume;
    registered_moving: RegistrationQaVolume;
  };
  coverage_mask: RegistrationQaCoverageMask;
  transform: {
    filename: 'moving-to-fixed.tfm';
    sha256: string;
    coordinate_system: 'DICOM patient LPS';
  };
  intended_use: 'shared_coverage_exploratory_overlay_swipe';
  qualitative_checks: { id: string; label: string }[];
  landmark_options: string[];
  landmark_statuses: ('aligned' | 'uncertain' | 'misaligned' | 'not_visible')[];
  allowed_decisions: ('accepted_for_shared_coverage_overlay_swipe' | 'rejected')[];
  display_policy: {
    qa_preview_allowed_while_pending: [...typeof REGISTRATION_QA_PREVIEW_MODES];
    accepted_unlocks: ['overlay', 'swipe'];
    always_locked: [...typeof REGISTRATION_QA_ALWAYS_LOCKED];
    sampling_support_enforcement: 'required_pixel_mask';
    shared_anatomy_scope: 'reviewer_attested_visual_only';
    mask_failure_behavior: 'lock_display';
    mask_sampling: 'nearest_neighbor';
  };
  limitations: [...typeof REGISTRATION_QA_LIMITATIONS];
};

export type LandmarkPairDraft = {
  label: string;
  fixed_physical_mm: [number, number, number];
  registered_moving_physical_mm: [number, number, number];
};

export type RegistrationReviewRequest = {
  schema_version: '2.0.0';
  reviewer: {
    name: string;
    role:
      | 'clinician'
      | 'medical_physicist'
      | 'patient_or_family'
      | 'researcher_or_engineer'
      | 'other';
    organization: string | null;
    training_status: 'self_attested_trained' | 'self_attested_not_trained';
  };
  attest: true;
  decision: 'accepted_for_shared_coverage_overlay_swipe' | 'rejected';
  region_of_importance: string;
  qualitative_checks: Record<string, boolean>;
  inspection_evidence: {
    planes: Partial<
      Record<
        'axial' | 'coronal' | 'sagittal',
        { normalized_min: number; normalized_max: number }
      >
    >;
    modes: ('checkerboard' | 'edges' | 'opacity' | 'swipe')[];
  };
  landmark_observations: {
    landmark: string;
    status: 'aligned' | 'uncertain' | 'misaligned' | 'not_visible';
    note: string;
  }[];
  quantitative_assessment: {
    status: 'recorded' | 'unavailable';
    tolerance_mm: number | null;
    tolerance_basis: string | null;
    pairs: LandmarkPairDraft[];
    unavailable_reason: string | null;
  };
  regional_defects: string[];
  note: string;
};

const isRecord = (value: unknown): value is Record<string, unknown> =>
  Boolean(value && typeof value === 'object' && !Array.isArray(value));

const exactKeys = (value: Record<string, unknown>, keys: string[]): boolean =>
  Object.keys(value).sort().join('|') === [...keys].sort().join('|');

const finiteTuple = (value: unknown): value is [number, number, number] =>
  Array.isArray(value) &&
  value.length === 3 &&
  value.every(
    (item) =>
      typeof item === 'number' &&
      Number.isFinite(item) &&
      Math.abs(item) <= 1_000_000,
  );

const isSha256 = (value: unknown): value is string =>
  typeof value === 'string' && /^[0-9a-f]{64}$/.test(value);

const isOpaque = (value: unknown, prefix: string): value is string =>
  typeof value === 'string' && new RegExp(`^${prefix}_[0-9a-f]{20}$`).test(value);

const sameSequence = (value: unknown, expected: readonly unknown[]): boolean =>
  Array.isArray(value) &&
  value.length === expected.length &&
  value.every((item, index) => {
    const expectedItem = expected[index];
    if (Array.isArray(item) && Array.isArray(expectedItem)) {
      return sameSequence(item, expectedItem);
    }
    return item === expectedItem;
  });

const geometriesEqual = (
  left: RegistrationVolumeGeometry,
  right: RegistrationVolumeGeometry,
): boolean =>
  left.coordinate_system === right.coordinate_system &&
  sameSequence(left.sizes, right.sizes) &&
  sameSequence(left.voxel_spacing_mm, right.voxel_spacing_mm) &&
  sameSequence(left.space_directions, right.space_directions) &&
  sameSequence(left.space_origin, right.space_origin);

const vectorLength = (value: [number, number, number]): number =>
  Math.hypot(value[0], value[1], value[2]);

const directionDeterminant = (directions: RegistrationVolumeGeometry['space_directions']) =>
  directions[0][0] *
    (directions[1][1] * directions[2][2] - directions[2][1] * directions[1][2]) -
  directions[1][0] *
    (directions[0][1] * directions[2][2] - directions[2][1] * directions[0][2]) +
  directions[2][0] *
    (directions[0][1] * directions[1][2] - directions[1][1] * directions[0][2]);

const readGeometry = (value: unknown): RegistrationVolumeGeometry | undefined => {
  if (
    !isRecord(value) ||
    !exactKeys(value, [
      'sizes',
      'voxel_spacing_mm',
      'coordinate_system',
      'space_directions',
      'space_origin',
    ]) ||
    !finiteTuple(value.sizes) ||
    !value.sizes.every((item) => Number.isSafeInteger(item) && item > 0) ||
    !finiteTuple(value.voxel_spacing_mm) ||
    !value.voxel_spacing_mm.every((item) => item > 0) ||
    !['left-posterior-superior', 'right-anterior-superior'].includes(
      String(value.coordinate_system),
    ) ||
    !Array.isArray(value.space_directions) ||
    value.space_directions.length !== 3 ||
    !value.space_directions.every(finiteTuple) ||
    !finiteTuple(value.space_origin)
  ) {
    return undefined;
  }
  const geometry = value as RegistrationVolumeGeometry;
  if (Math.abs(directionDeterminant(geometry.space_directions)) <= 1e-9) {
    return undefined;
  }
  return geometry.space_directions.every((direction, index) => {
    const expected = geometry.voxel_spacing_mm[index];
    return Math.abs(vectorLength(direction) - expected) <= Math.max(1e-6, expected * 1e-6);
  })
    ? geometry
    : undefined;
};

const readVolume = (
  value: unknown,
  filename: RegistrationQaVolume['filename'],
  role: string,
  resampled: boolean,
): RegistrationQaVolume | undefined => {
  if (
    !isRecord(value) ||
    !exactKeys(value, ['role', 'filename', 'url', 'bytes', 'sha256', 'resampled', 'geometry']) ||
    value.filename !== filename ||
    value.url !== `/v1/registration-qa/files/${filename}` ||
    value.role !== role ||
    typeof value.bytes !== 'number' ||
    !Number.isSafeInteger(value.bytes) ||
    value.bytes <= 0 ||
    value.bytes > MAX_REGISTRATION_QA_ENCODED_VOLUME_BYTES ||
    !isSha256(value.sha256) ||
    value.resampled !== resampled
  ) {
    return undefined;
  }
  const geometry = readGeometry(value.geometry);
  return geometry ? ({ ...value, geometry } as RegistrationQaVolume) : undefined;
};

const readCoverageMask = (
  value: unknown,
): RegistrationQaCoverageMask | undefined => {
  if (
    !isRecord(value) ||
    !exactKeys(value, [
      'role',
      'filename',
      'url',
      'bytes',
      'sha256',
      'derived',
      'scalar_type',
      'binary_values',
      'semantics',
      'geometry',
    ]) ||
    value.role !== 'registered_moving_sampling_support_in_fixed_geometry' ||
    value.filename !== 'registered-moving-coverage.nrrd' ||
    value.url !== REGISTRATION_QA_COVERAGE_MASK_URL ||
    typeof value.bytes !== 'number' ||
    !Number.isSafeInteger(value.bytes) ||
    value.bytes <= 0 ||
    value.bytes > MAX_REGISTRATION_QA_ENCODED_MASK_BYTES ||
    !isSha256(value.sha256) ||
    value.derived !== true ||
    value.scalar_type !== 'uint8' ||
    !sameSequence(value.binary_values, [0, 1]) ||
    value.semantics !== 'technical_sampling_support_not_anatomy_or_segmentation'
  ) {
    return undefined;
  }
  const geometry = readGeometry(value.geometry);
  return geometry ? ({ ...value, geometry } as RegistrationQaCoverageMask) : undefined;
};

const isAcquisitionDate = (value: unknown): value is string => {
  if (typeof value !== 'string' || !/^\d{8}$/.test(value)) return false;
  const year = Number(value.slice(0, 4));
  const month = Number(value.slice(4, 6));
  const day = Number(value.slice(6, 8));
  const date = new Date(Date.UTC(year, month - 1, day));
  return (
    date.getUTCFullYear() === year &&
    date.getUTCMonth() === month - 1 &&
    date.getUTCDate() === day
  );
};

const readSourceSide = (
  value: unknown,
  role: 'fixed_earlier' | 'moving_later',
): RegistrationQaContext['source']['fixed'] | undefined => {
  if (
    !isRecord(value) ||
    !exactKeys(value, ['role', 'study_id', 'series_id', 'acquisition_date']) ||
    value.role !== role ||
    !isOpaque(value.study_id, 'study') ||
    !isOpaque(value.series_id, 'series') ||
    !isAcquisitionDate(value.acquisition_date)
  ) {
    return undefined;
  }
  return value as RegistrationQaContext['source']['fixed'];
};

export const readRegistrationQaContext = (
  value: unknown,
): RegistrationQaContext | undefined => {
  if (
    !isRecord(value) ||
    !exactKeys(value, [
      'schema_version',
      'artifact_type',
      'mode',
      'qa_preview_only',
      'watermark',
      'job_id',
      'artifact_state',
      'review_status',
      'source',
      'volumes',
      'coverage_mask',
      'transform',
      'intended_use',
      'qualitative_checks',
      'landmark_options',
      'landmark_statuses',
      'allowed_decisions',
      'display_policy',
      'limitations',
    ]) ||
    value.schema_version !== '2.0.0' ||
    value.artifact_type !== 'registration_qa_context' ||
    value.mode !== 'human_qa_preview' ||
    value.qa_preview_only !== true ||
    value.watermark !== 'UNAPPROVED REGISTRATION — QA ONLY' ||
    !isOpaque(value.job_id, 'registration') ||
    value.artifact_state !== 'generated_pending_qa' ||
    value.review_status !== 'unreviewed' ||
    value.intended_use !== 'shared_coverage_exploratory_overlay_swipe' ||
    !isRecord(value.source) ||
    !isRecord(value.volumes) ||
    !isRecord(value.coverage_mask) ||
    !isRecord(value.transform) ||
    !Array.isArray(value.qualitative_checks) ||
    !Array.isArray(value.landmark_options) ||
    !Array.isArray(value.landmark_statuses) ||
    !Array.isArray(value.allowed_decisions) ||
    !isRecord(value.display_policy) ||
    !Array.isArray(value.limitations)
  ) {
    return undefined;
  }
  const fixed = readSourceSide(value.source.fixed, 'fixed_earlier');
  const moving = readSourceSide(value.source.moving, 'moving_later');
  if (
    !exactKeys(value.source, [
      'manifest_sha256',
      'transform_direction',
      'modality',
      'fixed',
      'moving',
    ]) ||
    !exactKeys(value.volumes, ['fixed', 'moving', 'registered_moving'])
  ) {
    return undefined;
  }
  const fixedVolume = readVolume(
    value.volumes.fixed,
    'fixed.nrrd',
    'fixed_earlier_reference',
    false,
  );
  const movingVolume = readVolume(
    value.volumes.moving,
    'moving.nrrd',
    'moving_later_reference',
    false,
  );
  const registered = readVolume(
    value.volumes.registered_moving,
    'registered-moving.nrrd',
    'moving_later_registered_to_fixed',
    true,
  );
  const coverageMask = readCoverageMask(value.coverage_mask);
  if (
    !fixed ||
    !moving ||
    !fixedVolume ||
    !movingVolume ||
    !registered ||
    !coverageMask ||
    fixed.acquisition_date >= moving.acquisition_date ||
    fixed.study_id === moving.study_id ||
    fixed.series_id === moving.series_id ||
    fixedVolume.bytes + movingVolume.bytes + registered.bytes + coverageMask.bytes >
      MAX_REGISTRATION_QA_ENCODED_TOTAL_BYTES ||
    !geometriesEqual(fixedVolume.geometry, registered.geometry) ||
    !geometriesEqual(fixedVolume.geometry, coverageMask.geometry) ||
    !isSha256(value.source.manifest_sha256) ||
    value.source.transform_direction !== 'moving_later_to_fixed_earlier' ||
    !['MR', 'CT'].includes(String(value.source.modality)) ||
    !exactKeys(value.transform, ['filename', 'sha256', 'coordinate_system']) ||
    value.transform.filename !== 'moving-to-fixed.tfm' ||
    !isSha256(value.transform.sha256) ||
    value.transform.coordinate_system !== 'DICOM patient LPS' ||
    value.qualitative_checks.length !== REGISTRATION_QA_QUALITATIVE_CHECKS.length ||
    !value.qualitative_checks.every((item, index) => {
      const expected = REGISTRATION_QA_QUALITATIVE_CHECKS[index];
      return (
        isRecord(item) &&
        exactKeys(item, ['id', 'label']) &&
        item.id === expected[0] &&
        item.label === expected[1]
      );
    }) ||
    !sameSequence(value.landmark_options, [
      'brainstem',
      'clivus',
      'external_auditory_canals',
      'nose',
      'optic_nerves',
      'orbits',
      'other_stable_landmark',
      'outer_brain_or_skull_boundary',
      'region_of_importance',
      'sagittal_suture',
      'sella_turcica',
      'ventricles',
    ]) ||
    !sameSequence(value.landmark_statuses, [
      'aligned',
      'misaligned',
      'not_visible',
      'uncertain',
    ]) ||
    !sameSequence(value.allowed_decisions, [
      'accepted_for_shared_coverage_overlay_swipe',
      'rejected',
    ]) ||
    !exactKeys(value.display_policy, [
      'qa_preview_allowed_while_pending',
      'accepted_unlocks',
      'always_locked',
      'sampling_support_enforcement',
      'shared_anatomy_scope',
      'mask_failure_behavior',
      'mask_sampling',
    ]) ||
    !sameSequence(value.display_policy.accepted_unlocks, ['overlay', 'swipe']) ||
    !sameSequence(
      value.display_policy.qa_preview_allowed_while_pending,
      REGISTRATION_QA_PREVIEW_MODES,
    ) ||
    !sameSequence(value.display_policy.always_locked, REGISTRATION_QA_ALWAYS_LOCKED) ||
    value.display_policy.sampling_support_enforcement !== 'required_pixel_mask' ||
    value.display_policy.shared_anatomy_scope !== 'reviewer_attested_visual_only' ||
    value.display_policy.mask_failure_behavior !== 'lock_display' ||
    value.display_policy.mask_sampling !== 'nearest_neighbor' ||
    !sameSequence(value.limitations, REGISTRATION_QA_LIMITATIONS)
  ) {
    return undefined;
  }
  return value as RegistrationQaContext;
};

export const loadRegistrationQaContext = async (
  signal?: AbortSignal,
): Promise<
  | { status: 'available'; context: RegistrationQaContext }
  | { status: 'none' }
  | { status: 'error'; message: string }
> => {
  try {
    const response = await fetch(REGISTRATION_QA_PREVIEW_ENDPOINT, {
      cache: 'no-store',
      credentials: 'same-origin',
      headers: { Accept: 'application/json' },
      signal,
    });
    if (response.status === 404) return { status: 'none' };
    if (!response.ok) {
      return {
        status: 'error',
        message: `Local registration QA probe failed (${response.status}).`,
      };
    }
    if (response.headers.get('Content-Type')?.split(';', 1)[0] !== 'application/json') {
      return {
        status: 'error',
        message: 'Local registration QA context has an unexpected media type.',
      };
    }
    const context = readRegistrationQaContext(await response.json());
    return context
      ? { status: 'available', context }
      : { status: 'error', message: 'Local registration QA context failed validation.' };
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      return { status: 'none' };
    }
    return {
      status: 'error',
      message: 'Local registration QA probe could not complete.',
    };
  }
};

const sha256Hex = async (buffer: ArrayBuffer): Promise<string> => {
  const digest = await crypto.subtle.digest('SHA-256', buffer);
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('');
};

const fetchRegistrationQaFile = async (
  descriptor: RegistrationQaVolume | RegistrationQaCoverageMask,
  signal?: AbortSignal,
): Promise<ArrayBuffer> => {
  const isMask = descriptor.filename === 'registered-moving-coverage.nrrd';
  const label = isMask ? 'sampling-support mask' : 'volume';
  const byteLimit = isMask
    ? MAX_REGISTRATION_QA_ENCODED_MASK_BYTES
    : MAX_REGISTRATION_QA_ENCODED_VOLUME_BYTES;
  if (descriptor.bytes > byteLimit) {
    throw new Error(`Local registration QA ${label} exceeds the browser safety limit.`);
  }
  const validatedDescriptor =
    descriptor.filename === 'fixed.nrrd'
      ? readVolume(descriptor, 'fixed.nrrd', 'fixed_earlier_reference', false)
      : descriptor.filename === 'moving.nrrd'
        ? readVolume(descriptor, 'moving.nrrd', 'moving_later_reference', false)
        : descriptor.filename === 'registered-moving.nrrd'
          ? readVolume(
              descriptor,
              'registered-moving.nrrd',
              'moving_later_registered_to_fixed',
              true,
            )
          : descriptor.filename === 'registered-moving-coverage.nrrd'
            ? readCoverageMask(descriptor)
            : undefined;
  if (!validatedDescriptor) {
    throw new Error(`Local registration QA ${label} descriptor failed strict validation.`);
  }
  const response = await fetch(validatedDescriptor.url, {
    cache: 'no-store',
    credentials: 'same-origin',
    headers: { Accept: 'application/vnd.nrrd' },
    signal,
  });
  if (!response.ok) throw new Error(`Local registration QA ${label} could not be loaded.`);
  if (response.headers.get('Content-Type')?.split(';', 1)[0] !== 'application/vnd.nrrd') {
    throw new Error(`Local registration QA ${label} has an unexpected media type.`);
  }
  const declaredLength = Number(response.headers.get('Content-Length'));
  if (!Number.isSafeInteger(declaredLength) || declaredLength !== validatedDescriptor.bytes) {
    throw new Error(`Local registration QA ${label} response byte count changed.`);
  }
  if (response.headers.get('X-Content-SHA256') !== validatedDescriptor.sha256) {
    throw new Error(`Local registration QA ${label} response digest changed.`);
  }
  const buffer = await response.arrayBuffer();
  if (buffer.byteLength !== validatedDescriptor.bytes) {
    throw new Error(`Local registration QA ${label} byte count changed.`);
  }
  if ((await sha256Hex(buffer)) !== validatedDescriptor.sha256) {
    throw new Error(`Local registration QA ${label} SHA-256 changed.`);
  }
  return buffer;
};

export const fetchRegistrationQaVolume = async (
  volume: RegistrationQaVolume,
  signal?: AbortSignal,
): Promise<ArrayBuffer> => fetchRegistrationQaFile(volume, signal);

export const fetchRegistrationQaCoverageMask = async (
  mask: RegistrationQaCoverageMask,
  signal?: AbortSignal,
): Promise<ArrayBuffer> => fetchRegistrationQaFile(mask, signal);

export const submitRegistrationReview = async (
  request: RegistrationReviewRequest,
): Promise<{ bytes: Uint8Array; filename: string }> => {
  const response = await fetch(REGISTRATION_REVIEW_ENDPOINT, {
    method: 'POST',
    cache: 'no-store',
    credentials: 'same-origin',
    headers: {
      Accept: REGISTRATION_REVIEW_MEDIA_TYPE,
      'Content-Type': REGISTRATION_REVIEW_INPUT_MEDIA_TYPE,
    },
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    let detail = 'Local registration QA review was rejected.';
    try {
      const value = (await response.json()) as { detail?: unknown };
      if (typeof value.detail === 'string') detail = value.detail;
    } catch {
      // Keep the privacy-minimized generic message.
    }
    throw new Error(detail);
  }
  if (response.headers.get('Content-Type')?.split(';', 1)[0] !== REGISTRATION_REVIEW_MEDIA_TYPE) {
    throw new Error('Local registration QA review response has an unexpected media type.');
  }
  const disposition = response.headers.get('Content-Disposition') ?? '';
  const filename = /filename="([A-Za-z0-9._-]+)"/.exec(disposition)?.[1];
  if (!filename) throw new Error('Local registration QA review response has no safe filename.');
  return { bytes: new Uint8Array(await response.arrayBuffer()), filename };
};

export const downloadRegistrationReview = (
  bytes: Uint8Array,
  filename: string,
): void => {
  const url = URL.createObjectURL(
    new Blob([bytes as BlobPart], { type: REGISTRATION_REVIEW_MEDIA_TYPE }),
  );
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
};
