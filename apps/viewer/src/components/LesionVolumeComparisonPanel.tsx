import { useEffect, useMemo, useRef, useState } from 'react';
import { formatDicomDate, type DicomSeries } from '../dicom';
import {
  LESION_VOLUME_COMPARISON_ATTESTATION,
  buildPairingRequest,
  readBoundaryReviewArchive,
  saveLesionVolumeComparison,
  type ImportedBoundaryReview,
  type LesionVolumeComparisonChecklist,
  type LesionVolumeComparisonRequest,
} from '../lesionVolumeComparisonService';
import {
  LESION_VOLUME_REVIEW_ROLES,
  type LesionVolumeReviewerRole,
} from '../lesionVolumeReview';

type Props = {
  series: DicomSeries[];
  selectedBaselineSeriesId?: string;
  selectedFollowupSeriesId?: string;
};
type Role = 'baseline' | 'followup';
type ExportState = 'idle' | 'working' | 'saved' | 'error';

const checklistLabels: Array<[keyof LesionVolumeComparisonChecklist, string]> = [
  ['both_original_sources_reviewed', 'Both original source series reviewed'],
  ['both_complete_boundaries_reviewed', 'Both complete boundaries reviewed in all three planes'],
  ['boundary_definitions_compared', 'Inclusion/exclusion definitions compared'],
  ['same_lesion_identity_reviewed', 'Same-lesion identity explicitly reviewed'],
  ['same_represented_tissue_reviewed', 'Same represented tissue explicitly reviewed'],
  ['acquisition_differences_reviewed', 'Acquisition and image-quality differences reviewed'],
  ['chronology_confirmed', 'Baseline-before-follow-up chronology confirmed'],
  ['registration_need_reviewed', 'Need for spatial registration separately considered'],
];

const emptyChecklist = (): LesionVolumeComparisonChecklist => ({
  both_original_sources_reviewed: false,
  both_complete_boundaries_reviewed: false,
  boundary_definitions_compared: false,
  same_lesion_identity_reviewed: false,
  same_represented_tissue_reviewed: false,
  acquisition_differences_reviewed: false,
  chronology_confirmed: false,
  registration_need_reviewed: false,
});

const reviewCard = (
  role: Role,
  review: ImportedBoundaryReview | undefined,
  matchedSeries: DicomSeries | undefined,
) => (
  <article className="volume-pair-source-card">
    <span className="eyebrow">{role === 'baseline' ? 'Baseline' : 'Follow-up'} accepted boundary</span>
    {review ? (
      <>
        <strong>{review.filename}</strong>
        <span>{review.modality} · {review.reviewedVolumeMl.toFixed(6)} mL</span>
        <span>{review.representedTissue}</span>
        <span>
          {matchedSeries
            ? `${formatDicomDate(matchedSeries.acquisitionDate)} · exact local series found`
            : 'No exact series match in the current local catalog'}
        </span>
      </>
    ) : <span>No boundary-review ZIP selected.</span>}
  </article>
);

