export const REVIEWED_REGISTRATION_DISPLAY_ENDPOINT =
  '/v1/reviewed-registration/display';
export const REVIEWED_REGISTRATION_FIXED_URL =
  '/v1/reviewed-registration/files/fixed.nrrd';
export const REVIEWED_REGISTRATION_MOVING_URL =
  '/v1/reviewed-registration/files/registered-moving.nrrd';
export const MAX_REVIEWED_REGISTRATION_ENCODED_VOLUME_BYTES = 256 * 1024 * 1024;
export const MAX_REVIEWED_REGISTRATION_ENCODED_TOTAL_BYTES = 384 * 1024 * 1024;
export const MAX_REVIEWED_REGISTRATION_DECODED_TOTAL_BYTES = 256 * 1024 * 1024;

export const REVIEWED_REGISTRATION_ALLOWED_MODES = ['opacity', 'swipe'] as const;
export const REVIEWED_REGISTRATION_ALWAYS_LOCKED = [
  'subtraction',
  'mask_propagation',
  'segmentation',
  'resampled_image_measurements',
  'response_conclusions',
] as const;
export const REVIEWED_REGISTRATION_LIMITATIONS = [
  'Authorization applies only where both derived volumes contain anatomy; display outside their shared anatomical coverage is unauthorized.',
  'The bundle contains no pixel-level transformed moving-coverage mask; shared coverage is enforced only by reviewer visual inspection.',
  'Reviewer identity, role, training, and organization are self asserted and unauthenticated.',
  'The fixed volume is a derived local scalar-volume representation that preserves fixed geometry; it is not native DICOM.',
  'The registered-moving volume is derived and interpolated into fixed geometry; it is not native DICOM.',
  'Subtraction, mask propagation, segmentation, resampled-image measurements, and response conclusions remain prohibited.',
  'This authorization is bound to the exact saved review and live six-file registration bundle hashes and geometry.',
  'This exploratory display is not a diagnosis, treatment-response conclusion, or authorization for treatment planning.',
  'The review event SHA-256 and saved-review SHA-256 provide tamper evidence, not a digital signature or reviewer authentication.',
] as const;

export type ReviewedRegistrationMode =
  (typeof REVIEWED_REGISTRATION_ALLOWED_MODES)[number];

