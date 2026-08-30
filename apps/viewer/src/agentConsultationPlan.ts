import type { DicomSeries } from './dicom';

export const AGENT_CONSULTATION_PLAN_ENDPOINT =
  '/v1/agent-consultation-plans/validate';
export const AGENT_CONSULTATION_PLAN_MEDIA_TYPE =
  'application/vnd.dicom-guide.agent-consultation-plan+json';
export const AGENT_CONSULTATION_PLAN_MAX_BYTES = 32 * 1024;
export const AGENT_CONSULTATION_PLAN_MIN_ITEMS = 2;
export const AGENT_CONSULTATION_PLAN_MAX_ITEMS = 8;
export const AGENT_CONSULTATION_PLAN_MAX_HEADING_CHARACTERS = 80;

const seriesIdPattern = /^series_[0-9a-f]{20}$/;
const instanceIdPattern = /^instance_[0-9a-f]{20}$/;
const itemIdPattern = /^item_0[1-8]$/;
const sha256Pattern = /^[0-9a-f]{64}$/;

export type AgentConsultationPlanItem = {
  item_id: string;
  series_id: string;
  instance_id: string;
  modality: 'MR' | 'CT';
  discussion_heading: string;
  proposal_source: 'software_agent_unverified';
  review_status: 'unreviewed';
  auto_selected: false;
};

export type AgentConsultationPlan = {
  schema_version: '1.0.0';
  artifact_type: 'dicom-guide.agent-consultation-plan';
  generated_at: string;
  catalog_content_sha256: string;
  local_only: true;
  privacy: {
    classification: 'sensitive_local_medical_data';
    direct_identifier_tags_excluded: true;
    discussion_headings_may_contain_identifiers: true;
    deidentified: false;
    contains_pixels: false;
    contains_paths: false;
  };
  author: {
    kind: 'software_agent_unverified';
    identity_authenticated: false;
  };
  review_status: 'unreviewed';
  items: AgentConsultationPlanItem[];
  relationship: {
    selection_method: 'agent_proposed_exact_native_sources';
    item_count: number;
    same_patient_context: true;
    modalities_present: ['MR', 'CT'];
    distinct_source_study_count: number;
    distinct_source_instances: true;
    chronology_asserted: false;
    registration_asserted: false;
    lesion_identity_asserted: false;
  };
  clinical_interpretations: [];
  required_human_actions: string[];
  permissions: {
    exact_source_navigation_authorized: true;
    automatic_board_capture_authorized: false;
    source_mutation_authorized: false;
    chronology_authorized: false;
    registration_authorized: false;
    lesion_link_authorized: false;
    response_classification_authorized: false;
    treatment_effect_conclusion_authorized: false;
    diagnosis_authorized: false;
    clinical_conclusion_authorized: false;
  };
  limitations: string[];
};

export type ResolvedAgentConsultationPlanItem = {
  itemId: string;
  seriesId: string;
  instanceId: string;
  instanceIndex: number;
  modality: 'MR' | 'CT';
  discussionHeading: string;
  seriesDescription: string;
  stackPosition: number;
  stackCount: number;
};

export type ResolvedAgentConsultationPlan = {
  plan: AgentConsultationPlan;
  items: ResolvedAgentConsultationPlanItem[];
};

type ValidationSummary = {
  valid: true;
  item_count: number;
  modalities_present: ['MR', 'CT'];
  review_status: 'unreviewed';
  agent_identity_authenticated: false;
  exact_source_navigation_authorized: true;
  automatic_board_capture_authorized: false;
  clinical_conclusion_authorized: false;
  contains_prompts: false;
  contains_source_ids: false;
  local_only: true;
};

const isRecord = (value: unknown): value is Record<string, unknown> =>
  Boolean(value) && typeof value === 'object' && !Array.isArray(value);

const exactKeys = (value: Record<string, unknown>, expected: string[]): boolean => {
  const keys = Object.keys(value).sort();
  return keys.length === expected.length && keys.every((key, index) => key === [...expected].sort()[index]);
};

const headingValid = (value: unknown): value is string =>
  typeof value === 'string' &&
  value === value.trim() &&
  [...value].length >= 1 &&
  [...value].length <= AGENT_CONSULTATION_PLAN_MAX_HEADING_CHARACTERS &&
  !/\p{C}/u.test(value);

