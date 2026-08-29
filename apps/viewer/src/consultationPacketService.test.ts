import { afterEach, describe, expect, it, vi } from 'vitest';
import { unzipSync } from 'fflate';

const downloadArchiveMock = vi.hoisted(() => vi.fn());

vi.mock('./keyImages', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./keyImages')>()),
  downloadArchive: downloadArchiveMock,
}));

import {
  buildConsultationPacketTransport,
  CONSULTATION_PACKET_ENDPOINT,
  CONSULTATION_PACKET_INPUT_MEDIA_TYPE,
  requestConsultationPacket,
  saveConsultationPacket,
} from './consultationPacketService';

afterEach(() => {
  vi.unstubAllGlobals();
  downloadArchiveMock.mockReset();
});

describe('local consultation-packet service', () => {
  it('wraps exactly the two neutral view archives', () => {
    const viewA = new Uint8Array([1, 2, 3]);
    const viewB = new Uint8Array([4, 5]);

    const files = unzipSync(buildConsultationPacketTransport(viewA, viewB));

    expect(Object.keys(files).sort()).toEqual(['view-a.zip', 'view-b.zip']);
    expect(files['view-a.zip']).toEqual(viewA);
    expect(files['view-b.zip']).toEqual(viewB);
  });

  it('posts only to the same-origin relative endpoint with the consultation media type', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(new Uint8Array([9, 8, 7]), {
        status: 200,
        headers: {
          'Content-Type': 'application/zip',
          'Content-Disposition':
            'attachment; filename="scanview-consultation-packet-test.zip"',
        },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const result = await requestConsultationPacket(
      new Uint8Array([1]),
      new Uint8Array([2]),
    );

    expect(CONSULTATION_PACKET_ENDPOINT).toBe('/v1/consultation-packets');
    expect(result).toEqual({
      filename: 'scanview-consultation-packet-test.zip',
      bytes: new Uint8Array([9, 8, 7]),
    });
    const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/v1/consultation-packets');
    expect(options).toMatchObject({
      method: 'POST',
      cache: 'no-store',
      credentials: 'same-origin',
      headers: {
        Accept: 'application/zip',
        'Content-Type': CONSULTATION_PACKET_INPUT_MEDIA_TYPE,
      },
    });
    expect(Object.keys(unzipSync(new Uint8Array(options.body as ArrayBuffer))).sort()).toEqual([
      'view-a.zip',
      'view-b.zip',
    ]);
  });

  it('downloads the validated consultation response with its server filename', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(new Uint8Array([7, 6, 5]), {
          status: 200,
          headers: {
            'Content-Type': 'application/zip',
            'Content-Disposition':
              'attachment; filename="scanview-consultation-packet-saved.zip"',
          },
        }),
      ),
    );

    const result = await saveConsultationPacket(
      new Uint8Array([1]),
      new Uint8Array([2]),
    );

    expect(result.filename).toBe('scanview-consultation-packet-saved.zip');
    expect(downloadArchiveMock).toHaveBeenCalledOnce();
    expect(downloadArchiveMock).toHaveBeenCalledWith(
      new Uint8Array([7, 6, 5]),
      'scanview-consultation-packet-saved.zip',
    );
  });

  it('rejects a successful response with a non-ZIP media type', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response('{}', {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    );

    await expect(
      requestConsultationPacket(new Uint8Array([1]), new Uint8Array([2])),
    ).rejects.toThrow('unsupported file type');
  });
});