export type ReviewedRegistrationGeometry = {
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

export type ReviewedRegistrationVolume = {
  role: 'fixed_earlier_reference' | 'moving_later_registered_to_fixed';
  filename: 'fixed.nrrd' | 'registered-moving.nrrd';
  url:
    | typeof REVIEWED_REGISTRATION_FIXED_URL
    | typeof REVIEWED_REGISTRATION_MOVING_URL;
  bytes: number;
  sha256: string;
  derived: true;
  resampled: boolean;
  geometry: ReviewedRegistrationGeometry;
};

export type ReviewedRegistrationContext = {
  schema_version: '1.0.0';
  artifact_type: 'reviewed_registration_display_context';
  sensitive: true;
  deidentified: false;
  display_status: 'authorized_for_exploratory_shared_coverage_overlay_swipe';
  intended_use: 'shared_coverage_exploratory_overlay_swipe';
  scope: 'shared_coverage';
  display_label: 'EXPLORATORY — SELF-ATTESTED REGISTRATION QA';
  review: {
    review_id: string;
    job_id: string;
    decision: 'accepted_for_shared_coverage_overlay_swipe';
    review_sha256: string;
    event_sha256: string;
    self_attested: true;
  };
  source: {
    manifest_sha256: string;
    transform_sha256: string;
    bundle_sha256: string;
    bundle_files: {
      name:
        | 'engine-report.json'
        | 'fixed.nrrd'
        | 'moving-to-fixed.tfm'
        | 'moving.nrrd'
        | 'registered-moving.nrrd'
        | 'registration.json';
      bytes: number;
      sha256: string;
    }[];
    transform_direction: 'moving_later_to_fixed_earlier';
    modality: 'MR' | 'CT';
    fixed: {
      study_id: string;
      series_id: string;
      acquisition_date: string;
    };
    moving: {
      study_id: string;
      series_id: string;
      acquisition_date: string;
    };
  };
  reviewer: {
    role: 'clinician' | 'medical_physicist';
    training_status: 'self_attested_trained';
    identity_status: 'self_attested_unverified';
  };
  volumes: {
    fixed: ReviewedRegistrationVolume;
    registered_moving: ReviewedRegistrationVolume;
  };
  display_policy: {
    allowed_modes: [...typeof REVIEWED_REGISTRATION_ALLOWED_MODES];
    always_locked: [...typeof REVIEWED_REGISTRATION_ALWAYS_LOCKED];
    native_moving_available: false;
    native_moving_withheld: true;
    shared_coverage_enforcement: 'reviewer_visual_only_no_machine_mask';
  };
  limitations: [...typeof REVIEWED_REGISTRATION_LIMITATIONS];
};

export type ReviewedRegistrationProbeResult =
  | { status: 'available'; context: ReviewedRegistrationContext }
  | { status: 'none' }
  | { status: 'error'; message: string };

const BUNDLE_FILE_NAMES = [
  'engine-report.json',
  'fixed.nrrd',
  'moving-to-fixed.tfm',
  'moving.nrrd',
  'registered-moving.nrrd',
  'registration.json',
] as const;

const isRecord = (value: unknown): value is Record<string, unknown> =>
  Boolean(value && typeof value === 'object' && !Array.isArray(value));

const exactKeys = (value: Record<string, unknown>, keys: readonly string[]): boolean =>
  Object.keys(value).sort().join('|') === [...keys].sort().join('|');

const isSha256 = (value: unknown): value is string =>
  typeof value === 'string' && /^[0-9a-f]{64}$/.test(value);

const isOpaque = (value: unknown, prefix: string): value is string =>
  typeof value === 'string' && new RegExp(`^${prefix}_[0-9a-f]{20}$`).test(value);

const finiteTuple = (value: unknown): value is [number, number, number] =>
  Array.isArray(value) &&
  value.length === 3 &&
  value.every(
    (item) =>
      typeof item === 'number' &&
      Number.isFinite(item) &&
      Math.abs(item) <= 1_000_000,
  );

const sameStringSequence = (value: unknown, expected: readonly string[]): boolean =>
  Array.isArray(value) &&
  value.length === expected.length &&
  value.every((item, index) => item === expected[index]);

const arraysEqual = (left: unknown, right: unknown): boolean => {
  if (!Array.isArray(left) || !Array.isArray(right) || left.length !== right.length) {
    return left === right;
  }
  return left.every((item, index) => arraysEqual(item, right[index]));
};

const geometriesEqual = (
  left: ReviewedRegistrationGeometry,
  right: ReviewedRegistrationGeometry,
): boolean =>
  left.coordinate_system === right.coordinate_system &&
  arraysEqual(left.sizes, right.sizes) &&
  arraysEqual(left.voxel_spacing_mm, right.voxel_spacing_mm) &&
  arraysEqual(left.space_directions, right.space_directions) &&
  arraysEqual(left.space_origin, right.space_origin);

const vectorLength = (value: [number, number, number]): number =>
  Math.hypot(value[0], value[1], value[2]);

const directionDeterminant = (
  directions: ReviewedRegistrationGeometry['space_directions'],
): number =>
  directions[0][0] *
    (directions[1][1] * directions[2][2] - directions[2][1] * directions[1][2]) -
  directions[1][0] *
    (directions[0][1] * directions[2][2] - directions[2][1] * directions[0][2]) +
  directions[2][0] *
    (directions[0][1] * directions[1][2] - directions[1][1] * directions[0][2]);

const readGeometry = (value: unknown): ReviewedRegistrationGeometry | undefined => {
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
  const geometry = value as ReviewedRegistrationGeometry;
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
  expected: {
    role: ReviewedRegistrationVolume['role'];
    filename: ReviewedRegistrationVolume['filename'];
    url: ReviewedRegistrationVolume['url'];
    resampled: boolean;
  },
): ReviewedRegistrationVolume | undefined => {
  if (
    !isRecord(value) ||
    !exactKeys(value, [
      'role',
      'filename',
      'url',
      'bytes',
      'sha256',
      'derived',
      'resampled',
      'geometry',
    ]) ||
    value.role !== expected.role ||
    value.filename !== expected.filename ||
    value.url !== expected.url ||
    typeof value.bytes !== 'number' ||
    !Number.isSafeInteger(value.bytes) ||
    value.bytes <= 0 ||
    value.bytes > MAX_REVIEWED_REGISTRATION_ENCODED_VOLUME_BYTES ||
    !isSha256(value.sha256) ||
    value.derived !== true ||
    value.resampled !== expected.resampled
  ) {
    return undefined;
  }
  const geometry = readGeometry(value.geometry);
  return geometry ? ({ ...value, geometry } as ReviewedRegistrationVolume) : undefined;
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

const readSourceSide = (value: unknown): ReviewedRegistrationContext['source']['fixed'] | undefined => {
  if (
    !isRecord(value) ||
    !exactKeys(value, ['study_id', 'series_id', 'acquisition_date']) ||
    !isOpaque(value.study_id, 'study') ||
    !isOpaque(value.series_id, 'series') ||
    !isAcquisitionDate(value.acquisition_date)
  ) {
    return undefined;
  }
  return value as ReviewedRegistrationContext['source']['fixed'];
};

const readBundleFiles = (
  value: unknown,
): ReviewedRegistrationContext['source']['bundle_files'] | undefined => {
  if (!Array.isArray(value) || value.length !== BUNDLE_FILE_NAMES.length) return undefined;
  if (
    !value.every(
      (item, index) =>
        isRecord(item) &&
        exactKeys(item, ['name', 'bytes', 'sha256']) &&
        item.name === BUNDLE_FILE_NAMES[index] &&
        typeof item.bytes === 'number' &&
        Number.isSafeInteger(item.bytes) &&
        item.bytes > 0 &&
        isSha256(item.sha256),
    )
  ) {
    return undefined;
  }
  return value as ReviewedRegistrationContext['source']['bundle_files'];
};

export const readReviewedRegistrationContext = (
  value: unknown,
): ReviewedRegistrationContext | undefined => {
  if (
    !isRecord(value) ||
    !exactKeys(value, [
      'schema_version',
      'artifact_type',
      'sensitive',
      'deidentified',
      'display_status',
      'intended_use',
      'scope',
      'display_label',
      'review',
      'source',
      'reviewer',
      'volumes',
      'display_policy',
      'limitations',
    ]) ||
    value.schema_version !== '1.0.0' ||
    value.artifact_type !== 'reviewed_registration_display_context' ||
    value.sensitive !== true ||
    value.deidentified !== false ||
    value.display_status !== 'authorized_for_exploratory_shared_coverage_overlay_swipe' ||
    value.intended_use !== 'shared_coverage_exploratory_overlay_swipe' ||
    value.scope !== 'shared_coverage' ||
    value.display_label !== 'EXPLORATORY — SELF-ATTESTED REGISTRATION QA' ||
    !isRecord(value.review) ||
    !isRecord(value.source) ||
    !isRecord(value.reviewer) ||
    !isRecord(value.volumes) ||
    !isRecord(value.display_policy) ||
    !Array.isArray(value.limitations)
  ) {
    return undefined;
  }

  if (
    !exactKeys(value.review, [
      'review_id',
      'job_id',
      'decision',
      'review_sha256',
      'event_sha256',
      'self_attested',
    ]) ||
    !isOpaque(value.review.review_id, 'registration_review') ||
    !isOpaque(value.review.job_id, 'registration') ||
    value.review.decision !== 'accepted_for_shared_coverage_overlay_swipe' ||
    !isSha256(value.review.review_sha256) ||
    !isSha256(value.review.event_sha256) ||
    value.review.self_attested !== true
  ) {
    return undefined;
  }

  if (
    !exactKeys(value.reviewer, ['role', 'training_status', 'identity_status']) ||
    !['clinician', 'medical_physicist'].includes(String(value.reviewer.role)) ||
    value.reviewer.training_status !== 'self_attested_trained' ||
    value.reviewer.identity_status !== 'self_attested_unverified'
  ) {
    return undefined;
  }

  if (
    !exactKeys(value.source, [
      'manifest_sha256',
      'transform_sha256',
      'bundle_sha256',
      'bundle_files',
      'transform_direction',
      'modality',
      'fixed',
      'moving',
    ]) ||
    !isSha256(value.source.manifest_sha256) ||
    !isSha256(value.source.transform_sha256) ||
    !isSha256(value.source.bundle_sha256) ||
    value.source.transform_direction !== 'moving_later_to_fixed_earlier' ||
    !['MR', 'CT'].includes(String(value.source.modality))
  ) {
    return undefined;
  }
  const fixedSource = readSourceSide(value.source.fixed);
  const movingSource = readSourceSide(value.source.moving);
  const bundleFiles = readBundleFiles(value.source.bundle_files);
  if (
    !fixedSource ||
    !movingSource ||
    !bundleFiles ||
    fixedSource.acquisition_date >= movingSource.acquisition_date ||
    fixedSource.study_id === movingSource.study_id ||
    fixedSource.series_id === movingSource.series_id
  ) {
    return undefined;
  }

  const bundleFile = (name: (typeof BUNDLE_FILE_NAMES)[number]) =>
    bundleFiles.find((item) => item.name === name);
  if (
    bundleFile('registration.json')?.sha256 !== value.source.manifest_sha256 ||
    bundleFile('moving-to-fixed.tfm')?.sha256 !== value.source.transform_sha256
  ) {
    return undefined;
  }

  if (
    !exactKeys(value.volumes, ['fixed', 'registered_moving']) ||
    !exactKeys(value.display_policy, [
      'allowed_modes',
      'always_locked',
      'native_moving_available',
      'native_moving_withheld',
      'shared_coverage_enforcement',
    ]) ||
    !sameStringSequence(
      value.display_policy.allowed_modes,
      REVIEWED_REGISTRATION_ALLOWED_MODES,
    ) ||
    !sameStringSequence(
      value.display_policy.always_locked,
      REVIEWED_REGISTRATION_ALWAYS_LOCKED,
    ) ||
    value.display_policy.native_moving_available !== false ||
    value.display_policy.native_moving_withheld !== true ||
    value.display_policy.shared_coverage_enforcement !==
      'reviewer_visual_only_no_machine_mask' ||
    !sameStringSequence(value.limitations, REVIEWED_REGISTRATION_LIMITATIONS)
  ) {
    return undefined;
  }

  const fixed = readVolume(value.volumes.fixed, {
    role: 'fixed_earlier_reference',
    filename: 'fixed.nrrd',
    url: REVIEWED_REGISTRATION_FIXED_URL,
    resampled: false,
  });
  const registered = readVolume(value.volumes.registered_moving, {
    role: 'moving_later_registered_to_fixed',
    filename: 'registered-moving.nrrd',
    url: REVIEWED_REGISTRATION_MOVING_URL,
    resampled: true,
  });
  if (
    !fixed ||
    !registered ||
    fixed.bytes + registered.bytes > MAX_REVIEWED_REGISTRATION_ENCODED_TOTAL_BYTES ||
    fixed.sha256 !== bundleFile('fixed.nrrd')?.sha256 ||
    registered.sha256 !== bundleFile('registered-moving.nrrd')?.sha256 ||
    fixed.bytes !== bundleFile('fixed.nrrd')?.bytes ||
    registered.bytes !== bundleFile('registered-moving.nrrd')?.bytes ||
    !geometriesEqual(fixed.geometry, registered.geometry)
  ) {
    return undefined;
  }
  return value as ReviewedRegistrationContext;
};

export const loadReviewedRegistrationContext = async (
  signal?: AbortSignal,
): Promise<ReviewedRegistrationProbeResult> => {
  try {
    const response = await fetch(REVIEWED_REGISTRATION_DISPLAY_ENDPOINT, {
      cache: 'no-store',
      credentials: 'same-origin',
      headers: { Accept: 'application/json' },
      signal,
    });
    if (response.status === 404) return { status: 'none' };
    if (!response.ok) {
      return {
        status: 'error',
        message: `Accepted exploratory registration is locked or unavailable (${response.status}).`,
      };
    }
    if (response.headers.get('Content-Type')?.split(';', 1)[0] !== 'application/json') {
      return {
        status: 'error',
        message: 'Accepted exploratory registration context has an unexpected media type.',
      };
    }
    const context = readReviewedRegistrationContext(await response.json());
    if (context) {
      const canonicalBundleFiles = JSON.stringify(
        context.source.bundle_files.map(({ bytes, name, sha256 }) => ({
          bytes,
          name,
          sha256,
        })),
      );
      const observedBundleSha256 = await sha256Hex(
        new TextEncoder().encode(canonicalBundleFiles).buffer,
      );
      if (observedBundleSha256 !== context.source.bundle_sha256) {
        return {
          status: 'error',
          message: 'Accepted exploratory registration bundle anchor failed validation.',
        };
      }
    }
    return context
      ? { status: 'available', context }
      : {
          status: 'error',
          message: 'Accepted exploratory registration context failed strict validation.',
        };
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      return { status: 'none' };
    }
    return {
      status: 'error',
      message: 'Accepted exploratory registration probe could not complete.',
    };
  }
};

async function sha256Hex(buffer: ArrayBuffer): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', buffer);
  return Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, '0'),
  ).join('');
}

