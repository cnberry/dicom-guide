import { isLongitudinalSourcePair, type DicomSeries } from './dicom';

export type ModalityReadinessState =
  | 'not_present'
  | 'no_eligible_series'
  | 'needs_distinct_study'
  | 'needs_complete_dates'
  | 'needs_same_patient_context'
  | 'needs_distinct_dates'
  | 'candidate_pairs_require_human_review';

export type ReadinessMissingData =
  | 'dicom_studies'
  | 'eligible_mr_or_ct_stack'
  | 'future_distinct_study_same_modality_series'
  | 'complete_acquisition_dates'
  | 'same_patient_context_across_exams'
  | 'distinct_exam_dates';

export type ModalityReadiness = {
  modality: 'MR' | 'CT';
  state: ModalityReadinessState;
  studyCount: number;
  eligibleStudyCount: number;
  seriesCount: number;
  eligibleSeriesCount: number;
  datedStudyCount: number;
  patientContextCount: number;
  candidatePairCount: number;
};

export type LongitudinalReadinessSummary = {
  state:
    | 'no_dicom_studies'
    | 'no_same_modality_longitudinal_pair'
    | 'candidate_pairs_require_human_review';
  studyCount: number;
  eligibleSeriesCount: number;
  patientContextCount: number;
  candidatePairCount: number;
  modalityReadiness: [ModalityReadiness, ModalityReadiness];
  missingData: ReadinessMissingData[];
  candidateSelectionAuthorized: false;
  responseClassificationAuthorized: false;
};

const validDicomDate = (value?: string): value is string => {
  if (!value || !/^\d{8}$/.test(value)) return false;
  const year = Number(value.slice(0, 4));
  const month = Number(value.slice(4, 6));
  const day = Number(value.slice(6, 8));
  const date = new Date(Date.UTC(year, month - 1, day));
  return (
    date.getUTCFullYear() === year &&
    date.getUTCMonth() === month - 1 &&
    date.getUTCDate() === day
  );
};

const eligibleSeries = (series: DicomSeries): boolean => {
  if (!['MR', 'CT'].includes(series.modality) || series.instances.length < 2) return false;
  const terms = new Set(
    series.description
      .toLowerCase()
      .split(/[^a-z0-9]+/)
      .filter(Boolean),
  );
  const imageTerms = new Set(series.imageType.map((value) => value.toUpperCase()));
  return !(
    imageTerms.has('LOCALIZER') ||
    imageTerms.has('SCOUT') ||
    terms.has('localizer') ||
    terms.has('scout') ||
    terms.has('survey')
  );
};

const candidatePairs = (series: DicomSeries[]): [DicomSeries, DicomSeries][] => {
  const pairs: [DicomSeries, DicomSeries][] = [];
  series.forEach((left, index) => {
    series.slice(index + 1).forEach((right) => {
      if (isLongitudinalSourcePair(left, right)) pairs.push([left, right]);
    });
  });
  return pairs;
};

const modalitySummary = (
  modality: 'MR' | 'CT',
  allSeries: DicomSeries[],
): ModalityReadiness => {
  const records = allSeries.filter((series) => series.modality === modality);
  const eligible = records.filter(eligibleSeries);
  const pairs = candidatePairs(eligible);
  const studyCount = new Set(records.map((series) => series.studyId)).size;
  const eligibleStudyCount = new Set(eligible.map((series) => series.studyId)).size;
  const datedStudyCount = new Set(
    eligible.filter((series) => validDicomDate(series.acquisitionDate)).map(
      (series) => series.studyId,
    ),
  ).size;
  const patientContextCount = new Set(
    eligible.flatMap((series) =>
      series.patientContextId ? [series.patientContextId] : [],
    ),
  ).size;
  let state: ModalityReadinessState;
  if (records.length === 0) {
    state = 'not_present';
  } else if (eligible.length === 0) {
    state = 'no_eligible_series';
  } else if (pairs.length > 0) {
    state = 'candidate_pairs_require_human_review';
  } else if (eligibleStudyCount < 2) {
    state = 'needs_distinct_study';
  } else if (datedStudyCount < 2) {
    state = 'needs_complete_dates';
  } else {
    const contexts = new Map<string, DicomSeries[]>();
    eligible.forEach((series) => {
      if (!series.patientContextId || !validDicomDate(series.acquisitionDate)) return;
      const values = contexts.get(series.patientContextId) ?? [];
      values.push(series);
      contexts.set(series.patientContextId, values);
    });
    const sameContextGroups = [...contexts.values()].filter(
      (values) => new Set(values.map((series) => series.studyId)).size >= 2,
    );
    state = sameContextGroups.length === 0
      ? 'needs_same_patient_context'
      : sameContextGroups.some(
          (values) => new Set(values.map((series) => series.acquisitionDate)).size >= 2,
        )
        ? 'candidate_pairs_require_human_review'
        : 'needs_distinct_dates';
  }
  return {
    modality,
    state,
    studyCount,
    eligibleStudyCount,
    seriesCount: records.length,
    eligibleSeriesCount: eligible.length,
    datedStudyCount,
    patientContextCount,
    candidatePairCount: pairs.length,
  };
};

