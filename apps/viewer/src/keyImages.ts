import { strToU8, zipSync } from 'fflate';
import type { PatientOrientationLabels } from './dicom';
import type { MeasurementEvidencePacket } from './measurements';

export type KeyImagePresentation = {
  voi_range?: { lower: number; upper: number };
  invert?: boolean;
  zoom?: number;
  pan?: [number, number];
};

export type KeyImageEvidencePacket = {
  schema_version: '2.0.0';
  created_at: string;
  review_status: 'unreviewed';
  artifact_type: 'derived_display_key_image';
  source: {
    study_id: string;
    series_id: string;
    instance_id: string;
    patient_context_id: string;
    frame_of_reference_id?: string;
    modality: string;
    acquisition_date?: string;
    series_description: string;
    instance_number: number;
  };
  display: {
    viewport_role: 'baseline' | 'followup';
    stack_position: number;
    stack_count: number;
    source_kind: 'browser-folder' | 'loopback-service';
    viewport_width_px: number;
    viewport_height_px: number;
    patient_orientation?: PatientOrientationLabels;
    presentation: KeyImagePresentation;
  };
  image: {
    filename: 'key-image.png';
    mime_type: 'image/png';
    width_px: number;
    height_px: number;
    sha256: string;
  };
  measurement_evidence: {
    filename: 'measurements.json';
    schema_version: '3.0.0';
    measurement_count: number;
    tracking_ids: string[];
    sha256: string;
  };
  implementation: {
    name: 'ScanView key-image exporter';
    version: '0.2.0';
    renderer: 'Cornerstone3D 5.8.2';
  };
  limitations: string[];
};

export type ConsultationSelectionSlot = 'view_a' | 'view_b';

export const CONSULTATION_KEY_IMAGE_IMPLEMENTATION = {
  name: 'ScanView consultation key-image normalizer',
  version: '0.1.0',
  renderer: 'Cornerstone3D 5.8.2',
  source_key_image_schema: '2.0.0',
} as const;

export const CONSULTATION_KEY_IMAGE_LIMITATIONS = [
  'This PNG is an unreviewed derived display capture for source-image discussion only; original DICOM remains authoritative.',
  'The packet-local view slot does not establish chronology, lesion matching, diagnosis, or treatment response.',
  'Rendered pixels and burned-in text may identify the patient; this evidence is sensitive and not deidentified.',
] as const;

export type ConsultationKeyImageEvidencePacket = {
  schema_version: '1.0.0';
  created_at: string;
  review_status: 'unreviewed';
  artifact_type: 'derived_display_consultation_key_image';
  source: KeyImageEvidencePacket['source'];
  display: Omit<KeyImageEvidencePacket['display'], 'viewport_role'> & {
    selection_slot: ConsultationSelectionSlot;
  };
  image: KeyImageEvidencePacket['image'];
  measurement_evidence: KeyImageEvidencePacket['measurement_evidence'];
  implementation: typeof CONSULTATION_KEY_IMAGE_IMPLEMENTATION;
  limitations: [...typeof CONSULTATION_KEY_IMAGE_LIMITATIONS];
};

type BuildPacketInput = {
  createdAt: string;
  source: KeyImageEvidencePacket['source'];
  display: KeyImageEvidencePacket['display'];
  imageWidth: number;
  imageHeight: number;
  pngBytes: Uint8Array;
  measurementPacket: MeasurementEvidencePacket;
  measurementBytes: Uint8Array;
};

type BuildConsultationPacketInput = Omit<BuildPacketInput, 'display'> & {
  display: ConsultationKeyImageEvidencePacket['display'];
};

export type KeyImageArchiveInput = {
  viewportCanvas: HTMLCanvasElement;
  annotationSvg?: SVGSVGElement;
  orientationLabels?: PatientOrientationLabels;
  viewportRole: 'baseline' | 'followup';
  source: KeyImageEvidencePacket['source'];
  display: Omit<
    KeyImageEvidencePacket['display'],
    'viewport_role' | 'viewport_width_px' | 'viewport_height_px' | 'patient_orientation'
  >;
  measurementPacket: MeasurementEvidencePacket;
  createdAt?: string;
};

export type KeyImageArchive = {
  filename: string;
  packet: KeyImageEvidencePacket;
  bytes: Uint8Array;
};

export type ConsultationKeyImageArchiveInput = Omit<
  KeyImageArchiveInput,
  'viewportRole'
> & {
  selectionSlot: ConsultationSelectionSlot;
};

