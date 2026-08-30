import { strToU8, unzipSync, zipSync } from 'fflate';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  LESION_VOLUME_COMPARISON_ATTESTATION,
  LESION_VOLUME_COMPARISON_ENDPOINT,
  LESION_VOLUME_COMPARISON_INPUT_MEDIA_TYPE,
  buildLesionVolumeComparisonTransport,
  buildPairingRequest,
  readBoundaryReviewArchive,
  saveLesionVolumeComparison,
  type LesionVolumeComparisonChecklist,
} from './lesionVolumeComparisonService';

const reviewArchive = (
  role: 'baseline' | 'followup',
  overrides: Record<string, unknown> = {},
): Uint8Array => {
  const suffix = role === 'baseline' ? '1' : '2';
  const record = {
    artifact_type: 'dicom-guide.lesion-volume-review',
    review_id: `review_${suffix.repeat(8)}-${suffix.repeat(4)}-4${suffix.repeat(3)}-8${suffix.repeat(3)}-${suffix.repeat(12)}`,
    review_status: 'accepted_for_discussion',
    source_snapshot: {
      evidence_artifact_id: `seg_${suffix.repeat(8)}-${suffix.repeat(4)}-4${suffix.repeat(3)}-8${suffix.repeat(3)}-${suffix.repeat(12)}`,
      patient_context_id: 'patient_0123456789abcdef0123',
      study_id: `study_${suffix.repeat(20)}`,
      series_id: `series_${suffix.repeat(20)}`,
      modality: 'MR',
      volume_ml: role === 'baseline' ? 1.2 : 0.9,
    },
    review: { represented_tissue: 'Synthetic enhancing-tissue discussion region.' },
    permitted_uses: { eligible_for_future_pairing_review: true },
    ...overrides,
  };
  return zipSync({
    'review.json': strToU8(JSON.stringify(record)),
    'evidence.zip': strToU8('nested'),
    'review.html': strToU8('<!doctype html>'),
    'README.txt': strToU8('local'),
  });
};

const checklist = (value = true): LesionVolumeComparisonChecklist => ({
  both_original_sources_reviewed: value,
  both_complete_boundaries_reviewed: value,
  boundary_definitions_compared: value,
  same_lesion_identity_reviewed: value,
  same_represented_tissue_reviewed: value,
  acquisition_differences_reviewed: value,
  chronology_confirmed: value,
  registration_need_reviewed: value,
});

const acceptedRequest = () => buildPairingRequest({
  reviewerName: 'Synthetic Reviewer',
  reviewerRole: 'neuro_oncologist',
  reviewerOrganization: 'Synthetic clinic',
  decision: 'accepted_for_volume_change_discussion',
  pairing: {
    same_lesion_identity: 'confirmed',
    same_represented_tissue: 'confirmed',
    chronology: 'confirmed',
    acquisition_comparability: 'suitable',
    boundary_comparability: 'suitable',
    registration_consideration: 'not_required',
    limitation_note: '',
    treatment_context_note: 'Synthetic interval; no causal attribution.',
  },
  checklist: checklist(),
  attested: true,
});

afterEach(() => vi.unstubAllGlobals());

