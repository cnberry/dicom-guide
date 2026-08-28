import { describe, expect, it } from 'vitest';
import type { DicomSeries } from './dicom';
import {
  buildNavigationFragment,
  MAX_NAVIGATION_FRAGMENT_LENGTH,
  parseNavigationFragment,
  resolveNavigationIntent,
} from './navigationIntent';

const SERIES_A = 'series_0123456789abcdef0123';
const INSTANCE_A = 'instance_0123456789abcdef0123';
const SERIES_B = 'series_1123456789abcdef0123';
const INSTANCE_B = 'instance_1123456789abcdef0123';

const dicomSeries = (
  id: string,
  instanceIds: string[],
  sourceKind: DicomSeries['sourceKind'] = 'loopback-service',
): DicomSeries => ({
  id,
  studyId: id.replace('series_', 'study_'),
  modality: 'MR',
  description: 'Synthetic T1 post',
  imageType: ['ORIGINAL', 'PRIMARY'],
  sourceKind,
  geometry: {},
  instances: instanceIds.map((instanceId, index) => ({ instanceId, instanceNumber: index + 1 })),
});

describe('one-use local viewer navigation', () => {
  it('round-trips an exact canonical baseline/follow-up fragment', () => {
    const intent = {
      baseline: { seriesId: SERIES_A, instanceId: INSTANCE_A },
      followup: { seriesId: SERIES_B, instanceId: INSTANCE_B },
    };

    const fragment = buildNavigationFragment(intent);

    expect(fragment).toBe(
      `#scanview-v1?baseline_series=${SERIES_A}&baseline_instance=${INSTANCE_A}` +
        `&followup_series=${SERIES_B}&followup_instance=${INSTANCE_B}`,
    );
    expect(parseNavigationFragment(fragment)).toEqual({ present: true, intent });
  });

  it('ignores unrelated fragments but consumes and rejects malformed ScanView intents', () => {
    expect(parseNavigationFragment('#other')).toEqual({ present: false });
    for (const fragment of [
      `#scanview-v1?baseline_series=${SERIES_A}&baseline_instance=not-an-instance`,
      `#scanview-v1?baseline_series=${SERIES_A}&baseline_instance=${INSTANCE_A}&extra=value`,
      `#scanview-v1?baseline_series=${SERIES_A}&baseline_series=${SERIES_B}&baseline_instance=${INSTANCE_A}`,
      `#scanview-v1?baseline_series=${SERIES_A}&baseline_instance=${INSTANCE_A}&followup_series=${SERIES_B}`,
      `#scanview-v1?baseline_series=${SERIES_A}&baseline_instance=${INSTANCE_A}&followup_series=${SERIES_A}&followup_instance=${INSTANCE_A}`,
      `#scanview-v1?baseline_series=0123456789abcdef&baseline_instance=0123456789abcdef`,
      `#scanview-v1?${'x'.repeat(MAX_NAVIGATION_FRAGMENT_LENGTH)}`,
    ]) {
      const parsed = parseNavigationFragment(fragment);
      expect(parsed.present).toBe(true);
      expect(parsed.intent).toBeUndefined();
      expect(parsed.error).toBeTruthy();
    }
  });

  it('resolves exact source indexes only inside the local service catalog', () => {
    const intent = parseNavigationFragment(
      buildNavigationFragment({
        baseline: { seriesId: SERIES_A, instanceId: INSTANCE_A },
        followup: { seriesId: SERIES_B, instanceId: INSTANCE_B },
      }),
    ).intent!;
    const result = resolveNavigationIntent(intent, [
      dicomSeries(SERIES_A, ['instance_aaaaaaaaaaaaaaaaaaaa', INSTANCE_A]),
      dicomSeries(SERIES_B, [INSTANCE_B, 'instance_bbbbbbbbbbbbbbbbbbbb']),
    ]);

    expect(result).toEqual({
      navigation: {
        baseline: { seriesId: SERIES_A, instanceIndex: 1 },
        followup: { seriesId: SERIES_B, instanceIndex: 0 },
      },
    });
  });

  it('rejects a misowned instance or browser-folder lookalike without partial navigation', () => {
    const intent = {
      baseline: { seriesId: SERIES_A, instanceId: INSTANCE_A },
      followup: { seriesId: SERIES_B, instanceId: INSTANCE_B },
    };

    expect(
      resolveNavigationIntent(intent, [
        dicomSeries(SERIES_A, [INSTANCE_A]),
        dicomSeries(SERIES_B, ['instance_bbbbbbbbbbbbbbbbbbbb']),
      ]),
    ).toEqual({ error: 'Requested follow-up instance does not belong to its selected series.' });
    expect(
      resolveNavigationIntent(intent, [
        dicomSeries(SERIES_A, [INSTANCE_A], 'browser-folder'),
        dicomSeries(SERIES_B, [INSTANCE_B]),
      ]),
    ).toEqual({ error: 'Requested baseline series is not available in this local catalog.' });
  });
});
