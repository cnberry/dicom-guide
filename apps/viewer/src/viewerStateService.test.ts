import { afterEach, describe, expect, it, vi } from 'vitest';
import type { DicomSeries, LinkStrategy } from './dicom';
import {
  buildViewerStatePublication,
  clearViewerState,
  createViewerStatePublisherId,
  publishViewerState,
  VIEWER_STATE_ENDPOINT,
  VIEWER_STATE_MEDIA_TYPE,
} from './viewerStateService';

afterEach(() => vi.unstubAllGlobals());

const publisherId = `publisher_${'a'.repeat(32)}`;

const localSeries = (seed: string, count = 2): DicomSeries => ({
  id: `series_${seed.repeat(20)}`,
  studyId: `study_${seed.repeat(20)}`,
  patientContextId: `patient_${seed.repeat(20)}`,
  acquisitionDate: '20260828',
  modality: 'MR',
  description: 'SECRET ANATOMY DESCRIPTION',
  protocol: 'SECRET PROTOCOL',
  bodyPart: 'BRAIN',
  imageType: ['ORIGINAL', 'PRIMARY'],
  sourceKind: 'loopback-service',
  geometry: {},
  instances: Array.from({ length: count }, (_, index) => ({
    instanceId: `instance_${seed.repeat(19)}${index}`,
    instanceNumber: index + 1,
    imageUrl: `/v1/instances/instance_${seed.repeat(19)}${index}`,
  })),
});

const publication = (
  linkStrategy: LinkStrategy = 'patient-position',
  viewB: DicomSeries | undefined = localSeries('2'),
  workspaceMode: 'consult_prep' | 'longitudinal_review' = 'longitudinal_review',
) =>
  buildViewerStatePublication({
    publisherId,
    workspaceMode,
    activeTool: 'length',
    synchronized: true,
    linkStrategy,
    viewA: localSeries('1'),
    viewAIndex: 1,
    viewB,
    viewBIndex: 0,
    mprSeries: localSeries('1'),
    measurementCount: 3,
    comparisonDraftPresent: true,
  });

