import { afterEach, describe, expect, it, vi } from 'vitest';
import { unzipSync } from 'fflate';

const downloadArchiveMock = vi.hoisted(() => vi.fn());

vi.mock('./keyImages', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./keyImages')>()),
  downloadArchive: downloadArchiveMock,
}));

import {
  buildConsultationBoardTransport,
  CONSULTATION_BOARD_ENDPOINT,
  CONSULTATION_BOARD_INPUT_MEDIA_TYPE,
  consultationBoardLabelError,
  requestConsultationBoard,
  saveConsultationBoard,
} from './consultationBoardService';

const inputs = [
  { discussionLabel: 'MRI reference', archive: new Uint8Array([1, 2, 3]) },
  { discussionLabel: 'CT reference', archive: new Uint8Array([4, 5]) },
  { discussionLabel: 'Additional MRI view', archive: new Uint8Array([6]) },
];

afterEach(() => {
  vi.unstubAllGlobals();
  downloadArchiveMock.mockReset();
});

describe('local consultation-board service', () => {
  it('wraps an ordered manifest and exactly 2-8 neutral key-image archives', () => {
    const files = unzipSync(buildConsultationBoardTransport(inputs));

    expect(Object.keys(files).sort()).toEqual([
      'board-input.json',
      'item-01.zip',
      'item-02.zip',
      'item-03.zip',
    ]);
    expect(JSON.parse(new TextDecoder().decode(files['board-input.json']))).toEqual({
      schema_version: '1.0.0',
      artifact_type: 'consultation_board_input',
      items: [
        { archive: 'item-01.zip', discussion_label: 'MRI reference' },
        { archive: 'item-02.zip', discussion_label: 'CT reference' },
        { archive: 'item-03.zip', discussion_label: 'Additional MRI view' },
      ],
    });
    expect(files['item-02.zip']).toEqual(inputs[1].archive);
  });

  it('rejects unsafe labels and item counts before transport', () => {
    expect(consultationBoardLabelError(' leading')).toContain('trimmed');
    expect(consultationBoardLabelError('line\nbreak')).toContain('control');
    expect(consultationBoardLabelError('hidden\u200djoiner')).toContain('control');
    expect(() => buildConsultationBoardTransport(inputs.slice(0, 1))).toThrow('2–8');
    expect(() =>
      buildConsultationBoardTransport(
        Array.from({ length: 9 }, (_, index) => ({
          discussionLabel: `View ${index + 1}`,
          archive: new Uint8Array([index]),
        })),
      ),
    ).toThrow('2–8');
    expect(() =>
      buildConsultationBoardTransport([
        inputs[0],
        { discussionLabel: 'Empty capture', archive: new Uint8Array() },
      ]),
    ).toThrow('empty evidence archive');
  });

  it('posts only to the same-origin relative board endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(new Uint8Array([9, 8, 7]), {
        status: 200,
        headers: {
          'Content-Type': 'application/zip',
          'Content-Disposition':
            'attachment; filename="dicom-guide-consultation-board-test.zip"',
        },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const result = await requestConsultationBoard(inputs.slice(0, 2));

    expect(CONSULTATION_BOARD_ENDPOINT).toBe('/v1/consultation-boards');
    expect(result.filename).toBe('dicom-guide-consultation-board-test.zip');
    const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/v1/consultation-boards');
    expect(options).toMatchObject({
      method: 'POST',
      cache: 'no-store',
      credentials: 'same-origin',
      headers: {
        Accept: 'application/zip',
        'Content-Type': CONSULTATION_BOARD_INPUT_MEDIA_TYPE,
      },
    });
  });

  it('downloads the validated board response with its server filename', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(new Uint8Array([7, 6, 5]), {
          status: 200,
          headers: {
            'Content-Type': 'application/zip',
            'Content-Disposition':
              'attachment; filename="dicom-guide-consultation-board-saved.zip"',
          },
        }),
      ),
    );

    const result = await saveConsultationBoard(inputs.slice(0, 2));

    expect(result.filename).toBe('dicom-guide-consultation-board-saved.zip');
    expect(downloadArchiveMock).toHaveBeenCalledWith(
      new Uint8Array([7, 6, 5]),
      'dicom-guide-consultation-board-saved.zip',
    );
  });

  it('rejects a successful non-ZIP response', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response('{}', {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    );

    await expect(requestConsultationBoard(inputs.slice(0, 2))).rejects.toThrow(
      'unsupported file type',
    );
  });
});
