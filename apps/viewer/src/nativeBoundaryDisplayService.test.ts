import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  NATIVE_BOUNDARY_ALWAYS_LOCKED,
  NATIVE_BOUNDARY_LIMITATIONS,
  NATIVE_BOUNDARY_MASK_MEDIA_TYPE,
  fetchNativeBoundaryMask,
  nativeBoundaryMaskCentroid,
  readNativeBoundaryDisplayContext,
  type NativeBoundaryDisplayContext,
  type NativeBoundaryTimepoint,
} from './nativeBoundaryDisplayService';

const sha = (value: string) => value.repeat(64);

const timepoint = (
  role: 'baseline' | 'followup',
  overrides: Partial<NativeBoundaryTimepoint> = {},
): NativeBoundaryTimepoint => ({
  role,
  review_id:
    role === 'baseline'
      ? 'review_11111111-1111-4111-8111-111111111111'
      : 'review_22222222-2222-4222-8222-222222222222',
  evidence_artifact_id:
    role === 'baseline'
      ? 'seg_11111111-1111-4111-8111-111111111111'
      : 'seg_22222222-2222-4222-8222-222222222222',
  patient_context_id: 'patient_11111111111111111111',
  study_id:
    role === 'baseline' ? 'study_11111111111111111111' : 'study_22222222222222222222',
  series_id:
    role === 'baseline' ? 'series_11111111111111111111' : 'series_22222222222222222222',
  frame_of_reference_id:
    role === 'baseline' ? 'frame_11111111111111111111' : 'frame_22222222222222222222',
  modality: 'MR',
  acquisition_date: role === 'baseline' ? '20260101' : '20260201',
  series_description: `${role} synthetic MR`,
  protocol_name: null,
  source_set_sha256: role === 'baseline' ? sha('1') : sha('2'),
  ordered_instance_ids:
    role === 'baseline'
      ? [
          'instance_11111111111111111111',
          'instance_11111111111111111112',
          'instance_11111111111111111113',
        ]
      : [
          'instance_22222222222222222221',
          'instance_22222222222222222222',
          'instance_22222222222222222223',
        ],
  dimensions: [2, 2, 3],
  reviewed_volume_ml: role === 'baseline' ? 0.00225 : 0.003,
  foreground_voxel_count: role === 'baseline' ? 3 : 4,
  mask: {
    url: `/v1/lesion-volume-comparison-display/masks/${role}`,
    bytes: 12,
    sha256: role === 'baseline' ? sha('a') : sha('b'),
    scalar_type: 'uint8',
    binary_values: [0, 1],
    grid_order: 'source_volume_frame_row_column',
  },
  boundary_review: {
    status: 'accepted_for_discussion',
    self_attested: true,
    represented_tissue: 'Synthetic enhancing tissue',
    inclusion_criteria: 'Include contiguous synthetic signal.',
    exclusion_criteria: 'Exclude synthetic vessels and cavity.',
    boundary_uncertainty: 'not_quantified',
  },
  ...overrides,
});

const context = (): NativeBoundaryDisplayContext => ({
  schema_version: '1.0.0',
  artifact_type: 'lesion_volume_native_boundary_display_context',
  local_only: true,
  sensitive: true,
  deidentified: false,
  display_status: 'authorized_reviewed_native_boundaries_unregistered',
  display_label: 'REVIEWED NATIVE BOUNDARIES — UNREGISTERED',
  comparison_id: 'volume_pair_33333333-3333-4333-8333-333333333333',
  review: {
    decision: 'accepted_for_volume_change_discussion',
    reviewer_role: 'neuro_oncologist',
    identity_status: 'self_attested_unverified',
    same_lesion_identity: 'confirmed',
    same_represented_tissue: 'confirmed',
    acquisition_comparability: 'suitable',
    boundary_comparability: 'suitable',
    registration_consideration: 'not_required',
    limitation_note: '',
    treatment_context_note: 'Synthetic context; no causal attribution.',
  },
  comparison: {
    status: 'qualified_pairing_review_for_discussion_only',
    method: 'followup_reviewed_volume_minus_baseline_reviewed_volume',
    baseline_volume_ml: 0.00225,
    followup_volume_ml: 0.003,
    absolute_change_ml: 0.00075,
    percent_change: 100 / 3,
    numeric_direction: 'increased',
    elapsed_days: 31,
    boundary_uncertainty: 'not_quantified',
    response_assessment: 'not_performed',
    causal_treatment_attribution: false,
    interpretations: [],
  },
  timepoints: { baseline: timepoint('baseline'), followup: timepoint('followup') },
  navigation_policy: {
    default_linked: false,
    link_mode: 'normalized_native_grid_fraction',
    approximate_navigation_only: true,
    anatomical_correspondence: false,
    registered: false,
    independent_navigation_available: true,
  },
  display_policy: {
    allowed_modes: ['native_side_by_side', 'normalized_navigation_link'],
    always_locked: [...NATIVE_BOUNDARY_ALWAYS_LOCKED],
    masks_read_only: true,
    native_dicom_required: true,
  },
  limitations: [...NATIVE_BOUNDARY_LIMITATIONS],
});

