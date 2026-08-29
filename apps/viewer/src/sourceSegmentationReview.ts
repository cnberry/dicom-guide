import type {
  AcquisitionSuitability,
  LesionVolumeReviewDecision,
  LesionVolumeReviewerRole,
} from './lesionVolumeReview';

export const SOURCE_SEGMENTATION_REVIEW_ENDPOINT = '/v1/source-segmentation-reviews';
export const SOURCE_SEGMENTATION_REVIEW_REQUEST_MEDIA_TYPE =
  'application/vnd.scanview.source-segmentation-review-request+json';
export const SOURCE_SEGMENTATION_REVIEW_ATTESTATION =
  'I attest that I personally reviewed the complete source-carried DICOM SEG boundary on the original local source images within the scope of my stated role. I treated the source label, codes, creator, and algorithm as unauthenticated and unverified. ScanView has not verified my identity or credentials.';
export const SOURCE_SEGMENTATION_REVIEW_MAX_REQUEST_BYTES = 32 * 1024;
export const SOURCE_SEGMENTATION_REVIEW_MAX_ARCHIVE_BYTES = 420 * 1024 * 1024;

export type SourceSegmentationReviewChecklist = {
  original_images_reviewed: boolean;
  full_source_boundary_reviewed: boolean;
  all_three_planes_reviewed: boolean;
  mask_to_source_alignment_reviewed: boolean;
  source_segment_metadata_treated_as_unverified: boolean;
  creator_and_algorithm_treated_as_unverified: boolean;
  motion_considered: boolean;
  partial_volume_considered: boolean;
  treatment_effect_considered: boolean;
  acquisition_protocol_considered: boolean;
};

export type SourceSegmentationReviewInput = {
  catalogContentSha256: string;
  segmentationId: string;
  segmentNumber: number;
  reviewerName: string;
  reviewerRole: LesionVolumeReviewerRole;
  reviewerOrganization?: string;
  decision: LesionVolumeReviewDecision;
  acquisitionSuitability: AcquisitionSuitability;
  representedTissue: string;
  inclusionCriteria: string;
  exclusionCriteria: string;
  note?: string;
  checklist: SourceSegmentationReviewChecklist;
  attested: boolean;
};

export type SourceSegmentationReviewArchive = {
  filename: string;
  bytes: Uint8Array;
};

const sha256Pattern = /^[0-9a-f]{64}$/;
const segmentationIdPattern = /^instance_[0-9a-f]{20}$/;
const checklistKeys: Array<keyof SourceSegmentationReviewChecklist> = [
  'original_images_reviewed',
  'full_source_boundary_reviewed',
  'all_three_planes_reviewed',
  'mask_to_source_alignment_reviewed',
  'source_segment_metadata_treated_as_unverified',
  'creator_and_algorithm_treated_as_unverified',
  'motion_considered',
  'partial_volume_considered',
  'treatment_effect_considered',
  'acquisition_protocol_considered',
];

const textValue = (
  value: string,
  label: string,
  maximum: number,
  { optional = false, multiline = false }: { optional?: boolean; multiline?: boolean } = {},
): string => {
  const normalized = value.replace(/\r\n?/g, '\n').trim();
  if (!normalized && !optional) throw new Error(`${label} is required.`);
  if ([...normalized].length > maximum) {
    throw new Error(`${label} must be ${maximum} characters or fewer.`);
  }
  for (const character of normalized) {
    const code = character.charCodeAt(0);
    if ((code < 32 && !(multiline && (character === '\n' || character === '\t'))) || code === 127) {
      throw new Error(`${label} contains unsupported control characters.`);
    }
  }
  if (!multiline && /[\n\t]/.test(normalized)) throw new Error(`${label} must be one line.`);
  return normalized;
};

