import { strToU8, zipSync } from 'fflate';
import { downloadArchive } from './keyImages';

export const CONSULTATION_BOARD_ENDPOINT = '/v1/consultation-boards';
export const CONSULTATION_BOARD_INPUT_MEDIA_TYPE =
  'application/vnd.scanview.consultation-board-input+zip';
export const CONSULTATION_BOARD_MIN_ITEMS = 2;
export const CONSULTATION_BOARD_MAX_ITEMS = 8;
export const CONSULTATION_BOARD_MAX_LABEL_CHARACTERS = 80;
export const CONSULTATION_BOARD_MAX_ITEM_ARCHIVE_BYTES = 96 * 1024 * 1024;
export const CONSULTATION_BOARD_MAX_TRANSPORT_BYTES = 512 * 1024 * 1024;

export type ConsultationBoardInput = {
  discussionLabel: string;
  archive: Uint8Array;
};

export type ConsultationBoardArchive = {
  filename: string;
  bytes: Uint8Array;
};

export const consultationBoardLabelError = (value: string): string | undefined => {
  if (
    value !== value.trim() ||
    value.length < 1 ||
    value.length > CONSULTATION_BOARD_MAX_LABEL_CHARACTERS
  ) {
    return `Use a trimmed discussion label of 1–${CONSULTATION_BOARD_MAX_LABEL_CHARACTERS} characters.`;
  }
  if (/\p{C}/u.test(value)) {
    return 'Discussion labels cannot contain control characters.';
  }
  return undefined;
};

export const buildConsultationBoardTransport = (
  items: ConsultationBoardInput[],
): Uint8Array => {
  if (items.length < CONSULTATION_BOARD_MIN_ITEMS || items.length > CONSULTATION_BOARD_MAX_ITEMS) {
    throw new Error(
      `A consultation board requires ${CONSULTATION_BOARD_MIN_ITEMS}–${CONSULTATION_BOARD_MAX_ITEMS} selected views.`,
    );
  }
  let archiveBytes = 0;
  const manifestItems = items.map((item, index) => {
    const error = consultationBoardLabelError(item.discussionLabel);
    if (error) throw new Error(error);
    if (item.archive.byteLength === 0) {
      throw new Error(`Selected view ${index + 1} contains an empty evidence archive.`);
    }
    if (item.archive.byteLength > CONSULTATION_BOARD_MAX_ITEM_ARCHIVE_BYTES) {
      throw new Error(
        `Selected view ${index + 1} exceeds the ${CONSULTATION_BOARD_MAX_ITEM_ARCHIVE_BYTES / 1024 / 1024} MiB local archive limit.`,
      );
    }
    archiveBytes += item.archive.byteLength;
    return {
      archive: `item-${String(index + 1).padStart(2, '0')}.zip`,
      discussion_label: item.discussionLabel,
    };
  });
  if (archiveBytes > CONSULTATION_BOARD_MAX_TRANSPORT_BYTES) {
    throw new Error(
      `The selected evidence exceeds the ${CONSULTATION_BOARD_MAX_TRANSPORT_BYTES / 1024 / 1024} MiB local board limit.`,
    );
  }
  const files: Record<string, Uint8Array | [Uint8Array, { level: number }]> = {
    'board-input.json': strToU8(
      `${JSON.stringify(
        {
          schema_version: '1.0.0',
          artifact_type: 'consultation_board_input',
          items: manifestItems,
        },
        null,
        2,
      )}\n`,
    ),
  };
  items.forEach((item, index) => {
    files[`item-${String(index + 1).padStart(2, '0')}.zip`] = [
      item.archive,
      { level: 0 },
    ];
  });
  const transport = zipSync(files, { level: 0 });
  if (transport.byteLength > CONSULTATION_BOARD_MAX_TRANSPORT_BYTES) {
    throw new Error(
      `The assembled evidence exceeds the ${CONSULTATION_BOARD_MAX_TRANSPORT_BYTES / 1024 / 1024} MiB local board limit.`,
    );
  }
  return transport;
};

const responseFilename = (header: string | null): string => {
  const candidate = header?.match(/filename="?([A-Za-z0-9._-]+)"?/i)?.[1];
  return candidate?.endsWith('.zip')
    ? candidate
    : `scanview-consultation-board-${new Date().toISOString().slice(0, 10)}.zip`;
};

export const requestConsultationBoard = async (
  items: ConsultationBoardInput[],
): Promise<ConsultationBoardArchive> => {
  const transport = buildConsultationBoardTransport(items);
  const body = transport.buffer.slice(
    transport.byteOffset,
    transport.byteOffset + transport.byteLength,
  ) as ArrayBuffer;
  const response = await fetch(CONSULTATION_BOARD_ENDPOINT, {
    method: 'POST',
    cache: 'no-store',
    credentials: 'same-origin',
    headers: {
      Accept: 'application/zip',
      'Content-Type': CONSULTATION_BOARD_INPUT_MEDIA_TYPE,
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
        `The local consultation-board assembler rejected the selected views (${response.status}).`,
    );
  }
  if (response.headers.get('Content-Type')?.split(';', 1)[0] !== 'application/zip') {
    throw new Error(
      'The local consultation-board assembler returned an unsupported file type.',
    );
  }
  return {
    filename: responseFilename(response.headers.get('Content-Disposition')),
    bytes: new Uint8Array(await response.arrayBuffer()),
  };
};

export const saveConsultationBoard = async (
  items: ConsultationBoardInput[],
): Promise<ConsultationBoardArchive> => {
  const result = await requestConsultationBoard(items);
  downloadArchive(result.bytes, result.filename);
  return result;
};
