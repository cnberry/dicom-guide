import { zipSync } from 'fflate';
import { downloadArchive } from './keyImages';

export const VISIT_PACKET_ENDPOINT = '/v1/visit-packets';
export const VISIT_PACKET_INPUT_MEDIA_TYPE = 'application/vnd.dicom-guide.visit-input+zip';

export type VisitPacketArchive = {
  filename: string;
  bytes: Uint8Array;
};

export const buildVisitPacketTransport = (
  baseline: Uint8Array,
  followup: Uint8Array,
): Uint8Array =>
  zipSync(
    {
      'baseline.zip': [baseline, { level: 0 }],
      'followup.zip': [followup, { level: 0 }],
    },
    { level: 0 },
  );

const responseFilename = (header: string | null): string => {
  const candidate = header?.match(/filename="?([A-Za-z0-9._-]+)"?/i)?.[1];
  return candidate?.endsWith('.zip')
    ? candidate
    : `dicom-guide-visit-packet-${new Date().toISOString().slice(0, 10)}.zip`;
};

export const requestVisitPacket = async (
  baseline: Uint8Array,
  followup: Uint8Array,
): Promise<VisitPacketArchive> => {
  const transport = buildVisitPacketTransport(baseline, followup);
  const body = transport.buffer.slice(
    transport.byteOffset,
    transport.byteOffset + transport.byteLength,
  ) as ArrayBuffer;
  const response = await fetch(VISIT_PACKET_ENDPOINT, {
    method: 'POST',
    cache: 'no-store',
    credentials: 'same-origin',
    headers: {
      Accept: 'application/zip',
      'Content-Type': VISIT_PACKET_INPUT_MEDIA_TYPE,
    },
    body,
  });
  if (!response.ok) {
    let detail = '';
    try {
      const value = (await response.json()) as { detail?: unknown };
      if (typeof value.detail === 'string') detail = value.detail;
    } catch {
      // The status is sufficient when the local response is not JSON.
    }
    throw new Error(
      detail || `The local visit-packet assembler rejected the pair (${response.status}).`,
    );
  }
  if (response.headers.get('Content-Type')?.split(';', 1)[0] !== 'application/zip') {
    throw new Error('The local visit-packet assembler returned an unsupported file type.');
  }
  return {
    filename: responseFilename(response.headers.get('Content-Disposition')),
    bytes: new Uint8Array(await response.arrayBuffer()),
  };
};

export const saveVisitPacket = async (
  baseline: Uint8Array,
  followup: Uint8Array,
): Promise<VisitPacketArchive> => {
  const result = await requestVisitPacket(baseline, followup);
  downloadArchive(result.bytes, result.filename);
  return result;
};
