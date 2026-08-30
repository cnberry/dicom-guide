import { afterEach, describe, expect, it, vi } from 'vitest';
import type { DicomSeries } from './dicom';
import {
  AGENT_CONSULTATION_PLAN_ENDPOINT,
  AGENT_CONSULTATION_PLAN_MAX_BYTES,
  AGENT_CONSULTATION_PLAN_MEDIA_TYPE,
  loadAgentConsultationPlan,
  parseAgentConsultationPlan,
} from './agentConsultationPlan';

const SERIES_MR = 'series_00000000000000000001';
const SERIES_CT = 'series_00000000000000000002';
const INSTANCE_MR = 'instance_0000000000000000000b';
const INSTANCE_CT = 'instance_00000000000000000015';

const plan = () => ({
  schema_version: '1.0.0',
  artifact_type: 'dicom-guide.agent-consultation-plan',
  generated_at: '2026-08-29T09:01:00Z',
  catalog_content_sha256: 'a'.repeat(64),
  local_only: true,
  privacy: {
    classification: 'sensitive_local_medical_data',
    direct_identifier_tags_excluded: true,
    discussion_headings_may_contain_identifiers: true,
    deidentified: false,
    contains_pixels: false,
    contains_paths: false,
  },
  author: {
    kind: 'software_agent_unverified',
    identity_authenticated: false,
  },
  review_status: 'unreviewed',
  items: [
    {
      item_id: 'item_01',
      series_id: SERIES_MR,
      instance_id: INSTANCE_MR,
      modality: 'MR',
      discussion_heading: 'MRI overview — ask what anatomy matters',
      proposal_source: 'software_agent_unverified',
      review_status: 'unreviewed',
      auto_selected: false,
    },
    {
      item_id: 'item_02',
      series_id: SERIES_CT,
      instance_id: INSTANCE_CT,
      modality: 'CT',
      discussion_heading: 'CT overview — ask what is complementary',
      proposal_source: 'software_agent_unverified',
      review_status: 'unreviewed',
      auto_selected: false,
    },
  ],
  relationship: {
    selection_method: 'agent_proposed_exact_native_sources',
    item_count: 2,
    same_patient_context: true,
    modalities_present: ['MR', 'CT'],
    distinct_source_study_count: 2,
    distinct_source_instances: true,
    chronology_asserted: false,
    registration_asserted: false,
    lesion_identity_asserted: false,
  },
  clinical_interpretations: [],
  required_human_actions: ['confirm source', 'decide relevance'],
  permissions: {
    exact_source_navigation_authorized: true,
    automatic_board_capture_authorized: false,
    source_mutation_authorized: false,
    chronology_authorized: false,
    registration_authorized: false,
    lesion_link_authorized: false,
    response_classification_authorized: false,
    treatment_effect_conclusion_authorized: false,
    diagnosis_authorized: false,
    clinical_conclusion_authorized: false,
  },
  limitations: ['Unreviewed agent proposals only.'],
});

const dicomSeries = (
  id: string,
  modality: 'MR' | 'CT',
  instanceIds: string[],
  sourceKind: DicomSeries['sourceKind'] = 'loopback-service',
): DicomSeries => ({
  id,
  studyId: id.replace('series_', 'study_'),
  patientContextId: 'patient_aaaaaaaaaaaaaaaaaaaa',
  modality,
  description: `Synthetic ${modality}`,
  imageType: ['ORIGINAL', 'PRIMARY'],
  sourceKind,
  geometry: {},
  instances: instanceIds.map((instanceId, index) => ({
    instanceId,
    instanceNumber: index + 1,
  })),
});

const summary = {
  valid: true,
  item_count: 2,
  modalities_present: ['MR', 'CT'],
  review_status: 'unreviewed',
  agent_identity_authenticated: false,
  exact_source_navigation_authorized: true,
  automatic_board_capture_authorized: false,
  clinical_conclusion_authorized: false,
  contains_prompts: false,
  contains_source_ids: false,
  local_only: true,
};

afterEach(() => vi.unstubAllGlobals());

describe('agent consultation plans', () => {
  it('parses only the fixed unreviewed navigation-only contract', () => {
    const parsed = parseAgentConsultationPlan(JSON.stringify(plan()));

    expect(parsed.items).toHaveLength(2);
    expect(parsed.items[0].discussion_heading).toContain('MRI overview');
    expect(parsed.permissions.exact_source_navigation_authorized).toBe(true);
    expect(parsed.permissions.automatic_board_capture_authorized).toBe(false);
    expect(parsed.permissions.diagnosis_authorized).toBe(false);
    expect(parsed.clinical_interpretations).toEqual([]);
  });

  it('rejects extra fields, unsafe headings, duplicate instances, authority, and size', () => {
    const extra = { ...plan(), extra: true };
    expect(() => parseAgentConsultationPlan(JSON.stringify(extra))).toThrow('contract');

    const unsafe = plan();
    unsafe.items[0].discussion_heading = 'line\nbreak';
    expect(() => parseAgentConsultationPlan(JSON.stringify(unsafe))).toThrow(
      'invalid proposed view',
    );

    const duplicate = plan();
    duplicate.items[1].instance_id = duplicate.items[0].instance_id;
    expect(() => parseAgentConsultationPlan(JSON.stringify(duplicate))).toThrow(
      'invalid proposed view',
    );

    const authority = plan();
    authority.permissions.diagnosis_authorized = true;
    expect(() => parseAgentConsultationPlan(JSON.stringify(authority))).toThrow('contract');

    expect(() => parseAgentConsultationPlan('x'.repeat(AGENT_CONSULTATION_PLAN_MAX_BYTES + 1))).toThrow(
      '32 KiB',
    );
  });

  it('validates with the exact local server before resolving native slice positions', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(summary), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);
    const text = JSON.stringify(plan());
    const loaded = await loadAgentConsultationPlan(text, [
      dicomSeries(SERIES_MR, 'MR', ['instance_aaaaaaaaaaaaaaaaaaaa', INSTANCE_MR]),
      dicomSeries(SERIES_CT, 'CT', [INSTANCE_CT, 'instance_bbbbbbbbbbbbbbbbbbbb']),
    ]);

    expect(loaded.items.map((item) => item.instanceIndex)).toEqual([1, 0]);
    expect(loaded.items.map((item) => item.stackPosition)).toEqual([2, 1]);
    expect(AGENT_CONSULTATION_PLAN_ENDPOINT).toBe(
      '/v1/agent-consultation-plans/validate',
    );
    const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(AGENT_CONSULTATION_PLAN_ENDPOINT);
    expect(options).toMatchObject({
      method: 'POST',
      cache: 'no-store',
      credentials: 'same-origin',
      headers: {
        Accept: 'application/json',
        'Content-Type': AGENT_CONSULTATION_PLAN_MEDIA_TYPE,
      },
      body: text,
    });
  });

  it('refuses browser-folder lookalikes and server rejection without partial navigation', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(summary), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    );
    await expect(
      loadAgentConsultationPlan(JSON.stringify(plan()), [
        dicomSeries(SERIES_MR, 'MR', [INSTANCE_MR], 'browser-folder'),
        dicomSeries(SERIES_CT, 'CT', [INSTANCE_CT]),
      ]),
    ).rejects.toThrow('unavailable');

    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('{}', { status: 422 })),
    );
    await expect(
      loadAgentConsultationPlan(JSON.stringify(plan()), [
        dicomSeries(SERIES_MR, 'MR', [INSTANCE_MR]),
        dicomSeries(SERIES_CT, 'CT', [INSTANCE_CT]),
      ]),
    ).rejects.toThrow('(422)');
  });
});
