import type { DicomSeries } from './dicom';

export const NAVIGATION_FRAGMENT_PREFIX = '#dicom-guide-v1?';
export const MAX_NAVIGATION_FRAGMENT_LENGTH = 320;

const seriesIdPattern = /^series_[0-9a-f]{20}$/;
const instanceIdPattern = /^instance_[0-9a-f]{20}$/;
const allowedKeys = new Set([
  'baseline_series',
  'baseline_instance',
  'followup_series',
  'followup_instance',
]);

export type NavigationTarget = {
  seriesId: string;
  instanceId: string;
};

export type NavigationIntent = {
  baseline: NavigationTarget;
  followup?: NavigationTarget;
};

export type NavigationParseResult = {
  present: boolean;
  intent?: NavigationIntent;
  error?: string;
};

export type ResolvedNavigation = {
  baseline: { seriesId: string; instanceIndex: number };
  followup?: { seriesId: string; instanceIndex: number };
};

const oneValue = (parameters: URLSearchParams, key: string): string | undefined => {
  const values = parameters.getAll(key);
  return values.length === 1 ? values[0] : undefined;
};

export const parseNavigationFragment = (fragment: string): NavigationParseResult => {
  if (!fragment.startsWith(NAVIGATION_FRAGMENT_PREFIX)) return { present: false };
  const rejected = (error: string): NavigationParseResult => ({ present: true, error });
  if (fragment.length > MAX_NAVIGATION_FRAGMENT_LENGTH) {
    return rejected('Local navigation intent exceeds the safety limit.');
  }
  const parameters = new URLSearchParams(fragment.slice(NAVIGATION_FRAGMENT_PREFIX.length));
  const keys = [...parameters.keys()];
  if (
    keys.length < 2 ||
    keys.some((key) => !allowedKeys.has(key)) ||
    [...allowedKeys].some((key) => parameters.getAll(key).length > 1)
  ) {
    return rejected('Local navigation intent has unsupported or repeated fields.');
  }
  const baselineSeries = oneValue(parameters, 'baseline_series');
  const baselineInstance = oneValue(parameters, 'baseline_instance');
  const followupSeries = oneValue(parameters, 'followup_series');
  const followupInstance = oneValue(parameters, 'followup_instance');
  if (
    !baselineSeries ||
    !baselineInstance ||
    !seriesIdPattern.test(baselineSeries) ||
    !instanceIdPattern.test(baselineInstance)
  ) {
    return rejected('Local navigation intent requires one valid opaque baseline source.');
  }
  if (Boolean(followupSeries) !== Boolean(followupInstance)) {
    return rejected('Local navigation intent requires both follow-up source fields.');
  }
  if (
    (followupSeries && !seriesIdPattern.test(followupSeries)) ||
    (followupInstance && !instanceIdPattern.test(followupInstance))
  ) {
    return rejected('Local navigation intent has an invalid opaque follow-up source.');
  }
  if (followupSeries === baselineSeries) {
    return rejected('Local navigation intent requires distinct baseline and follow-up series.');
  }
  return {
    present: true,
    intent: {
      baseline: { seriesId: baselineSeries, instanceId: baselineInstance },
      ...(followupSeries && followupInstance
        ? { followup: { seriesId: followupSeries, instanceId: followupInstance } }
        : {}),
    },
  };
};

const resolveTarget = (
  target: NavigationTarget,
  role: 'baseline' | 'follow-up',
  series: DicomSeries[],
): { value?: { seriesId: string; instanceIndex: number }; error?: string } => {
  const selected = series.find(
    (item) => item.id === target.seriesId && item.sourceKind === 'loopback-service',
  );
  if (!selected) {
    return { error: `Requested ${role} series is not available in this local catalog.` };
  }
  const instanceIndex = selected.instances.findIndex(
    (instance) => instance.instanceId === target.instanceId,
  );
  if (instanceIndex < 0) {
    return { error: `Requested ${role} instance does not belong to its selected series.` };
  }
  return { value: { seriesId: selected.id, instanceIndex } };
};

export const resolveNavigationIntent = (
  intent: NavigationIntent,
  series: DicomSeries[],
): { navigation?: ResolvedNavigation; error?: string } => {
  const baseline = resolveTarget(intent.baseline, 'baseline', series);
  if (!baseline.value) return { error: baseline.error };
  if (!intent.followup) return { navigation: { baseline: baseline.value } };
  const followup = resolveTarget(intent.followup, 'follow-up', series);
  if (!followup.value) return { error: followup.error };
  return { navigation: { baseline: baseline.value, followup: followup.value } };
};

export const buildNavigationFragment = (intent: NavigationIntent): string => {
  const parameters = new URLSearchParams({
    baseline_series: intent.baseline.seriesId,
    baseline_instance: intent.baseline.instanceId,
  });
  if (intent.followup) {
    parameters.set('followup_series', intent.followup.seriesId);
    parameters.set('followup_instance', intent.followup.instanceId);
  }
  const fragment = `${NAVIGATION_FRAGMENT_PREFIX}${parameters.toString()}`;
  const parsed = parseNavigationFragment(fragment);
  if (!parsed.intent) throw new Error(parsed.error ?? 'Unable to build local navigation intent.');
  return fragment;
};
