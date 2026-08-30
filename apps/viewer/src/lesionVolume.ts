import { strToU8, zipSync } from 'fflate';
import {
  MAX_MANUAL_LABELMAP_VOXELS,
  assessLesionVolumeEligibility,
  type DicomInstance,
  type DicomSeries,
} from './dicom';

export { MAX_MANUAL_LABELMAP_VOXELS } from './dicom';

export type SourceInstanceEvidence = {
  frame_index: number;
  instance_id: string;
  bytes: number;
  sha256: string;
  rows: number;
  columns: number;
  pixel_spacing_mm: [number, number];
  image_orientation_patient: [number, number, number, number, number, number];
  image_position_patient: [number, number, number];
};

export type LesionVolumeEvidence = {
  schema_version: '1.0.0';
  artifact_type: 'dicom-guide.lesion-volume-evidence';
  artifact_id: string;
  created_at: string;
  state: 'draft_unreviewed';
  local_only: true;
  sensitive: true;
  deidentified: false;
  source: {
    patient_context_id?: string;
    study_id: string;
    series_id: string;
    frame_of_reference_id: string;
    modality: 'MR' | 'CT';
    instance_count: number;
    instances: SourceInstanceEvidence[];
    source_set_sha256: string;
  };
  segment: {
    segment_number: 1;
    tracking_id: string;
    tracking_uid: string;
    label: string;
    target_definition: string;
    algorithm_type: 'MANUAL';
    property_category: { value: '49755003'; scheme: 'SCT'; meaning: 'Morphologically Abnormal Structure' };
    property_type: { value: '52988006'; scheme: 'SCT'; meaning: 'Lesion' };
  };
  geometry: {
    grid_order: 'source_volume_frame_row_column';
    dimensions: [number, number, number];
    pixel_spacing_mm: [number, number];
    projected_slice_spacing_mm: number;
    row_direction: [number, number, number];
    column_direction: [number, number, number];
    normal_direction: [number, number, number];
    voxel_volume_mm3: number;
    geometry_matches_source: true;
    resampled: false;
  };
  measurement: {
    status: 'computed_unreviewed';
    method: 'binary_voxel_count_times_native_voxel_determinant';
    foreground_voxel_count: number;
    volume_mm3: number;
    volume_ml: number;
    mask_pixel_sha256: string;
    boundary_uncertainty: 'not_quantified';
  };
  files: {
    dicom_seg: { filename: 'segmentation.dcm'; bytes: number; sha256: string };
  };
  review: { status: 'unreviewed' };
  permitted_uses: {
    source_overlay: true;
    mask_overlay: true;
    exact_timepoint_volume: 'computed_unreviewed_only';
    longitudinal_link: false;
    percent_change: false;
    response_classification: false;
    diagnosis: false;
    clinical_conclusion: false;
  };
  limitations: string[];
};

export type ManualSegmentationStats = {
  foregroundVoxels: number;
  voxelVolumeMm3: number;
  volumeMm3: number;
  volumeMl: number;
};

export type LesionVolumeArchive = {
  filename: string;
  bytes: Uint8Array;
  evidence: LesionVolumeEvidence;
};

const sha256Hex = async (bytes: ArrayBuffer | Uint8Array): Promise<string> => {
  const view = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  const owned = new Uint8Array(view.byteLength);
  owned.set(view);
  const digest = await crypto.subtle.digest('SHA-256', owned.buffer);
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, '0'))
    .join('');
};

const cross = (
  left: [number, number, number],
  right: [number, number, number],
): [number, number, number] => [
  left[1] * right[2] - left[2] * right[1],
  left[2] * right[0] - left[0] * right[2],
  left[0] * right[1] - left[1] * right[0],
];

const validateBoundedText = (value: string, name: string, maximum: number): string => {
  const normalized = value.trim().replace(/\s+/g, ' ');
  if (!normalized) throw new Error(`${name} is required.`);
  if (normalized.length > maximum) throw new Error(`${name} must be ${maximum} characters or fewer.`);
  return normalized;
};

const binaryMask = (values: ArrayLike<number>, expectedLength: number): Uint8Array => {
  if (expectedLength < 1 || expectedLength > MAX_MANUAL_LABELMAP_VOXELS) {
    throw new Error('The manual labelmap exceeds the 64 Mi-voxel local safety bound.');
  }
  if (values.length !== expectedLength) {
    throw new Error('The manual labelmap does not match the native source grid.');
  }
  const output = values instanceof Uint8Array ? values : new Uint8Array(expectedLength);
  let foreground = 0;
  for (let index = 0; index < values.length; index += 1) {
    const value = Number(values[index]);
    if (value !== 0 && value !== 1) {
      throw new Error('The v1 manual labelmap must be strictly binary (0 or 1).');
    }
    if (!(values instanceof Uint8Array)) output[index] = value;
    foreground += value;
  }
  if (foreground === 0) throw new Error('Paint at least one voxel before exporting evidence.');
  return output;
};

