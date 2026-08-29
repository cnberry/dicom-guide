import { strToU8, zipSync } from 'fflate';
import type { LesionVolumeArchive } from './lesionVolume';

export const LESION_VOLUME_REVIEW_ATTESTATION =
  'I attest that I personally reviewed the complete manual boundary on the original local source images within the scope of my stated role. ScanView has not verified my identity or credentials.';

export const LESION_VOLUME_REVIEW_ROLES = [
  'radiologist',
  'neuro_oncologist',
  'neurosurgeon',
  'medical_physicist',
  'other_qualified_clinician',
] as const;

export type LesionVolumeReviewerRole = (typeof LESION_VOLUME_REVIEW_ROLES)[number];
export type LesionVolumeReviewDecision =
  | 'accepted_for_discussion'
  | 'revision_requested'
  | 'rejected';
export type AcquisitionSuitability = 'suitable' | 'uncertain' | 'not_suitable';

export type LesionVolumeReviewChecklist = {
  original_images_reviewed: boolean;
  full_boundary_reviewed: boolean;
  all_three_planes_reviewed: boolean;
  source_overlay_reviewed: boolean;
  motion_considered: boolean;
  partial_volume_considered: boolean;
  treatment_effect_considered: boolean;
  acquisition_protocol_considered: boolean;
};

export type LesionVolumeReviewRecord = {
  schema_version: '1.0.0';
  artifact_type: 'scanview.lesion-volume-review';
  review_id: string;
  created_at: string;
  review_status: LesionVolumeReviewDecision;
  local_only: true;
  sensitive: true;
  deidentified: false;
  source_snapshot: {
    evidence_artifact_id: string;
    patient_context_id: string | null;
    study_id: string;
    series_id: string;
    frame_of_reference_id: string;
    modality: 'MR' | 'CT';
    source_set_sha256: string;
    mask_pixel_sha256: string;
    foreground_voxel_count: number;
    volume_mm3: number;
    volume_ml: number;
    boundary_uncertainty: 'not_quantified';
  };
  reviewer: {
    name: string;
    role: LesionVolumeReviewerRole;
    organization: string | null;
    identity_verification: 'self_asserted_unverified';
  };
  review: {
    decision: LesionVolumeReviewDecision;
    acquisition_suitability: AcquisitionSuitability;
    planes_reviewed: ['axial', 'coronal', 'sagittal'];
    represented_tissue: string;
    inclusion_criteria: string;
    exclusion_criteria: string;
    note: string;
    checklist: LesionVolumeReviewChecklist;
  };
  attestation: typeof LESION_VOLUME_REVIEW_ATTESTATION;
  permitted_uses: {
    source_boundary_discussion: true;
    reviewed_volume_for_discussion: boolean;
    eligible_for_future_pairing_review: boolean;
    longitudinal_link: false;
    percent_change: false;
    response_classification: false;
    diagnosis: false;
    clinical_conclusion: false;
  };
  files: {
    evidence_archive: { filename: 'evidence.zip'; bytes: number; sha256: string };
    review_page: { filename: 'review.html'; bytes: number; sha256: string };
    readme: { filename: 'README.txt'; bytes: number; sha256: string };
  };
  limitations: string[];
};

export type LesionVolumeReviewArchive = {
  filename: string;
  bytes: Uint8Array;
  record: LesionVolumeReviewRecord;
};

export type BuildLesionVolumeReviewInput = {
  evidenceArchive: LesionVolumeArchive;
  reviewerName: string;
  reviewerRole: LesionVolumeReviewerRole;
  reviewerOrganization?: string;
  decision: LesionVolumeReviewDecision;
  acquisitionSuitability: AcquisitionSuitability;
  representedTissue: string;
  inclusionCriteria: string;
  exclusionCriteria: string;
  note?: string;
  checklist: LesionVolumeReviewChecklist;
  attested: boolean;
  reviewId?: string;
  createdAt?: string;
};

