import { unzipSync } from 'fflate';
import { describe, expect, it } from 'vitest';
import type { DicomSeries } from './dicom';
import { buildLesionVolumeArchive } from './lesionVolume';
import {
  LESION_VOLUME_REVIEW_ATTESTATION,
  buildLesionVolumeReviewArchive,
  type BuildLesionVolumeReviewInput,
  type LesionVolumeReviewChecklist,
} from './lesionVolumeReview';

const sourceSeries = (): DicomSeries => ({
  id: '0000000000000002',
  studyId: '0000000000000001',
  patientContextId: '0000000000000004',
  frameOfReferenceId: '0000000000000003',
  modality: 'MR',
  description: 'Synthetic series',
  imageType: ['ORIGINAL', 'PRIMARY'],
  sourceKind: 'browser-folder',
  geometry: {
    rows: 2,
    columns: 2,
    pixelSpacing: [0.5, 0.75],
    sliceThickness: 2,
    orientation: [1, 0, 0, 0, 1, 0],
  },
  instances: [0, 1, 2].map((index) => ({
    instanceId: `${index + 1}`.padStart(16, '0'),
    instanceNumber: index + 1,
    imagePosition: [0, 0, index * 2],
    rows: 2,
    columns: 2,
    pixelSpacing: [0.5, 0.75],
    sliceThickness: 2,
    orientation: [1, 0, 0, 0, 1, 0],
    numberOfFrames: 1,
    file: new File([new Uint8Array([index, 1, 2, 3])], `source-${index}.dcm`),
  })),
});

const completeChecklist = (): LesionVolumeReviewChecklist => ({
  original_images_reviewed: true,
  full_boundary_reviewed: true,
  all_three_planes_reviewed: true,
  source_overlay_reviewed: true,
  motion_considered: true,
  partial_volume_considered: true,
  treatment_effect_considered: true,
  acquisition_protocol_considered: true,
});

const acceptedInput = async (): Promise<BuildLesionVolumeReviewInput> => {
  const series = sourceSeries();
  const evidenceArchive = await buildLesionVolumeArchive({
    series,
    orderedInstanceIds: series.instances.map((instance) => instance.instanceId),
    dimensions: [2, 2, 3],
    sliceSpacingMm: 2,
    maskValues: new Uint8Array([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0]),
    dicomSegBytes: new Uint8Array(132).fill(7),
    artifactId: 'seg_12345678-1234-4abc-8def-1234567890ab',
    trackingUid: '2.25.123456789',
    label: 'Reviewer-defined region',
    targetDefinition: 'Manual discussion boundary; tissue identity is unreviewed.',
    createdAt: '2026-08-28T12:00:00.000Z',
  });
  return {
    evidenceArchive,
    reviewerName: 'Synthetic Reviewer',
    reviewerRole: 'neuro_oncologist',
    reviewerOrganization: 'Synthetic clinic',
    decision: 'accepted_for_discussion',
    acquisitionSuitability: 'suitable',
    representedTissue: 'Contrast-enhancing tissue selected for the discussion draft.',
    inclusionCriteria: 'Include contiguous enhancing tissue visible in all three planes.',
    exclusionCriteria: 'Exclude vessels, necrosis, edema, and postoperative cavity.',
    note: 'Synthetic review only.',
    checklist: completeChecklist(),
    attested: true,
    reviewId: 'review_12345678-1234-4abc-8def-1234567890ab',
    createdAt: '2026-08-28T13:00:00.000Z',
  };
};

describe('manual lesion ROI boundary review archive', () => {
  it('binds an accepted self-attested review to the exact nested source evidence', async () => {
    const result = await buildLesionVolumeReviewArchive(await acceptedInput());
    const files = unzipSync(result.bytes);
    expect(Object.keys(files).sort()).toEqual([
      'README.txt',
      'evidence.zip',
      'review.html',
      'review.json',
    ]);
    const record = JSON.parse(new TextDecoder().decode(files['review.json']));
    expect(record).toEqual(result.record);
    expect(record.source_snapshot).toMatchObject({
      evidence_artifact_id: 'seg_12345678-1234-4abc-8def-1234567890ab',
      patient_context_id: '0000000000000004',
      volume_mm3: 2.25,
      volume_ml: 0.00225,
      boundary_uncertainty: 'not_quantified',
    });
    expect(record.reviewer.identity_verification).toBe('self_asserted_unverified');
    expect(record.attestation).toBe(LESION_VOLUME_REVIEW_ATTESTATION);
    expect(record.permitted_uses).toEqual({
      source_boundary_discussion: true,
      reviewed_volume_for_discussion: true,
      eligible_for_future_pairing_review: true,
      longitudinal_link: false,
      percent_change: false,
      response_classification: false,
      diagnosis: false,
      clinical_conclusion: false,
    });
    const page = new TextDecoder().decode(files['review.html']);
    expect(page).toContain('SELF-ATTESTED REVIEW FOR DISCUSSION ONLY');
    expect(page).not.toMatch(/<script|https?:\/\/|src=|href=/i);
    expect(record.files.evidence_archive.sha256).toMatch(/^[0-9a-f]{64}$/);
    expect(record.files.review_page.bytes).toBe(files['review.html'].byteLength);
  });

  it('requires suitable acquisition, a complete checklist, and attestation for acceptance', async () => {
    const unsuitable = await acceptedInput();
    unsuitable.acquisitionSuitability = 'uncertain';
    await expect(buildLesionVolumeReviewArchive(unsuitable)).rejects.toThrow(/suitable acquisition/i);

    const incomplete = await acceptedInput();
    incomplete.checklist.partial_volume_considered = false;
    await expect(buildLesionVolumeReviewArchive(incomplete)).rejects.toThrow(/every.*checklist/i);

    const unattested = await acceptedInput();
    unattested.attested = false;
    await expect(buildLesionVolumeReviewArchive(unattested)).rejects.toThrow(/attestation/i);

    const missingPatientContext = await acceptedInput();
    delete missingPatientContext.evidenceArchive.evidence.source.patient_context_id;
    await expect(buildLesionVolumeReviewArchive(missingPatientContext)).rejects.toThrow(
      /opaque patient context/i,
    );
  });

  it('records revision requests without granting future pairing eligibility', async () => {
    const input = await acceptedInput();
    input.decision = 'revision_requested';
    input.acquisitionSuitability = 'uncertain';
    input.checklist.full_boundary_reviewed = false;
    const result = await buildLesionVolumeReviewArchive(input);
    expect(result.record.review_status).toBe('revision_requested');
    expect(result.record.permitted_uses.reviewed_volume_for_discussion).toBe(false);
    expect(result.record.permitted_uses.eligible_for_future_pairing_review).toBe(false);
    expect(result.record.permitted_uses.percent_change).toBe(false);
  });

  it('escapes review-page text and rejects unsupported controls', async () => {
    const escaped = await acceptedInput();
    escaped.representedTissue = '<img src=x onerror=alert(1)> & tissue';
    const result = await buildLesionVolumeReviewArchive(escaped);
    const page = new TextDecoder().decode(unzipSync(result.bytes)['review.html']);
    expect(page).toContain('&lt;img src=x onerror=alert(1)&gt; &amp; tissue');
    expect(page).not.toContain('<img src=x');

    const control = await acceptedInput();
    control.reviewerName = 'Reviewer\u0000Name';
    await expect(buildLesionVolumeReviewArchive(control)).rejects.toThrow(/control characters/i);
  });
});
