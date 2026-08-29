import { describe, expect, it } from 'vitest';
import {
  assessCompatibility,
  assessLesionVolumeEligibility,
  assessMprEligibility,
  formatDicomDate,
  getPatientOrientationLabels,
  getLinkStrategy,
  hasLongitudinalSourcePair,
  isConsultationSourcePair,
  isLongitudinalSourcePair,
  mapLinkedIndex,
  mapNormalizedIndex,
  type DicomInstance,
  type DicomSeries,
} from './dicom';

const instance = (position: number, instanceNumber = position): DicomInstance => ({
  instanceId: `instance-${instanceNumber}`,
  file: { name: `image-${instanceNumber}.dcm` } as File,
  instanceNumber,
  imagePosition: [0, 0, position],
  rows: 128,
  columns: 128,
  pixelSpacing: [0.8, 0.8],
  sliceThickness: 1,
  orientation: [1, 0, 0, 0, 1, 0],
  numberOfFrames: 1,
});

const series = (overrides: Partial<DicomSeries> = {}): DicomSeries => ({
  id: 'series-a',
  studyId: 'study-a',
  patientContextId: 'patient-a',
  acquisitionDate: '20260101',
  modality: 'MR',
  description: 'T1 POST CONTRAST',
  imageType: ['ORIGINAL', 'PRIMARY'],
  sourceKind: 'browser-folder',
  geometry: { rows: 512, columns: 512 },
  frameOfReferenceId: 'frame-a',
  instances: [],
  ...overrides,
});

describe('comparison safety', () => {
  it('detects only dated same-patient, same-modality, cross-study longitudinal sources', () => {
    const earlier = series();
    const later = series({
      id: 'series-b',
      studyId: 'study-b',
      acquisitionDate: '20260201',
    });
    expect(isLongitudinalSourcePair(earlier, later)).toBe(true);
    expect(hasLongitudinalSourcePair([earlier, later])).toBe(true);
    expect(isLongitudinalSourcePair(earlier, { ...later, modality: 'CT' })).toBe(false);
    expect(isLongitudinalSourcePair(earlier, { ...later, acquisitionDate: '20260231' })).toBe(false);
    expect(isLongitudinalSourcePair(earlier, { ...later, patientContextId: 'patient-b' })).toBe(
      false,
    );
    expect(hasLongitudinalSourcePair([earlier, { ...later, modality: 'CT' }])).toBe(false);
  });

  it('accepts distinct same-patient MRI and CT studies only as neutral consultation views', () => {
    const mr = series();
    const ct = series({
      id: 'series-b',
      studyId: 'study-b',
      acquisitionDate: undefined,
      modality: 'CT',
    });
    expect(isConsultationSourcePair(mr, ct)).toBe(true);
    expect(isLongitudinalSourcePair(mr, ct)).toBe(false);
    expect(isConsultationSourcePair(mr, { ...ct, modality: 'MR' })).toBe(false);
    expect(isConsultationSourcePair(mr, { ...ct, studyId: mr.studyId })).toBe(false);
    expect(isConsultationSourcePair(mr, { ...ct, patientContextId: 'patient-b' })).toBe(false);
  });

  it('never treats CT and MR as intensity-compatible', () => {
    const result = assessCompatibility(series(), series({ modality: 'CT' }));
    expect(result.level).toBe('incompatible');
    expect(result.reasons.join(' ')).toContain('not directly comparable');
  });

  it('warns when a spatial registration is needed', () => {
    const result = assessCompatibility(series(), series({ id: 'series-b', frameOfReferenceId: 'frame-b' }));
    expect(result.reasons.join(' ')).toContain('registration');
  });

  it('rejects two series from the same exam as a longitudinal pair', () => {
    const result = assessCompatibility(series(), series({ id: 'series-b' }));
    expect(result.level).toBe('incompatible');
    expect(result.reasons.join(' ')).toContain('same exam');
  });

  it('rejects cross-patient or unprovable patient contexts', () => {
    const baseline = series();
    const otherPatient = series({
      id: 'series-b',
      studyId: 'study-b',
      acquisitionDate: '20260201',
      patientContextId: 'patient-b',
    });
    const unavailable = series({
      id: 'series-c',
      studyId: 'study-c',
      acquisitionDate: '20260201',
      patientContextId: undefined,
    });

    expect(assessCompatibility(baseline, otherPatient).level).toBe('incompatible');
    expect(assessCompatibility(baseline, otherPatient).reasons.join(' ')).toContain(
      'different opaque patient contexts',
    );
    expect(assessCompatibility(baseline, unavailable).level).toBe('incompatible');
    expect(assessCompatibility(baseline, unavailable).reasons.join(' ')).toContain(
      'Patient context is unavailable',
    );
  });
});