const REVIEW_LIMITATIONS = [
  'Reviewer identity, role, and credentials are self-asserted and are not authenticated by ScanView.',
  'Acceptance means suitable for discussion only; it is not clinical validation, medical-record sign-off, or regulatory clearance.',
  'The underlying source evidence remains a manually painted native-grid draft and its boundary uncertainty is not quantified.',
  'This review applies to one exact source series and does not establish that another scan contains the same lesion or tissue component.',
  'Differences in acquisition, motion, partial-volume effects, enhancement, edema, necrosis, and treatment effect can alter a boundary or volume.',
  'No longitudinal change, percentage change, treatment-response category, diagnosis, or clinical conclusion is authorized.',
  'Original DICOM images and the clinical medical record remain authoritative.',
];

const textValue = (
  value: string,
  label: string,
  maximum: number,
  { optional = false, multiline = false }: { optional?: boolean; multiline?: boolean } = {},
): string => {
  const normalized = value.replace(/\r\n?/g, '\n').trim();
  if (!normalized && !optional) throw new Error(`${label} is required.`);
  if (normalized.length > maximum) throw new Error(`${label} must be ${maximum} characters or fewer.`);
  for (const character of normalized) {
    const code = character.charCodeAt(0);
    if ((code < 32 && !(multiline && (character === '\n' || character === '\t'))) || code === 127) {
      throw new Error(`${label} contains unsupported control characters.`);
    }
  }
  if (!multiline && /[\n\t]/.test(normalized)) throw new Error(`${label} must be one line.`);
  return normalized;
};

const sha256Hex = async (bytes: Uint8Array): Promise<string> => {
  const owned = new Uint8Array(bytes.byteLength);
  owned.set(bytes);
  const digest = await crypto.subtle.digest('SHA-256', owned.buffer);
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, '0'))
    .join('');
};