export type ConsultationKeyImageArchive = {
  filename: string;
  packet: ConsultationKeyImageEvidencePacket;
  bytes: Uint8Array;
};

const sha256Hex = async (bytes: Uint8Array): Promise<string> => {
  const digest = await crypto.subtle.digest('SHA-256', bytes.slice().buffer);
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, '0'))
    .join('');
};

const canvasToPngBytes = (canvas: HTMLCanvasElement): Promise<Uint8Array> =>
  new Promise((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (!blob) {
        reject(new Error('The browser could not encode the key image.'));
        return;
      }
      void blob.arrayBuffer().then((buffer) => resolve(new Uint8Array(buffer)), reject);
    }, 'image/png');
  });

const drawSvgLayer = async (
  context: CanvasRenderingContext2D,
  svg: SVGSVGElement | undefined,
  outputWidth: number,
  outputHeight: number,
): Promise<void> => {
  if (!svg) return;
  const bounds = svg.getBoundingClientRect();
  if (bounds.width <= 0 || bounds.height <= 0) return;
  const clone = svg.cloneNode(true) as SVGSVGElement;
  clone.setAttribute('width', String(bounds.width));
  clone.setAttribute('height', String(bounds.height));
  clone.setAttribute('viewBox', `0 0 ${bounds.width} ${bounds.height}`);
  clone.style.width = `${bounds.width}px`;
  clone.style.height = `${bounds.height}px`;
  const blob = new Blob([new XMLSerializer().serializeToString(clone)], {
    type: 'image/svg+xml;charset=utf-8',
  });
  const url = URL.createObjectURL(blob);
  try {
    const image = new Image();
    await new Promise<void>((resolve, reject) => {
      image.onload = () => resolve();
      image.onerror = () => reject(new Error('The measurement overlay could not be captured.'));
      image.src = url;
    });
    context.drawImage(image, 0, 0, outputWidth, outputHeight);
  } finally {
    URL.revokeObjectURL(url);
  }
};

const drawLabel = (
  context: CanvasRenderingContext2D,
  value: string,
  x: number,
  y: number,
  align: CanvasTextAlign,
): void => {
  context.textAlign = align;
  context.strokeText(value, x, y);
  context.fillText(value, x, y);
};

const composeKeyImage = async (
  sourceCanvas: HTMLCanvasElement,
  annotationSvg: SVGSVGElement | undefined,
  orientationLabels: PatientOrientationLabels | undefined,
  footer:
    | { kind: 'longitudinal'; viewportRole: 'baseline' | 'followup' }
    | { kind: 'consultation'; selectionSlot: ConsultationSelectionSlot },
  stackPosition: number,
  stackCount: number,
): Promise<HTMLCanvasElement> => {
  if (sourceCanvas.width <= 0 || sourceCanvas.height <= 0) {
    throw new Error('The selected image has not finished rendering.');
  }
  const scale = Math.max(1, sourceCanvas.width / Math.max(1, sourceCanvas.clientWidth));
  const footerHeight = Math.max(48, Math.round(48 * scale));
  const output = document.createElement('canvas');
  output.width = sourceCanvas.width;
  output.height = sourceCanvas.height + footerHeight;
  const context = output.getContext('2d');
  if (!context) throw new Error('The browser could not create the key-image canvas.');

  context.fillStyle = '#000';
  context.fillRect(0, 0, output.width, output.height);
  context.drawImage(sourceCanvas, 0, 0, sourceCanvas.width, sourceCanvas.height);
  await drawSvgLayer(context, annotationSvg, sourceCanvas.width, sourceCanvas.height);

  if (orientationLabels) {
    const inset = 10 * scale;
    context.save();
    context.font = `600 ${Math.max(12, 12 * scale)}px ui-monospace, monospace`;
    context.fillStyle = '#fff';
    context.strokeStyle = '#000';
    context.lineWidth = Math.max(3, 3 * scale);
    context.textBaseline = 'middle';
    drawLabel(context, orientationLabels.left, inset, sourceCanvas.height / 2, 'left');
    drawLabel(
      context,
      orientationLabels.right,
      sourceCanvas.width - inset,
      sourceCanvas.height / 2,
      'right',
    );
    context.textBaseline = 'top';
    drawLabel(context, orientationLabels.top, sourceCanvas.width / 2, inset, 'center');
    context.textBaseline = 'bottom';
    drawLabel(
      context,
      orientationLabels.bottom,
      sourceCanvas.width / 2,
      sourceCanvas.height - inset,
      'center',
    );
    context.restore();
  }

  context.fillStyle = '#071411';
  context.fillRect(0, sourceCanvas.height, output.width, footerHeight);
  context.fillStyle = '#e7f3ef';
  context.textAlign = 'center';
  context.textBaseline = 'middle';
  context.font = `600 ${Math.max(10, 11 * scale)}px ui-monospace, monospace`;
  context.fillText(
    footer.kind === 'consultation'
      ? 'UNREVIEWED · CONSULTATION REFERENCE VIEW · NOT FOR DIAGNOSIS'
      : 'UNREVIEWED · DERIVED DISPLAY KEY IMAGE · NOT FOR DIAGNOSIS',
    output.width / 2,
    sourceCanvas.height + footerHeight * 0.34,
  );
  context.fillStyle = '#9bb0aa';
  context.font = `400 ${Math.max(9, 9 * scale)}px ui-monospace, monospace`;
  context.fillText(
    footer.kind === 'consultation'
      ? `${footer.selectionSlot === 'view_a' ? 'VIEW A' : 'VIEW B'} · slice ${stackPosition} / ${stackCount} · no chronology or response relationship`
      : `${footer.viewportRole.toUpperCase()} · slice ${stackPosition} / ${stackCount} · original DICOM retained separately`,
    output.width / 2,
    sourceCanvas.height + footerHeight * 0.72,
  );
  return output;
};

