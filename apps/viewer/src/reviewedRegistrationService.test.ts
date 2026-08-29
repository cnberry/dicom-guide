import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  fetchReviewedRegistrationCoverageMask,
  fetchReviewedRegistrationVolume,
  loadReviewedRegistrationContext,
  MAX_REVIEWED_REGISTRATION_ENCODED_VOLUME_BYTES,
  readReviewedRegistrationContext,
  REVIEWED_REGISTRATION_ALLOWED_MODES,
  REVIEWED_REGISTRATION_ALWAYS_LOCKED,
  REVIEWED_REGISTRATION_COVERAGE_MASK_URL,
  REVIEWED_REGISTRATION_DISPLAY_ENDPOINT,
  REVIEWED_REGISTRATION_FIXED_URL,
  REVIEWED_REGISTRATION_LIMITATIONS,
  REVIEWED_REGISTRATION_MOVING_URL,
  type ReviewedRegistrationContext,
  type ReviewedRegistrationCoverageMask,
  type ReviewedRegistrationVolume,
} from './reviewedRegistrationService';

afterEach(() => vi.unstubAllGlobals());

const geometry = {
  sizes: [2, 2, 2] as [number, number, number],
  voxel_spacing_mm: [1, 1, 1] as [number, number, number],
  coordinate_system: 'left-posterior-superior' as const,
  space_directions: [
    [1, 0, 0],
    [0, 1, 0],
    [0, 0, 1],
  ] as [[number, number, number], [number, number, number], [number, number, number]],
  space_origin: [0, 0, 0] as [number, number, number],
};

const hashes = {
  engine: 'e'.repeat(64),
  fixed: 'a'.repeat(64),
  transform: 'b'.repeat(64),
  moving: 'c'.repeat(64),
  coverage: '5'.repeat(64),
  registered: 'd'.repeat(64),
  manifest: 'f'.repeat(64),
};

const context: ReviewedRegistrationContext = {
  schema_version: '2.0.0',
  artifact_type: 'reviewed_registration_display_context',
  sensitive: true,
  deidentified: false,
  display_status: 'authorized_for_exploratory_shared_coverage_overlay_swipe',
  intended_use: 'shared_coverage_exploratory_overlay_swipe',
  scope: 'shared_coverage',
  review: {
    review_id: `registration_review_${'1'.repeat(20)}`,
    job_id: `registration_${'2'.repeat(20)}`,
    decision: 'accepted_for_shared_coverage_overlay_swipe',
    review_sha256: '3'.repeat(64),
    event_sha256: '4'.repeat(64),
    self_attested: true,
  },
  source: {
    manifest_sha256: hashes.manifest,
    bundle_sha256: '7a136ea998fbab230fb416f5afb474876bd25220be31757e1bf0e43da27a18c8',
    transform_sha256: hashes.transform,
    bundle_files: [
      { name: 'engine-report.json', bytes: 10, sha256: hashes.engine },
      { name: 'fixed.nrrd', bytes: 3, sha256: hashes.fixed },
      { name: 'moving-to-fixed.tfm', bytes: 10, sha256: hashes.transform },
      { name: 'moving.nrrd', bytes: 10, sha256: hashes.moving },
      { name: 'registered-moving-coverage.nrrd', bytes: 2, sha256: hashes.coverage },
      { name: 'registered-moving.nrrd', bytes: 4, sha256: hashes.registered },
      { name: 'registration.json', bytes: 10, sha256: hashes.manifest },
    ],
    transform_direction: 'moving_later_to_fixed_earlier',
    modality: 'MR',
    fixed: {
      study_id: `study_${'6'.repeat(20)}`,
      series_id: `series_${'7'.repeat(20)}`,
      acquisition_date: '20260101',
    },
    moving: {
      study_id: `study_${'8'.repeat(20)}`,
      series_id: `series_${'9'.repeat(20)}`,
      acquisition_date: '20260301',
    },
  },
  reviewer: {
    role: 'clinician',
    training_status: 'self_attested_trained',
    identity_status: 'self_attested_unverified',
  },
  volumes: {
    fixed: {
      role: 'fixed_earlier_reference',
      filename: 'fixed.nrrd',
      url: REVIEWED_REGISTRATION_FIXED_URL,
      bytes: 3,
      sha256: hashes.fixed,
      derived: true,
      resampled: false,
      geometry,
    },
    registered_moving: {
      role: 'moving_later_registered_to_fixed',
      filename: 'registered-moving.nrrd',
      url: REVIEWED_REGISTRATION_MOVING_URL,
      bytes: 4,
      sha256: hashes.registered,
      derived: true,
      resampled: true,
      geometry,
    },
  },
  coverage_mask: {
    role: 'registered_moving_sampling_support_in_fixed_geometry',
    filename: 'registered-moving-coverage.nrrd',
    url: REVIEWED_REGISTRATION_COVERAGE_MASK_URL,
    bytes: 2,
    sha256: hashes.coverage,
    derived: true,
    scalar_type: 'uint8',
    binary_values: [0, 1],
    semantics: 'technical_sampling_support_not_anatomy_or_segmentation',
    geometry,
  },
  display_policy: {
    allowed_modes: [...REVIEWED_REGISTRATION_ALLOWED_MODES],
    always_locked: [...REVIEWED_REGISTRATION_ALWAYS_LOCKED],
    native_moving_available: false,
    native_moving_withheld: true,
    sampling_support_enforcement: 'required_pixel_mask',
    shared_anatomy_scope: 'reviewer_attested_visual_only',
    mask_failure_behavior: 'lock_display',
    mask_sampling: 'nearest_neighbor',
  },
  display_label: 'EXPLORATORY — SELF-ATTESTED REGISTRATION QA',
  limitations: [...REVIEWED_REGISTRATION_LIMITATIONS],
};

