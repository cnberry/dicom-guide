import { afterEach, describe, expect, it, vi } from 'vitest';
import type { DicomSeries } from './dicom';
import {
  VIEWER_CONTROL_ENDPOINT,
  VIEWER_CONTROL_MEDIA_TYPE,
  VIEWER_CONTROL_OBSERVATION_ENDPOINT,
  buildViewerControlObservation,
  fetchViewerControl,
  publishViewerControlObservation,
} from './viewerControlService';

afterEach(() => vi.unstubAllGlobals());

const viewerId = 'viewer_0123456789abcdef0123';

const series = (): DicomSeries => ({
  id: 'series_0123456789abcdef0123',
  studyId: 'study_0123456789abcdef0123',
  modality: 'MR',
  description: 'Local display label',
  imageType: [],
  sourceKind: 'loopback-service',
  geometry: { orientation: [1, 0, 0, 0, 1, 0] },
  instances: [
    { instanceId: 'instance_0123456789abcdef0123', instanceNumber: 1, imagePosition: [0, 0, 0] },
    { instanceId: 'instance_abcdef0123456789abcd', instanceNumber: 2, imagePosition: [0, 0, 5] },
  ],
});

describe('Codex viewer control bridge', () => {
  it('builds a privacy-declared exact MPR observation', () => {
    const observation = buildViewerControlObservation({
      viewerId,
      series: series(),
      index: 0,
      viewMode: 'mpr',
      nativeTool: 'window',
      mprTool: 'crosshairs',
      patientPoint: [1, 2, 3],
      renderStatus: 'ready',
      appliedCommand: {
        commandId: 'control_0123456789abcdef0123456789abcdef',
        revision: 7,
      },
    });
    expect(observation).toMatchObject({
      interaction_source: 'agent',
      view_mode: 'mpr',
      instance_id: 'instance_abcdef0123456789abcd',
      stack_position: 2,
      tool: 'crosshairs',
      patient_point_lps_mm: [1, 2, 3],
      point_pinned: true,
      privacy: { local_only: true, contains_pixels: false, contains_source_text: false },
      permissions: { agent_view_navigation_authorized: true, diagnosis_authorized: false },
    });
    expect(JSON.stringify(observation)).not.toContain('Local display label');
  });

  it('reads commands and publishes observations through fixed same-origin routes', async () => {
    const command = {
      schema_version: '1.0.0',
      command_id: 'control_0123456789abcdef0123456789abcdef',
      view_mode: 'native',
      series_id: 'series_0123456789abcdef0123',
      instance_id: 'instance_0123456789abcdef0123',
      tool: 'window',
      patient_point_lps_mm: null,
      reset_view: false,
      target_viewer_id: viewerId,
      revision: 3,
      issued_at: '2026-08-29T12:00:00Z',
    } as const;
    const observation = buildViewerControlObservation({
      viewerId,
      series: series(),
      index: 0,
      viewMode: 'native',
      nativeTool: 'window',
      mprTool: 'crosshairs',
      renderStatus: 'ready',
    })!;
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ schema_version: '1.0.0', viewer_connected: true, command })),
      )
      .mockResolvedValueOnce(new Response(JSON.stringify({ accepted: true })));
    vi.stubGlobal('fetch', fetchMock);

    await expect(fetchViewerControl(2, viewerId)).resolves.toMatchObject({ command });
    await publishViewerControlObservation(observation);

    expect(fetchMock.mock.calls[0]).toEqual([
      `${VIEWER_CONTROL_ENDPOINT}?after_revision=2&wait_seconds=10&viewer_id=${viewerId}`,
      expect.objectContaining({ cache: 'no-store', credentials: 'same-origin' }),
    ]);
    expect(fetchMock.mock.calls[1][0]).toBe(VIEWER_CONTROL_OBSERVATION_ENDPOINT);
    expect(fetchMock.mock.calls[1][1]).toMatchObject({
      method: 'POST',
      credentials: 'same-origin',
      headers: { Accept: 'application/json', 'Content-Type': VIEWER_CONTROL_MEDIA_TYPE },
    });
  });

  it('surfaces the local validation reason for a rejected observation', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: 'invalid_viewer_observation',
            detail: 'viewer observation did not apply the requested patient point',
          }),
          { status: 422 },
        ),
      ),
    );
    const value = buildViewerControlObservation({
      viewerId,
      series: series(),
      index: 0,
      viewMode: 'mpr',
      nativeTool: 'window',
      mprTool: 'crosshairs',
      patientPoint: [1, 2, 3],
      renderStatus: 'ready',
    })!;

    await expect(publishViewerControlObservation(value)).rejects.toThrow(
      'Viewer observation was rejected (422). viewer observation did not apply the requested patient point',
    );
  });

  it('publishes patient-space discussion marks for agent-readable highlighting', () => {
    expect(
      buildViewerControlObservation({
        viewerId,
        series: series(),
        index: 0,
        viewMode: 'mpr',
        nativeTool: 'window',
        mprTool: 'highlight',
        renderStatus: 'ready',
        discussionMarks: [
          {
            id: 'mark_0123456789abcdef0123',
            orientation: 'axial',
            color: 'yellow',
            author: 'person',
            points_lps_mm: [[1, 2, 3]],
          },
        ],
      }),
    ).toMatchObject({
      tool: 'highlight',
      discussion_marks: [
        {
          orientation: 'axial',
          color: 'yellow',
          points_lps_mm: [[1, 2, 3]],
        },
      ],
    });
  });

  it('publishes discussion marks from a native single view', () => {
    expect(
      buildViewerControlObservation({
        viewerId,
        series: series(),
        index: 0,
        viewMode: 'native',
        nativeTool: 'highlight',
        mprTool: 'crosshairs',
        renderStatus: 'ready',
        discussionMarks: [
          {
            id: 'mark_abcdef0123456789abcd',
            orientation: 'axial',
            color: 'green',
            author: 'person',
            points_lps_mm: [[1, 2, 0]],
          },
        ],
      }),
    ).toMatchObject({
      view_mode: 'native',
      tool: 'highlight',
      discussion_marks: [{ color: 'green', author: 'person' }],
    });
  });

  it('rejects malformed commands before applying them', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            schema_version: '1.0.0',
            viewer_connected: true,
            command: { command_id: 'bad' },
          }),
        ),
      ),
    );
    await expect(fetchViewerControl()).rejects.toThrow('invalid command');
  });
});
