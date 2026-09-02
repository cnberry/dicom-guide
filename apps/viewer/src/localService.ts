import type { DicomInstance, DicomSeries, Geometry } from './dicom';

export type LocalServiceCatalog = {
  series: DicomSeries[];
  studyCount: number;
  instanceCount: number;
};

export type LocalFolderSelection =
  | { status: 'cancelled' }
  | {
      status: 'selected';
      sourceRevision: number;
      studyCount: number;
      seriesCount: number;
      instanceCount: number;
    };

const isRecord = (value: unknown): value is Record<string, unknown> =>
  Boolean(value && typeof value === 'object' && !Array.isArray(value));

const isOpaqueId = (
  value: unknown,
  kind: 'study' | 'series' | 'instance' | 'frame' | 'patient',
): value is string =>
  typeof value === 'string' && new RegExp(`^${kind}_[0-9a-f]{20}$`).test(value);

const finiteNumber = (value: unknown): number | undefined =>
  typeof value === 'number' && Number.isFinite(value) ? value : undefined;

const finiteNumbers = (value: unknown, length?: number): number[] | undefined => {
  if (
    !Array.isArray(value) ||
    (length !== undefined && value.length !== length) ||
    !value.every((item) => typeof item === 'number' && Number.isFinite(item))
  ) {
    return undefined;
  }
  return value;
};

const stringArray = (value: unknown): string[] =>
  Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [];

const readInstance = (value: unknown, index: number): DicomInstance | undefined => {
  if (!isRecord(value) || !isOpaqueId(value.id, 'instance')) return undefined;
  const imagePosition = finiteNumbers(value.image_position_patient, 3);
  const pixelSpacing = finiteNumbers(value.pixel_spacing, 2);
  const orientation = finiteNumbers(value.image_orientation_patient, 6);
  return {
    instanceId: value.id,
    imageUrl: `/v1/instances/${encodeURIComponent(value.id)}`,
    bytes:
      typeof value.bytes === 'number' && Number.isSafeInteger(value.bytes) && value.bytes > 0
        ? value.bytes
        : undefined,
    sha256:
      typeof value.sha256 === 'string' && /^[0-9a-f]{64}$/.test(value.sha256)
        ? value.sha256
        : undefined,
    instanceNumber: finiteNumber(value.instance_number) ?? index,
    imagePosition,
    rows: finiteNumber(value.rows),
    columns: finiteNumber(value.columns),
    pixelSpacing,
    sliceThickness: finiteNumber(value.slice_thickness),
    orientation,
    numberOfFrames: finiteNumber(value.number_of_frames),
  };
};

const readGeometry = (value: Record<string, unknown>): Geometry => {
  const pixelSpacing = finiteNumbers(value.pixel_spacing, 2);
  return {
    rows: finiteNumber(value.rows),
    columns: finiteNumber(value.columns),
    pixelSpacing:
      pixelSpacing && pixelSpacing.every((item) => item > 0)
        ? [pixelSpacing[0], pixelSpacing[1]]
        : undefined,
    sliceThickness: finiteNumber(value.slice_thickness),
    orientation: finiteNumbers(value.image_orientation_patient, 6),
  };
};

const readSeries = (studyId: string, value: unknown): DicomSeries | undefined => {
  if (
    !isRecord(value) ||
    !isOpaqueId(value.id, 'series') ||
    !['MR', 'CT'].includes(String(value.modality)) ||
    !Array.isArray(value.instances)
  ) {
    return undefined;
  }
  const instances = value.instances.flatMap((item, index) => {
    const instance = readInstance(item, index);
    return instance ? [instance] : [];
  });
  if (instances.length === 0) return undefined;
  return {
    id: value.id,
    studyId,
    patientContextId: isOpaqueId(value.patient_context_id, 'patient')
      ? value.patient_context_id
      : undefined,
    acquisitionDate:
      typeof value.acquisition_date === 'string' ? value.acquisition_date : undefined,
    modality: String(value.modality),
    description:
      typeof value.series_description === 'string' ? value.series_description : 'Unnamed series',
    protocol: typeof value.protocol_name === 'string' ? value.protocol_name : undefined,
    bodyPart: typeof value.body_part === 'string' ? value.body_part : undefined,
    imageType: stringArray(value.image_type),
    frameOfReferenceId: isOpaqueId(value.frame_of_reference_id, 'frame')
      ? value.frame_of_reference_id
      : undefined,
    sourceKind: 'loopback-service',
    geometry: readGeometry(value),
    instances,
  };
};