export function LesionVolumeComparisonPanel({
  series,
  selectedBaselineSeriesId,
  selectedFollowupSeriesId,
}: Props) {
  const baselineInput = useRef<HTMLInputElement>(null);
  const followupInput = useRef<HTMLInputElement>(null);
  const [baseline, setBaseline] = useState<ImportedBoundaryReview>();
  const [followup, setFollowup] = useState<ImportedBoundaryReview>();
  const [reviewerName, setReviewerName] = useState('');
  const [reviewerRole, setReviewerRole] = useState<LesionVolumeReviewerRole | ''>('');
  const [reviewerOrganization, setReviewerOrganization] = useState('');
  const [decision, setDecision] = useState<LesionVolumeComparisonRequest['decision']>('revision_requested');
  const [sameLesion, setSameLesion] = useState<'confirmed' | 'uncertain' | 'not_confirmed'>('uncertain');
  const [sameTissue, setSameTissue] = useState<'confirmed' | 'uncertain' | 'not_confirmed'>('uncertain');
  const [chronology, setChronology] = useState<'confirmed' | 'not_confirmed'>('not_confirmed');
  const [acquisitionComparability, setAcquisitionComparability] =
    useState<'suitable' | 'suitable_with_limitations' | 'not_suitable'>('not_suitable');
  const [boundaryComparability, setBoundaryComparability] =
    useState<'suitable' | 'suitable_with_limitations' | 'not_suitable'>('not_suitable');
  const [registrationConsideration, setRegistrationConsideration] =
    useState<'required' | 'not_required' | 'uncertain'>('uncertain');
  const [limitationNote, setLimitationNote] = useState('');
  const [treatmentContextNote, setTreatmentContextNote] = useState('');
  const [checklist, setChecklist] = useState(emptyChecklist);
  const [attested, setAttested] = useState(false);
  const [state, setState] = useState<ExportState>('idle');
  const [message, setMessage] = useState(
    'Import two separately accepted boundary-review ZIPs. The local server will recursively revalidate both against the current DICOM folder.',
  );
  const sourceKey = series.map((item) => item.id).sort().join('|');

  useEffect(() => {
    setBaseline(undefined);
    setFollowup(undefined);
    setState('idle');
    setMessage(
      'The review pair was cleared because the active local DICOM catalog changed.',
    );
  }, [sourceKey]);

  const baselineSeries = series.find((item) => item.id === baseline?.seriesId);
  const followupSeries = series.find((item) => item.id === followup?.seriesId);
  const localService = series.length > 0 && series.every((item) => item.sourceKind === 'loopback-service');
  const pairErrors = useMemo(() => {
    const errors: string[] = [];
    if (!localService) errors.push('Use the unified local launcher; folder-picker mode cannot assemble this source-recursive artifact.');
    if (!baseline || !followup) return errors;
    if (!baselineSeries || !followupSeries) errors.push('Both review series must exist in the current local catalog.');
    if (
      baseline &&
      followup &&
      (selectedBaselineSeriesId !== baseline.seriesId ||
        selectedFollowupSeriesId !== followup.seriesId)
    ) {
      errors.push('Display the exact baseline and follow-up review series in the two source panes before pairing.');
    }
    if (baseline.reviewId === followup.reviewId) errors.push('Choose two distinct boundary reviews.');
    if (baseline.patientContextId !== followup.patientContextId) errors.push('The reviews do not share one patient context.');
    if (baseline.modality !== followup.modality) errors.push('The reviews must use the same modality.');
    if (baseline.studyId === followup.studyId) errors.push('The reviews must come from distinct studies.');
    if (baseline.seriesId === followup.seriesId) errors.push('The reviews must come from distinct series.');
    if (
      baselineSeries &&
      followupSeries &&
      (!baselineSeries.acquisitionDate ||
        !followupSeries.acquisitionDate ||
        baselineSeries.acquisitionDate >= followupSeries.acquisitionDate)
    ) {
      errors.push('Exact DICOM dates must establish baseline before follow-up.');
    }
    return errors;
  }, [
    baseline,
    baselineSeries,
    followup,
    followupSeries,
    localService,
    selectedBaselineSeriesId,
    selectedFollowupSeriesId,
  ]);
  const accepted = decision === 'accepted_for_volume_change_discussion';
  const limitationsNeedNote =
    acquisitionComparability === 'suitable_with_limitations' ||
    boundaryComparability === 'suitable_with_limitations' ||
    registrationConsideration !== 'not_required';
  const acceptedGatesComplete =
    !accepted ||
    (sameLesion === 'confirmed' &&
      sameTissue === 'confirmed' &&
      chronology === 'confirmed' &&
      acquisitionComparability !== 'not_suitable' &&
      boundaryComparability !== 'not_suitable' &&
      Object.values(checklist).every((value) => value === true));
  const ready = Boolean(
    baseline &&
      followup &&
      reviewerName.trim() &&
      reviewerRole &&
      attested &&
      pairErrors.length === 0 &&
      acceptedGatesComplete &&
      (!limitationsNeedNote || limitationNote.trim()) &&
      state !== 'working',
  );

  const importReview = async (role: Role, file: File | undefined) => {
    if (!file) return;
    try {
      const review = readBoundaryReviewArchive(new Uint8Array(await file.arrayBuffer()), file.name);
      if (role === 'baseline') setBaseline(review);
      else setFollowup(review);
      setState('idle');
      setMessage(
        `Loaded ${role} review for local preview. Server-side nested evidence and source validation remains required.`,
      );
    } catch (error) {
      setState('error');
      setMessage(error instanceof Error ? error.message : 'Unable to read the local boundary review.');
    }
  };

  const exportComparison = async () => {
    if (!baseline || !followup || !reviewerRole) return;
    setState('working');
    setMessage('Revalidating both nested DICOM SEG archives, live source bytes, chronology, and pairing judgments locally…');
    try {
      const request = buildPairingRequest({
        reviewerName,
        reviewerRole,
        reviewerOrganization,
        decision,
        pairing: {
          same_lesion_identity: sameLesion,
          same_represented_tissue: sameTissue,
          chronology,
          acquisition_comparability: acquisitionComparability,
          boundary_comparability: boundaryComparability,
          registration_consideration: registrationConsideration,
          limitation_note: limitationNote,
          treatment_context_note: treatmentContextNote,
        },
        checklist,
        attested,
      });
      const result = await saveLesionVolumeComparison(baseline, followup, request);
      setState('saved');
      setMessage(
        accepted
          ? `Saved ${result.filename}: qualified manual volume change for discussion only; no response or treatment-causality conclusion.`
          : `Saved ${result.filename}: pairing ${decision.replaceAll('_', ' ')} record with numeric change withheld.`,
      );
    } catch (error) {
      setState('error');
      setMessage(error instanceof Error ? error.message : 'Local volume-comparison assembly failed.');
    }
  };

  return (
    <section className="volume-pair-panel" aria-labelledby="volume-pair-heading">
      <div className="volume-pair-heading">
        <div>
          <span className="eyebrow">Agent-readable longitudinal boundary evidence</span>
          <h2 id="volume-pair-heading">Pair two accepted manual ROI boundaries</h2>
          <p>
            DICOM Guide derives chronology from the current local DICOM catalog and recursively
            revalidates both complete review archives. A person—not software—must confirm the same
            lesion and represented tissue. Numeric change never becomes a response classification.
          </p>
        </div>
        <span className="unreviewed-badge">Identity self-asserted</span>
      </div>
      <input
        ref={baselineInput}
        className="hidden-input"
        type="file"
        accept=".zip,application/zip"
        onChange={(event) => void importReview('baseline', event.target.files?.[0])}
      />
      <input
        ref={followupInput}
        className="hidden-input"
        type="file"
        accept=".zip,application/zip"
        onChange={(event) => void importReview('followup', event.target.files?.[0])}
      />
      <div className="volume-pair-source-grid">
        {reviewCard('baseline', baseline, baselineSeries)}
        {reviewCard('followup', followup, followupSeries)}
      </div>
      <div className="volume-pair-import-actions">
        <button onClick={() => baselineInput.current?.click()}>Open baseline boundary review</button>
        <button onClick={() => followupInput.current?.click()}>Open follow-up boundary review</button>
      </div>
      {pairErrors.length > 0 && baseline && followup && (
        <ul className="volume-pair-errors">{pairErrors.map((error) => <li key={error}>{error}</li>)}</ul>
      )}
      <details>
        <summary>Qualified pairing-review record</summary>
        <div className="volume-pair-fields">
          <label>Reviewer name<input value={reviewerName} maxLength={120} onChange={(event) => setReviewerName(event.target.value)} /></label>
          <label>Qualified role<select value={reviewerRole} onChange={(event) => setReviewerRole(event.target.value as LesionVolumeReviewerRole | '')}><option value="">Select role</option>{LESION_VOLUME_REVIEW_ROLES.map((role) => <option key={role} value={role}>{role.replaceAll('_', ' ')}</option>)}</select></label>
          <label>Organization (optional)<input value={reviewerOrganization} maxLength={160} onChange={(event) => setReviewerOrganization(event.target.value)} /></label>
          <label>Pairing decision<select value={decision} onChange={(event) => setDecision(event.target.value as LesionVolumeComparisonRequest['decision'])}><option value="revision_requested">Revision requested</option><option value="rejected">Rejected</option><option value="accepted_for_volume_change_discussion">Accepted for volume-change discussion</option></select></label>
          <label>Same lesion identity<select value={sameLesion} onChange={(event) => setSameLesion(event.target.value as typeof sameLesion)}><option value="uncertain">Uncertain</option><option value="not_confirmed">Not confirmed</option><option value="confirmed">Confirmed by reviewer</option></select></label>
          <label>Same represented tissue<select value={sameTissue} onChange={(event) => setSameTissue(event.target.value as typeof sameTissue)}><option value="uncertain">Uncertain</option><option value="not_confirmed">Not confirmed</option><option value="confirmed">Confirmed by reviewer</option></select></label>
          <label>Chronology<select value={chronology} onChange={(event) => setChronology(event.target.value as typeof chronology)}><option value="not_confirmed">Not confirmed</option><option value="confirmed">Confirmed with DICOM dates</option></select></label>
          <label>Acquisition comparability<select value={acquisitionComparability} onChange={(event) => setAcquisitionComparability(event.target.value as typeof acquisitionComparability)}><option value="not_suitable">Not suitable</option><option value="suitable_with_limitations">Suitable with limitations</option><option value="suitable">Suitable</option></select></label>
          <label>Boundary comparability<select value={boundaryComparability} onChange={(event) => setBoundaryComparability(event.target.value as typeof boundaryComparability)}><option value="not_suitable">Not suitable</option><option value="suitable_with_limitations">Suitable with limitations</option><option value="suitable">Suitable</option></select></label>
          <label>Registration consideration<select value={registrationConsideration} onChange={(event) => setRegistrationConsideration(event.target.value as typeof registrationConsideration)}><option value="uncertain">Uncertain</option><option value="required">Required for spatial use</option><option value="not_required">Not required for this volume-only discussion</option></select></label>
          <label className="volume-pair-wide">Comparability / registration limitations<textarea rows={3} maxLength={2000} value={limitationNote} onChange={(event) => setLimitationNote(event.target.value)} /></label>
          <label className="volume-pair-wide">Treatment context note (optional; never causal attribution)<textarea rows={3} maxLength={2000} value={treatmentContextNote} onChange={(event) => setTreatmentContextNote(event.target.value)} /></label>
        </div>
        <fieldset className="volume-pair-checklist">
          <legend>Pairing review checklist</legend>
          {checklistLabels.map(([key, label]) => <label key={key}><input type="checkbox" checked={checklist[key]} onChange={(event) => setChecklist((current) => ({ ...current, [key]: event.target.checked }))} />{label}</label>)}
        </fieldset>
        <label className="volume-pair-attestation"><input type="checkbox" checked={attested} onChange={(event) => setAttested(event.target.checked)} />{LESION_VOLUME_COMPARISON_ATTESTATION}</label>
      </details>
      <div className="volume-pair-actions">
        <button className="primary-action" disabled={!ready} onClick={() => void exportComparison()}>
          {state === 'working' ? 'Revalidating and assembling…' : 'Save reviewed volume-comparison archive'}
        </button>
        <output className={state === 'error' ? 'error' : undefined} role={state === 'error' ? 'alert' : 'status'}>{message}</output>
      </div>
      <p className="volume-pair-safety">
        The resulting archive can authorize discussion of reviewed manual volume arithmetic only.
        It cannot authorize response classification, progression, treatment causality, spatial
        overlay, voxelwise localization, diagnosis, or a clinical conclusion.
      </p>
    </section>
  );
}
