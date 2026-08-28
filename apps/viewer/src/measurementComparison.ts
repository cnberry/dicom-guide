import type { Compatibility, DicomSeries } from './dicom';
import type { MeasurementEvidence, MeasurementType } from './measurements';

export type ComparisonMetric =
  | 'length'
  | 'long_axis'
  | 'short_axis'
  | 'bidimensional_product'
  | 'major_axis'
  | 'minor_axis'
  | 'elliptical_area';

export type MeasurementComparisonResult = {
  metric: ComparisonMetric;
  baseline: number;
  followup: number;
  absolute_change: number;
  percent_change?: number;
  unit: 'mm' | 'mm2';
  source_measurement_ids: [string, string];
  review_status: 'unreviewed';
};

export type MeasurementComparisonDraft = {
  schema_version: '1.0.0';
  created_at: string;
  review_status: 'unreviewed';
  pairing: {
    method: 'explicit_tracking_id_selection';
    lesion_label: string;
    baseline_measurement_id: string;
    followup_measurement_id: string;
  };
  observations: Array<{
    timepoint: 'baseline' | 'followup';
    measurement_type: MeasurementType;
    source: MeasurementEvidence['source'];
    review_status: 'unreviewed';
  }>;
  computed_results: MeasurementComparisonResult[];
  candidate_interpretations: [];
  limitations: string[];
  missing_context: string[];
  questions_for_clinician: string[];
};

export type ComparisonSourceIndexes = {
  baseline: number;
  followup: number;
};

type MetricDefinition = {
  metric: ComparisonMetric;
  key:
    | 'value'
    | 'long_axis'
    | 'short_axis'
    | 'product'
    | 'major_axis'
    | 'minor_axis'
    | 'area';
  unit: 'mm' | 'mm2';
};

const metricDefinitions = (type: MeasurementType): MetricDefinition[] =>
  type === 'length'
    ? [{ metric: 'length', key: 'value', unit: 'mm' }]
    : type === 'bidirectional'
      ? [
          { metric: 'long_axis', key: 'long_axis', unit: 'mm' },
          { metric: 'short_axis', key: 'short_axis', unit: 'mm' },
          { metric: 'bidimensional_product', key: 'product', unit: 'mm2' },
        ]
      : [
          { metric: 'major_axis', key: 'major_axis', unit: 'mm' },
          { metric: 'minor_axis', key: 'minor_axis', unit: 'mm' },
          { metric: 'elliptical_area', key: 'area', unit: 'mm2' },
        ];

const normalizeLesionLabel = (value: string): string => {
  if (/\p{Cc}/u.test(value)) throw new Error('Lesion labels cannot contain control characters.');
  const normalized = value.trim().replace(/\s+/g, ' ');
  if (!normalized) throw new Error('Enter a working lesion label before pairing.');
  if (normalized.length > 80) throw new Error('Lesion labels are limited to 80 characters.');
  return normalized;
};

const resultValue = (measurement: MeasurementEvidence, key: MetricDefinition['key']): number => {
  const value = (measurement.result as unknown as Record<string, unknown>)[key];
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 0) {
    throw new Error('Both measurements need trusted physical values.');
  }
  return value;
};

export const assessMeasurementPairingContext = (
  baseline: DicomSeries | undefined,
  followup: DicomSeries | undefined,
  compatibilityLevel: Compatibility['level'],
): { ready: boolean; reason: string } => {
  if (!baseline || !followup) {
    return { ready: false, reason: 'Choose a baseline and follow-up series first.' };
  }
  if (compatibilityLevel === 'incompatible') {
    return { ready: false, reason: 'The selected series fail longitudinal safety gates.' };
  }
  if (!baseline.acquisitionDate || !followup.acquisitionDate) {
    return { ready: false, reason: 'Both series need explicit acquisition dates.' };
  }
  if (baseline.acquisitionDate >= followup.acquisitionDate) {
    return {
      ready: false,
      reason: 'Baseline must have an earlier acquisition date than follow-up.',
    };
  }
  return { ready: true, reason: 'Context supports explicit unreviewed measurement pairing.' };
};

