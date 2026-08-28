import dicomParser from 'dicom-parser';

export type Geometry = {
  rows?: number;
  columns?: number;
  pixelSpacing?: [number, number];
  sliceThickness?: number;
  orientation?: number[];
};

export type DicomInstance = {
  file: File;
  instanceNumber: number;
  imagePosition?: number[];
};

export type DicomSeries = {
  id: string;
  studyId: string;
  acquisitionDate?: string;
  modality: string;
  description: string;
  protocol?: string;
  bodyPart?: string;
  imageType: string[];
  frameOfReferenceId?: string;
  geometry: Geometry;
  instances: DicomInstance[];
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
  if (!studyUid || !seriesUid || !sopClassUid) return undefined;

  const modality = textTag(dataset, 'x00080060') ?? 'Unknown';
  // PR/SR and other DICOM objects remain available to the agent catalog, but
  // this MVP stack renderer only advertises CT/MR pixel series.
  if (!['CT', 'MR'].includes(modality)) return undefined;

  const pixelSpacing = numberListTag(dataset, 'x00280030');
  const orientation = numberListTag(dataset, 'x00200037');
  const position = numberListTag(dataset, 'x00200032');
  const frameOfReferenceUid = textTag(dataset, 'x00200052');

  return {
    file,
    id: await safeId('series', seriesUid),
    studyId: await safeId('study', studyUid),
    frameOfReferenceId: frameOfReferenceUid
      ? await safeId('frame-of-reference', frameOfReferenceUid)
      : undefined,
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

const sortInstances = (instances: DicomInstance[]): DicomInstance[] =>
  [...instances].sort((a, b) => {
    if (a.imagePosition && b.imagePosition && a.imagePosition.length === b.imagePosition.length) {
      const positionDifference = a.imagePosition[2] - b.imagePosition[2];
      if (positionDifference !== 0) return positionDifference;
    }
    if (a.instanceNumber !== b.instanceNumber) return a.instanceNumber - b.instanceNumber;
    return a.file.name.localeCompare(b.file.name);
  });

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
        const { file, instanceNumber, imagePosition, ...seriesHeader } = parsed;
        const existing = bySeries.get(parsed.id);
        const instance = { file, instanceNumber, imagePosition };
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
    .map((series) => ({ ...series, instances: sortInstances(series.instances) }))
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

export const assessCompatibility = (left?: DicomSeries, right?: DicomSeries): Compatibility => {
  if (!left || !right) {
    return { level: 'review', score: 0, reasons: ['Select a series in each viewport.'] };
  }

  let score = 100;
  const reasons: string[] = [];
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
    level: modalityMismatch
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