const fixedPermissions = (value: unknown): boolean => {
  if (!isRecord(value)) return false;
  const expected = [
    'exact_source_navigation_authorized',
    'automatic_board_capture_authorized',
    'source_mutation_authorized',
    'chronology_authorized',
    'registration_authorized',
    'lesion_link_authorized',
    'response_classification_authorized',
    'treatment_effect_conclusion_authorized',
    'diagnosis_authorized',
    'clinical_conclusion_authorized',
  ];
  return (
    exactKeys(value, expected) &&
    value.exact_source_navigation_authorized === true &&
    expected
      .filter((key) => key !== 'exact_source_navigation_authorized')
      .every((key) => value[key] === false)
  );
};

const fixedPrivacy = (value: unknown): boolean =>
  isRecord(value) &&
  exactKeys(value, [
    'classification',
    'direct_identifier_tags_excluded',
    'discussion_headings_may_contain_identifiers',
    'deidentified',
    'contains_pixels',
    'contains_paths',
  ]) &&
  value.classification === 'sensitive_local_medical_data' &&
  value.direct_identifier_tags_excluded === true &&
  value.discussion_headings_may_contain_identifiers === true &&
  value.deidentified === false &&
  value.contains_pixels === false &&
  value.contains_paths === false;

export const parseAgentConsultationPlan = (text: string): AgentConsultationPlan => {
  const bytes = new TextEncoder().encode(text).byteLength;
  if (bytes === 0 || bytes > AGENT_CONSULTATION_PLAN_MAX_BYTES) {
    throw new Error('Agent consultation plan exceeds the 32 KiB local safety limit.');
  }
  let candidate: unknown;
  try {
    candidate = JSON.parse(text);
  } catch {
    throw new Error('Agent consultation plan is not valid JSON.');
  }
  const topKeys = [
    'schema_version',
    'artifact_type',
    'generated_at',
    'catalog_content_sha256',
    'local_only',
    'privacy',
    'author',
    'review_status',
    'items',
    'relationship',
    'clinical_interpretations',
    'required_human_actions',
    'permissions',
    'limitations',
  ];
  if (
    !isRecord(candidate) ||
    !exactKeys(candidate, topKeys) ||
    candidate.schema_version !== '1.0.0' ||
    candidate.artifact_type !== 'dicom-guide.agent-consultation-plan' ||
    typeof candidate.generated_at !== 'string' ||
    Number.isNaN(Date.parse(candidate.generated_at)) ||
    typeof candidate.catalog_content_sha256 !== 'string' ||
    !sha256Pattern.test(candidate.catalog_content_sha256) ||
    candidate.local_only !== true ||
    candidate.review_status !== 'unreviewed' ||
    !fixedPrivacy(candidate.privacy) ||
    !isRecord(candidate.author) ||
    !exactKeys(candidate.author, ['kind', 'identity_authenticated']) ||
    candidate.author.kind !== 'software_agent_unverified' ||
    candidate.author.identity_authenticated !== false ||
    !Array.isArray(candidate.items) ||
    candidate.items.length < AGENT_CONSULTATION_PLAN_MIN_ITEMS ||
    candidate.items.length > AGENT_CONSULTATION_PLAN_MAX_ITEMS ||
    !Array.isArray(candidate.clinical_interpretations) ||
    candidate.clinical_interpretations.length !== 0 ||
    !Array.isArray(candidate.required_human_actions) ||
    !candidate.required_human_actions.every((item) => typeof item === 'string') ||
    !Array.isArray(candidate.limitations) ||
    !candidate.limitations.every((item) => typeof item === 'string') ||
    !fixedPermissions(candidate.permissions)
  ) {
    throw new Error('Agent consultation plan contract is invalid.');
  }
  if (!isRecord(candidate.relationship)) {
    throw new Error('Agent consultation plan relationship is invalid.');
  }
  const relationshipKeys = [
    'selection_method',
    'item_count',
    'same_patient_context',
    'modalities_present',
    'distinct_source_study_count',
    'distinct_source_instances',
    'chronology_asserted',
    'registration_asserted',
    'lesion_identity_asserted',
  ];
  const modalities = candidate.relationship.modalities_present;
  if (
    !exactKeys(candidate.relationship, relationshipKeys) ||
    candidate.relationship.selection_method !== 'agent_proposed_exact_native_sources' ||
    candidate.relationship.item_count !== candidate.items.length ||
    candidate.relationship.same_patient_context !== true ||
    !Array.isArray(modalities) ||
    modalities.length !== 2 ||
    modalities[0] !== 'MR' ||
    modalities[1] !== 'CT' ||
    !Number.isInteger(candidate.relationship.distinct_source_study_count) ||
    Number(candidate.relationship.distinct_source_study_count) < 2 ||
    candidate.relationship.distinct_source_instances !== true ||
    candidate.relationship.chronology_asserted !== false ||
    candidate.relationship.registration_asserted !== false ||
    candidate.relationship.lesion_identity_asserted !== false
  ) {
    throw new Error('Agent consultation plan relationship is invalid.');
  }
  const itemKeys = [
    'item_id',
    'series_id',
    'instance_id',
    'modality',
    'discussion_heading',
    'proposal_source',
    'review_status',
    'auto_selected',
  ];
  const seenInstances = new Set<string>();
  candidate.items.forEach((item, index) => {
    if (
      !isRecord(item) ||
      !exactKeys(item, itemKeys) ||
      item.item_id !== `item_${String(index + 1).padStart(2, '0')}` ||
      typeof item.item_id !== 'string' ||
      !itemIdPattern.test(item.item_id) ||
      typeof item.series_id !== 'string' ||
      !seriesIdPattern.test(item.series_id) ||
      typeof item.instance_id !== 'string' ||
      !instanceIdPattern.test(item.instance_id) ||
      seenInstances.has(item.instance_id) ||
      !['MR', 'CT'].includes(String(item.modality)) ||
      !headingValid(item.discussion_heading) ||
      item.proposal_source !== 'software_agent_unverified' ||
      item.review_status !== 'unreviewed' ||
      item.auto_selected !== false
    ) {
      throw new Error('Agent consultation plan contains an invalid proposed view.');
    }
    seenInstances.add(item.instance_id);
  });
  return candidate as AgentConsultationPlan;
};