describe('reviewed registration display service', () => {
  it('accepts only the exact hash-bound two-volume plus required mask contract', () => {
    expect(readReviewedRegistrationContext(context)).toEqual(context);
    expect(
      readReviewedRegistrationContext({ ...context, patient_name: 'must fail closed' }),
    ).toBeUndefined();
    expect(
      readReviewedRegistrationContext({
        ...context,
        display_status: 'locked',
      }),
    ).toBeUndefined();
    expect(
      readReviewedRegistrationContext({ ...context, schema_version: '1.0.0' }),
    ).toBeUndefined();
    expect(
      readReviewedRegistrationContext({
        ...context,
        coverage_mask: {
          ...context.coverage_mask,
          geometry: { ...geometry, space_origin: [1, 0, 0] },
        },
      }),
    ).toBeUndefined();
    const withoutMask = structuredClone(context) as unknown as Record<string, unknown>;
    delete withoutMask.coverage_mask;
    expect(readReviewedRegistrationContext(withoutMask)).toBeUndefined();
    expect(
      readReviewedRegistrationContext({
        ...context,
        coverage_mask: { ...context.coverage_mask, binary_values: [0, 255] },
      }),
    ).toBeUndefined();
    expect(
      readReviewedRegistrationContext({
        ...context,
        source: {
          ...context.source,
          moving: {
            ...context.source.moving,
            study_id: context.source.fixed.study_id,
            acquisition_date: context.source.fixed.acquisition_date,
          },
        },
      }),
    ).toBeUndefined();
    expect(
      readReviewedRegistrationContext({
        ...context,
        volumes: {
          ...context.volumes,
          fixed: { ...context.volumes.fixed, url: 'https://example.invalid/fixed.nrrd' },
        },
      }),
    ).toBeUndefined();
    expect(
      readReviewedRegistrationContext({
        ...context,
        volumes: {
          ...context.volumes,
          registered_moving: {
            ...context.volumes.registered_moving,
            geometry: { ...geometry, space_origin: [1, 0, 0] },
          },
        },
      }),
    ).toBeUndefined();
    expect(
      readReviewedRegistrationContext({
        ...context,
        display_policy: {
          ...context.display_policy,
          allowed_modes: ['swipe', 'opacity'],
        },
      }),
    ).toBeUndefined();
    expect(
      readReviewedRegistrationContext({
        ...context,
        display_policy: {
          ...context.display_policy,
          native_moving_available: true,
        },
      }),
    ).toBeUndefined();
    expect(
      readReviewedRegistrationContext({
        ...context,
        limitations: context.limitations.slice(0, -1),
      }),
    ).toBeUndefined();

    const aggregateOverCap = structuredClone(context);
    const nearPerVolumeCap = MAX_REVIEWED_REGISTRATION_ENCODED_VOLUME_BYTES - 1;
    aggregateOverCap.volumes.fixed.bytes = nearPerVolumeCap;
    aggregateOverCap.volumes.registered_moving.bytes = nearPerVolumeCap;
    aggregateOverCap.source.bundle_files[1].bytes = nearPerVolumeCap;
    aggregateOverCap.source.bundle_files[5].bytes = nearPerVolumeCap;
    expect(readReviewedRegistrationContext(aggregateOverCap)).toBeUndefined();
  });

  it('treats only 404 as absent and fails closed on locked or invalid contexts', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response('{}', { status: 404 }))
      .mockResolvedValueOnce(
        new Response('{}', {
          status: 423,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify(context), {
          headers: { 'Content-Type': 'application/json; charset=utf-8' },
        }),
      )
      .mockResolvedValueOnce(
        new Response('{}', {
          headers: { 'Content-Type': 'application/json' },
        }),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            ...context,
            source: { ...context.source, bundle_sha256: '0'.repeat(64) },
          }),
          { headers: { 'Content-Type': 'application/json' } },
        ),
      );
    vi.stubGlobal('fetch', fetchMock);

    await expect(loadReviewedRegistrationContext()).resolves.toEqual({ status: 'none' });
    await expect(loadReviewedRegistrationContext()).resolves.toEqual({
      status: 'error',
      message: 'Accepted exploratory registration is locked or unavailable (423).',
    });
    await expect(loadReviewedRegistrationContext()).resolves.toEqual({
      status: 'available',
      context,
    });
    await expect(loadReviewedRegistrationContext()).resolves.toEqual({
      status: 'error',
      message: 'Accepted exploratory registration context failed strict validation.',
    });
    await expect(loadReviewedRegistrationContext()).resolves.toEqual({
      status: 'error',
      message: 'Accepted exploratory registration bundle anchor failed validation.',
    });
    expect(fetchMock).toHaveBeenCalledWith(
      REVIEWED_REGISTRATION_DISPLAY_ENDPOINT,
      expect.objectContaining({ cache: 'no-store', credentials: 'same-origin' }),
    );
  });

  it('rejects a successful context response with a non-JSON media type', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(context), {
          headers: { 'Content-Type': 'text/plain' },
        }),
      ),
    );
    await expect(loadReviewedRegistrationContext()).resolves.toEqual({
      status: 'error',
      message: 'Accepted exploratory registration context has an unexpected media type.',
    });
  });

  it('verifies required response length and digest headers plus local SHA-256', async () => {
    const bytes = new Uint8Array([1, 2, 3, 4]);
    const digest = Array.from(
      new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)),
      (byte) => byte.toString(16).padStart(2, '0'),
    ).join('');
    const descriptor: ReviewedRegistrationVolume = {
      ...context.volumes.fixed,
      bytes: bytes.byteLength,
      sha256: digest,
    };
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(bytes, {
        headers: {
          'Content-Type': 'application/vnd.nrrd',
          'Content-Length': String(bytes.byteLength),
          'X-Content-SHA256': digest,
        },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await expect(fetchReviewedRegistrationVolume(descriptor)).resolves.toEqual(
      bytes.buffer,
    );
    expect(fetchMock).toHaveBeenCalledWith(
      REVIEWED_REGISTRATION_FIXED_URL,
      expect.objectContaining({ cache: 'no-store', credentials: 'same-origin' }),
    );
  });

  it('fetches the required mask only from its strict same-origin descriptor', async () => {
    const bytes = new Uint8Array([0, 1]);
    const digest = Array.from(
      new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)),
      (byte) => byte.toString(16).padStart(2, '0'),
    ).join('');
    const descriptor: ReviewedRegistrationCoverageMask = {
      ...context.coverage_mask,
      bytes: bytes.byteLength,
      sha256: digest,
    };
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(bytes, {
        headers: {
          'Content-Type': 'application/vnd.nrrd',
          'Content-Length': String(bytes.byteLength),
          'X-Content-SHA256': digest,
        },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await expect(fetchReviewedRegistrationCoverageMask(descriptor)).resolves.toEqual(
      bytes.buffer,
    );
    expect(fetchMock).toHaveBeenCalledWith(
      REVIEWED_REGISTRATION_COVERAGE_MASK_URL,
      expect.objectContaining({ cache: 'no-store', credentials: 'same-origin' }),
    );
  });

  it('rejects changed volume headers and over-cap descriptors before retaining bytes', async () => {
    const descriptor = { ...context.volumes.fixed, bytes: 4 };
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(new Uint8Array([1, 2, 3, 4]), {
          headers: {
            'Content-Type': 'application/vnd.nrrd',
            'Content-Length': '4',
            'X-Content-SHA256': '0'.repeat(64),
          },
        }),
      ),
    );
    await expect(fetchReviewedRegistrationVolume(descriptor)).rejects.toThrow(
      /response digest changed/i,
    );

    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(new Uint8Array([1, 2, 3, 4]), {
          headers: {
            'Content-Type': 'application/vnd.nrrd',
            'Content-Length': '4',
          },
        }),
      ),
    );
    await expect(fetchReviewedRegistrationVolume(descriptor)).rejects.toThrow(
      /response digest changed/i,
    );

    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(new Uint8Array([1, 2, 3, 4]), {
          headers: {
            'Content-Type': 'text/plain',
            'Content-Length': '4',
            'X-Content-SHA256': descriptor.sha256,
          },
        }),
      ),
    );
    await expect(fetchReviewedRegistrationVolume(descriptor)).rejects.toThrow(
      /unexpected media type/i,
    );

    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(new Uint8Array([1, 2, 3, 4]), {
          headers: {
            'Content-Type': 'application/vnd.nrrd',
            'Content-Length': '3',
            'X-Content-SHA256': descriptor.sha256,
          },
        }),
      ),
    );
    await expect(fetchReviewedRegistrationVolume(descriptor)).rejects.toThrow(
      /response byte count changed/i,
    );

    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(new Uint8Array([1, 2, 3, 4]), {
          headers: {
            'Content-Type': 'application/vnd.nrrd',
            'Content-Length': '4',
            'X-Content-SHA256': descriptor.sha256,
          },
        }),
      ),
    );
    await expect(fetchReviewedRegistrationVolume(descriptor)).rejects.toThrow(
      /SHA-256 changed/i,
    );

    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    await expect(
      fetchReviewedRegistrationVolume({
        ...descriptor,
        bytes: MAX_REVIEWED_REGISTRATION_ENCODED_VOLUME_BYTES + 1,
      }),
    ).rejects.toThrow(/browser safety limit/i);
    await expect(
      fetchReviewedRegistrationVolume({
        ...context.volumes.fixed,
        url: 'https://example.invalid/fixed.nrrd',
      } as unknown as ReviewedRegistrationVolume),
    ).rejects.toThrow(/strict validation/i);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