export const scopeMeasurementPacketToInstance = (
  packet: MeasurementEvidencePacket,
  seriesId: string,
  instanceId: string,
  createdAt: string,
): MeasurementEvidencePacket => ({
  schema_version: '3.0.0',
  created_at: createdAt,
  review_status: 'unreviewed',
  measurements: packet.measurements.filter(
    (measurement) =>
      measurement.source.series_id === seriesId && measurement.source.instance_id === instanceId,
  ),
  limitations: [
    ...packet.limitations,
    'This measurement packet is scoped to the single displayed source instance in the accompanying key image.',
  ],
});

export const buildKeyImageEvidencePacket = async ({
  createdAt,
  source,
  display,
  imageWidth,
  imageHeight,
  pngBytes,
  measurementPacket,
  measurementBytes,
}: BuildPacketInput): Promise<KeyImageEvidencePacket> => ({
  schema_version: '2.0.0',
  created_at: createdAt,
  review_status: 'unreviewed',
  artifact_type: 'derived_display_key_image',
  source,
  display,
  image: {
    filename: 'key-image.png',
    mime_type: 'image/png',
    width_px: imageWidth,
    height_px: imageHeight,
    sha256: await sha256Hex(pngBytes),
  },
  measurement_evidence: {
    filename: 'measurements.json',
    schema_version: '3.0.0',
    measurement_count: measurementPacket.measurements.length,
    tracking_ids: measurementPacket.measurements.map((measurement) => measurement.tracking_id),
    sha256: await sha256Hex(measurementBytes),
  },
  implementation: {
    name: 'ScanView key-image exporter',
    version: '0.2.0',
    renderer: 'Cornerstone3D 5.8.2',
  },
  limitations: [
    'This is a display-rendered, unreviewed derivative; the original DICOM instance remains authoritative.',
    'Window/level, zoom, pan, annotations, and orientation labels reflect the captured viewer state.',
    'Measurements and annotations require qualified clinician review and do not establish diagnosis or treatment response.',
    'DICOM pixels may contain burned-in identifiers or recognizable anatomy; treat the entire archive as sensitive medical data.',
  ],
});

export const buildConsultationKeyImageEvidencePacket = async ({
  createdAt,
  source,
  display,
  imageWidth,
  imageHeight,
  pngBytes,
  measurementPacket,
  measurementBytes,
}: BuildConsultationPacketInput): Promise<ConsultationKeyImageEvidencePacket> => ({
  schema_version: '1.0.0',
  created_at: createdAt,
  review_status: 'unreviewed',
  artifact_type: 'derived_display_consultation_key_image',
  source,
  display,
  image: {
    filename: 'key-image.png',
    mime_type: 'image/png',
    width_px: imageWidth,
    height_px: imageHeight,
    sha256: await sha256Hex(pngBytes),
  },
  measurement_evidence: {
    filename: 'measurements.json',
    schema_version: '3.0.0',
    measurement_count: measurementPacket.measurements.length,
    tracking_ids: measurementPacket.measurements.map((measurement) => measurement.tracking_id),
    sha256: await sha256Hex(measurementBytes),
  },
  implementation: CONSULTATION_KEY_IMAGE_IMPLEMENTATION,
  limitations: [...CONSULTATION_KEY_IMAGE_LIMITATIONS],
});

