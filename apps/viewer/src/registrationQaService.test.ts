import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  REGISTRATION_REVIEW_ENDPOINT,
  REGISTRATION_REVIEW_INPUT_MEDIA_TYPE,
  REGISTRATION_REVIEW_MEDIA_TYPE,
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
  schema_version: '1.0.0',
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
  transform: {
    filename: 'moving-to-fixed.tfm',
    sha256: 'c'.repeat(64),
    coordinate_system: 'DICOM patient LPS',
  },
  intended_use: 'shared_coverage_exploratory_overlay_swipe',
  qualitative_checks: [{ id: 'full_volume', label: 'Review the full volume.' }],
  landmark_options: ['brainstem', 'ventricles', 'clivus'],
  landmark_statuses: ['aligned', 'uncertain', 'misaligned', 'not_visible'],
  allowed_decisions: ['accepted_for_shared_coverage_overlay_swipe', 'rejected'],
  display_policy: {
    qa_preview_allowed_while_pending: [
      'reference_volume_side_by_side',
      'registered_side_by_side',
      'opacity_overlay',
      'swipe_or_flicker',
      'checkerboard',
      'edge_overlay',
      'landmark_residuals',
    ],
    accepted_unlocks: ['overlay', 'swipe'],
    always_locked: [
      'subtraction',
      'mask_propagation',
      'segmentation',
      'resampled_image_measurements',
      'response_conclusions',
    ],
  },
  limitations: ['Synthetic test limitation.'],
};

const review: RegistrationReviewRequest = {
  schema_version: '1.0.0',
  reviewer: {
    name: 'Reviewer',
    role: 'patient_or_family',
    organization: null,
    training_status: 'self_attested_not_trained',
  },
  attest: true,
  decision: 'rejected',
  region_of_importance: 'Whole brain',
  qualitative_checks: { full_volume: false },
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
  });

  it('distinguishes no QA launch from probe failures', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response('{}', { status: 404 }))
      .mockResolvedValueOnce(new Response('{}', { status: 409 }))
      .mockResolvedValueOnce(new Response('{}', { status: 200 }));
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
