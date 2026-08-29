import { zipSync } from 'fflate';
import { downloadArchive } from './keyImages';

export const CONSULTATION_PACKET_ENDPOINT = '/v1/consultation-packets';
export const CONSULTATION_PACKET_INPUT_MEDIA_TYPE =
  'application/vnd.scanview.consultation-input+zip';

export type ConsultationPacketArchive = {
  filename: string;
  bytes: Uint8Array;
};

export const buildConsultationPacketTransport = (
  viewA: Uint8Array,
  viewB: Uint8Array,
): Uint8Array =>
  zipSync(
    {
      'view-a.zip': [viewA, { level: 0 }],
      'view-b.zip': [viewB, { level: 0 }],
    },
    { level: 0 },
  );

const responseFilename = (header: string | null): string => {
  const candidate = header?.match(/filename="?([A-Za-z0-9._-]+)"?/i)?.[1];
  return candidate?.endsWith('.zip')
    ? candidate
    : `scanview-consultation-packet-${new Date().toISOString().slice(0, 10)}.zip`;
};

export const requestConsultationPacket = async (
  viewA: Uint8Array,
  viewB: Uint8Array,
): Promise<ConsultationPacketArchive> => {
  const transport = buildConsultationPacketTransport(viewA, viewB);
  const body = transport.buffer.slice(
    transport.byteOffset,
    transport.byteOffset + transport.byteLength,
  ) as ArrayBuffer;
  const response = await fetch(CONSULTATION_PACKET_ENDPOINT, {
    method: 'POST',
    cache: 'no-store',
    credentials: 'same-origin',
    headers: {
      Accept: 'application/zip',
      'Content-Type': CONSULTATION_PACKET_INPUT_MEDIA_TYPE,
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
      detail ||
        `The local consultation-packet assembler rejected the reference views (${response.status}).`,
    );
  }
  if (response.headers.get('Content-Type')?.split(';', 1)[0] !== 'application/zip') {
    throw new Error(
      'The local consultation-packet assembler returned an unsupported file type.',
    );
  }
  return {
    filename: responseFilename(response.headers.get('Content-Disposition')),
    bytes: new Uint8Array(await response.arrayBuffer()),
  };
};

export const saveConsultationPacket = async (
  viewA: Uint8Array,
  viewB: Uint8Array,
): Promise<ConsultationPacketArchive> => {
  const result = await requestConsultationPacket(viewA, viewB);
  downloadArchive(result.bytes, result.filename);
  return result;
};
