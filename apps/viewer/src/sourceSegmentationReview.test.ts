import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  SOURCE_SEGMENTATION_REVIEW_ATTESTATION,
  SOURCE_SEGMENTATION_REVIEW_ENDPOINT,
  SOURCE_SEGMENTATION_REVIEW_REQUEST_MEDIA_TYPE,
  buildSourceSegmentationReviewRequest,
  requestSourceSegmentationReview,
  type SourceSegmentationReviewChecklist,
  type SourceSegmentationReviewInput,
} from './sourceSegmentationReview';

const checklist = (checked = true): SourceSegmentationReviewChecklist => ({
  original_images_reviewed: checked,
  full_source_boundary_reviewed: checked,
  all_three_planes_reviewed: checked,
  mask_to_source_alignment_reviewed: checked,
  source_segment_metadata_treated_as_unverified: checked,
  creator_and_algorithm_treated_as_unverified: checked,
  motion_considered: checked,
  partial_volume_considered: checked,
  treatment_effect_considered: checked,
  acquisition_protocol_considered: checked,
});

const acceptedInput = (): SourceSegmentationReviewInput => ({
  catalogContentSha256: 'a'.repeat(64),
  segmentationId: 'instance_0123456789abcdefabcd',
  segmentNumber: 3,
  reviewerName: 'Synthetic Reviewer',
  reviewerRole: 'radiologist',
  reviewerOrganization: 'Synthetic Test Lab',
  decision: 'accepted_for_discussion',
  acquisitionSuitability: 'suitable',
  representedTissue: 'Reviewer-defined synthetic tissue.',
  inclusionCriteria: 'Complete displayed synthetic boundary.',
  exclusionCriteria: 'Everything outside the displayed boundary.',
  note: 'Patient-free synthetic review.',
  checklist: checklist(),
  attested: true,
});

afterEach(() => vi.restoreAllMocks());

describe('source DICOM SEG review transport', () => {
  it('builds the strict opaque-reference request without pixels or source text', () => {
    const request = buildSourceSegmentationReviewRequest(acceptedInput());
    expect(request).toMatchObject({
      schema_version: '1.0.0',
      artifact_type: 'scanview.source-segmentation-review-request',
      source: {
        catalog_content_sha256: 'a'.repeat(64),
        segmentation_id: 'instance_0123456789abcdefabcd',
        segment_number: 3,
      },
      attestation: SOURCE_SEGMENTATION_REVIEW_ATTESTATION,
    });
    expect(Object.keys(request.source as object)).toEqual([
      'catalog_content_sha256',
      'segmentation_id',
      'segment_number',
    ]);
    expect(JSON.stringify(request)).not.toContain('mask_pixels');
    expect(JSON.stringify(request)).not.toContain('segment_label');
    expect(JSON.stringify(request)).not.toContain('computed_volume');
  });

  it('requires complete review gates only for acceptance', () => {
    expect(() => buildSourceSegmentationReviewRequest({
      ...acceptedInput(),
      acquisitionSuitability: 'uncertain',
    })).toThrow(/suitable acquisition/i);
    expect(() => buildSourceSegmentationReviewRequest({
      ...acceptedInput(),
      checklist: { ...checklist(), motion_considered: false },
    })).toThrow(/every source-SEG checklist/i);
    expect(() => buildSourceSegmentationReviewRequest({
      ...acceptedInput(),
      attested: false,
    })).toThrow(/attestation/i);
    expect(() => buildSourceSegmentationReviewRequest({
      ...acceptedInput(),
      decision: 'revision_requested',
      acquisitionSuitability: 'uncertain',
      checklist: checklist(false),
    })).not.toThrow();
  });

  it('rejects control characters and invalid source bindings before fetch', async () => {
    expect(() => buildSourceSegmentationReviewRequest({
      ...acceptedInput(),
      reviewerName: 'Reviewer\u0000Name',
    })).toThrow(/control characters/i);
    await expect(requestSourceSegmentationReview({
      ...acceptedInput(),
      catalogContentSha256: '',
    })).rejects.toThrow(/catalog binding/i);
  });

  it('uses a same-origin no-store POST and accepts a bounded ZIP', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(
      new Uint8Array([80, 75, 3, 4]),
      {
        status: 200,
        headers: {
          'Content-Type': 'application/zip',
          'Content-Disposition': 'attachment; filename="scanview-source-segmentation-review-test.zip"',
          'Content-Length': '4',
        },
      },
    ));
    const result = await requestSourceSegmentationReview(acceptedInput());
    expect(result.filename).toBe('scanview-source-segmentation-review-test.zip');
    expect(result.bytes).toEqual(new Uint8Array([80, 75, 3, 4]));
    expect(fetchMock).toHaveBeenCalledWith(SOURCE_SEGMENTATION_REVIEW_ENDPOINT, expect.objectContaining({
      method: 'POST',
      cache: 'no-store',
      credentials: 'same-origin',
      headers: {
        Accept: 'application/zip',
        'Content-Type': SOURCE_SEGMENTATION_REVIEW_REQUEST_MEDIA_TYPE,
      },
    }));
  });

  it('surfaces bounded local rejection details and rejects a non-ZIP response', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(new Response(
      JSON.stringify({ detail: 'source-SEG catalog binding is unavailable or changed' }),
      { status: 422, headers: { 'Content-Type': 'application/json' } },
    ));
    await expect(requestSourceSegmentationReview(acceptedInput())).rejects.toThrow(
      /catalog binding is unavailable or changed/i,
    );

    vi.mocked(globalThis.fetch).mockResolvedValueOnce(new Response('not a ZIP', {
      status: 200,
      headers: { 'Content-Type': 'text/plain' },
    }));
    await expect(requestSourceSegmentationReview(acceptedInput())).rejects.toThrow(
      /unsupported file type/i,
    );
  });
});