const missingData = (
  studyCount: number,
  eligibleCount: number,
  candidateCount: number,
  modalities: ModalityReadiness[],
): ReadinessMissingData[] => {
  if (studyCount === 0) return ['dicom_studies'];
  if (eligibleCount === 0) return ['eligible_mr_or_ct_stack'];
  if (candidateCount > 0) return [];
  const stateRequirements: Partial<
    Record<ModalityReadinessState, ReadinessMissingData>
  > = {
    needs_distinct_study: 'future_distinct_study_same_modality_series',
    needs_complete_dates: 'complete_acquisition_dates',
    needs_same_patient_context: 'same_patient_context_across_exams',
    needs_distinct_dates: 'distinct_exam_dates',
  };
  const requirements = new Set(
    modalities.flatMap((item) => {
      const requirement = stateRequirements[item.state];
      return requirement ? [requirement] : [];
    }),
  );
  return [
    'future_distinct_study_same_modality_series',
    'complete_acquisition_dates',
    'same_patient_context_across_exams',
    'distinct_exam_dates',
  ].filter((value): value is ReadinessMissingData =>
    requirements.has(value as ReadinessMissingData),
  );
};

export const summarizeLongitudinalReadiness = (
  series: DicomSeries[],
): LongitudinalReadinessSummary => {
  const modalityReadiness: [ModalityReadiness, ModalityReadiness] = [
    modalitySummary('MR', series),
    modalitySummary('CT', series),
  ];
  const candidates = candidatePairs(series.filter(eligibleSeries));
  const studyCount = new Set(series.map((item) => item.studyId)).size;
  const eligibleCount = series.filter(eligibleSeries).length;
  const patientContextCount = new Set(
    series.flatMap((item) => (item.patientContextId ? [item.patientContextId] : [])),
  ).size;
  return {
    state: studyCount === 0
      ? 'no_dicom_studies'
      : candidates.length > 0
        ? 'candidate_pairs_require_human_review'
        : 'no_same_modality_longitudinal_pair',
    studyCount,
    eligibleSeriesCount: eligibleCount,
    patientContextCount,
    candidatePairCount: candidates.length,
    modalityReadiness,
    missingData: missingData(
      studyCount,
      eligibleCount,
      candidates.length,
      modalityReadiness,
    ),
    candidateSelectionAuthorized: false,
    responseClassificationAuthorized: false,
  };
};

export const readinessRequirementText = (value: ReadinessMissingData): string => {
  const labels: Record<ReadinessMissingData, string> = {
    dicom_studies: 'Load at least one DICOM study.',
    eligible_mr_or_ct_stack: 'No eligible multi-image MR or CT stack is available.',
    future_distinct_study_same_modality_series:
      'A future same-patient MR or CT exam is needed before longitudinal pairing can begin.',
    complete_acquisition_dates:
      'At least two exams need complete, valid DICOM acquisition dates.',
    same_patient_context_across_exams:
      'Cross-exam patient context cannot be proven locally; confirm identity in the clinical imaging system.',
    distinct_exam_dates: 'The candidate exams need distinct acquisition dates.',
  };
  return labels[value];
};