const requestValidation = async (
  text: string,
  expectedItems: number,
): Promise<void> => {
  const response = await fetch(AGENT_CONSULTATION_PLAN_ENDPOINT, {
    method: 'POST',
    cache: 'no-store',
    credentials: 'same-origin',
    headers: {
      Accept: 'application/json',
      'Content-Type': AGENT_CONSULTATION_PLAN_MEDIA_TYPE,
    },
    body: text,
  });
  if (!response.ok) {
    throw new Error(
      response.status === 403
        ? 'Agent consultation plans require the authenticated local browser workspace.'
        : `The local catalog rejected the agent consultation plan (${response.status}).`,
    );
  }
  const summary = (await response.json()) as Partial<ValidationSummary>;
  if (
    summary.valid !== true ||
    summary.item_count !== expectedItems ||
    summary.review_status !== 'unreviewed' ||
    summary.agent_identity_authenticated !== false ||
    summary.exact_source_navigation_authorized !== true ||
    summary.automatic_board_capture_authorized !== false ||
    summary.clinical_conclusion_authorized !== false ||
    summary.contains_prompts !== false ||
    summary.contains_source_ids !== false ||
    summary.local_only !== true
  ) {
    throw new Error('The local catalog returned an invalid consultation-plan summary.');
  }
};

const resolveItems = (
  plan: AgentConsultationPlan,
  series: DicomSeries[],
): ResolvedAgentConsultationPlanItem[] =>
  plan.items.map((item) => {
    const selected = series.find(
      (candidate) =>
        candidate.id === item.series_id &&
        candidate.sourceKind === 'loopback-service' &&
        candidate.modality === item.modality,
    );
    if (!selected) {
      throw new Error('An agent-proposed series is unavailable in this local workspace.');
    }
    const instanceIndex = selected.instances.findIndex(
      (instance) => instance.instanceId === item.instance_id,
    );
    if (instanceIndex < 0) {
      throw new Error('An agent-proposed instance is unavailable in its selected series.');
    }
    return {
      itemId: item.item_id,
      seriesId: selected.id,
      instanceId: item.instance_id,
      instanceIndex,
      modality: item.modality,
      discussionHeading: item.discussion_heading,
      seriesDescription: selected.description,
      stackPosition: instanceIndex + 1,
      stackCount: selected.instances.length,
    };
  });

export const loadAgentConsultationPlan = async (
  text: string,
  series: DicomSeries[],
): Promise<ResolvedAgentConsultationPlan> => {
  const plan = parseAgentConsultationPlan(text);
  await requestValidation(text, plan.items.length);
  return { plan, items: resolveItems(plan, series) };
};
