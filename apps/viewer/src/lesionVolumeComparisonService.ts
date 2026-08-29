import { strToU8, unzipSync, zipSync } from 'fflate';
import { downloadArchive } from './keyImages';
import type { LesionVolumeReviewerRole } from './lesionVolumeReview';

export const LESION_VOLUME_COMPARISON_ENDPOINT = '/v1/lesion-volume-comparisons';
export const LESION_VOLUME_COMPARISON_INPUT_MEDIA_TYPE =
  'application/vnd.scanview.lesion-volume-comparison-input+zip';
export const MAX_BOUNDARY_REVIEW_ARCHIVE_BYTES = 160 * 1024 * 1024;
export const MAX_BOUNDARY_REVIEW_TEXT_BYTES = 2 * 1024 * 1024;
export const LESION_VOLUME_COMPARISON_ATTESTATION =
  'I attest that I personally reviewed both accepted boundary records and their original local source images, and recorded my judgments about chronology, same-lesion identity, represented tissue, acquisition comparability, boundary comparability, and registration need. ScanView has not verified my identity or credentials.';

export type ImportedBoundaryReview = {
  filename: string;
  bytes: Uint8Array;
  reviewId: string;
  evidenceArtifactId: string;
  patientContextId: string;
  studyId: string;
  seriesId: string;
  modality: 'MR' | 'CT';
  reviewedVolumeMl: number;
  representedTissue: string;
};

export type LesionVolumeComparisonChecklist = {
  both_original_sources_reviewed: boolean;
  both_complete_boundaries_reviewed: boolean;
  boundary_definitions_compared: boolean;
  same_lesion_identity_reviewed: boolean;
  same_represented_tissue_reviewed: boolean;
  acquisition_differences_reviewed: boolean;
  chronology_confirmed: boolean;
  registration_need_reviewed: boolean;
};

export type LesionVolumeComparisonRequest = {
  schema_version: '1.0.0';
  artifact_type: 'scanview.lesion-volume-comparison-request';
  reviewer: {
    name: string;
    role: LesionVolumeReviewerRole;
    organization: string | null;
    identity_verification: 'self_asserted_unverified';
  };
  decision:
    | 'accepted_for_volume_change_discussion'
    | 'revision_requested'
    | 'rejected';
  pairing: {
    same_lesion_identity: 'confirmed' | 'uncertain' | 'not_confirmed';
    same_represented_tissue: 'confirmed' | 'uncertain' | 'not_confirmed';
    chronology: 'confirmed' | 'not_confirmed';
    acquisition_comparability: 'suitable' | 'suitable_with_limitations' | 'not_suitable';
    boundary_comparability: 'suitable' | 'suitable_with_limitations' | 'not_suitable';
    registration_consideration: 'required' | 'not_required' | 'uncertain';
    limitation_note: string;
    treatment_context_note: string;
  };
  checklist: LesionVolumeComparisonChecklist;
  attestation: typeof LESION_VOLUME_COMPARISON_ATTESTATION;
};

type ReviewRecord = {
  artifact_type?: unknown;
  review_id?: unknown;
  review_status?: unknown;
  source_snapshot?: unknown;
  review?: unknown;
  permitted_uses?: unknown;
};

const objectValue = (value: unknown): Record<string, unknown> | undefined =>
  typeof value === 'object' && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : undefined;

const boundedText = (
  value: string,
  label: string,
  maximum: number,
  optional = false,
): string => {
  const normalized = value.replace(/\r\n?/g, '\n').trim();
  if (!normalized && !optional) throw new Error(`${label} is required.`);
  if (normalized.length > maximum) throw new Error(`${label} must be ${maximum} characters or fewer.`);
  if (/\p{Cc}/u.test(normalized.replace(/[\n\t]/g, ''))) {
    throw new Error(`${label} contains unsupported control characters.`);
  }
  return normalized;
};

