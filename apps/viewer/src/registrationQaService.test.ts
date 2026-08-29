import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  REGISTRATION_REVIEW_ENDPOINT,
  REGISTRATION_REVIEW_INPUT_MEDIA_TYPE,
  REGISTRATION_REVIEW_MEDIA_TYPE,
  REGISTRATION_QA_ALWAYS_LOCKED,
  REGISTRATION_QA_LIMITATIONS,
  REGISTRATION_QA_PREVIEW_MODES,
  REGISTRATION_QA_QUALITATIVE_CHECKS,
  fetchRegistrationQaCoverageMask,
  fetchRegistrationQaVolume,
  loadRegistrationQaContext,
  readRegistrationQaContext,
  submitRegistrationReview,
  type RegistrationQaContext,
  type RegistrationReviewRequest,
} from './registrationQaService';

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

const volume = (
  filename: 'fixed.nrrd' | 'moving.nrrd' | 'registered-moving.nrrd',
  role: string,
  resampled: boolean,
) => ({
  role,
  filename,
  url: `/v1/registration-qa/files/${filename}`,
  bytes: 200,
  sha256: 'a'.repeat(64),
  resampled,
  geometry,
});

const context: RegistrationQaContext = {
  schema_version: '2.0.0',
  artifact_type: 'registration_qa_context',
  mode: 'human_qa_preview',
  qa_preview_only: true,
  watermark: 'UNAPPROVED REGISTRATION — QA ONLY',
  job_id: `registration_${'1'.repeat(20)}`,
  artifact_state: 'generated_pending_qa',
  review_status: 'unreviewed',
  source: {
    manifest_sha256: 'b'.repeat(64),
    transform_direction: 'moving_later_to_fixed_earlier',
    modality: 'MR',
    fixed: {
      role: 'fixed_earlier',
      study_id: `study_${'1'.repeat(20)}`,
      series_id: `series_${'2'.repeat(20)}`,
      acquisition_date: '20260101',
    },
    moving: {
      role: 'moving_later',
      study_id: `study_${'3'.repeat(20)}`,
      series_id: `series_${'4'.repeat(20)}`,
      acquisition_date: '20260301',
    },
  },
  volumes: {
    fixed: volume('fixed.nrrd', 'fixed_earlier_reference', false),
    moving: volume('moving.nrrd', 'moving_later_reference', false),
    registered_moving: volume(
      'registered-moving.nrrd',
      'moving_later_registered_to_fixed',
      true,
    ),
  },
  coverage_mask: {
    role: 'registered_moving_sampling_support_in_fixed_geometry',
    filename: 'registered-moving-coverage.nrrd',
    url: '/v1/registration-qa/files/registered-moving-coverage.nrrd',
    bytes: 200,
    sha256: 'd'.repeat(64),
    derived: true,
    scalar_type: 'uint8',
    binary_values: [0, 1],
    semantics: 'technical_sampling_support_not_anatomy_or_segmentation',
    geometry,
  },
  transform: {
    filename: 'moving-to-fixed.tfm',
    sha256: 'c'.repeat(64),
    coordinate_system: 'DICOM patient LPS',
  },
  intended_use: 'shared_coverage_exploratory_overlay_swipe',
  qualitative_checks: REGISTRATION_QA_QUALITATIVE_CHECKS.map(([id, label]) => ({
    id,
    label,
  })),
  landmark_options: [
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
  ],
  landmark_statuses: ['aligned', 'misaligned', 'not_visible', 'uncertain'],
  allowed_decisions: ['accepted_for_shared_coverage_overlay_swipe', 'rejected'],
  display_policy: {
    qa_preview_allowed_while_pending: [...REGISTRATION_QA_PREVIEW_MODES],
    accepted_unlocks: ['overlay', 'swipe'],
    always_locked: [...REGISTRATION_QA_ALWAYS_LOCKED],
    sampling_support_enforcement: 'required_pixel_mask',
    shared_anatomy_scope: 'reviewer_attested_visual_only',
    mask_failure_behavior: 'lock_display',
    mask_sampling: 'nearest_neighbor',
  },
  limitations: [...REGISTRATION_QA_LIMITATIONS],
};

const review: RegistrationReviewRequest = {
  schema_version: '2.0.0',
  reviewer: {
    name: 'Reviewer',
    role: 'patient_or_family',
    organization: null,
    training_status: 'self_attested_not_trained',
  },
  attest: true,
  decision: 'rejected',
  region_of_importance: 'Whole brain',
  qualitative_checks: Object.fromEntries(
    REGISTRATION_QA_QUALITATIVE_CHECKS.map(([id]) => [id, false]),
  ),
  inspection_evidence: { planes: {}, modes: [] },
  landmark_observations: [],
  quantitative_assessment: {
    status: 'unavailable',
    tolerance_mm: null,
    tolerance_basis: null,
    pairs: [],
    unavailable_reason: 'Rejected before quantitative assessment.',
  },
  regional_defects: ['Synthetic mismatch.'],
  note: 'Reject synthetic transform.',
};

