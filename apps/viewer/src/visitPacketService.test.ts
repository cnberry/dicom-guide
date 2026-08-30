import { afterEach, describe, expect, it, vi } from 'vitest';
import { unzipSync } from 'fflate';
import {
  buildVisitPacketTransport,
  requestVisitPacket,
  VISIT_PACKET_ENDPOINT,
  VISIT_PACKET_INPUT_MEDIA_TYPE,
} from './visitPacketService';

afterEach(() => vi.unstubAllGlobals());

describe('local visit-packet service', () => {
  it('wraps exactly the two role-specific key-image archives', () => {
    const baseline = new Uint8Array([1, 2, 3]);
    const followup = new Uint8Array([4, 5]);

    const files = unzipSync(buildVisitPacketTransport(baseline, followup));

    expect(Object.keys(files).sort()).toEqual(['baseline.zip', 'followup.zip']);
    expect(files['baseline.zip']).toEqual(baseline);
    expect(files['followup.zip']).toEqual(followup);
  });

  it('posts only to the same-origin relative endpoint and accepts a local ZIP response', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(new Uint8Array([9, 8, 7]), {
        status: 200,
        headers: {
          'Content-Type': 'application/zip',
          'Content-Disposition': 'attachment; filename="dicom-guide-visit-packet-test.zip"',
        },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const result = await requestVisitPacket(new Uint8Array([1]), new Uint8Array([2]));

    expect(VISIT_PACKET_ENDPOINT).toBe('/v1/visit-packets');
    expect(result).toEqual({
      filename: 'dicom-guide-visit-packet-test.zip',
      bytes: new Uint8Array([9, 8, 7]),
    });
    const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/v1/visit-packets');
    expect(options).toMatchObject({
      method: 'POST',
      cache: 'no-store',
      credentials: 'same-origin',
      headers: {
        Accept: 'application/zip',
        'Content-Type': VISIT_PACKET_INPUT_MEDIA_TYPE,
      },
    });
    expect(Object.keys(unzipSync(new Uint8Array(options.body as ArrayBuffer))).sort()).toEqual([
      'baseline.zip',
      'followup.zip',
    ]);
  });

  it('surfaces the local assembler safety-gate detail', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: 'invalid_visit_packet_input',
            detail: 'visit packets require the same MR or CT modality at both timepoints',
          }),
          { status: 422, headers: { 'Content-Type': 'application/json' } },
        ),
      ),
    );

    await expect(
      requestVisitPacket(new Uint8Array([1]), new Uint8Array([2])),
    ).rejects.toThrow('same MR or CT modality');
  });
});