export const createKeyImageArchive = async ({
  viewportCanvas,
  annotationSvg,
  orientationLabels,
  viewportRole,
  source,
  display,
  measurementPacket,
  createdAt = new Date().toISOString(),
}: KeyImageArchiveInput): Promise<KeyImageArchive> => {
  const scopedMeasurements = scopeMeasurementPacketToInstance(
    measurementPacket,
    source.series_id,
    source.instance_id,
    createdAt,
  );
  const measurementBytes = strToU8(`${JSON.stringify(scopedMeasurements, null, 2)}\n`);
  const composite = await composeKeyImage(
    viewportCanvas,
    annotationSvg,
    orientationLabels,
    { kind: 'longitudinal', viewportRole },
    display.stack_position,
    display.stack_count,
  );
  const pngBytes = await canvasToPngBytes(composite);
  const packet = await buildKeyImageEvidencePacket({
    createdAt,
    source,
    display: {
      viewport_role: viewportRole,
      ...display,
      viewport_width_px: viewportCanvas.width,
      viewport_height_px: viewportCanvas.height,
      patient_orientation: orientationLabels,
    },
    imageWidth: composite.width,
    imageHeight: composite.height,
    pngBytes,
    measurementPacket: scopedMeasurements,
    measurementBytes,
  });
  const packetBytes = strToU8(`${JSON.stringify(packet, null, 2)}\n`);
  const archive = zipSync(
    {
      'key-image.json': [packetBytes, { level: 6 }],
      'key-image.png': [pngBytes, { level: 6 }],
      'measurements.json': [measurementBytes, { level: 6 }],
    },
    { level: 6 },
  );
  const timestamp = createdAt.replace(/[-:]/g, '').replace(/\.\d{3}Z$/, 'Z');
  const filename = `scanview-key-image-${timestamp}-${viewportRole}.zip`;
  return { filename, packet, bytes: archive };
};

export const createConsultationKeyImageArchive = async ({
  viewportCanvas,
  annotationSvg,
  orientationLabels,
  selectionSlot,
  source,
  display,
  measurementPacket,
  createdAt = new Date().toISOString(),
}: ConsultationKeyImageArchiveInput): Promise<ConsultationKeyImageArchive> => {
  const scopedMeasurements = scopeMeasurementPacketToInstance(
    measurementPacket,
    source.series_id,
    source.instance_id,
    createdAt,
  );
  const measurementBytes = strToU8(`${JSON.stringify(scopedMeasurements, null, 2)}\n`);
  const composite = await composeKeyImage(
    viewportCanvas,
    annotationSvg,
    orientationLabels,
    { kind: 'consultation', selectionSlot },
    display.stack_position,
    display.stack_count,
  );
  const pngBytes = await canvasToPngBytes(composite);
  const packet = await buildConsultationKeyImageEvidencePacket({
    createdAt,
    source,
    display: {
      selection_slot: selectionSlot,
      ...display,
      viewport_width_px: viewportCanvas.width,
      viewport_height_px: viewportCanvas.height,
      patient_orientation: orientationLabels,
    },
    imageWidth: composite.width,
    imageHeight: composite.height,
    pngBytes,
    measurementPacket: scopedMeasurements,
    measurementBytes,
  });
  const packetBytes = strToU8(`${JSON.stringify(packet, null, 2)}\n`);
  const archive = zipSync(
    {
      'key-image.json': [packetBytes, { level: 6 }],
      'key-image.png': [pngBytes, { level: 6 }],
      'measurements.json': [measurementBytes, { level: 6 }],
    },
    { level: 6 },
  );
  const timestamp = createdAt.replace(/[-:]/g, '').replace(/\.\d{3}Z$/, 'Z');
  const slot = selectionSlot.replace('_', '-');
  return {
    filename: `scanview-consultation-key-image-${timestamp}-${slot}.zip`,
    packet,
    bytes: archive,
  };
};

export const downloadArchive = (bytes: Uint8Array, filename: string): void => {
  const archiveBuffer = bytes.buffer.slice(
    bytes.byteOffset,
    bytes.byteOffset + bytes.byteLength,
  ) as ArrayBuffer;
  const url = URL.createObjectURL(new Blob([archiveBuffer], { type: 'application/zip' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.style.display = 'none';
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
};

export const exportKeyImageArchive = async (
  input: KeyImageArchiveInput,
): Promise<KeyImageArchive> => {
  const result = await createKeyImageArchive(input);
  downloadArchive(result.bytes, result.filename);
  return result;
};
