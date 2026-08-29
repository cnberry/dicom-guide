import { gzipSync } from 'fflate';
import { describe, expect, it } from 'vitest';
import {
  composeCoveredRegistrationSlice,
  composeQaSlice,
  extractPatientSpaceBinaryMaskSlice,
  extractNrrdSlice,
  extractPatientSpaceSlice,
  landmarkResidual,
  lpsToPatientSlicePixel,
  lpsToVoxel,
  parseNrrd,
  planeOrientationLabels,
  planeLength,
  patientSlicePixelToLps,
  patientSpacePlaneLength,
  patientSpaceSliceIndexForLps,
  sampleNrrdAtLps,
  slicePointToVoxel,
  validateBinaryCoverageVolume,
  voxelToPhysical,
} from './nrrd';

type NrrdOptions = {
  encoding?: 'raw' | 'gzip';
  sizes?: [number, number, number];
  space?: 'left-posterior-superior' | 'right-anterior-superior';
  directions?: [[number, number, number], [number, number, number], [number, number, number]];
  origin?: [number, number, number];
  values?: number[];
  scalarType?: 'short' | 'uint8';
};

const nrrd = ({
  encoding = 'raw',
  sizes = [2, 2, 2],
  space = 'left-posterior-superior',
  directions = [
    [2, 0, 0],
    [0, 3, 0],
    [0, 0, 4],
  ],
  origin = [10, 20, 30],
  values,
  scalarType = 'short',
}: NrrdOptions = {}): ArrayBuffer => {
  const voxelCount = sizes[0] * sizes[1] * sizes[2];
  const payload = new Uint8Array(voxelCount * (scalarType === 'short' ? 2 : 1));
  if (scalarType === 'short') {
    const view = new DataView(payload.buffer);
    for (let index = 0; index < voxelCount; index += 1) {
      view.setInt16(index * 2, values?.[index] ?? index, true);
    }
  } else {
    for (let index = 0; index < voxelCount; index += 1) {
      payload[index] = values?.[index] ?? index % 2;
    }
  }
  const encoded = encoding === 'gzip' ? gzipSync(payload) : payload;
  const vector = (value: [number, number, number]) => `(${value.join(',')})`;
  const header = new TextEncoder().encode(
    `NRRD0005\n` +
      `type: ${scalarType}\n` +
      `dimension: 3\n` +
      `sizes: ${sizes.join(' ')}\n` +
      `space: ${space}\n` +
      `space directions: ${directions.map(vector).join(' ')}\n` +
      `space origin: ${vector(origin)}\n` +
      (scalarType === 'short' ? `endian: little\n` : '') +
      `encoding: ${encoding}\n\n`,
  );
  const result = new Uint8Array(header.byteLength + encoded.byteLength);
  result.set(header);
  result.set(encoded, header.byteLength);
  return result.buffer;
};

