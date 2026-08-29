import { describe, expect, it } from 'vitest';
import type { DicomInstance, DicomSeries } from './dicom';
import { summarizeLongitudinalReadiness } from './longitudinalReadiness';

const instances: DicomInstance[] = [
  { instanceId: 'instance-a', instanceNumber: 1 },
  { instanceId: 'instance-b', instanceNumber: 2 },
];

const series = (overrides: Partial<DicomSeries> = {}): DicomSeries => ({
  id: 'series-a',
  studyId: 'study-a',
  patientContextId: 'patient-a',
  acquisitionDate: '20260101',
  modality: 'MR',
  description: 'T1 POST',
  imageType: ['ORIGINAL', 'PRIMARY'],
  sourceKind: 'loopback-service',
  geometry: {},
  instances,
  ...overrides,
});

describe('longitudinal readiness', () => {
  it('keeps one MRI plus one CT in neutral follow-up readiness', () => {
    const report = summarizeLongitudinalReadiness([
      series(),
      series({
        id: 'series-b',
        studyId: 'study-b',
        acquisitionDate: '20260102',
        modality: 'CT',
        description: 'HEAD CT',
      }),
    ]);

    expect(report.state).toBe('no_same_modality_longitudinal_pair');
    expect(report.candidatePairCount).toBe(0);
    expect(report.missingData).toEqual([
      'future_distinct_study_same_modality_series',
    ]);
    expect(report.modalityReadiness.map((item) => item.state)).toEqual([
      'needs_distinct_study',
      'needs_distinct_study',
    ]);
    expect(report.candidateSelectionAuthorized).toBe(false);
    expect(report.responseClassificationAuthorized).toBe(false);
  });

  it('reports a same-patient, dated, cross-study MR candidate without approval', () => {
    const report = summarizeLongitudinalReadiness([
      series(),
      series({ id: 'series-b', studyId: 'study-b', acquisitionDate: '20260201' }),
    ]);

    expect(report.state).toBe('candidate_pairs_require_human_review');
    expect(report.candidatePairCount).toBe(1);
    expect(report.missingData).toEqual([]);
    expect(report.modalityReadiness[0].state).toBe(
      'candidate_pairs_require_human_review',
    );
    expect(report.candidateSelectionAuthorized).toBe(false);
  });

  it('distinguishes missing dates, patient context, and eligible stacks', () => {
    const missingDate = summarizeLongitudinalReadiness([
      series({ acquisitionDate: undefined }),
      series({ id: 'series-b', studyId: 'study-b', acquisitionDate: '20260201' }),
    ]);
    expect(missingDate.modalityReadiness[0].state).toBe('needs_complete_dates');
    expect(missingDate.missingData).toEqual(['complete_acquisition_dates']);

    const differentPatients = summarizeLongitudinalReadiness([
      series(),
      series({
        id: 'series-b',
        studyId: 'study-b',
        acquisitionDate: '20260201',
        patientContextId: 'patient-b',
      }),
    ]);
    expect(differentPatients.modalityReadiness[0].state).toBe(
      'needs_same_patient_context',
    );
    expect(differentPatients.missingData).toEqual([
      'same_patient_context_across_exams',
    ]);

    const localizers = summarizeLongitudinalReadiness([
      series({ description: 'LOCALIZER' }),
      series({
        id: 'series-b',
        studyId: 'study-b',
        acquisitionDate: '20260201',
        imageType: ['SCOUT'],
      }),
    ]);
    expect(localizers.eligibleSeriesCount).toBe(0);
    expect(localizers.modalityReadiness[0].state).toBe('no_eligible_series');
    expect(localizers.missingData).toEqual(['eligible_mr_or_ct_stack']);
  });
});