describe('registration QA local service', () => {
  it('strictly accepts only launch-scoped relative volume resources', () => {
    expect(readRegistrationQaContext(context)).toEqual(context);
    expect(readRegistrationQaContext({ ...context, source_path: '/private/patient' })).toBeUndefined();
    expect(
      readRegistrationQaContext({
        ...context,
        volumes: {
          ...context.volumes,
          fixed: { ...context.volumes.fixed, url: 'https://example.invalid/fixed.nrrd' },
        },
      }),
    ).toBeUndefined();
    expect(
      readRegistrationQaContext({
        ...context,
        transform: { ...context.transform, sha256: 'not-a-digest' },
      }),
    ).toBeUndefined();
    expect(
      readRegistrationQaContext({
        ...context,
        source: { ...context.source, unexpected: 'must fail closed' },
      }),
    ).toBeUndefined();
    expect(
      readRegistrationQaContext({
        ...context,
        volumes: {
          ...context.volumes,
          fixed: {
            ...context.volumes.fixed,
            geometry: {
              ...context.volumes.fixed.geometry,
              space_directions: [
                [1, 0, 0],
                [2, 0, 0],
                [0, 0, 1],
              ],
            },
          },
        },
      }),
    ).toBeUndefined();
    expect(
      readRegistrationQaContext({
        ...context,
        coverage_mask: {
          ...context.coverage_mask,
          semantics: 'anatomy_or_segmentation',
        },
      }),
    ).toBeUndefined();
    expect(
      readRegistrationQaContext({
        ...context,
        coverage_mask: {
          ...context.coverage_mask,
          geometry: { ...context.coverage_mask.geometry, space_origin: [1, 0, 0] },
        },
      }),
    ).toBeUndefined();
    expect(
      readRegistrationQaContext({
        ...context,
        display_policy: {
          ...context.display_policy,
          qa_preview_allowed_while_pending:
            context.display_policy.qa_preview_allowed_while_pending.filter(
              (mode) => mode !== 'coverage_mask_boundary',
            ),
        },
      }),
    ).toBeUndefined();
    expect(
      readRegistrationQaContext({
        ...context,
        qualitative_checks: context.qualitative_checks.filter(
          (item) => item.id !== 'coverage_mask_boundary_and_excluded_region_reviewed',
        ),
      }),
    ).toBeUndefined();
  });

  it('distinguishes no QA launch from probe failures', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response('{}', { status: 404, headers: { 'Content-Type': 'application/json' } }),
      )
      .mockResolvedValueOnce(
        new Response('{}', { status: 409, headers: { 'Content-Type': 'application/json' } }),
      )
      .mockResolvedValueOnce(
        new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } }),
      );
    vi.stubGlobal('fetch', fetchMock);

    await expect(loadRegistrationQaContext()).resolves.toEqual({ status: 'none' });
    await expect(loadRegistrationQaContext()).resolves.toEqual({
      status: 'error',
      message: 'Local registration QA probe failed (409).',
    });
    await expect(loadRegistrationQaContext()).resolves.toEqual({
      status: 'error',
      message: 'Local registration QA context failed validation.',
    });
  });

  it('checks volume response length before retaining local bytes', async () => {
    const descriptor = { ...context.volumes.fixed, bytes: 4 };
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(new Uint8Array([1, 2, 3]), {
          headers: {
            'Content-Type': 'application/vnd.nrrd',
            'Content-Length': '3',
          },
        }),
      ),
    );

    await expect(fetchRegistrationQaVolume(descriptor)).rejects.toThrow(
      /response byte count changed/i,
    );
  });

  it('requires transport digest and local hash for the binary sampling-support mask', async () => {
    const bytes = new Uint8Array([1, 2, 3, 4]);
    const sha256 = '9f64a747e1b97f131fabb6b447296c9b6f0201e79fb3c5356e6c77e89b6a806a';
    const descriptor = { ...context.coverage_mask, bytes: bytes.byteLength, sha256 };
    const response = (digest: string | undefined) =>
      new Response(bytes, {
        headers: {
          'Content-Type': 'application/vnd.nrrd',
          'Content-Length': String(bytes.byteLength),
          ...(digest ? { 'X-Content-SHA256': digest } : {}),
        },
      });
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(response(undefined))
        .mockResolvedValueOnce(response(sha256)),
    );

    await expect(fetchRegistrationQaCoverageMask(descriptor)).rejects.toThrow(
      /response digest changed/i,
    );
    await expect(fetchRegistrationQaCoverageMask(descriptor)).resolves.toEqual(
      bytes.buffer,
    );
  });

  it('posts decision evidence only to the same-origin relative endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(new TextEncoder().encode('{"artifact_type":"registration_qa_review"}\n'), {
        status: 200,
        headers: {
          'Content-Type': REGISTRATION_REVIEW_MEDIA_TYPE,
          'Content-Disposition':
            'attachment; filename="scanview-registration-review-test.json"',
          'Content-Length': '51',
        },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const result = await submitRegistrationReview(review);

    expect(REGISTRATION_REVIEW_ENDPOINT).toBe('/v1/registration-reviews');
    expect(result.filename).toBe('scanview-registration-review-test.json');
    const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/v1/registration-reviews');
    expect(options).toMatchObject({
      method: 'POST',
      cache: 'no-store',
      credentials: 'same-origin',
      headers: {
        Accept: REGISTRATION_REVIEW_MEDIA_TYPE,
        'Content-Type': REGISTRATION_REVIEW_INPUT_MEDIA_TYPE,
      },
    });
    const body = String(options.body);
    expect(JSON.parse(body)).toEqual(review);
    expect(body).not.toContain('nrrd');
    expect(body).not.toContain('/Users/');
    expect(body).not.toContain('http://');
    expect(body).not.toContain('https://');
  });
});