export const buildSourceSegmentationReviewRequest = (
  input: SourceSegmentationReviewInput,
): Record<string, unknown> => {
  if (!sha256Pattern.test(input.catalogContentSha256)) {
    throw new Error('The exact source-segmentation catalog binding is unavailable.');
  }
  if (!segmentationIdPattern.test(input.segmentationId)) {
    throw new Error('The source DICOM SEG reference is invalid.');
  }
  if (!Number.isSafeInteger(input.segmentNumber) || input.segmentNumber < 1 || input.segmentNumber > 65535) {
    throw new Error('The source DICOM SEG segment number is invalid.');
  }
  if (!['radiologist', 'neuro_oncologist', 'neurosurgeon', 'medical_physicist', 'other_qualified_clinician'].includes(input.reviewerRole)) {
    throw new Error('Select one supported qualified reviewer role.');
  }
  if (!['accepted_for_discussion', 'revision_requested', 'rejected'].includes(input.decision)) {
    throw new Error('Select a supported source-SEG boundary decision.');
  }
  if (!['suitable', 'uncertain', 'not_suitable'].includes(input.acquisitionSuitability)) {
    throw new Error('Select an acquisition-suitability decision.');
  }
  if (!input.attested) throw new Error('The source-SEG reviewer attestation is required.');
  const checklist = Object.fromEntries(
    checklistKeys.map((key) => {
      const value = input.checklist[key];
      if (typeof value !== 'boolean') throw new Error('Every source-SEG checklist value must be boolean.');
      return [key, value];
    }),
  ) as SourceSegmentationReviewChecklist;
  if (input.decision === 'accepted_for_discussion') {
    if (input.acquisitionSuitability !== 'suitable') {
      throw new Error('Acceptance for discussion requires suitable acquisition.');
    }
    if (!Object.values(checklist).every((value) => value === true)) {
      throw new Error('Acceptance for discussion requires every source-SEG checklist item.');
    }
  }

  return {
    schema_version: '1.0.0',
    artifact_type: 'scanview.source-segmentation-review-request',
    source: {
      catalog_content_sha256: input.catalogContentSha256,
      segmentation_id: input.segmentationId,
      segment_number: input.segmentNumber,
    },
    reviewer: {
      name: textValue(input.reviewerName, 'Reviewer name', 120),
      role: input.reviewerRole,
      organization: textValue(
        input.reviewerOrganization ?? '',
        'Reviewer organization',
        160,
        { optional: true },
      ) || null,
      identity_verification: 'self_asserted_unverified',
    },
    decision: input.decision,
    acquisition_suitability: input.acquisitionSuitability,
    represented_tissue: textValue(input.representedTissue, 'Represented tissue', 500, {
      multiline: true,
    }),
    inclusion_criteria: textValue(input.inclusionCriteria, 'Inclusion criteria', 1000, {
      multiline: true,
    }),
    exclusion_criteria: textValue(input.exclusionCriteria, 'Exclusion criteria', 1000, {
      multiline: true,
    }),
    note: textValue(input.note ?? '', 'Review note', 2000, {
      optional: true,
      multiline: true,
    }),
    checklist,
    attestation: SOURCE_SEGMENTATION_REVIEW_ATTESTATION,
  };
};

const responseFilename = (header: string | null): string => {
  const candidate = header?.match(/filename="?([A-Za-z0-9._-]+)"?/i)?.[1];
  return candidate?.endsWith('.zip')
    ? candidate
    : `scanview-source-segmentation-review-${new Date().toISOString().slice(0, 10)}.zip`;
};

export const requestSourceSegmentationReview = async (
  input: SourceSegmentationReviewInput,
): Promise<SourceSegmentationReviewArchive> => {
  const request = buildSourceSegmentationReviewRequest(input);
  const body = `${JSON.stringify(request)}\n`;
  const requestBytes = new TextEncoder().encode(body);
  if (requestBytes.byteLength > SOURCE_SEGMENTATION_REVIEW_MAX_REQUEST_BYTES) {
    throw new Error('The source-SEG review request exceeds the local safety limit.');
  }
  const response = await fetch(SOURCE_SEGMENTATION_REVIEW_ENDPOINT, {
    method: 'POST',
    cache: 'no-store',
    credentials: 'same-origin',
    headers: {
      Accept: 'application/zip',
      'Content-Type': SOURCE_SEGMENTATION_REVIEW_REQUEST_MEDIA_TYPE,
    },
    body,
  });
  if (!response.ok) {
    let detail = '';
    try {
      const value = (await response.json()) as { detail?: unknown };
      if (typeof value.detail === 'string') detail = value.detail;
    } catch {
      // The status is sufficient when the loopback response is not JSON.
    }
    throw new Error(
      detail || `The local source-SEG review assembler rejected the request (${response.status}).`,
    );
  }
  if (response.headers.get('Content-Type')?.split(';', 1)[0] !== 'application/zip') {
    throw new Error('The local source-SEG review assembler returned an unsupported file type.');
  }
  const declaredLength = Number(response.headers.get('Content-Length'));
  if (Number.isFinite(declaredLength) && declaredLength > SOURCE_SEGMENTATION_REVIEW_MAX_ARCHIVE_BYTES) {
    throw new Error('The local source-SEG review archive exceeds the safety limit.');
  }
  const bytes = new Uint8Array(await response.arrayBuffer());
  if (bytes.byteLength < 1 || bytes.byteLength > SOURCE_SEGMENTATION_REVIEW_MAX_ARCHIVE_BYTES) {
    throw new Error('The local source-SEG review archive is empty or exceeds the safety limit.');
  }
  return {
    filename: responseFilename(response.headers.get('Content-Disposition')),
    bytes,
  };
};
