import dicomParser from 'dicom-parser';

export type Geometry = {
  rows?: number;
  columns?: number;
  pixelSpacing?: [number, number];
  sliceThickness?: number;
  orientation?: number[];
};

export type PatientOrientationLabels = {
  left: string;
  right: string;
  top: string;
  bottom: string;
};

export type DicomInstance = {
  instanceId: string;
  file?: File;
  imageUrl?: string;
  instanceNumber: number;
  imagePosition?: number[];
};

export type DicomSeries = {
  id: string;
  studyId: string;
  patientContextId?: string;
  acquisitionDate?: string;
  modality: string;
  description: string;
  protocol?: string;
  bodyPart?: string;
  imageType: string[];
  frameOfReferenceId?: string;
  sourceKind: 'browser-folder' | 'loopback-service';
  geometry: Geometry;
  instances: DicomInstance[];
};

export type MprEligibility = {
  eligible: boolean;
  reason: string;
  sliceSpacingMm?: number;
};

type ParsedHeader = Omit<DicomSeries, 'instances'> & DicomInstance;

const textTag = (dataset: dicomParser.DataSet, tag: string): string | undefined => {
  const value = dataset.string(tag)?.trim();
  return value || undefined;
};

const numberTag = (dataset: dicomParser.DataSet, tag: string): number | undefined => {
  const value = textTag(dataset, tag);
  if (!value) return undefined;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
};

const numberListTag = (dataset: dicomParser.DataSet, tag: string): number[] | undefined => {
  const value = textTag(dataset, tag);
  if (!value) return undefined;
  const parsed = value.split('\\').map(Number);
  return parsed.every(Number.isFinite) ? parsed : undefined;
};

const safeId = async (namespace: string, value: string): Promise<string> => {
  const bytes = new TextEncoder().encode(`scanview-v1:${namespace}:${value}`);
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(digest).slice(0, 8))
    .map((byte) => byte.toString(16).padStart(2, '0'))
    .join('');
};

const dot = (left: number[], right: number[]): number =>
  left.reduce((sum, value, index) => sum + value * (right[index] ?? 0), 0);

const orientationStringLps = (vector: number[]): string =>
  [
    { magnitude: Math.abs(vector[0]), label: vector[0] < 0 ? 'R' : 'L' },
    { magnitude: Math.abs(vector[1]), label: vector[1] < 0 ? 'A' : 'P' },
    { magnitude: Math.abs(vector[2]), label: vector[2] < 0 ? 'F' : 'H' },
  ]
    .filter(({ magnitude }) => magnitude > 0.0001)
    .sort((left, right) => right.magnitude - left.magnitude)
    .map(({ label }) => label)
    .join('');

const invertOrientationStringLps = (value: string): string =>
  [...value]
    .map((label) => ({ R: 'L', L: 'R', A: 'P', P: 'A', F: 'H', H: 'F' })[label] ?? '')
    .join('');

export const getPatientOrientationLabels = (
  orientation?: number[],
): PatientOrientationLabels | undefined => {
  if (!orientation || orientation.length !== 6 || !orientation.every(Number.isFinite)) {
    return undefined;
  }
  const row = orientation.slice(0, 3);
  const column = orientation.slice(3, 6);
  const rowMagnitude = Math.sqrt(dot(row, row));
  const columnMagnitude = Math.sqrt(dot(column, column));
  if (
    Math.abs(rowMagnitude - 1) > 0.01 ||
    Math.abs(columnMagnitude - 1) > 0.01 ||
    Math.abs(dot(row, column)) > 0.01
  ) {
    return undefined;
  }
  const right = orientationStringLps(row);
  const bottom = orientationStringLps(column);
  if (!right || !bottom) return undefined;
  return {
    left: invertOrientationStringLps(right),
    right,
    top: invertOrientationStringLps(bottom),
    bottom,
  };
};

const normalFromOrientation = (orientation?: number[]): number[] | undefined => {
  if (!orientation || orientation.length < 6) return undefined;
  const [rx, ry, rz, cx, cy, cz] = orientation;
  const normal = [ry * cz - rz * cy, rz * cx - rx * cz, rx * cy - ry * cx];
  const magnitude = Math.sqrt(dot(normal, normal));
  return magnitude > 0 ? normal.map((value) => value / magnitude) : undefined;
};

