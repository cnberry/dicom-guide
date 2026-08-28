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
  followup: DicomSeries | undefined = localSeries('2'),
) =>
  buildViewerStatePublication({
    publisherId,
    activeTool: 'length',
    synchronized: true,
    linkStrategy,
    baseline: localSeries('1'),
    baselineIndex: 1,
    followup,
    followupIndex: 0,
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
      schema_version: '1.0.0',
      sharing: true,
      publisher_id: publisherId,
      review_status: 'unreviewed',
      active_tool: 'length',
      slice_link: 'patient_position',
      baseline: {
        series_id: `series_${'1'.repeat(20)}`,
        instance_id: `instance_${'1'.repeat(19)}1`,
        stack_position: 2,
        stack_count: 2,
      },
      followup: {
        series_id: `series_${'2'.repeat(20)}`,
        instance_id: `instance_${'2'.repeat(19)}0`,
        stack_position: 1,
        stack_count: 2,
      },
      mpr_series_id: `series_${'1'.repeat(20)}`,
      measurement_count: 3,
      comparison_draft_present: true,
      privacy: {
        local_only: true,
        contains_pixels: false,
        contains_direct_identifiers: false,
        persisted: false,
      },
    });
    expect(JSON.stringify(result)).not.toMatch(/SECRET|20260828|BRAIN|imageUrl|measurement.*value/i);
  });

  it('labels unpaired, independent, physical, and approximate slice behavior explicitly', () => {
    const baseline = localSeries('1');
    const build = (synchronized: boolean, linkStrategy: LinkStrategy, followup?: DicomSeries) =>
      buildViewerStatePublication({
        publisherId,
        activeTool: 'window',
        synchronized,
        linkStrategy,
        baseline,
        baselineIndex: 0,
        followup,
        followupIndex: 0,
        measurementCount: 0,
        comparisonDraftPresent: false,
      })?.slice_link;

    expect(build(true, 'patient-position')).toBe('unpaired');
    expect(build(false, 'patient-position', localSeries('2'))).toBe('independent');
    expect(build(true, 'patient-position', localSeries('2'))).toBe('patient_position');
    expect(build(true, 'normalized', localSeries('2'))).toBe('approximate_index');
  });

  it('refuses browser-folder, malformed, out-of-stack, and excessive-count state', () => {
    const browserSeries = { ...localSeries('1'), sourceKind: 'browser-folder' as const };
    const inputs = [
      { baseline: browserSeries },
      { baseline: { ...localSeries('1'), id: 'series_bad' } },
      { baseline: localSeries('1'), baselineIndex: 2 },
      { baseline: localSeries('1'), measurementCount: 10_001 },
    ];

    for (const overrides of inputs) {
      const validInput = {
        publisherId,
        activeTool: 'window' as const,
        synchronized: true,
        linkStrategy: 'patient-position' as const,
        baseline: localSeries('1'),
        baselineIndex: 0,
        followupIndex: 0,
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
      schema_version: '1.0.0',
      sharing: false,
      publisher_id: publisherId,
    });
  });
});