export const manifestToDicomSeries = (value: unknown): LocalServiceCatalog | undefined => {
  if (!isRecord(value) || value.schema_version !== '1.0.0' || !Array.isArray(value.studies)) {
    return undefined;
  }
  const source = isRecord(value.source) ? value.source : undefined;
  const instanceCount = source ? finiteNumber(source.dicom_instances) : undefined;
  if (instanceCount === undefined || instanceCount < 0) return undefined;
  const series: DicomSeries[] = [];
  let studyCount = 0;
  value.studies.forEach((study) => {
    if (!isRecord(study) || !isOpaqueId(study.id, 'study') || !Array.isArray(study.series)) {
      return;
    }
    studyCount += 1;
    study.series.forEach((candidate) => {
      const parsed = readSeries(study.id as string, candidate);
      if (parsed) series.push(parsed);
    });
  });
  series.sort((left, right) => {
    const dateOrder = (left.acquisitionDate ?? '').localeCompare(right.acquisitionDate ?? '');
    return dateOrder || left.description.localeCompare(right.description);
  });
  return { series, studyCount, instanceCount };
};

export const loadLocalServiceCatalog = async (
  signal?: AbortSignal,
): Promise<LocalServiceCatalog | undefined> => {
  try {
    const response = await fetch('/v1/manifest', {
      cache: 'no-store',
      credentials: 'same-origin',
      headers: { Accept: 'application/json' },
      signal,
    });
    if (!response.ok) return undefined;
    return manifestToDicomSeries(await response.json());
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') return undefined;
    return undefined;
  }
};

const localFolderError = (value: unknown): string => {
  const code = isRecord(value) && typeof value.error === 'string' ? value.error : undefined;
  if (code === 'no_renderable_dicom') {
    return 'No readable MR or CT image series were found. The current folder remains open.';
  }
  if (code === 'folder_picker_unavailable') {
    return 'The native folder chooser is unavailable on this computer.';
  }
  if (code === 'folder_selection_in_progress') {
    return 'A folder is already being opened. Please wait.';
  }
  if (code === 'source_locked') {
    return 'This special review session is locked to its launch folder.';
  }
  return 'The local folder could not be indexed. The current folder remains open.';
};

export const selectLocalServiceFolder = async (): Promise<
  LocalFolderSelection | undefined
> => {
  let response: Response;
  try {
    response = await fetch('/v1/local-folders/select', {
      method: 'POST',
      cache: 'no-store',
      credentials: 'same-origin',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
      },
      body: '{}',
    });
  } catch {
    throw new Error('The local folder service is unavailable. The current folder remains open.');
  }
  if (response.status === 404) return undefined;
  let value: unknown;
  try {
    value = await response.json();
  } catch {
    throw new Error('The local folder service returned an invalid response.');
  }
  if (!response.ok) throw new Error(localFolderError(value));
  if (isRecord(value) && value.status === 'cancelled') return { status: 'cancelled' };
  if (
    !isRecord(value) ||
    value.status !== 'selected' ||
    !Number.isSafeInteger(value.source_revision) ||
    !Number.isSafeInteger(value.study_count) ||
    !Number.isSafeInteger(value.renderable_series) ||
    !Number.isSafeInteger(value.dicom_instances)
  ) {
    throw new Error('The local folder service returned an invalid response.');
  }
  return {
    status: 'selected',
    sourceRevision: value.source_revision as number,
    studyCount: value.study_count as number,
    seriesCount: value.renderable_series as number,
    instanceCount: value.dicom_instances as number,
  };
};