const median = (values: number[]): number => {
  const sorted = [...values].sort((left, right) => left - right);
  const midpoint = Math.floor(sorted.length / 2);
  return sorted.length % 2
    ? sorted[midpoint]
    : (sorted[midpoint - 1] + sorted[midpoint]) / 2;
};

export const assessMprEligibility = (series?: DicomSeries): MprEligibility => {
  if (!series) return { eligible: false, reason: 'Choose a source series first.' };
  if (!['MR', 'CT'].includes(series.modality)) {
    return { eligible: false, reason: 'MPR is limited to MR and CT pixel series.' };
  }
  if (series.instances.length < 3) {
    return { eligible: false, reason: 'MPR requires at least three source slices.' };
  }
  if (!series.frameOfReferenceId) {
    return { eligible: false, reason: 'DICOM Frame of Reference is unavailable.' };
  }
  if (
    !Number.isInteger(series.geometry.rows) ||
    !Number.isInteger(series.geometry.columns) ||
    (series.geometry.rows ?? 0) < 2 ||
    (series.geometry.columns ?? 0) < 2
  ) {
    return { eligible: false, reason: 'Source matrix dimensions are unavailable.' };
  }
  if (
    !series.geometry.pixelSpacing ||
    series.geometry.pixelSpacing.length !== 2 ||
    !series.geometry.pixelSpacing.every((value) => Number.isFinite(value) && value > 0)
  ) {
    return { eligible: false, reason: 'Trusted in-plane pixel spacing is unavailable.' };
  }
  if (!getPatientOrientationLabels(series.geometry.orientation)) {
    return { eligible: false, reason: 'Validated DICOM image orientation is unavailable.' };
  }
  const normal = normalFromOrientation(series.geometry.orientation);
  if (!normal) {
    return { eligible: false, reason: 'A source slice normal cannot be derived.' };
  }
  if (
    series.instances.some(
      (instance) =>
        instance.imagePosition?.length !== 3 ||
        !instance.imagePosition.every(Number.isFinite),
    )
  ) {
    return { eligible: false, reason: 'Every source slice needs a finite patient position.' };
  }
  const coordinates = series.instances.map((instance) => dot(instance.imagePosition!, normal));
  const spacings = coordinates
    .slice(1)
    .map((coordinate, index) => Math.abs(coordinate - coordinates[index]));
  if (spacings.some((spacing) => !Number.isFinite(spacing) || spacing < 0.01)) {
    return { eligible: false, reason: 'Source slice positions overlap or are malformed.' };
  }
  const sliceSpacingMm = median(spacings);
  const tolerance = Math.max(0.1, sliceSpacingMm * 0.1);
  if (spacings.some((spacing) => Math.abs(spacing - sliceSpacingMm) > tolerance)) {
    return {
      eligible: false,
      reason: 'Source slice spacing is too irregular for trustworthy local MPR.',
    };
  }
  return {
    eligible: true,
    reason: 'Geometry supports local orthographic reslicing.',
    sliceSpacingMm,
  };
};

