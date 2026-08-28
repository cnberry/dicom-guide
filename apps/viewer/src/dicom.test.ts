import { describe, expect, it } from 'vitest';
import {
  assessCompatibility,
  formatDicomDate,
  getPatientOrientationLabels,
  getLinkStrategy,
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