describe('reviewed manual ROI volume comparison service', () => {
  it('reads only accepted pairing-eligible boundary review records for preview', () => {
    const baseline = readBoundaryReviewArchive(reviewArchive('baseline'), 'baseline.zip');
    expect(baseline.reviewedVolumeMl).toBe(1.2);
    expect(baseline.modality).toBe('MR');
    expect(baseline.patientContextId).toBe('patient_0123456789abcdef0123');
    expect(baseline.representedTissue).toContain('enhancing-tissue');

    expect(() => readBoundaryReviewArchive(
      reviewArchive('baseline', { review_status: 'revision_requested' }),
      'revision.zip',
    )).toThrow(/not an accepted v1 record/);
  });

  it('refuses oversized expanded preview members before retaining them', () => {
    const archive = zipSync({
      'review.json': strToU8(JSON.stringify({ artifact_type: 'dicom-guide.lesion-volume-review' })),
      'evidence.zip': strToU8('nested'),
      'review.html': new Uint8Array(2 * 1024 * 1024 + 1),
      'README.txt': strToU8('local'),
    }, { level: 9 });
    expect(() => readBoundaryReviewArchive(archive, 'oversized.zip')).toThrow(
      /unsupported member set/,
    );
  });

  it('builds the exact three-member same-origin transport', () => {
    const baseline = readBoundaryReviewArchive(reviewArchive('baseline'), 'baseline.zip');
    const followup = readBoundaryReviewArchive(reviewArchive('followup'), 'followup.zip');
    const request = acceptedRequest();
    const transport = buildLesionVolumeComparisonTransport(baseline, followup, request);
    const members = unzipSync(transport);
    expect(Object.keys(members).sort()).toEqual([
      'baseline-review.zip',
      'followup-review.zip',
      'pairing-request.json',
    ]);
    expect(JSON.parse(new TextDecoder().decode(members['pairing-request.json']))).toEqual(request);
    expect(request.attestation).toBe(LESION_VOLUME_COMPARISON_ATTESTATION);
  });

  it('fails acceptance until every human pairing gate is satisfied', () => {
    expect(() => buildPairingRequest({
      reviewerName: 'Synthetic Reviewer',
      reviewerRole: 'radiologist',
      decision: 'accepted_for_volume_change_discussion',
      pairing: {
        same_lesion_identity: 'uncertain',
        same_represented_tissue: 'confirmed',
        chronology: 'confirmed',
        acquisition_comparability: 'suitable',
        boundary_comparability: 'suitable',
        registration_consideration: 'not_required',
        limitation_note: '',
        treatment_context_note: '',
      },
      checklist: checklist(false),
      attested: true,
    })).toThrow(/Acceptance requires/);
  });

  it('requires a limitation note for qualified limitations or registration need', () => {
    expect(() => buildPairingRequest({
      reviewerName: 'Synthetic Reviewer',
      reviewerRole: 'medical_physicist',
      decision: 'revision_requested',
      pairing: {
        same_lesion_identity: 'uncertain',
        same_represented_tissue: 'uncertain',
        chronology: 'not_confirmed',
        acquisition_comparability: 'suitable_with_limitations',
        boundary_comparability: 'not_suitable',
        registration_consideration: 'required',
        limitation_note: '',
        treatment_context_note: '',
      },
      checklist: checklist(false),
      attested: true,
    })).toThrow(/require a note/);
  });

  it('posts only to the exact local endpoint and downloads a ZIP response', async () => {
    const responseBytes = new Uint8Array([80, 75, 3, 4]);
    const fetchMock = vi.fn().mockResolvedValue(new Response(responseBytes, {
      status: 200,
      headers: {
        'Content-Type': 'application/zip',
        'Content-Disposition': 'attachment; filename="dicom-guide-lesion-volume-comparison-test.zip"',
      },
    }));
    vi.stubGlobal('fetch', fetchMock);
    vi.stubGlobal('URL', {
      createObjectURL: vi.fn(() => 'blob:test'),
      revokeObjectURL: vi.fn(),
    });
    const click = vi.fn();
    vi.stubGlobal('document', {
      createElement: vi.fn(() => ({
        click,
        remove: vi.fn(),
        style: {},
        set href(_: string) {},
        set download(_: string) {},
      })),
      body: { append: vi.fn() },
    });
    vi.stubGlobal('window', { setTimeout: vi.fn((callback: () => void) => callback()) });
    const baseline = readBoundaryReviewArchive(reviewArchive('baseline'), 'baseline.zip');
    const followup = readBoundaryReviewArchive(reviewArchive('followup'), 'followup.zip');
    const result = await saveLesionVolumeComparison(baseline, followup, acceptedRequest());

    expect(result.filename).toBe('dicom-guide-lesion-volume-comparison-test.zip');
    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(LESION_VOLUME_COMPARISON_ENDPOINT);
    expect(init.credentials).toBe('same-origin');
    expect(init.headers['Content-Type']).toBe(LESION_VOLUME_COMPARISON_INPUT_MEDIA_TYPE);
    expect(click).toHaveBeenCalledOnce();
  });
});