const parseHeader = async (file: File): Promise<ParsedHeader | undefined> => {
  // DICOM headers precede Pixel Data. Capping the read prevents importing a study
  // from holding all pixel arrays in memory at once.
  const headerBytes = await file.slice(0, Math.min(file.size, 2 * 1024 * 1024)).arrayBuffer();
  let dataset: dicomParser.DataSet;
  try {
    dataset = dicomParser.parseDicom(new Uint8Array(headerBytes), {
      untilTag: 'x7fe00010',
    });
  } catch {
    return undefined;
  }

  const studyUid = textTag(dataset, 'x0020000d');
  const seriesUid = textTag(dataset, 'x0020000e');
  const sopClassUid = textTag(dataset, 'x00080016');
  const sopInstanceUid = textTag(dataset, 'x00080018');
  if (!studyUid || !seriesUid || !sopClassUid || !sopInstanceUid) return undefined;

  const modality = textTag(dataset, 'x00080060') ?? 'Unknown';
  // PR/SR and other DICOM objects remain available to the agent catalog, but
  // this MVP stack renderer only advertises CT/MR pixel series.
  if (!['CT', 'MR'].includes(modality)) return undefined;

  const pixelSpacing = numberListTag(dataset, 'x00280030');
  const orientation = numberListTag(dataset, 'x00200037');
  const position = numberListTag(dataset, 'x00200032');
  const frameOfReferenceUid = textTag(dataset, 'x00200052');
  const patientId = textTag(dataset, 'x00100020');
  const patientIssuer = textTag(dataset, 'x00100021');
  const patientName = textTag(dataset, 'x00100010');
  const patientBirthDate = textTag(dataset, 'x00100030');
  const patientIdentity = patientId
    ? patientName || patientBirthDate
      ? `id-demographics:${patientId}:${patientName ?? ''}:${patientBirthDate ?? ''}`
      : `id-issuer:${patientIssuer ?? ''}:${patientId}`
    : patientName || patientBirthDate
      ? `demographics:${patientName ?? ''}:${patientBirthDate ?? ''}`
      : `study-only:${studyUid}`;

  return {
    file,
    instanceId: await safeId('instance', sopInstanceUid),
    id: await safeId('series', seriesUid),
    studyId: await safeId('study', studyUid),
    patientContextId: await safeId('patient-context', patientIdentity),
    frameOfReferenceId: frameOfReferenceUid
      ? await safeId('frame-of-reference', frameOfReferenceUid)
      : undefined,
    sourceKind: 'browser-folder',
    acquisitionDate:
      textTag(dataset, 'x00080022') ??
      textTag(dataset, 'x00080021') ??
      textTag(dataset, 'x00080020'),
    modality,
    description: textTag(dataset, 'x0008103e') ?? 'Unnamed series',
    protocol: textTag(dataset, 'x00181030'),
    bodyPart: textTag(dataset, 'x00180015'),
    imageType: (textTag(dataset, 'x00080008') ?? '').split('\\').filter(Boolean),
    geometry: {
      rows: numberTag(dataset, 'x00280010'),
      columns: numberTag(dataset, 'x00280011'),
      pixelSpacing:
        pixelSpacing && pixelSpacing.length >= 2
          ? [pixelSpacing[0], pixelSpacing[1]]
          : undefined,
      sliceThickness: numberTag(dataset, 'x00180050'),
      orientation,
    },
    instanceNumber: numberTag(dataset, 'x00200013') ?? 0,
    imagePosition: position,
  };
};

const sortInstances = (instances: DicomInstance[], orientation?: number[]): DicomInstance[] => {
  const normal = normalFromOrientation(orientation);
  return [...instances].sort((a, b) => {
    if (normal && a.imagePosition?.length === 3 && b.imagePosition?.length === 3) {
      const positionDifference = dot(a.imagePosition, normal) - dot(b.imagePosition, normal);
      if (positionDifference !== 0) return positionDifference;
    }
    if (a.imagePosition && b.imagePosition && a.imagePosition.length === b.imagePosition.length) {
      const positionDifference = a.imagePosition[2] - b.imagePosition[2];
      if (positionDifference !== 0) return positionDifference;
    }
    if (a.instanceNumber !== b.instanceNumber) return a.instanceNumber - b.instanceNumber;
    return (a.file?.name ?? a.instanceId).localeCompare(b.file?.name ?? b.instanceId);
  });
};

export type LinkStrategy = 'patient-position' | 'normalized';

export const getLinkStrategy = (
  source?: DicomSeries,
  target?: DicomSeries,
): LinkStrategy => {
  if (
    !source ||
    !target ||
    !source.frameOfReferenceId ||
    source.frameOfReferenceId !== target.frameOfReferenceId
  ) {
    return 'normalized';
  }
  const sourceNormal = normalFromOrientation(source.geometry.orientation);
  const targetNormal = normalFromOrientation(target.geometry.orientation);
  if (!sourceNormal || !targetNormal || Math.abs(dot(sourceNormal, targetNormal)) < 0.999) {
    return 'normalized';
  }
  const sourceHasPosition =
    source.instances.length > 0 &&
    source.instances.every((instance) => instance.imagePosition?.length === 3);
  const targetHasPosition =
    target.instances.length > 0 &&
    target.instances.every((instance) => instance.imagePosition?.length === 3);
  return sourceHasPosition && targetHasPosition ? 'patient-position' : 'normalized';
};

