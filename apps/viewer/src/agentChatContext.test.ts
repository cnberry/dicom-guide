import { describe, expect, it } from 'vitest';
import { buildAgentChatContext } from './agentChatContext';
import type { DicomSeries } from './dicom';

const series = (): DicomSeries =>
  ({
    id: 'series_0123456789abcdefabcd',
    studyId: 'study_0123456789abcdefabcd',
    patientContextId: 'patient_context_0123456789abcdefabcd',
    modality: 'MR',
    description: 'Structural volume',
    acquisitionDate: '20260829',
    frameOfReferenceId: 'frame_0123456789abcdefabcd',
    sourceKind: 'loopback-service',
    geometry: { orientation: [1, 0, 0, 0, 1, 0] },
    instances: [
      { instanceId: 'instance_0123456789abcdefabcd', imagePosition: [0, 0, 0] },
      { instanceId: 'instance_abcdef0123456789abcd', imagePosition: [0, 0, 5] },
    ],
  }) as DicomSeries;

describe('agent chat image context', () => {
  it('binds a native pointer to the exact selected source image', () => {
    const context = buildAgentChatContext({
      series: series(),
      index: 1,
      viewMode: 'native',
      patientPoint: [12.5, -4, 98.25],
    });
    expect(context).toMatchObject({
      schema_version: '1.0.0',
      view_mode: 'native',
      instance_id: 'instance_abcdef0123456789abcd',
      stack_position: 2,
      stack_count: 2,
      patient_point_lps_mm: [12.5, -4, 98.25],
      pointer_source: 'cursor',
      privacy: {
        local_only: true,
        contains_pixels: false,
        contains_source_text: false,
        persisted: false,
      },
    });
  });

  it('marks MPR coordinates as crosshair context and rejects an invalid slice', () => {
    expect(
      buildAgentChatContext({
        series: series(),
        index: 0,
        viewMode: 'mpr',
        patientPoint: [1, 2, 3],
      }),
    ).toMatchObject({
      instance_id: 'instance_abcdef0123456789abcd',
      stack_position: 2,
      pointer_source: 'mpr_crosshair',
    });
    expect(buildAgentChatContext({ series: series(), index: 2, viewMode: 'native' })).toBeUndefined();
  });
});