export const readBoundaryReviewArchive = (
  bytes: Uint8Array,
  filename: string,
): ImportedBoundaryReview => {
  if (bytes.byteLength === 0 || bytes.byteLength > MAX_BOUNDARY_REVIEW_ARCHIVE_BYTES) {
    throw new Error('Boundary review archive is empty or exceeds the 160 MiB local limit.');
  }
  let members: Record<string, Uint8Array>;
  const entries: string[] = [];
  let expandedBytes = 0;
  let unsafeMember = false;
  try {
    members = unzipSync(bytes, {
      filter: (file) => {
        entries.push(file.name);
        const maximum = file.name === 'evidence.zip'
          ? MAX_BOUNDARY_REVIEW_ARCHIVE_BYTES
          : ['review.json', 'review.html', 'README.txt'].includes(file.name)
            ? MAX_BOUNDARY_REVIEW_TEXT_BYTES
            : 0;
        expandedBytes += file.originalSize;
        if (
          maximum === 0 ||
          file.originalSize > maximum ||
          expandedBytes > MAX_BOUNDARY_REVIEW_ARCHIVE_BYTES + 3 * MAX_BOUNDARY_REVIEW_TEXT_BYTES
        ) {
          unsafeMember = true;
          return false;
        }
        return true;
      },
    });
  } catch {
    throw new Error('Boundary review archive is not a readable local ZIP.');
  }
  const expected = ['README.txt', 'evidence.zip', 'review.html', 'review.json'];
  const names = Object.keys(members).sort();
  if (
    unsafeMember ||
    entries.length !== expected.length ||
    new Set(entries).size !== entries.length ||
    JSON.stringify(entries.sort()) !== JSON.stringify(expected) ||
    JSON.stringify(names) !== JSON.stringify(expected)
  ) {
    throw new Error('Boundary review archive has an unsupported member set.');
  }
  let record: ReviewRecord;
  try {
    record = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(members['review.json'])) as ReviewRecord;
  } catch {
    throw new Error('Boundary review record is not valid JSON.');
  }
  const source = objectValue(record.source_snapshot);
  const review = objectValue(record.review);
  const permissions = objectValue(record.permitted_uses);
  if (
    record.artifact_type !== 'scanview.lesion-volume-review' ||
    record.review_status !== 'accepted_for_discussion' ||
    permissions?.eligible_for_future_pairing_review !== true ||
    typeof record.review_id !== 'string' ||
    !/^review_[0-9a-f-]{36}$/.test(record.review_id) ||
    !source ||
    typeof source.evidence_artifact_id !== 'string' ||
    typeof source.patient_context_id !== 'string' ||
    typeof source.study_id !== 'string' ||
    typeof source.series_id !== 'string' ||
    !['MR', 'CT'].includes(String(source.modality)) ||
    typeof source.volume_ml !== 'number' ||
    !Number.isFinite(source.volume_ml) ||
    source.volume_ml <= 0 ||
    !review ||
    typeof review.represented_tissue !== 'string'
  ) {
    throw new Error('Boundary review is not an accepted v1 record eligible for pairing review.');
  }
  const owned = new Uint8Array(bytes.byteLength);
  owned.set(bytes);
  return {
    filename,
    bytes: owned,
    reviewId: record.review_id,
    evidenceArtifactId: source.evidence_artifact_id,
    patientContextId: source.patient_context_id,
    studyId: source.study_id,
    seriesId: source.series_id,
    modality: source.modality as 'MR' | 'CT',
    reviewedVolumeMl: source.volume_ml,
    representedTissue: review.represented_tissue,
  };
};

export type BuildPairingRequestInput = Omit<
  LesionVolumeComparisonRequest,
  'schema_version' | 'artifact_type' | 'attestation' | 'reviewer'
> & {
  reviewerName: string;
  reviewerRole: LesionVolumeReviewerRole;
  reviewerOrganization?: string;
  attested: boolean;
};