export const mapLinkedIndex = (
  sourceIndex: number,
  source: DicomSeries,
  target: DicomSeries,
): { index: number; strategy: LinkStrategy } => {
  const strategy = getLinkStrategy(source, target);
  if (strategy === 'patient-position') {
    const boundedSource = Math.max(0, Math.min(sourceIndex, source.instances.length - 1));
    const position = source.instances[boundedSource]?.imagePosition;
    const normal = normalFromOrientation(source.geometry.orientation);
    if (position?.length === 3 && normal) {
      const sourceCoordinate = dot(position, normal);
      let closestIndex = 0;
      let closestDistance = Number.POSITIVE_INFINITY;
      target.instances.forEach((instance, index) => {
        if (instance.imagePosition?.length !== 3) return;
        const distance = Math.abs(dot(instance.imagePosition, normal) - sourceCoordinate);
        if (distance < closestDistance) {
          closestDistance = distance;
          closestIndex = index;
        }
      });
      if (Number.isFinite(closestDistance)) return { index: closestIndex, strategy };
    }
  }
  return {
    index: mapNormalizedIndex(sourceIndex, source.instances.length, target.instances.length),
    strategy: 'normalized',
  };
};

export const parseDicomFiles = async (
  files: File[],
  onProgress: (processed: number, total: number) => void,
): Promise<DicomSeries[]> => {
  const bySeries = new Map<string, DicomSeries>();
  let cursor = 0;
  const workers = Array.from({ length: Math.min(6, Math.max(1, files.length)) }, async () => {
    while (cursor < files.length) {
      const index = cursor++;
      const parsed = await parseHeader(files[index]);
      if (parsed) {
        const { file, instanceId, instanceNumber, imagePosition, ...seriesHeader } = parsed;
        const existing = bySeries.get(parsed.id);
        const instance = { file, instanceId, instanceNumber, imagePosition };
        if (existing) {
          existing.instances.push(instance);
        } else {
          bySeries.set(parsed.id, { ...seriesHeader, instances: [instance] });
        }
      }
      onProgress(index + 1, files.length);
    }
  });
  await Promise.all(workers);

  return [...bySeries.values()]
    .map((series) => ({
      ...series,
      instances: sortInstances(series.instances, series.geometry.orientation),
    }))
    .sort((a, b) => {
      const dateOrder = (a.acquisitionDate ?? '').localeCompare(b.acquisitionDate ?? '');
      return dateOrder || a.description.localeCompare(b.description);
    });
};

export type Compatibility = {
  level: 'compatible' | 'review' | 'incompatible';
  score: number;
  reasons: string[];
};

const isValidDicomDate = (value?: string): value is string => {
  if (!value || !/^\d{8}$/.test(value)) return false;
  const year = Number(value.slice(0, 4));
  const month = Number(value.slice(4, 6));
  const day = Number(value.slice(6, 8));
  const parsed = new Date(Date.UTC(year, month - 1, day));
  return (
    parsed.getUTCFullYear() === year &&
    parsed.getUTCMonth() === month - 1 &&
    parsed.getUTCDate() === day
  );
};

export const isLongitudinalSourcePair = (
  left?: DicomSeries,
  right?: DicomSeries,
): boolean =>
  Boolean(
    left &&
      right &&
      left.id !== right.id &&
      left.studyId !== right.studyId &&
      left.patientContextId &&
      left.patientContextId === right.patientContextId &&
      ['MR', 'CT'].includes(left.modality) &&
      left.modality === right.modality &&
      isValidDicomDate(left.acquisitionDate) &&
      isValidDicomDate(right.acquisitionDate) &&
      left.acquisitionDate !== right.acquisitionDate,
  );

export const hasLongitudinalSourcePair = (series: DicomSeries[]): boolean =>
  series.some((left, index) =>
    series.slice(index + 1).some((right) => isLongitudinalSourcePair(left, right)),
  );