export const findComparisonSourceIndexes = (
  draft: MeasurementComparisonDraft | undefined,
  baseline: DicomSeries | undefined,
  followup: DicomSeries | undefined,
): ComparisonSourceIndexes | undefined => {
  if (!draft || !baseline || !followup) return undefined;
  const baselineObservation = draft.observations.find(
    (observation) => observation.timepoint === 'baseline',
  );
  const followupObservation = draft.observations.find(
    (observation) => observation.timepoint === 'followup',
  );
  return {
    baseline:
      baselineObservation?.source.series_id === baseline.id
        ? baseline.instances.findIndex(
            (instance) => instance.instanceId === baselineObservation.source.instance_id,
          )
        : -1,
    followup:
      followupObservation?.source.series_id === followup.id
        ? followup.instances.findIndex(
            (instance) => instance.instanceId === followupObservation.source.instance_id,
          )
        : -1,
  };
};

export const comparisonSourcesAreVisible = (
  indexes: ComparisonSourceIndexes | undefined,
  baselineIndex: number,
  followupIndex: number,
): boolean =>
  Boolean(
    indexes &&
      indexes.baseline >= 0 &&
      indexes.followup >= 0 &&
      indexes.baseline === baselineIndex &&
      indexes.followup === followupIndex,
  );

export const buildMeasurementComparisonDraft = (
  baseline: MeasurementEvidence,
  followup: MeasurementEvidence,
  lesionLabel: string,
  createdAt = new Date().toISOString(),
): MeasurementComparisonDraft => {
  if (baseline.type !== followup.type) {
    throw new Error('Baseline and follow-up measurement types must match.');
  }
  if (baseline.source.series_id === followup.source.series_id) {
    throw new Error('Baseline and follow-up measurements must use distinct source series.');
  }
  if (baseline.result.unit !== 'mm' || followup.result.unit !== 'mm') {
    throw new Error('Both measurements need trusted physical millimeter units.');
  }
  if (!Number.isFinite(Date.parse(createdAt))) throw new Error('Comparison time is invalid.');

  const label = normalizeLesionLabel(lesionLabel);
  const limitations = [
    'The measurements were paired only because a person explicitly selected both tracking IDs and entered a working lesion label.',
    'The label does not prove same-lesion identity, compatible acquisition, or the intended tumor component.',
    'Numeric change alone is not a treatment-response category.',
  ];
  const computedResults = metricDefinitions(baseline.type).map<MeasurementComparisonResult>(
    ({ metric, key, unit }) => {
      const baselineValue = resultValue(baseline, key);
      const followupValue = resultValue(followup, key);
      const result: MeasurementComparisonResult = {
        metric,
        baseline: baselineValue,
        followup: followupValue,
        absolute_change: followupValue - baselineValue,
        unit,
        source_measurement_ids: [baseline.tracking_id, followup.tracking_id],
        review_status: 'unreviewed',
      };
      if (baselineValue === 0) {
        limitations.push(`Percent change for ${metric} is undefined because baseline is zero.`);
      } else {
        result.percent_change = ((followupValue - baselineValue) / baselineValue) * 100;
      }
      return result;
    },
  );

  return {
    schema_version: '1.0.0',
    created_at: createdAt,
    review_status: 'unreviewed',
    pairing: {
      method: 'explicit_tracking_id_selection',
      lesion_label: label,
      baseline_measurement_id: baseline.tracking_id,
      followup_measurement_id: followup.tracking_id,
    },
    observations: [
      {
        timepoint: 'baseline',
        measurement_type: baseline.type,
        source: baseline.source,
        review_status: 'unreviewed',
      },
      {
        timepoint: 'followup',
        measurement_type: followup.type,
        source: followup.source,
        review_status: 'unreviewed',
      },
    ],
    computed_results: computedResults,
    candidate_interpretations: [],
    limitations,
    missing_context: [
      'clinician-confirmed same-lesion identity',
      'compatible acquisition and contrast protocol',
      'diagnosis-specific response criteria',
      'clinical status, steroid context, and treatment timing',
    ],
    questions_for_clinician: [
      `Does “${label}” identify the same lesion and tumor component at both timepoints?`,
      'Are these source series suitable for longitudinal response measurement?',
      'Which response criteria and baseline or nadir convention should apply?',
    ],
  };
};

export const downloadMeasurementComparisonDraft = (draft: MeasurementComparisonDraft): void => {
  const url = URL.createObjectURL(
    new Blob([`${JSON.stringify(draft, null, 2)}\n`], { type: 'application/json' }),
  );
  const link = document.createElement('a');
  link.href = url;
  link.download = `scanview-comparison-${new Date().toISOString().slice(0, 10)}.json`;
  link.click();
  URL.revokeObjectURL(url);
};