export const buildPairingRequest = (
  input: BuildPairingRequestInput,
): LesionVolumeComparisonRequest => {
  const reviewerName = boundedText(input.reviewerName, 'Reviewer name', 120);
  const reviewerOrganization = boundedText(
    input.reviewerOrganization ?? '',
    'Reviewer organization',
    160,
    true,
  );
  const limitationNote = boundedText(
    input.pairing.limitation_note,
    'Limitation note',
    2000,
    true,
  );
  const treatmentContextNote = boundedText(
    input.pairing.treatment_context_note,
    'Treatment context note',
    2000,
    true,
  );
  if (!input.attested) throw new Error('The pairing-review attestation is required.');
  const needsLimitation =
    input.pairing.acquisition_comparability === 'suitable_with_limitations' ||
    input.pairing.boundary_comparability === 'suitable_with_limitations' ||
    input.pairing.registration_consideration !== 'not_required';
  if (needsLimitation && !limitationNote) {
    throw new Error('Documented comparability or registration limitations require a note.');
  }
  if (input.decision === 'accepted_for_volume_change_discussion') {
    if (
      input.pairing.same_lesion_identity !== 'confirmed' ||
      input.pairing.same_represented_tissue !== 'confirmed' ||
      input.pairing.chronology !== 'confirmed' ||
      !['suitable', 'suitable_with_limitations'].includes(input.pairing.acquisition_comparability) ||
      !['suitable', 'suitable_with_limitations'].includes(input.pairing.boundary_comparability) ||
      Object.values(input.checklist).some((value) => value !== true)
    ) {
      throw new Error('Acceptance requires confirmed identity/tissue/chronology, suitable comparability, and every checklist item.');
    }
  }
  return {
    schema_version: '1.0.0',
    artifact_type: 'scanview.lesion-volume-comparison-request',
    reviewer: {
      name: reviewerName,
      role: input.reviewerRole,
      organization: reviewerOrganization || null,
      identity_verification: 'self_asserted_unverified',
    },
    decision: input.decision,
    pairing: {
      ...input.pairing,
      limitation_note: limitationNote,
      treatment_context_note: treatmentContextNote,
    },
    checklist: { ...input.checklist },
    attestation: LESION_VOLUME_COMPARISON_ATTESTATION,
  };
};

export const buildLesionVolumeComparisonTransport = (
  baseline: ImportedBoundaryReview,
  followup: ImportedBoundaryReview,
  request: LesionVolumeComparisonRequest,
): Uint8Array => {
  if (baseline.reviewId === followup.reviewId) {
    throw new Error('Baseline and follow-up boundary reviews must be distinct.');
  }
  return zipSync(
    {
      'baseline-review.zip': [baseline.bytes, { level: 0 }],
      'followup-review.zip': [followup.bytes, { level: 0 }],
      'pairing-request.json': [
        strToU8(`${JSON.stringify(request, null, 2)}\n`),
        { level: 0 },
      ],
    },
    { level: 0 },
  );
};

const responseFilename = (header: string | null): string => {
  const candidate = header?.match(/filename="?([A-Za-z0-9._-]+)"?/i)?.[1];
  return candidate?.endsWith('.zip')
    ? candidate
    : `scanview-lesion-volume-comparison-${new Date().toISOString().slice(0, 10)}.zip`;
};

export const saveLesionVolumeComparison = async (
  baseline: ImportedBoundaryReview,
  followup: ImportedBoundaryReview,
  request: LesionVolumeComparisonRequest,
): Promise<{ filename: string; bytes: Uint8Array }> => {
  const transport = buildLesionVolumeComparisonTransport(baseline, followup, request);
  const body = transport.buffer.slice(
    transport.byteOffset,
    transport.byteOffset + transport.byteLength,
  ) as ArrayBuffer;
  const response = await fetch(LESION_VOLUME_COMPARISON_ENDPOINT, {
    method: 'POST',
    cache: 'no-store',
    credentials: 'same-origin',
    headers: {
      Accept: 'application/zip',
      'Content-Type': LESION_VOLUME_COMPARISON_INPUT_MEDIA_TYPE,
    },
    body,
  });
  if (!response.ok) {
    let detail = '';
    try {
      const value = await response.json() as { detail?: unknown };
      if (typeof value.detail === 'string') detail = value.detail;
    } catch {
      // Local status remains sufficient if an error response is not JSON.
    }
    throw new Error(
      detail || `The local volume-comparison assembler rejected the review pair (${response.status}).`,
    );
  }
  if (response.headers.get('Content-Type')?.split(';', 1)[0] !== 'application/zip') {
    throw new Error('The local volume-comparison assembler returned an unsupported file type.');
  }
  const result = {
    filename: responseFilename(response.headers.get('Content-Disposition')),
    bytes: new Uint8Array(await response.arrayBuffer()),
  };
  downloadArchive(result.bytes, result.filename);
  return result;
};