describe('privacy-minimized local viewer state', () => {
  it('builds exact opaque positions without pixels, labels, dates, or measurement values', () => {
    const generatedPublisherId = createViewerStatePublisherId();
    expect(generatedPublisherId).toMatch(/^publisher_[0-9a-f]{32}$/);
    expect(createViewerStatePublisherId()).not.toBe(generatedPublisherId);

    const result = publication();

    expect(result).toEqual({
      schema_version: '2.0.0',
      sharing: true,
      publisher_id: publisherId,
      workspace_mode: 'longitudinal_review',
      view_roles: { view_a: 'baseline', view_b: 'followup' },
      review_status: 'unreviewed',
      active_tool: 'length',
      slice_link: 'patient_position',
      view_a: {
        series_id: `series_${'1'.repeat(20)}`,
        instance_id: `instance_${'1'.repeat(19)}1`,
        stack_position: 2,
        stack_count: 2,
      },
      view_b: {
        series_id: `series_${'2'.repeat(20)}`,
        instance_id: `instance_${'2'.repeat(19)}0`,
        stack_position: 1,
        stack_count: 2,
      },
      mpr_series_id: `series_${'1'.repeat(20)}`,
      source_segmentation_display: null,
      measurement_count: 3,
      comparison_draft_present: true,
      permissions: {
        agent_navigation_from_state_authorized: false,
        source_mutation_authorized: false,
        source_segmentation_mask_read_authorized: false,
        source_segmentation_interpretation_authorized: false,
        diagnosis_authorized: false,
        response_classification_authorized: false,
        clinical_conclusion_authorized: false,
      },
      privacy: {
        local_only: true,
        contains_pixels: false,
        contains_direct_identifiers: false,
        contains_source_text: false,
        contains_measurement_values: false,
        contains_segmentation_mask: false,
        contains_opaque_source_references: true,
        contains_sensitive_segmentation_reference: false,
        contains_hashes: false,
        deidentified: false,
        persisted: false,
      },
    });
    expect(JSON.stringify(result)).not.toMatch(/SECRET|20260828|BRAIN|imageUrl|"value":/i);
  });

  it('labels unpaired, independent, physical, and approximate slice behavior explicitly', () => {
    const baseline = localSeries('1');
    const build = (synchronized: boolean, linkStrategy: LinkStrategy, viewB?: DicomSeries) =>
      buildViewerStatePublication({
        publisherId,
        workspaceMode: 'longitudinal_review',
        activeTool: 'window',
        synchronized,
        linkStrategy,
        viewA: baseline,
        viewAIndex: 0,
        viewB,
        viewBIndex: 0,
        measurementCount: 0,
        comparisonDraftPresent: false,
      })?.slice_link;

    expect(build(true, 'patient-position')).toBe('unpaired');
    expect(build(false, 'patient-position', localSeries('2'))).toBe('independent');
    expect(build(true, 'patient-position', localSeries('2'))).toBe('patient_position');
    expect(build(true, 'normalized', localSeries('2'))).toBe('approximate_index');
  });

  it('publishes neutral Consult Prep roles and an exact read-only source SEG reference', () => {
    const result = buildViewerStatePublication({
      publisherId,
      workspaceMode: 'consult_prep',
      activeTool: 'window',
      synchronized: false,
      linkStrategy: 'normalized',
      viewA: localSeries('1'),
      viewAIndex: 0,
      viewB: localSeries('2'),
      viewBIndex: 1,
      mprSeries: localSeries('1'),
      sourceSegmentation: {
        segmentationId: `instance_${'f'.repeat(20)}`,
        segmentNumber: 7,
        referencedSeriesId: `series_${'1'.repeat(20)}`,
        catalogContentSha256: 'b'.repeat(64),
      },
      measurementCount: 0,
      comparisonDraftPresent: false,
    });

    expect(result?.workspace_mode).toBe('consult_prep');
    expect(result?.view_roles).toEqual({ view_a: 'reference', view_b: 'reference' });
    expect(result?.source_segmentation_display).toEqual({
      segmentation_id: `instance_${'f'.repeat(20)}`,
      segment_number: 7,
      referenced_series_id: `series_${'1'.repeat(20)}`,
      catalog_content_sha256: 'b'.repeat(64),
      display_status: 'read_only_native_grid',
      mask_pixels_shared: false,
      creator_identity_authenticated: false,
      segment_accuracy_verified: false,
      source_segment_clinical_meaning: 'not_assessed',
      scanview_interpretation_added: false,
    });
    expect(result?.permissions.source_segmentation_mask_read_authorized).toBe(false);
    expect(result?.privacy).toMatchObject({
      contains_sensitive_segmentation_reference: true,
      contains_hashes: true,
      contains_segmentation_mask: false,
      deidentified: false,
    });
    expect(JSON.stringify(result)).not.toMatch(/segment_label|computed_volume|mask_sha256|SECRET/);
  });

  it('refuses browser-folder, malformed, out-of-stack, and excessive-count state', () => {
    const browserSeries = { ...localSeries('1'), sourceKind: 'browser-folder' as const };
    const inputs = [
      { viewA: browserSeries },
      { viewA: { ...localSeries('1'), id: 'series_bad' } },
      { viewA: localSeries('1'), viewAIndex: 2 },
      { viewA: localSeries('1'), measurementCount: 10_001 },
      { workspaceMode: 'consult_prep' as const, comparisonDraftPresent: true },
      {
        mprSeries: localSeries('2'),
        sourceSegmentation: {
          segmentationId: `instance_${'f'.repeat(20)}`,
          segmentNumber: 1,
          referencedSeriesId: `series_${'1'.repeat(20)}`,
          catalogContentSha256: 'b'.repeat(64),
        },
      },
    ];

    for (const overrides of inputs) {
      const validInput = {
        publisherId,
        workspaceMode: 'longitudinal_review' as const,
        activeTool: 'window' as const,
        synchronized: true,
        linkStrategy: 'patient-position' as const,
        viewA: localSeries('1'),
        viewAIndex: 0,
        viewBIndex: 0,
        measurementCount: 0,
        comparisonDraftPresent: false,
      };
      expect(
        buildViewerStatePublication({
          ...validInput,
          ...overrides,
        }),
      ).toBeUndefined();
    }
  });

  it('publishes and clears only through the same-origin relative endpoint', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ accepted: true, sharing: true }), { status: 200 }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ accepted: true, sharing: false }), { status: 200 }),
      );
    vi.stubGlobal('fetch', fetchMock);

    await publishViewerState(publication()!);
    await clearViewerState(publisherId, true);

    expect(VIEWER_STATE_ENDPOINT).toBe('/v1/viewer-state');
    const [publishUrl, publishOptions] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(publishUrl).toBe('/v1/viewer-state');
    expect(publishOptions).toMatchObject({
      method: 'POST',
      cache: 'no-store',
      credentials: 'same-origin',
      keepalive: false,
      headers: { Accept: 'application/json', 'Content-Type': VIEWER_STATE_MEDIA_TYPE },
    });
    expect(JSON.parse(String(publishOptions.body))).toEqual(publication());
    const [clearUrl, clearOptions] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(clearUrl).toBe('/v1/viewer-state');
    expect(clearOptions.keepalive).toBe(true);
    expect(JSON.parse(String(clearOptions.body))).toEqual({
      schema_version: '2.0.0',
      sharing: false,
      publisher_id: publisherId,
    });
  });
});