describe('local NRRD QA parsing and rendering', () => {
  it.each(['raw', 'gzip'] as const)('parses bounded %s volumes', (encoding) => {
    const volume = parseNrrd(nrrd({ encoding }));
    expect(volume.sizes).toEqual([2, 2, 2]);
    expect(volume.space).toBe('left-posterior-superior');
    expect(volume.scalarType).toBe('int16');
    expect(volume.sampledRange).toEqual([0, 7]);
    expect(planeLength(volume, 'axial')).toBe(2);
    expect(planeLength(volume, 'coronal')).toBe(2);
    expect(planeLength(volume, 'sagittal')).toBe(2);

    const slice = extractNrrdSlice(volume, 'axial', 1, [0, 7]);
    expect([slice.width, slice.height]).toEqual([2, 2]);
    expect(Array.from(slice.pixels)).toEqual([146, 182, 219, 255]);
    expect(slicePointToVoxel(volume, 'coronal', 1, 1, 0)).toEqual([1, 1, 0]);
    expect(voxelToPhysical(volume, [1, 1, 1])).toEqual([12, 23, 34]);
    expect(planeOrientationLabels(volume, 'axial')).toEqual({
      left: 'R',
      right: 'L',
      top: 'A',
      bottom: 'P',
    });
  });

  it.each(['raw', 'gzip'] as const)(
    'validates and reformats binary uint8 sampling-support masks with nearest-neighbor %s data',
    (encoding) => {
      const mask = parseNrrd(
        nrrd({
          encoding,
          scalarType: 'uint8',
          origin: [0, 0, 0],
          directions: [
            [1, 0, 0],
            [0, 1, 0],
            [0, 0, 1],
          ],
          values: [1, 0, 0, 1, 0, 1, 1, 0],
        }),
      );
      expect(() => validateBinaryCoverageVolume(mask)).not.toThrow();
      for (const plane of ['axial', 'coronal', 'sagittal'] as const) {
        const slice = extractPatientSpaceBinaryMaskSlice(mask, plane, 0);
        expect([slice.width, slice.height]).toEqual([2, 2]);
        expect(slice.pixels.every((value) => value === 0 || value === 1)).toBe(true);
      }
      expect(
        Array.from(extractPatientSpaceBinaryMaskSlice(mask, 'axial', 0).pixels),
      ).toEqual([1, 0, 0, 1]);
    },
  );

  it('rejects non-binary, empty, and non-uint8 sampling-support masks', () => {
    const invalidBinary = parseNrrd(
      nrrd({ scalarType: 'uint8', values: [1, 0, 2, 0, 0, 0, 0, 0] }),
    );
    expect(() => validateBinaryCoverageVolume(invalidBinary)).toThrow(/only binary/i);
    const empty = parseNrrd(
      nrrd({ scalarType: 'uint8', values: Array.from({ length: 8 }, () => 0) }),
    );
    expect(() => validateBinaryCoverageVolume(empty)).toThrow(/no covered/i);
    expect(() => validateBinaryCoverageVolume(parseNrrd(nrrd()))).toThrow(/uint8/i);
  });

  it('uses zero outside the binary mask volume during oblique patient-space reformatting', () => {
    const cosine = Math.SQRT1_2;
    const mask = parseNrrd(
      nrrd({
        scalarType: 'uint8',
        sizes: [3, 3, 3],
        origin: [0, 0, 0],
        directions: [
          [cosine, cosine, 0],
          [-cosine, cosine, 0],
          [0, 0, 1],
        ],
        values: Array.from({ length: 27 }, () => 1),
      }),
    );
    validateBinaryCoverageVolume(mask);
    const slice = extractPatientSpaceBinaryMaskSlice(mask, 'axial', 1, {
      targetSpacingMm: 1,
    });
    expect(Array.from(slice.pixels)).toContain(0);
    expect(Array.from(slice.pixels)).toContain(1);
  });

  it('refuses detached, truncated, and unsupported patient-space volumes', () => {
    const truncated = nrrd().slice(0, -2);
    expect(() => parseNrrd(truncated)).toThrow(/payload length/i);

    const detached = new TextEncoder().encode(
      'NRRD0005\ntype: uchar\ndimension: 3\nsizes: 1 1 1\n' +
        'space: left-posterior-superior\nspace directions: (1,0,0) (0,1,0) (0,0,1)\n' +
        'space origin: (0,0,0)\nencoding: raw\ndata file: pixels.raw\n\n\0',
    );
    expect(() => parseNrrd(detached.buffer)).toThrow(/detached/i);

    const unknownSpace = new Uint8Array(nrrd());
    const text = new TextDecoder().decode(unknownSpace).replace(
      'left-posterior-superior',
      'scanner-xyz-unknown_____',
    );
    expect(() => parseNrrd(new TextEncoder().encode(text).buffer)).toThrow(/patient-space/i);
  });

  it('normalizes RAS affine points to LPS and inverts the mapping', () => {
    const volume = parseNrrd(
      nrrd({
        space: 'right-anterior-superior',
        directions: [
          [2, 0, 0],
          [0, 3, 0],
          [0, 0, 4],
        ],
      }),
    );

    const lps = voxelToPhysical(volume, [1, 1, 1]);
    expect(lps).toEqual([-12, -23, 34]);
    expect(lpsToVoxel(volume, lps)).toEqual([1, 1, 1]);
  });

  it('rejects singular affines and browser-unsafe voxel counts before allocation', () => {
    expect(() =>
      parseNrrd(
        nrrd({
          directions: [
            [1, 0, 0],
            [0, 1, 0],
            [1, 1, 0],
          ],
        }),
      ),
    ).toThrow(/invertible/i);

    const oversized = new TextEncoder().encode(
      'NRRD0005\n' +
        'type: uchar\n' +
        'dimension: 3\n' +
        `sizes: ${128 * 1024 * 1024 + 1} 1 1\n` +
        'space: left-posterior-superior\n' +
        'space directions: (1,0,0) (0,1,0) (0,0,1)\n' +
        'space origin: (0,0,0)\n' +
        'encoding: raw\n\n\0',
    );
    expect(() => parseNrrd(oversized.buffer)).toThrow(/voxel count/i);
  });

  it.each(['raw', 'gzip'] as const)(
    'enforces a caller-supplied decoded-byte budget before decoding %s payloads',
    (encoding) => {
      const encoded = nrrd({ encoding });
      expect(() => parseNrrd(encoded, { maxDecodedBytes: 15 })).toThrow(
        /decoded payload exceeds/i,
      );
      expect(parseNrrd(encoded, { maxDecodedBytes: 16 }).payload.byteLength).toBe(16);
      expect(() => parseNrrd(encoded, { maxDecodedBytes: 0 })).toThrow(
        /decoded payload limit is invalid/i,
      );
    },
  );

  it('orthogonally reformats oblique geometry with trilinear LPS sampling', () => {
    const cosine = Math.SQRT1_2;
    const values = Array.from({ length: 27 }, (_, index) => {
      const x = index % 3;
      const y = Math.floor(index / 3) % 3;
      const z = Math.floor(index / 9);
      return x + 10 * y + 100 * z;
    });
    const volume = parseNrrd(
      nrrd({
        sizes: [3, 3, 3],
        directions: [
          [cosine, cosine, 0],
          [-cosine, cosine, 0],
          [0, 0, 2],
        ],
        origin: [7, 11, 13],
        values,
      }),
    );
    const halfVoxelLps = voxelToPhysical(volume, [0.5, 0.5, 0.5]);
    expect(sampleNrrdAtLps(volume, halfVoxelLps)).toBeCloseTo(55.5, 8);
    expect(sampleNrrdAtLps(volume, [1000, 1000, 1000])).toBeUndefined();

    const centerLps = voxelToPhysical(volume, [1, 1, 1]);
    const index = patientSpaceSliceIndexForLps(volume, 'axial', centerLps);
    const slice = extractPatientSpaceSlice(volume, 'axial', index, [0, 222], {
      targetSpacingMm: 1,
    });
    const projected = lpsToPatientSlicePixel(slice.mapping, centerLps);
    expect(projected.distanceFromPlaneMm).toBeCloseTo(0, 8);
    patientSlicePixelToLps(slice.mapping, projected.horizontal, projected.vertical).forEach(
      (value, axis) => expect(value).toBeCloseTo(centerLps[axis], 8),
    );
  });

  it('handles permuted directions and preserves physical aspect for anisotropic voxels', () => {
    const permuted = parseNrrd(
      nrrd({
        sizes: [3, 3, 3],
        origin: [0, 0, 0],
        directions: [
          [0, 0, 2],
          [3, 0, 0],
          [0, 4, 0],
        ],
      }),
    );
    const center = voxelToPhysical(permuted, [1, 1, 1]);
    for (const plane of ['axial', 'coronal', 'sagittal'] as const) {
      const index = patientSpaceSliceIndexForLps(permuted, plane, center);
      const slice = extractPatientSpaceSlice(permuted, plane, index, undefined, {
        targetSpacingMm: 2,
      });
      const pixel = lpsToPatientSlicePixel(slice.mapping, center);
      expect(Math.abs(pixel.distanceFromPlaneMm)).toBeLessThanOrEqual(
        slice.mapping.sliceSpacingMm / 2,
      );
      const projectedToPlane = patientSlicePixelToLps(
        slice.mapping,
        pixel.horizontal,
        pixel.vertical,
      );
      projectedToPlane.forEach((value, axis) =>
        expect(
          value + slice.mapping.normalDirectionLps[axis] * pixel.distanceFromPlaneMm,
        ).toBeCloseTo(center[axis], 8),
      );
    }

    const anisotropic = parseNrrd(
      nrrd({
        sizes: [3, 3, 3],
        origin: [0, 0, 0],
        directions: [
          [2, 0, 0],
          [0, 3, 0],
          [0, 0, 5],
        ],
      }),
    );
    const axial = extractPatientSpaceSlice(anisotropic, 'axial', 0, undefined, {
      targetSpacingMm: 2,
    });
    const coronal = extractPatientSpaceSlice(anisotropic, 'coronal', 0, undefined, {
      targetSpacingMm: 2,
    });
    expect([axial.width, axial.height, ...axial.mapping.pixelSpacingMm]).toEqual([3, 4, 2, 2]);
    expect([coronal.width, coronal.height, ...coronal.mapping.pixelSpacingMm]).toEqual([
      3,
      6,
      2,
      2,
    ]);
    expect(patientSpacePlaneLength(anisotropic, 'sagittal', { targetSpacingMm: 2 })).toBe(3);
  });

  it('maps through-plane landmarks without discarding their normal residual', () => {
    const volume = parseNrrd(
      nrrd({
        sizes: [3, 3, 3],
        origin: [0, 0, 0],
        directions: [
          [1, 0, 0],
          [0, 1, 0],
          [0, 0, 1],
        ],
      }),
    );
    const mapping = extractPatientSpaceSlice(volume, 'axial', 1).mapping;
    const onPlane = patientSlicePixelToLps(mapping, 1, 1);
    const offPlane: [number, number, number] = [onPlane[0], onPlane[1], onPlane[2] + 3];
    expect(lpsToPatientSlicePixel(mapping, offPlane)).toEqual({
      horizontal: 1,
      vertical: 1,
      distanceFromPlaneMm: 3,
    });
  });

  it('uses standard patient-space orientation labels in every reformat plane', () => {
    const volume = parseNrrd(nrrd());
    expect(planeOrientationLabels(volume, 'axial')).toEqual({
      left: 'R',
      right: 'L',
      top: 'A',
      bottom: 'P',
    });
    expect(planeOrientationLabels(volume, 'coronal')).toEqual({
      left: 'R',
      right: 'L',
      top: 'S',
      bottom: 'I',
    });
    expect(planeOrientationLabels(volume, 'sagittal')).toEqual({
      left: 'A',
      right: 'P',
      top: 'S',
      bottom: 'I',
    });
  });

  it('creates deterministic QA composites and landmark residuals', () => {
    const fixed = { width: 2, height: 2, pixels: new Uint8ClampedArray([0, 64, 128, 255]) };
    const moving = {
      width: 2,
      height: 2,
      pixels: new Uint8ClampedArray([255, 128, 64, 0]),
    };
    const checker = composeQaSlice(fixed, moving, 'checkerboard', {
      opacity: 0.5,
      checkerSize: 1,
      edgeThreshold: 80,
      swipePosition: 0.5,
    });
    expect([checker.width, checker.height, checker.data.length]).toEqual([2, 2, 16]);
    expect(Array.from(checker.data.slice(0, 4))).toEqual([0, 0, 0, 255]);
    expect(landmarkResidual([0, 0, 0], [3, 4, 0])).toBe(5);
  });

  it('never emits registered pixels where the required coverage mask is zero', () => {
    const fixed = {
      width: 2,
      height: 2,
      pixels: new Uint8ClampedArray([10, 20, 30, 40]),
    };
    const registered = {
      width: 2,
      height: 2,
      pixels: new Uint8ClampedArray([100, 110, 120, 130]),
    };
    const coverage = {
      width: 2,
      height: 2,
      pixels: new Uint8Array([1, 0, 1, 0]),
    };
    const opacity = composeCoveredRegistrationSlice(
      fixed,
      registered,
      coverage,
      'opacity',
      { opacity: 1, swipePosition: 0.5 },
    );
    expect(Array.from(opacity.data.slice(0, 8))).toEqual([
      90, 100, 100, 255,
      20, 20, 20, 255,
    ]);
    expect(Array.from(opacity.data.slice(12, 16))).toEqual([40, 40, 40, 255]);

    const swipe = composeCoveredRegistrationSlice(
      fixed,
      registered,
      coverage,
      'swipe',
      { opacity: 0.5, swipePosition: 0 },
    );
    expect(Array.from(swipe.data)).toEqual([
      100, 100, 100, 255,
      20, 20, 20, 255,
      120, 120, 120, 255,
      40, 40, 40, 255,
    ]);
    expect(() =>
      composeCoveredRegistrationSlice(
        fixed,
        registered,
        { ...coverage, width: 1 },
        'opacity',
        { opacity: 0.5, swipePosition: 0.5 },
      ),
    ).toThrow(/matched slice dimensions/i);
    expect(() =>
      composeCoveredRegistrationSlice(
        fixed,
        registered,
        coverage,
        'checkerboard' as 'opacity',
        { opacity: 0.5, swipePosition: 0.5 },
      ),
    ).toThrow(/only opacity or swipe/i);
  });
});