export const fetchReviewedRegistrationVolume = async (
  volume: ReviewedRegistrationVolume,
  signal?: AbortSignal,
): Promise<ArrayBuffer> => {
  if (volume.bytes > MAX_REVIEWED_REGISTRATION_ENCODED_VOLUME_BYTES) {
    throw new Error('Accepted exploratory volume exceeds the browser safety limit.');
  }
  const validatedVolume =
    volume.filename === 'fixed.nrrd'
      ? readVolume(volume, {
          role: 'fixed_earlier_reference',
          filename: 'fixed.nrrd',
          url: REVIEWED_REGISTRATION_FIXED_URL,
          resampled: false,
        })
      : volume.filename === 'registered-moving.nrrd'
        ? readVolume(volume, {
            role: 'moving_later_registered_to_fixed',
            filename: 'registered-moving.nrrd',
            url: REVIEWED_REGISTRATION_MOVING_URL,
            resampled: true,
          })
        : undefined;
  if (!validatedVolume) {
    throw new Error('Accepted exploratory volume descriptor failed strict validation.');
  }
  const response = await fetch(validatedVolume.url, {
    cache: 'no-store',
    credentials: 'same-origin',
    headers: { Accept: 'application/vnd.nrrd' },
    signal,
  });
  if (!response.ok) {
    throw new Error('Accepted exploratory volume could not be loaded.');
  }
  if (response.headers.get('Content-Type')?.split(';', 1)[0] !== 'application/vnd.nrrd') {
    throw new Error('Accepted exploratory volume has an unexpected media type.');
  }
  const declaredLength = Number(response.headers.get('Content-Length'));
  if (!Number.isSafeInteger(declaredLength) || declaredLength !== validatedVolume.bytes) {
    throw new Error('Accepted exploratory volume response byte count changed.');
  }
  const responseDigest = response.headers.get('X-Content-SHA256');
  if (responseDigest !== null && responseDigest !== validatedVolume.sha256) {
    throw new Error('Accepted exploratory volume response digest changed.');
  }
  const buffer = await response.arrayBuffer();
  if (buffer.byteLength !== validatedVolume.bytes) {
    throw new Error('Accepted exploratory volume byte count changed.');
  }
  if ((await sha256Hex(buffer)) !== validatedVolume.sha256) {
    throw new Error('Accepted exploratory volume SHA-256 changed.');
  }
  return buffer;
};