export const isConsultationSourcePair = (
  left?: DicomSeries,
  right?: DicomSeries,
): boolean =>
  Boolean(
    left &&
      right &&
      left.id !== right.id &&
      left.studyId !== right.studyId &&
      left.patientContextId &&
      left.patientContextId === right.patientContextId &&
      ['MR', 'CT'].includes(left.modality) &&
      ['MR', 'CT'].includes(right.modality) &&
      left.modality !== right.modality,
  );

export const assessCompatibility = (left?: DicomSeries, right?: DicomSeries): Compatibility => {
  if (!left || !right) {
    return { level: 'review', score: 0, reasons: ['Select a series in each viewport.'] };
  }

  let score = 100;
  const reasons: string[] = [];
  const identicalSeries = left.id === right.id;
  const sameStudy = left.studyId === right.studyId;
  const samePatientContext = Boolean(
    left.patientContextId && left.patientContextId === right.patientContextId,
  );
  const sameDate = Boolean(
    left.acquisitionDate && right.acquisitionDate && left.acquisitionDate === right.acquisitionDate,
  );
  if (identicalSeries) {
    score = 0;
    reasons.push('The same series is selected twice; this cannot show change over time.');
  } else if (sameStudy) {
    score -= 80;
    reasons.push('Both series belong to the same exam; this is not a longitudinal response pair.');
  } else if (sameDate) {
    score -= 50;
    reasons.push(
      'Both exams have the same acquisition date; treatment-response timing is not established.',
    );
  }
  if (!samePatientContext) {
    score = 0;
    reasons.push(
      left.patientContextId && right.patientContextId
        ? 'The series have different opaque patient contexts and cannot be paired.'
        : 'Patient context is unavailable; cross-exam pairing is disabled.',
    );
  }
  const modalityMismatch = left.modality !== right.modality;
  if (modalityMismatch) {
    score -= 60;
    reasons.push(`${left.modality} and ${right.modality} intensities are not directly comparable.`);
  } else {
    reasons.push(`Both series use ${left.modality}.`);
  }

  const leftDescription = left.description.toLowerCase();
  const rightDescription = right.description.toLowerCase();
  const sharedTerms = leftDescription
    .split(/[^a-z0-9]+/)
    .filter((term) => term.length >= 2 && rightDescription.includes(term));
  if (sharedTerms.length === 0) {
    score -= 25;
    reasons.push('Sequence descriptions differ; a person must confirm this pairing.');
  } else {
    reasons.push(`Shared sequence terms: ${[...new Set(sharedTerms)].slice(0, 4).join(', ')}.`);
  }

  if (left.geometry.rows !== right.geometry.rows || left.geometry.columns !== right.geometry.columns) {
    score -= 10;
    reasons.push('Matrix dimensions differ.');
  }
  if (left.frameOfReferenceId && left.frameOfReferenceId === right.frameOfReferenceId) {
    reasons.push('The series share a DICOM Frame of Reference.');
  } else {
    score -= 5;
    reasons.push('No shared Frame of Reference; overlays require reviewed registration.');
  }

  const boundedScore = Math.max(0, score);
  return {
    score: boundedScore,
    level: identicalSeries || sameStudy || !samePatientContext || modalityMismatch
      ? 'incompatible'
      : boundedScore >= 80
        ? 'compatible'
        : boundedScore >= 40
          ? 'review'
          : 'incompatible',
    reasons,
  };
};

export const mapNormalizedIndex = (
  sourceIndex: number,
  sourceCount: number,
  targetCount: number,
): number => {
  if (sourceCount <= 1 || targetCount <= 1) return 0;
  const boundedSource = Math.max(0, Math.min(sourceIndex, sourceCount - 1));
  return Math.round((boundedSource / (sourceCount - 1)) * (targetCount - 1));
};

export const formatDicomDate = (value?: string): string => {
  if (!value || !/^\d{8}$/.test(value)) return value ?? 'Date unavailable';
  const year = value.slice(0, 4);
  const month = value.slice(4, 6);
  const day = value.slice(6, 8);
  return `${year}-${month}-${day}`;
};