afterEach(() => vi.unstubAllGlobals());

describe('reviewed native-boundary display contract', () => {
  it('accepts the exact unregistered native-space contract', () => {
    const value = readNativeBoundaryDisplayContext(context());
    expect(value?.navigation_policy.registered).toBe(false);
    expect(value?.navigation_policy.default_linked).toBe(false);
    expect(value?.display_policy.always_locked).toContain('spatial_overlay');
    expect(value?.comparison.response_assessment).toBe('not_performed');
  });

  it('rejects spatial implications, arithmetic changes, and source-order drift', () => {
    const registered = structuredClone(context()) as Record<string, any>;
    registered.navigation_policy.registered = true;
    expect(readNativeBoundaryDisplayContext(registered)).toBeUndefined();

    const arithmetic = structuredClone(context()) as Record<string, any>;
    arithmetic.comparison.percent_change = 12;
    expect(readNativeBoundaryDisplayContext(arithmetic)).toBeUndefined();

    const reordered = structuredClone(context()) as Record<string, any>;
    reordered.timepoints.baseline.ordered_instance_ids[1] =
      reordered.timepoints.baseline.ordered_instance_ids[0];
    expect(readNativeBoundaryDisplayContext(reordered)).toBeUndefined();

    const chronology = structuredClone(context()) as Record<string, any>;
    chronology.comparison.elapsed_days = 30;
    expect(readNativeBoundaryDisplayContext(chronology)).toBeUndefined();
  });

  it('rehashes and recounts the exact binary mask response', async () => {
    const mask = Uint8Array.from([1, 1, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0]);
    const digest = Array.from(
      new Uint8Array(await crypto.subtle.digest('SHA-256', mask)),
      (byte) => byte.toString(16).padStart(2, '0'),
    ).join('');
    const descriptor = timepoint('baseline', {
      mask: { ...timepoint('baseline').mask, sha256: digest },
    });
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        new Response(mask, {
          status: 200,
          headers: {
            'Content-Type': NATIVE_BOUNDARY_MASK_MEDIA_TYPE,
            'Content-Length': String(mask.byteLength),
            'X-Content-SHA256': digest,
          },
        }),
      ),
    );
    await expect(fetchNativeBoundaryMask(descriptor)).resolves.toEqual(mask);

    const nonBinary = Uint8Array.from(mask);
    nonBinary[0] = 2;
    const nonBinaryDigest = Array.from(
      new Uint8Array(await crypto.subtle.digest('SHA-256', nonBinary)),
      (byte) => byte.toString(16).padStart(2, '0'),
    ).join('');
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        new Response(nonBinary, {
          status: 200,
          headers: {
            'Content-Type': NATIVE_BOUNDARY_MASK_MEDIA_TYPE,
            'Content-Length': String(nonBinary.byteLength),
            'X-Content-SHA256': nonBinaryDigest,
          },
        }),
      ),
    );
    await expect(
      fetchNativeBoundaryMask({
        ...descriptor,
        mask: { ...descriptor.mask, sha256: nonBinaryDigest },
      }),
    ).rejects.toThrow(/strictly binary/i);
  });

  it('computes a deterministic centroid in each mask native grid', () => {
    const mask = new Uint8Array(12);
    mask[0] = 1;
    mask[1] = 1;
    mask[10] = 1;
    expect(nativeBoundaryMaskCentroid(mask, [2, 2, 3])).toEqual([
      1 / 3,
      1 / 3,
      1 / 3,
    ]);
    expect(() => nativeBoundaryMaskCentroid(new Uint8Array(11), [2, 2, 3])).toThrow(
      /exact source grid/i,
    );
  });
});