describe('display formatting', () => {
  it('labels standard axial DICOM patient orientation without guessing', () => {
    expect(getPatientOrientationLabels([1, 0, 0, 0, 1, 0])).toEqual({
      left: 'R',
      right: 'L',
      top: 'A',
      bottom: 'P',
    });
  });

  it('orders compound oblique labels by direction-cosine magnitude', () => {
    const diagonal = 1 / Math.sqrt(2);
    expect(getPatientOrientationLabels([diagonal, diagonal, 0, 0, 0, -1])).toEqual({
      left: 'RA',
      right: 'LP',
      top: 'H',
      bottom: 'F',
    });
  });

  it('withholds orientation labels for malformed or non-orthogonal geometry', () => {
    expect(getPatientOrientationLabels([1, 0, 0])).toBeUndefined();
    expect(getPatientOrientationLabels([1, 0, 0, 1, 0, 0])).toBeUndefined();
    expect(getPatientOrientationLabels([2, 0, 0, 0, 1, 0])).toBeUndefined();
  });

  it('formats DICOM dates without guessing malformed values', () => {
    expect(formatDicomDate('20260828')).toBe('2026-08-28');
    expect(formatDicomDate('unknown')).toBe('unknown');
  });

  it('maps normalized stack position for linked native views', () => {
    expect(mapNormalizedIndex(0, 5, 11)).toBe(0);
    expect(mapNormalizedIndex(2, 5, 11)).toBe(5);
    expect(mapNormalizedIndex(4, 5, 11)).toBe(10);
  });

  it('maps by nearest patient position when frame and orientation are shared', () => {
    const baseline = series({
      geometry: { orientation: [1, 0, 0, 0, 1, 0] },
      instances: [instance(0), instance(7), instance(14)],
    });
    const followup = series({
      id: 'series-b',
      studyId: 'study-b',
      acquisitionDate: '20260201',
      geometry: { orientation: [1, 0, 0, 0, 1, 0] },
      instances: [instance(0), instance(4), instance(8), instance(12)],
    });

    expect(getLinkStrategy(baseline, followup)).toBe('patient-position');
    expect(mapLinkedIndex(1, baseline, followup)).toEqual({
      index: 2,
      strategy: 'patient-position',
    });
  });

  it('labels different-frame slice linking as normalized and approximate', () => {
    const baseline = series({ instances: [instance(0), instance(10)] });
    const followup = series({
      id: 'series-b',
      studyId: 'study-b',
      acquisitionDate: '20260201',
      frameOfReferenceId: 'frame-b',
      instances: [instance(0), instance(5), instance(10)],
    });

    expect(mapLinkedIndex(1, baseline, followup)).toEqual({
      index: 2,
      strategy: 'normalized',
    });
  });

  it('falls back to normalized linking when any slice position is missing', () => {
    const withoutPosition = { ...instance(10), imagePosition: undefined };
    const baseline = series({ instances: [instance(0), withoutPosition] });
    const followup = series({
      id: 'series-b',
      studyId: 'study-b',
      acquisitionDate: '20260201',
      instances: [instance(0), instance(5), instance(10)],
    });

    expect(getLinkStrategy(baseline, followup)).toBe('normalized');
  });
});

describe('MPR geometry gate', () => {
  const volumetricSeries = (overrides: Partial<DicomSeries> = {}): DicomSeries =>
    series({
      geometry: {
        rows: 128,
        columns: 128,
        pixelSpacing: [0.8, 0.8],
        sliceThickness: 1,
        orientation: [1, 0, 0, 0, 1, 0],
      },
      instances: [instance(0), instance(1), instance(2), instance(3)],
      ...overrides,
    });

  it('accepts a source series with complete, regular patient-space geometry', () => {
    expect(assessMprEligibility(volumetricSeries())).toEqual({
      eligible: true,
      reason: 'Geometry supports local orthographic reslicing.',
      sliceSpacingMm: 1,
    });
  });

  it('accepts only strict per-instance native geometry for manual volume evidence', () => {
    expect(assessLesionVolumeEligibility(volumetricSeries())).toEqual({
      eligible: true,
      reason: 'Geometry supports source-bound native-grid manual volume evidence.',
      sliceSpacingMm: 1,
    });
    expect(
      assessLesionVolumeEligibility(
        volumetricSeries({
          instances: [
            instance(0),
            instance(1),
            { ...instance(2), orientation: [1, 0, 0, 0, 0.999, 0.01] },
          ],
        }),
      ).reason,
    ).toContain('every source slice');
  });

  it('keeps navigation available while refusing loose spacing or in-plane drift for evidence', () => {
    const looselySpaced = volumetricSeries({
      instances: [instance(0), instance(1), instance(2), instance(3.05)],
    });
    expect(assessMprEligibility(looselySpaced).eligible).toBe(true);
    expect(assessLesionVolumeEligibility(looselySpaced).reason).toContain('irregular');

    const drifted = volumetricSeries({
      instances: [instance(0), { ...instance(1), imagePosition: [0.02, 0, 1] }, instance(2)],
    });
    expect(assessMprEligibility(drifted).eligible).toBe(true);
    expect(assessLesionVolumeEligibility(drifted).reason).toContain('drift');
  });

  it('refuses missing orientation, spacing, frame, or slice position', () => {
    expect(
      assessMprEligibility(
        volumetricSeries({ geometry: { rows: 128, columns: 128, pixelSpacing: [1, 1] } }),
      ).reason,
    ).toContain('orientation');
    expect(
      assessMprEligibility(
        volumetricSeries({
          geometry: { rows: 128, columns: 128, orientation: [1, 0, 0, 0, 1, 0] },
        }),
      ).reason,
    ).toContain('pixel spacing');
    expect(assessMprEligibility(volumetricSeries({ frameOfReferenceId: undefined })).reason).toContain(
      'Frame of Reference',
    );
    expect(
      assessMprEligibility(
        volumetricSeries({ instances: [instance(0), { ...instance(1), imagePosition: undefined }, instance(2)] }),
      ).reason,
    ).toContain('patient position');
  });

  it('refuses duplicate or irregular source slice positions', () => {
    expect(
      assessMprEligibility(
        volumetricSeries({ instances: [instance(0), instance(1), instance(1, 2)] }),
      ).reason,
    ).toContain('overlap');
    expect(
      assessMprEligibility(
        volumetricSeries({ instances: [instance(0), instance(1), instance(4)] }),
      ).reason,
    ).toContain('irregular');
  });
});