const escapeHtml = (value: string): string =>
  value.replace(/[&<>"']/g, (character) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  })[character]!);

const roleLabel = (role: LesionVolumeReviewerRole): string => role.replaceAll('_', ' ');

const renderReviewPage = (record: Omit<LesionVolumeReviewRecord, 'files'>): Uint8Array => {
  const review = record.review;
  const checklist = Object.entries(review.checklist)
    .map(([name, checked]) => `<li>${checked ? 'Yes' : 'No'} · ${escapeHtml(name.replaceAll('_', ' '))}</li>`)
    .join('');
  const html = `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ScanView manual ROI boundary review</title><style>
body{font:16px/1.5 system-ui,sans-serif;margin:0;background:#f5f7f6;color:#17201e}.page{max-width:900px;margin:auto;padding:32px}.warning{border:3px solid #a23d35;background:#fff2f0;padding:16px;font-weight:700}.card{background:white;border:1px solid #cbd5d1;border-radius:10px;padding:20px;margin:18px 0}dt{font-weight:700}dd{margin:0 0 12px}code{overflow-wrap:anywhere}footer{font-size:13px;color:#4b5c57}@media print{body{background:white}.page{padding:0}.card{break-inside:avoid}}
</style></head><body><main class="page"><h1>Manual ROI boundary review</h1><p class="warning">SELF-ATTESTED REVIEW FOR DISCUSSION ONLY · IDENTITY NOT VERIFIED · NOT A DIAGNOSIS · NO LONGITUDINAL OR RESPONSE CONCLUSION</p>
<section class="card"><h2>Decision</h2><dl><dt>Status</dt><dd>${escapeHtml(record.review_status.replaceAll('_', ' '))}</dd><dt>Reviewer</dt><dd>${escapeHtml(record.reviewer.name)} · ${escapeHtml(roleLabel(record.reviewer.role))}${record.reviewer.organization ? ` · ${escapeHtml(record.reviewer.organization)}` : ''}</dd><dt>Acquisition suitability</dt><dd>${escapeHtml(review.acquisition_suitability.replaceAll('_', ' '))}</dd><dt>Reviewed volume</dt><dd>${record.source_snapshot.volume_ml.toFixed(6)} mL · ${record.source_snapshot.foreground_voxel_count.toLocaleString('en-US')} native voxels</dd></dl></section>
<section class="card"><h2>Boundary definition</h2><dl><dt>Represented tissue</dt><dd>${escapeHtml(review.represented_tissue)}</dd><dt>Inclusion criteria</dt><dd>${escapeHtml(review.inclusion_criteria)}</dd><dt>Exclusion criteria</dt><dd>${escapeHtml(review.exclusion_criteria)}</dd><dt>Note</dt><dd>${escapeHtml(review.note || 'None recorded.')}</dd></dl></section>
<section class="card"><h2>Checklist</h2><ul>${checklist}</ul><p>Planes reviewed: axial, coronal, sagittal.</p></section>
<section class="card"><h2>Source anchor</h2><p>Evidence <code>${escapeHtml(record.source_snapshot.evidence_artifact_id)}</code> · ${record.source_snapshot.modality} · exact source-set and mask hashes retained in <code>review.json</code>.</p></section>
<section class="card"><h2>Attestation</h2><p>${escapeHtml(record.attestation)}</p></section>
<footer>${record.limitations.map((item) => `<p>${escapeHtml(item)}</p>`).join('')}</footer></main></body></html>\n`;
  return strToU8(html);
};

const renderReadme = (): Uint8Array => strToU8(
  'ScanView manual ROI boundary review\n\n' +
  'This sensitive local archive contains review.json, evidence.zip, review.html, and README.txt.\n' +
  'The nested evidence remains source-bound and must be revalidated against the original local DICOM root.\n\n' +
  "Validate locally:\n  scanview-agent validate-lesion-volume-review review.zip '/path/to/DICOM-root'\n\n" +
  'A valid accepted record means self-attested review for discussion only. It does not authenticate the reviewer, establish a longitudinal lesion link, calculate change, classify response, diagnose, or create a clinical conclusion.\n',
);

const allChecklistItems = (checklist: LesionVolumeReviewChecklist): boolean =>
  Object.values(checklist).every((value) => value === true);

export const buildLesionVolumeReviewArchive = async (
  input: BuildLesionVolumeReviewInput,
): Promise<LesionVolumeReviewArchive> => {
  if (!LESION_VOLUME_REVIEW_ROLES.includes(input.reviewerRole)) {
    throw new Error('Select one supported qualified reviewer role.');
  }
  if (!['accepted_for_discussion', 'revision_requested', 'rejected'].includes(input.decision)) {
    throw new Error('Select a supported boundary review decision.');
  }
  if (!['suitable', 'uncertain', 'not_suitable'].includes(input.acquisitionSuitability)) {
    throw new Error('Select an acquisition-suitability decision.');
  }
  if (!input.attested) throw new Error('The reviewer attestation is required.');

  const reviewerName = textValue(input.reviewerName, 'Reviewer name', 120);
  const reviewerOrganization = textValue(
    input.reviewerOrganization ?? '',
    'Reviewer organization',
    160,
    { optional: true },
  );
  const representedTissue = textValue(input.representedTissue, 'Represented tissue', 500, { multiline: true });
  const inclusionCriteria = textValue(input.inclusionCriteria, 'Inclusion criteria', 1000, { multiline: true });
  const exclusionCriteria = textValue(input.exclusionCriteria, 'Exclusion criteria', 1000, { multiline: true });
  const note = textValue(input.note ?? '', 'Review note', 2000, { optional: true, multiline: true });

  const accepted = input.decision === 'accepted_for_discussion';
  if (accepted && input.acquisitionSuitability !== 'suitable') {
    throw new Error('Acceptance for discussion requires suitable acquisition.');
  }
  if (accepted && !allChecklistItems(input.checklist)) {
    throw new Error('Acceptance for discussion requires every boundary-review checklist item.');
  }

  const evidence = input.evidenceArchive.evidence;
  if (
    evidence.review.status !== 'unreviewed' ||
    evidence.permitted_uses.longitudinal_link !== false ||
    evidence.permitted_uses.percent_change !== false ||
    evidence.permitted_uses.response_classification !== false
  ) {
    throw new Error('The nested v1 evidence has unsupported review or longitudinal authority.');
  }
  if (accepted && !evidence.source.patient_context_id) {
    throw new Error(
      'Acceptance for future pairing review requires one locally derived opaque patient context.',
    );
  }
  const evidenceBytes = new Uint8Array(input.evidenceArchive.bytes.byteLength);
  evidenceBytes.set(input.evidenceArchive.bytes);
  const evidenceSha256 = await sha256Hex(evidenceBytes);
  const reviewId = input.reviewId ?? `review_${crypto.randomUUID()}`;
  if (!/^review_[0-9a-f-]{36}$/.test(reviewId)) throw new Error('Review ID is invalid.');
  const createdAt = input.createdAt ?? new Date().toISOString();
  if (!Number.isFinite(Date.parse(createdAt)) || !/[zZ]|[+-]\d\d:\d\d$/.test(createdAt)) {
    throw new Error('Review time must include a timezone.');
  }

  const recordWithoutFiles: Omit<LesionVolumeReviewRecord, 'files'> = {
    schema_version: '1.0.0',
    artifact_type: 'scanview.lesion-volume-review',
    review_id: reviewId,
    created_at: createdAt,
    review_status: input.decision,
    local_only: true,
    sensitive: true,
    deidentified: false,
    source_snapshot: {
      evidence_artifact_id: evidence.artifact_id,
      patient_context_id: evidence.source.patient_context_id ?? null,
      study_id: evidence.source.study_id,
      series_id: evidence.source.series_id,
      frame_of_reference_id: evidence.source.frame_of_reference_id,
      modality: evidence.source.modality,
      source_set_sha256: evidence.source.source_set_sha256,
      mask_pixel_sha256: evidence.measurement.mask_pixel_sha256,
      foreground_voxel_count: evidence.measurement.foreground_voxel_count,
      volume_mm3: evidence.measurement.volume_mm3,
      volume_ml: evidence.measurement.volume_ml,
      boundary_uncertainty: 'not_quantified',
    },
    reviewer: {
      name: reviewerName,
      role: input.reviewerRole,
      organization: reviewerOrganization || null,
      identity_verification: 'self_asserted_unverified',
    },
    review: {
      decision: input.decision,
      acquisition_suitability: input.acquisitionSuitability,
      planes_reviewed: ['axial', 'coronal', 'sagittal'],
      represented_tissue: representedTissue,
      inclusion_criteria: inclusionCriteria,
      exclusion_criteria: exclusionCriteria,
      note,
      checklist: { ...input.checklist },
    },
    attestation: LESION_VOLUME_REVIEW_ATTESTATION,
    permitted_uses: {
      source_boundary_discussion: true,
      reviewed_volume_for_discussion: accepted,
      eligible_for_future_pairing_review: accepted,
      longitudinal_link: false,
      percent_change: false,
      response_classification: false,
      diagnosis: false,
      clinical_conclusion: false,
    },
    limitations: [...REVIEW_LIMITATIONS],
  };
  const reviewPage = renderReviewPage(recordWithoutFiles);
  const readme = renderReadme();
  const record: LesionVolumeReviewRecord = {
    ...recordWithoutFiles,
    files: {
      evidence_archive: {
        filename: 'evidence.zip',
        bytes: evidenceBytes.byteLength,
        sha256: evidenceSha256,
      },
      review_page: {
        filename: 'review.html',
        bytes: reviewPage.byteLength,
        sha256: await sha256Hex(reviewPage),
      },
      readme: {
        filename: 'README.txt',
        bytes: readme.byteLength,
        sha256: await sha256Hex(readme),
      },
    },
  };
  const bytes = zipSync({
    'review.json': [strToU8(`${JSON.stringify(record, null, 2)}\n`), { level: 0 }],
    'evidence.zip': [evidenceBytes, { level: 0 }],
    'review.html': [reviewPage, { level: 0 }],
    'README.txt': [readme, { level: 0 }],
  });
  return {
    filename: `scanview-lesion-volume-review-${reviewId.slice(7, 15)}.zip`,
    bytes,
    record,
  };
};