const readInstanceBytes = async (instance: DicomInstance): Promise<{ bytes: number; sha256: string }> => {
  let payload: ArrayBuffer;
  if (instance.file) {
    payload = await instance.file.arrayBuffer();
  } else if (instance.imageUrl) {
    const response = await fetch(instance.imageUrl, {
      cache: 'no-store',
      credentials: 'same-origin',
    });
    if (!response.ok) throw new Error('An exact source instance could not be re-read locally.');
    payload = await response.arrayBuffer();
  } else {
    throw new Error('An exact source instance has no local byte source.');
  }
  return { bytes: payload.byteLength, sha256: await sha256Hex(payload) };
};

export const collectSourceInstanceEvidence = async (
  series: DicomSeries,
  orderedInstanceIds: string[],
): Promise<SourceInstanceEvidence[]> => {
  const byId = new Map(series.instances.map((instance) => [instance.instanceId, instance]));
  const output: SourceInstanceEvidence[] = [];
  for (const [frameIndex, instanceId] of orderedInstanceIds.entries()) {
    const instance = byId.get(instanceId);
    if (
      !instance?.imagePosition ||
      instance.imagePosition.length !== 3 ||
      !Number.isInteger(instance.rows) ||
      !Number.isInteger(instance.columns) ||
      instance.pixelSpacing?.length !== 2 ||
      instance.orientation?.length !== 6
    ) {
      throw new Error('An ordered native source geometry record is unavailable.');
    }
    const integrity = await readInstanceBytes(instance);
    output.push({
      frame_index: frameIndex,
      instance_id: instanceId,
      bytes: integrity.bytes,
      sha256: integrity.sha256,
      rows: instance.rows!,
      columns: instance.columns!,
      pixel_spacing_mm: [instance.pixelSpacing[0], instance.pixelSpacing[1]],
      image_orientation_patient: instance.orientation as [
        number,
        number,
        number,
        number,
        number,
        number,
      ],
      image_position_patient: instance.imagePosition as [number, number, number],
    });
  }
  return output;
};

export const calculateManualSegmentationStats = (
  values: ArrayLike<number>,
  dimensions: [number, number, number],
  pixelSpacing: [number, number],
  sliceSpacingMm: number,
): ManualSegmentationStats => {
  const expectedLength = dimensions[0] * dimensions[1] * dimensions[2];
  if (!Number.isSafeInteger(expectedLength)) throw new Error('Native grid size is not a safe integer.');
  const mask = binaryMask(values, expectedLength);
  const foregroundVoxels = mask.reduce((sum, value) => sum + value, 0);
  const voxelVolumeMm3 = pixelSpacing[0] * pixelSpacing[1] * sliceSpacingMm;
  if (!Number.isFinite(voxelVolumeMm3) || voxelVolumeMm3 <= 0) {
    throw new Error('Native voxel geometry is invalid.');
  }
  const volumeMm3 = foregroundVoxels * voxelVolumeMm3;
  return {
    foregroundVoxels,
    voxelVolumeMm3,
    volumeMm3,
    volumeMl: volumeMm3 / 1000,
  };
};

