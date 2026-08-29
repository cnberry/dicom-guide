export const REGISTRATION_QA_PREVIEW_ENDPOINT = '/v1/registration-qa/preview';
export const REGISTRATION_REVIEW_ENDPOINT = '/v1/registration-reviews';
export const REGISTRATION_REVIEW_INPUT_MEDIA_TYPE =
  'application/vnd.scanview.registration-review-input+json';
export const REGISTRATION_REVIEW_MEDIA_TYPE =
  'application/vnd.scanview.registration-review+json';
export const MAX_REGISTRATION_QA_ENCODED_VOLUME_BYTES = 512 * 1024 * 1024;
export const MAX_REGISTRATION_QA_ENCODED_TOTAL_BYTES = 1024 * 1024 * 1024;

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

export type RegistrationQaContext = {
  schema_version: '1.0.0';
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
    qa_preview_allowed_while_pending: string[];
    accepted_unlocks: ['overlay', 'swipe'];
    always_locked: string[];
  };
  limitations: string[];
};

export type LandmarkPairDraft = {
  label: string;
  fixed_physical_mm: [number, number, number];
  registered_moving_physical_mm: [number, number, number];
};

export type RegistrationReviewRequest = {
  schema_version: '1.0.0';
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
  attest: boolean;
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
  value.every((item) => typeof item === 'number' && Number.isFinite(item));

const isSha256 = (value: unknown): value is string =>
  typeof value === 'string' && /^[0-9a-f]{64}$/.test(value);

const isOpaque = (value: unknown, prefix: string): value is string =>
  typeof value === 'string' && new RegExp(`^${prefix}_[0-9a-f]{20}$`).test(value);

const sameStringSet = (value: unknown, expected: string[]): boolean =>
  Array.isArray(value) &&
  value.length === expected.length &&
  value.every((item) => typeof item === 'string') &&
  [...value].sort().every((item, index) => item === [...expected].sort()[index]);

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
  return Math.abs(directionDeterminant(geometry.space_directions)) > 1e-9
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
    !isSha256(value.sha256) ||
    value.resampled !== resampled
  ) {
    return undefined;
  }
  const geometry = readGeometry(value.geometry);
  return geometry ? ({ ...value, geometry } as RegistrationQaVolume) : undefined;
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
    typeof value.acquisition_date !== 'string' ||
    !/^[0-9]{8}$/.test(value.acquisition_date)
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
      'transform',
      'intended_use',
      'qualitative_checks',
      'landmark_options',
      'landmark_statuses',
      'allowed_decisions',
      'display_policy',
      'limitations',
    ]) ||
    value.schema_version !== '1.0.0' ||
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
  if (
    !fixed ||
    !moving ||
    !fixedVolume ||
    !movingVolume ||
    !registered ||
    !isSha256(value.source.manifest_sha256) ||
    value.source.transform_direction !== 'moving_later_to_fixed_earlier' ||
    !['MR', 'CT'].includes(String(value.source.modality)) ||
    !exactKeys(value.transform, ['filename', 'sha256', 'coordinate_system']) ||
    value.transform.filename !== 'moving-to-fixed.tfm' ||
    !isSha256(value.transform.sha256) ||
    value.transform.coordinate_system !== 'DICOM patient LPS' ||
    !value.qualitative_checks.every(
      (item) =>
        isRecord(item) &&
        exactKeys(item, ['id', 'label']) &&
        typeof item.id === 'string' &&
        /^[a-z][a-z0-9_]{1,79}$/.test(item.id) &&
        typeof item.label === 'string' &&
        item.label.length >= 1 &&
        item.label.length <= 500,
    ) ||
    new Set(
      value.qualitative_checks.flatMap((item) =>
        isRecord(item) && typeof item.id === 'string' ? [item.id] : [],
      ),
    ).size !== value.qualitative_checks.length ||
    !value.landmark_options.every((item) => typeof item === 'string') ||
    !value.landmark_statuses.every((item) =>
      ['aligned', 'uncertain', 'misaligned', 'not_visible'].includes(String(item)),
    ) ||
    !sameStringSet(value.allowed_decisions, [
      'accepted_for_shared_coverage_overlay_swipe',
      'rejected',
    ]) ||
    !exactKeys(value.display_policy, [
      'qa_preview_allowed_while_pending',
      'accepted_unlocks',
      'always_locked',
    ]) ||
    !sameStringSet(value.display_policy.accepted_unlocks, ['overlay', 'swipe']) ||
    !sameStringSet(value.display_policy.qa_preview_allowed_while_pending, [
      'reference_volume_side_by_side',
      'registered_side_by_side',
      'opacity_overlay',
      'swipe_or_flicker',
      'checkerboard',
      'edge_overlay',
      'landmark_residuals',
    ]) ||
    !sameStringSet(value.display_policy.always_locked, [
      'subtraction',
      'mask_propagation',
      'segmentation',
      'resampled_image_measurements',
      'response_conclusions',
    ]) ||
    !value.limitations.every(
      (item) => typeof item === 'string' && item.length >= 1 && item.length <= 300,
    )
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

export const fetchRegistrationQaVolume = async (
  volume: RegistrationQaVolume,
  signal?: AbortSignal,
): Promise<ArrayBuffer> => {
  if (volume.bytes > MAX_REGISTRATION_QA_ENCODED_VOLUME_BYTES) {
    throw new Error('Local registration QA volume exceeds the browser safety limit.');
  }
  const response = await fetch(volume.url, {
    cache: 'no-store',
    credentials: 'same-origin',
    headers: { Accept: 'application/vnd.nrrd' },
    signal,
  });
  if (!response.ok) throw new Error('Local registration QA volume could not be loaded.');
  if (response.headers.get('Content-Type')?.split(';', 1)[0] !== 'application/vnd.nrrd') {
    throw new Error('Local registration QA volume has an unexpected media type.');
  }
  const declaredLength = Number(response.headers.get('Content-Length'));
  if (!Number.isSafeInteger(declaredLength) || declaredLength !== volume.bytes) {
    throw new Error('Local registration QA response byte count changed.');
  }
  const buffer = await response.arrayBuffer();
  if (buffer.byteLength !== volume.bytes) {
    throw new Error('Local registration QA volume byte count changed.');
  }
  if ((await sha256Hex(buffer)) !== volume.sha256) {
    throw new Error('Local registration QA volume SHA-256 changed.');
  }
  return buffer;
};

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