export const buildLesionVolumeArchive = async ({
  series,
  orderedInstanceIds,
  dimensions,
  sliceSpacingMm,
  maskValues,
  dicomSegBytes,
  artifactId,
  trackingUid,
  label,
  targetDefinition,
  createdAt = new Date().toISOString(),
}: {
  series: DicomSeries;
  orderedInstanceIds: string[];
  dimensions: [number, number, number];
  sliceSpacingMm: number;
  maskValues: ArrayLike<number>;
  dicomSegBytes: Uint8Array;
  artifactId: string;
  trackingUid: string;
  label: string;
  targetDefinition: string;
  createdAt?: string;
}): Promise<LesionVolumeArchive> => {
  const normalizedLabel = validateBoundedText(label, 'Working region label', 64);
  const normalizedDefinition = validateBoundedText(targetDefinition, 'Target definition', 300);
  const eligibility = assessLesionVolumeEligibility(series);
  if (!eligibility.eligible || !eligibility.sliceSpacingMm) {
    throw new Error(eligibility.reason);
  }
  if (Math.abs(sliceSpacingMm - eligibility.sliceSpacingMm) > 0.01) {
    throw new Error('The loaded volume spacing does not match the exact source geometry.');
  }
  if (!series.frameOfReferenceId || !['MR', 'CT'].includes(series.modality)) {
    throw new Error('One native MR or CT Frame of Reference is required.');
  }
  const pixelSpacing = series.geometry.pixelSpacing;
  const orientation = series.geometry.orientation;
  if (!pixelSpacing || orientation?.length !== 6) throw new Error('Native source geometry is incomplete.');
  const mask = binaryMask(maskValues, dimensions[0] * dimensions[1] * dimensions[2]);
  const stats = calculateManualSegmentationStats(mask, dimensions, pixelSpacing, sliceSpacingMm);
  const instances = await collectSourceInstanceEvidence(series, orderedInstanceIds);
  const sourceLines = instances.map(
    (item) => `${item.frame_index}:${item.instance_id}:${item.bytes}:${item.sha256}`,
  );
  const rowDirection = orientation.slice(0, 3) as [number, number, number];
  const columnDirection = orientation.slice(3, 6) as [number, number, number];
  const normalDirection = cross(rowDirection, columnDirection);
  const evidence: LesionVolumeEvidence = {
    schema_version: '1.0.0',
    artifact_type: 'dicom-guide.lesion-volume-evidence',
    artifact_id: artifactId,
    created_at: createdAt,
    state: 'draft_unreviewed',
    local_only: true,
    sensitive: true,
    deidentified: false,
    source: {
      ...(series.patientContextId ? { patient_context_id: series.patientContextId } : {}),
      study_id: series.studyId,
      series_id: series.id,
      frame_of_reference_id: series.frameOfReferenceId,
      modality: series.modality as 'MR' | 'CT',
      instance_count: instances.length,
      instances,
      source_set_sha256: await sha256Hex(strToU8(`${sourceLines.join('\n')}\n`)),
    },
    segment: {
      segment_number: 1,
      tracking_id: artifactId,
      tracking_uid: trackingUid,
      label: normalizedLabel,
      target_definition: normalizedDefinition,
      algorithm_type: 'MANUAL',
      property_category: {
        value: '49755003',
        scheme: 'SCT',
        meaning: 'Morphologically Abnormal Structure',
      },
      property_type: { value: '52988006', scheme: 'SCT', meaning: 'Lesion' },
    },
    geometry: {
      grid_order: 'source_volume_frame_row_column',
      dimensions,
      pixel_spacing_mm: [pixelSpacing[0], pixelSpacing[1]],
      projected_slice_spacing_mm: sliceSpacingMm,
      row_direction: rowDirection,
      column_direction: columnDirection,
      normal_direction: normalDirection,
      voxel_volume_mm3: stats.voxelVolumeMm3,
      geometry_matches_source: true,
      resampled: false,
    },
    measurement: {
      status: 'computed_unreviewed',
      method: 'binary_voxel_count_times_native_voxel_determinant',
      foreground_voxel_count: stats.foregroundVoxels,
      volume_mm3: stats.volumeMm3,
      volume_ml: stats.volumeMl,
      mask_pixel_sha256: await sha256Hex(mask),
      boundary_uncertainty: 'not_quantified',
    },
    files: {
      dicom_seg: {
        filename: 'segmentation.dcm',
        bytes: dicomSegBytes.byteLength,
        sha256: await sha256Hex(dicomSegBytes),
      },
    },
    review: { status: 'unreviewed' },
    permitted_uses: {
      source_overlay: true,
      mask_overlay: true,
      exact_timepoint_volume: 'computed_unreviewed_only',
      longitudinal_link: false,
      percent_change: false,
      response_classification: false,
      diagnosis: false,
      clinical_conclusion: false,
    },
    limitations: [
      'The painted boundary, lesion identity, and target definition are unreviewed.',
      'The computed volume is native-grid geometry arithmetic, not a diagnosis.',
      'This artifact does not establish biological tumor burden or tissue type.',
      'This artifact cannot classify treatment response, progression, stability, or recurrence.',
      'Acquisition and boundary differences can change a future measurement.',
      'A qualified clinician must inspect the complete boundary on the original source images before considering the result; review alone does not establish clinical validation.',
    ],
  };
  const evidenceBytes = strToU8(`${JSON.stringify(evidence, null, 2)}\n`);
  const readme = strToU8(
    [
      'DICOM Guide local lesion ROI volume evidence',
      '',
      'SENSITIVE PATIENT-IDENTIFIABLE DATA. KEEP LOCAL.',
      'This is a manually painted, unreviewed region on one native MR or CT source grid.',
      'It is not a diagnosis, tumor identity, treatment-response result, or clinical conclusion.',
      '',
      'Validate against the exact local source directory:',
      "  dicom-guide validate-lesion-volume lesion-volume.zip '/path/to/DICOM-root'",
      '',
    ].join('\n'),
  );
  return {
    filename: `dicom-guide-lesion-volume-${artifactId.slice(4, 12)}.zip`,
    bytes: zipSync(
      {
        'evidence.json': [evidenceBytes, { level: 6 }],
        'segmentation.dcm': [dicomSegBytes, { level: 0 }],
        'README.txt': [readme, { level: 6 }],
      },
      { level: 6 },
    ),
    evidence,
  };
};
