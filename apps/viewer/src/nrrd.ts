import { gunzipSync } from 'fflate';

export type NrrdPlane = 'axial' | 'coronal' | 'sagittal';
export type NrrdScalarType =
  | 'int8'
  | 'uint8'
  | 'int16'
  | 'uint16'
  | 'int32'
  | 'uint32'
  | 'float32'
  | 'float64';

export type NrrdVolume = {
  sizes: [number, number, number];
  space: 'left-posterior-superior' | 'right-anterior-superior';
  spaceDirections: [
    [number, number, number],
    [number, number, number],
    [number, number, number],
  ];
  spaceOrigin: [number, number, number];
  scalarType: NrrdScalarType;
  littleEndian: boolean;
  payload: Uint8Array;
  dataView: DataView;
  bytesPerVoxel: number;
  sampledRange: [number, number];
  suggestedWindow: [number, number];
};

export type NrrdSlice = {
  width: number;
  height: number;
  pixels: Uint8ClampedArray;
};

export type LpsPoint = [number, number, number];

export type PatientSpaceSliceMapping = {
  plane: NrrdPlane;
  sliceIndex: number;
  sliceCount: number;
  sliceSpacingMm: number;
  pixelSpacingMm: [number, number];
  originLps: LpsPoint;
  horizontalDirectionLps: LpsPoint;
  verticalDirectionLps: LpsPoint;
  normalDirectionLps: LpsPoint;
};

export type PatientSpaceSlice = NrrdSlice & {
  mapping: PatientSpaceSliceMapping;
};

export type PatientSpacePixelProjection = {
  horizontal: number;
  vertical: number;
  distanceFromPlaneMm: number;
};

export type PatientSpaceReformatOptions = {
  targetSpacingMm?: number;
  maxDimension?: number;
  maxPixels?: number;
};

export type QaCompositeSlice = {
  width: number;
  height: number;
  data: Uint8ClampedArray;
};

export type QaCompositeMode = 'opacity' | 'checkerboard' | 'edges' | 'swipe';
export type PlaneOrientationLabels = {
  left: string;
  right: string;
  top: string;
  bottom: string;
};

const MAX_HEADER_BYTES = 1024 * 1024;
const MAX_DECODED_BYTES = 384 * 1024 * 1024;
const MAX_VOXELS = 128 * 1024 * 1024;
const MAX_PATIENT_SLICE_DIMENSION = 4096;
const MAX_PATIENT_SLICE_PIXELS = 16 * 1024 * 1024;
const MAX_PATIENT_SLICE_COUNT = 4096;
const MATRIX_RELATIVE_EPSILON = 1e-10;

const scalarTypes: Record<
  string,
  { type: NrrdScalarType; bytes: number }
> = {
  'signed char': { type: 'int8', bytes: 1 },
  int8: { type: 'int8', bytes: 1 },
  int8_t: { type: 'int8', bytes: 1 },
  uchar: { type: 'uint8', bytes: 1 },
  'unsigned char': { type: 'uint8', bytes: 1 },
  uint8: { type: 'uint8', bytes: 1 },
  uint8_t: { type: 'uint8', bytes: 1 },
  short: { type: 'int16', bytes: 2 },
  'short int': { type: 'int16', bytes: 2 },
  'signed short': { type: 'int16', bytes: 2 },
  int16: { type: 'int16', bytes: 2 },
  int16_t: { type: 'int16', bytes: 2 },
  ushort: { type: 'uint16', bytes: 2 },
  'unsigned short': { type: 'uint16', bytes: 2 },
  uint16: { type: 'uint16', bytes: 2 },
  uint16_t: { type: 'uint16', bytes: 2 },
  int: { type: 'int32', bytes: 4 },
  'signed int': { type: 'int32', bytes: 4 },
  int32: { type: 'int32', bytes: 4 },
  int32_t: { type: 'int32', bytes: 4 },
  uint: { type: 'uint32', bytes: 4 },
  'unsigned int': { type: 'uint32', bytes: 4 },
  uint32: { type: 'uint32', bytes: 4 },
  uint32_t: { type: 'uint32', bytes: 4 },
  float: { type: 'float32', bytes: 4 },
  double: { type: 'float64', bytes: 8 },
};

const parseVector = (value: string, label: string): [number, number, number] => {
  const values = value
    .trim()
    .replace(/^\(/, '')
    .replace(/\)$/, '')
    .split(',')
    .map(Number);
  if (values.length !== 3 || values.some((item) => !Number.isFinite(item))) {
    throw new Error(`NRRD ${label} is invalid.`);
  }
  return [values[0], values[1], values[2]];
};

type Matrix3 = [LpsPoint, LpsPoint, LpsPoint];

type NormalizedLpsGeometry = {
  origin: LpsPoint;
  directions: Matrix3;
  inverse: Matrix3;
  spacing: [number, number, number];
};

const normalizedGeometryCache = new WeakMap<NrrdVolume, NormalizedLpsGeometry>();

const dot = (left: LpsPoint, right: LpsPoint): number =>
  left[0] * right[0] + left[1] * right[1] + left[2] * right[2];

const addScaled = (origin: LpsPoint, direction: LpsPoint, scale: number): LpsPoint => [
  origin[0] + direction[0] * scale,
  origin[1] + direction[1] * scale,
  origin[2] + direction[2] * scale,
];

const subtract = (left: LpsPoint, right: LpsPoint): LpsPoint => [
  left[0] - right[0],
  left[1] - right[1],
  left[2] - right[2],
];

const applyMatrix = (matrix: Matrix3, vector: LpsPoint): LpsPoint => [
  dot(matrix[0], vector),
  dot(matrix[1], vector),
  dot(matrix[2], vector),
];

const determinantForDirections = (directions: Matrix3): number => {
  const [column0, column1, column2] = directions;
  const [a, d, g] = column0;
  const [b, e, h] = column1;
  const [c, f, i] = column2;
  return a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g);
};

const inverseForDirections = (directions: Matrix3): Matrix3 => {
  const [column0, column1, column2] = directions;
  const [a, d, g] = column0;
  const [b, e, h] = column1;
  const [c, f, i] = column2;
  const determinant = determinantForDirections(directions);
  const scale = directions.reduce(
    (product, direction) => product * Math.hypot(direction[0], direction[1], direction[2]),
    1,
  );
  if (
    !Number.isFinite(determinant) ||
    !Number.isFinite(scale) ||
    scale <= 0 ||
    Math.abs(determinant) <= scale * MATRIX_RELATIVE_EPSILON
  ) {
    throw new Error('NRRD space directions must form an invertible 3-D patient-space affine.');
  }
  return [
    [(e * i - f * h) / determinant, (c * h - b * i) / determinant, (b * f - c * e) / determinant],
    [(f * g - d * i) / determinant, (a * i - c * g) / determinant, (c * d - a * f) / determinant],
    [(d * h - e * g) / determinant, (b * g - a * h) / determinant, (a * e - b * d) / determinant],
  ];
};

const sourcePointToLps = (
  space: NrrdVolume['space'],
  point: LpsPoint,
): LpsPoint =>
  space === 'right-anterior-superior' ? [-point[0], -point[1], point[2]] : [...point];

const normalizedLpsGeometry = (volume: NrrdVolume): NormalizedLpsGeometry => {
  const cached = normalizedGeometryCache.get(volume);
  if (cached) return cached;
  const directions = volume.spaceDirections.map((direction) =>
    sourcePointToLps(volume.space, direction),
  ) as Matrix3;
  const geometry: NormalizedLpsGeometry = {
    origin: sourcePointToLps(volume.space, volume.spaceOrigin),
    directions,
    inverse: inverseForDirections(directions),
    spacing: directions.map((direction) =>
      Math.hypot(direction[0], direction[1], direction[2]),
    ) as [number, number, number],
  };
  normalizedGeometryCache.set(volume, geometry);
  return geometry;
};

const splitHeader = (bytes: Uint8Array): { header: string; payloadOffset: number } => {
  const limit = Math.min(bytes.byteLength, MAX_HEADER_BYTES);
  for (let index = 0; index < limit - 1; index += 1) {
    if (bytes[index] === 10 && bytes[index + 1] === 10) {
      return {
        header: new TextDecoder('ascii', { fatal: true }).decode(bytes.subarray(0, index)),
        payloadOffset: index + 2,
      };
    }
    if (
      index < limit - 3 &&
      bytes[index] === 13 &&
      bytes[index + 1] === 10 &&
      bytes[index + 2] === 13 &&
      bytes[index + 3] === 10
    ) {
      return {
        header: new TextDecoder('ascii', { fatal: true }).decode(bytes.subarray(0, index)),
        payloadOffset: index + 4,
      };
    }
  }
  throw new Error('NRRD header is missing or exceeds 1 MB.');
};

const valueAt = (volume: NrrdVolume, index: number): number => {
  const view = volume.dataView;
  const offset = index * volume.bytesPerVoxel;
  switch (volume.scalarType) {
    case 'int8':
      return view.getInt8(offset);
    case 'uint8':
      return view.getUint8(offset);
    case 'int16':
      return view.getInt16(offset, volume.littleEndian);
    case 'uint16':
      return view.getUint16(offset, volume.littleEndian);
    case 'int32':
      return view.getInt32(offset, volume.littleEndian);
    case 'uint32':
      return view.getUint32(offset, volume.littleEndian);
    case 'float32':
      return view.getFloat32(offset, volume.littleEndian);
    case 'float64':
      return view.getFloat64(offset, volume.littleEndian);
  }
};

const sampledWindow = (
  volume: Omit<NrrdVolume, 'sampledRange' | 'suggestedWindow'>,
): { sampledRange: [number, number]; suggestedWindow: [number, number] } => {
  const voxelCount = volume.sizes[0] * volume.sizes[1] * volume.sizes[2];
  const step = Math.max(1, Math.floor(voxelCount / 100_000));
  const values: number[] = [];
  const readable = volume as NrrdVolume;
  for (let index = 0; index < voxelCount; index += step) {
    const value = valueAt(readable, index);
    if (Number.isFinite(value)) values.push(value);
  }
  if (values.length === 0) throw new Error('NRRD contains no finite scalar samples.');
  values.sort((left, right) => left - right);
  const minimum = values[0];
  const maximum = values.at(-1) ?? minimum;
  let low = values[Math.floor((values.length - 1) * 0.01)];
  let high = values[Math.floor((values.length - 1) * 0.99)];
  if (!(high > low)) {
    low = minimum;
    high = maximum > minimum ? maximum : minimum + 1;
  }
  return { sampledRange: [minimum, maximum], suggestedWindow: [low, high] };
};

export const parseNrrd = (buffer: ArrayBuffer): NrrdVolume => {
  const bytes = new Uint8Array(buffer);
  const { header, payloadOffset } = splitHeader(bytes);
  const lines = header.split(/\r?\n/);
  if (!/^NRRD000[1-5]$/.test(lines[0] ?? '')) {
    throw new Error('File is not a supported NRRD.');
  }
  const fields = new Map<string, string>();
  lines.slice(1).forEach((line) => {
    if (!line || line.startsWith('#')) return;
    const separator = line.indexOf(':');
    if (separator < 1) throw new Error('NRRD header contains a malformed field.');
    const key = line.slice(0, separator).trim().toLowerCase();
    if (fields.has(key)) throw new Error(`NRRD repeats the ${key} field.`);
    fields.set(key, line.slice(separator + 1).trim());
  });
  if (fields.has('data file') || fields.has('datafile')) {
    throw new Error('Detached NRRD payloads are unsupported.');
  }
  if (fields.get('dimension') !== '3') throw new Error('QA requires a 3-D scalar NRRD.');
  const sizes = (fields.get('sizes') ?? '').split(/\s+/).map(Number);
  if (
    sizes.length !== 3 ||
    sizes.some((item) => !Number.isSafeInteger(item) || item <= 0)
  ) {
    throw new Error('NRRD sizes are invalid.');
  }
  const voxelCount = sizes[0] * sizes[1] * sizes[2];
  if (!Number.isSafeInteger(voxelCount) || voxelCount > MAX_VOXELS) {
    throw new Error('NRRD voxel count exceeds the browser QA safety limit.');
  }
  const scalar = scalarTypes[(fields.get('type') ?? '').toLowerCase()];
  if (!scalar) throw new Error('NRRD scalar type is unsupported.');
  const expectedBytes = voxelCount * scalar.bytes;
  if (!Number.isSafeInteger(expectedBytes) || expectedBytes > MAX_DECODED_BYTES) {
    throw new Error('NRRD decoded payload exceeds the browser QA safety limit.');
  }
  const encoding = (fields.get('encoding') ?? '').toLowerCase();
  if (!['raw', 'gzip', 'gz'].includes(encoding)) {
    throw new Error('NRRD encoding is unsupported.');
  }
  const encodedPayload = bytes.subarray(payloadOffset);
  if (encoding !== 'raw') {
    if (encodedPayload.byteLength < 18) {
      throw new Error('NRRD gzip payload is truncated.');
    }
    const trailer = new DataView(
      encodedPayload.buffer,
      encodedPayload.byteOffset + encodedPayload.byteLength - 4,
      4,
    );
    if (trailer.getUint32(0, true) !== expectedBytes) {
      throw new Error('NRRD gzip decoded length does not match its dimensions.');
    }
  }
  const payload =
    encoding === 'raw'
      ? encodedPayload
      : gunzipSync(encodedPayload, new Uint8Array(expectedBytes));
  if (payload.byteLength !== expectedBytes) {
    throw new Error('NRRD scalar payload length does not match its dimensions.');
  }
  const space = fields.get('space');
  if (space !== 'left-posterior-superior' && space !== 'right-anterior-superior') {
    throw new Error('NRRD patient-space convention is unsupported.');
  }
  const directionValues = fields.get('space directions')?.match(/\([^)]*\)/g);
  if (!directionValues || directionValues.length !== 3) {
    throw new Error('NRRD must contain three space directions.');
  }
  const spaceDirections = directionValues.map((item) =>
    parseVector(item, 'space direction'),
  ) as NrrdVolume['spaceDirections'];
  if (
    spaceDirections.some(
      (direction) => Math.hypot(direction[0], direction[1], direction[2]) <= 0,
    )
  ) {
    throw new Error('NRRD contains a zero space direction.');
  }
  inverseForDirections(spaceDirections);
  const spaceOrigin = parseVector(fields.get('space origin') ?? '', 'space origin');
  const endian = (fields.get('endian') ?? '').toLowerCase();
  if (scalar.bytes > 1 && endian !== 'little' && endian !== 'big') {
    throw new Error('NRRD endianness is required for multi-byte scalar data.');
  }
  const partial: Omit<NrrdVolume, 'sampledRange' | 'suggestedWindow'> = {
    sizes: [sizes[0], sizes[1], sizes[2]] as [number, number, number],
    space,
    spaceDirections,
    spaceOrigin,
    scalarType: scalar.type,
    littleEndian: endian !== 'big',
    payload,
    dataView: new DataView(payload.buffer, payload.byteOffset, payload.byteLength),
    bytesPerVoxel: scalar.bytes,
  };
  return { ...partial, ...sampledWindow(partial) };
};

export const planeLength = (volume: NrrdVolume, plane: NrrdPlane): number =>
  plane === 'axial'
    ? volume.sizes[2]
    : plane === 'coronal'
      ? volume.sizes[1]
      : volume.sizes[0];

export const slicePointToVoxel = (
  volume: NrrdVolume,
  plane: NrrdPlane,
  sliceIndex: number,
  horizontal: number,
  vertical: number,
): [number, number, number] => {
  const x = Math.max(0, Math.min(volume.sizes[0] - 1, horizontal));
  const y = Math.max(0, Math.min(volume.sizes[1] - 1, vertical));
  const z = Math.max(0, Math.min(volume.sizes[2] - 1, vertical));
  if (plane === 'axial') return [x, y, sliceIndex];
  if (plane === 'coronal') return [x, sliceIndex, z];
  return [sliceIndex, Math.max(0, Math.min(volume.sizes[1] - 1, horizontal)), z];
};

export const voxelToPhysical = (
  volume: NrrdVolume,
  voxel: [number, number, number],
): LpsPoint => {
  const geometry = normalizedLpsGeometry(volume);
  return [
    geometry.origin[0] +
      voxel[0] * geometry.directions[0][0] +
      voxel[1] * geometry.directions[1][0] +
      voxel[2] * geometry.directions[2][0],
    geometry.origin[1] +
      voxel[0] * geometry.directions[0][1] +
      voxel[1] * geometry.directions[1][1] +
      voxel[2] * geometry.directions[2][1],
    geometry.origin[2] +
      voxel[0] * geometry.directions[0][2] +
      voxel[1] * geometry.directions[1][2] +
      voxel[2] * geometry.directions[2][2],
  ];
};

export const lpsToVoxel = (volume: NrrdVolume, point: LpsPoint): LpsPoint => {
  const geometry = normalizedLpsGeometry(volume);
  return applyMatrix(geometry.inverse, subtract(point, geometry.origin));
};

export const planeOrientationLabels = (
  _volume: NrrdVolume,
  plane: NrrdPlane,
): PlaneOrientationLabels =>
  plane === 'axial'
    ? { left: 'R', right: 'L', top: 'A', bottom: 'P' }
    : plane === 'coronal'
      ? { left: 'R', right: 'L', top: 'S', bottom: 'I' }
      : { left: 'A', right: 'P', top: 'S', bottom: 'I' };

type PatientPlaneLayout = {
  horizontalDirection: LpsPoint;
  verticalDirection: LpsPoint;
  normalDirection: LpsPoint;
  horizontalStartMm: number;
  verticalStartMm: number;
  normalStartMm: number;
  pixelSpacingMm: number;
  sliceSpacingMm: number;
  width: number;
  height: number;
  sliceCount: number;
};

const patientPlaneDirections: Record<
  NrrdPlane,
  {
    horizontal: LpsPoint;
    vertical: LpsPoint;
    normal: LpsPoint;
  }
> = {
  axial: {
    horizontal: [1, 0, 0],
    vertical: [0, 1, 0],
    normal: [0, 0, 1],
  },
  coronal: {
    horizontal: [1, 0, 0],
    vertical: [0, 0, -1],
    normal: [0, 1, 0],
  },
  sagittal: {
    horizontal: [0, 1, 0],
    vertical: [0, 0, -1],
    normal: [-1, 0, 0],
  },
};

const pointFromBasis = (
  horizontal: LpsPoint,
  horizontalMm: number,
  vertical: LpsPoint,
  verticalMm: number,
  normal: LpsPoint,
  normalMm: number,
): LpsPoint => [
  horizontal[0] * horizontalMm + vertical[0] * verticalMm + normal[0] * normalMm,
  horizontal[1] * horizontalMm + vertical[1] * verticalMm + normal[1] * normalMm,
  horizontal[2] * horizontalMm + vertical[2] * verticalMm + normal[2] * normalMm,
];

const patientSpaceCorners = (volume: NrrdVolume): LpsPoint[] => {
  const corners: LpsPoint[] = [];
  for (const x of [0, volume.sizes[0] - 1]) {
    for (const y of [0, volume.sizes[1] - 1]) {
      for (const z of [0, volume.sizes[2] - 1]) {
        corners.push(voxelToPhysical(volume, [x, y, z]));
      }
    }
  }
  return corners;
};

const boundedIntegerOption = (
  value: number | undefined,
  fallback: number,
  maximum: number,
  minimum: number,
  label: string,
): number => {
  if (value === undefined) return fallback;
  if (!Number.isSafeInteger(value) || value < minimum) {
    throw new Error(`${label} is invalid.`);
  }
  return Math.min(value, maximum);
};

const patientPlaneLayout = (
  volume: NrrdVolume,
  plane: NrrdPlane,
  options: PatientSpaceReformatOptions = {},
): PatientPlaneLayout => {
  const geometry = normalizedLpsGeometry(volume);
  const targetSpacing = options.targetSpacingMm ?? Math.min(...geometry.spacing);
  if (!Number.isFinite(targetSpacing) || targetSpacing <= 0) {
    throw new Error('Patient-space target spacing must be finite and positive.');
  }
  const maxDimension = boundedIntegerOption(
    options.maxDimension,
    MAX_PATIENT_SLICE_DIMENSION,
    MAX_PATIENT_SLICE_DIMENSION,
    2,
    'Patient-space maximum dimension',
  );
  const maxPixels = boundedIntegerOption(
    options.maxPixels,
    MAX_PATIENT_SLICE_PIXELS,
    MAX_PATIENT_SLICE_PIXELS,
    4,
    'Patient-space maximum pixel count',
  );
  const directions = patientPlaneDirections[plane];
  const corners = patientSpaceCorners(volume);
  const projected = (direction: LpsPoint): [number, number] => {
    const values = corners.map((corner) => dot(corner, direction));
    return [Math.min(...values), Math.max(...values)];
  };
  const [horizontalMinimum, horizontalMaximum] = projected(directions.horizontal);
  const [verticalMinimum, verticalMaximum] = projected(directions.vertical);
  const [normalMinimum, normalMaximum] = projected(directions.normal);
  const horizontalSpan = horizontalMaximum - horizontalMinimum;
  const verticalSpan = verticalMaximum - verticalMinimum;
  const normalSpan = normalMaximum - normalMinimum;
  let pixelSpacing = Math.max(
    targetSpacing,
    horizontalSpan / Math.max(1, maxDimension - 1),
    verticalSpan / Math.max(1, maxDimension - 1),
  );
  const axisCount = (span: number, spacing: number): number =>
    span <= Number.EPSILON ? 1 : Math.ceil(span / spacing) + 1;
  let width = axisCount(horizontalSpan, pixelSpacing);
  let height = axisCount(verticalSpan, pixelSpacing);
  while (width * height > maxPixels) {
    pixelSpacing *= Math.max(1.05, Math.sqrt((width * height) / maxPixels) * 1.01);
    width = axisCount(horizontalSpan, pixelSpacing);
    height = axisCount(verticalSpan, pixelSpacing);
  }
  const horizontalStart =
    (horizontalMinimum + horizontalMaximum - (width - 1) * pixelSpacing) / 2;
  const verticalStart =
    (verticalMinimum + verticalMaximum - (height - 1) * pixelSpacing) / 2;
  const sliceSpacing = Math.max(
    targetSpacing,
    normalSpan / Math.max(1, MAX_PATIENT_SLICE_COUNT - 1),
  );
  const sliceCount = axisCount(normalSpan, sliceSpacing);
  const normalStart =
    (normalMinimum + normalMaximum - (sliceCount - 1) * sliceSpacing) / 2;
  return {
    horizontalDirection: directions.horizontal,
    verticalDirection: directions.vertical,
    normalDirection: directions.normal,
    horizontalStartMm: horizontalStart,
    verticalStartMm: verticalStart,
    normalStartMm: normalStart,
    pixelSpacingMm: pixelSpacing,
    sliceSpacingMm: sliceSpacing,
    width,
    height,
    sliceCount,
  };
};

export const patientSpacePlaneLength = (
  volume: NrrdVolume,
  plane: NrrdPlane,
  options: PatientSpaceReformatOptions = {},
): number => patientPlaneLayout(volume, plane, options).sliceCount;

export const patientSpaceSliceMapping = (
  volume: NrrdVolume,
  plane: NrrdPlane,
  requestedIndex: number,
  options: PatientSpaceReformatOptions = {},
): PatientSpaceSliceMapping => {
  const layout = patientPlaneLayout(volume, plane, options);
  const sliceIndex = Math.max(
    0,
    Math.min(layout.sliceCount - 1, Math.round(requestedIndex)),
  );
  const normalMm = layout.normalStartMm + sliceIndex * layout.sliceSpacingMm;
  return {
    plane,
    sliceIndex,
    sliceCount: layout.sliceCount,
    sliceSpacingMm: layout.sliceSpacingMm,
    pixelSpacingMm: [layout.pixelSpacingMm, layout.pixelSpacingMm],
    originLps: pointFromBasis(
      layout.horizontalDirection,
      layout.horizontalStartMm,
      layout.verticalDirection,
      layout.verticalStartMm,
      layout.normalDirection,
      normalMm,
    ),
    horizontalDirectionLps: layout.horizontalDirection,
    verticalDirectionLps: layout.verticalDirection,
    normalDirectionLps: layout.normalDirection,
  };
};

export const patientSlicePixelToLps = (
  mapping: PatientSpaceSliceMapping,
  horizontal: number,
  vertical: number,
): LpsPoint => {
  if (!Number.isFinite(horizontal) || !Number.isFinite(vertical)) {
    throw new Error('Patient-space canvas point must be finite.');
  }
  return addScaled(
    addScaled(
      mapping.originLps,
      mapping.horizontalDirectionLps,
      horizontal * mapping.pixelSpacingMm[0],
    ),
    mapping.verticalDirectionLps,
    vertical * mapping.pixelSpacingMm[1],
  );
};

export const lpsToPatientSlicePixel = (
  mapping: PatientSpaceSliceMapping,
  point: LpsPoint,
): PatientSpacePixelProjection => {
  if (!point.every(Number.isFinite)) {
    throw new Error('Patient-space marker point must be finite.');
  }
  const delta = subtract(point, mapping.originLps);
  return {
    horizontal: dot(delta, mapping.horizontalDirectionLps) / mapping.pixelSpacingMm[0],
    vertical: dot(delta, mapping.verticalDirectionLps) / mapping.pixelSpacingMm[1],
    distanceFromPlaneMm: dot(delta, mapping.normalDirectionLps),
  };
};

export const patientSpaceSliceIndexForLps = (
  volume: NrrdVolume,
  plane: NrrdPlane,
  point: LpsPoint,
  options: PatientSpaceReformatOptions = {},
): number => {
  if (!point.every(Number.isFinite)) {
    throw new Error('Patient-space point must be finite.');
  }
  const layout = patientPlaneLayout(volume, plane, options);
  const requested =
    (dot(point, layout.normalDirection) - layout.normalStartMm) / layout.sliceSpacingMm;
  return Math.max(0, Math.min(layout.sliceCount - 1, Math.round(requested)));
};

const sampleNrrdAtVoxel = (
  volume: NrrdVolume,
  requestedVoxel: LpsPoint,
): number | undefined => {
  const epsilon = 1e-6;
  if (
    requestedVoxel.some(
      (coordinate, axis) =>
        coordinate < -epsilon || coordinate > volume.sizes[axis] - 1 + epsilon,
    )
  ) {
    return undefined;
  }
  const voxel = requestedVoxel.map((coordinate, axis) =>
    Math.max(0, Math.min(volume.sizes[axis] - 1, coordinate)),
  ) as LpsPoint;
  const lower = voxel.map(Math.floor) as LpsPoint;
  const upper = lower.map((coordinate, axis) =>
    Math.min(volume.sizes[axis] - 1, coordinate + 1),
  ) as LpsPoint;
  const fraction = voxel.map((coordinate, axis) => coordinate - lower[axis]) as LpsPoint;
  const [sizeX, sizeY] = volume.sizes;
  let result = 0;
  for (let zSide = 0; zSide <= 1; zSide += 1) {
    const z = zSide ? upper[2] : lower[2];
    const zWeight = zSide ? fraction[2] : 1 - fraction[2];
    for (let ySide = 0; ySide <= 1; ySide += 1) {
      const y = ySide ? upper[1] : lower[1];
      const yWeight = ySide ? fraction[1] : 1 - fraction[1];
      for (let xSide = 0; xSide <= 1; xSide += 1) {
        const x = xSide ? upper[0] : lower[0];
        const xWeight = xSide ? fraction[0] : 1 - fraction[0];
        const value = valueAt(volume, x + sizeX * (y + sizeY * z));
        if (!Number.isFinite(value)) return undefined;
        result += value * xWeight * yWeight * zWeight;
      }
    }
  }
  return result;
};

export const sampleNrrdAtLps = (
  volume: NrrdVolume,
  point: LpsPoint,
): number | undefined => sampleNrrdAtVoxel(volume, lpsToVoxel(volume, point));

export const extractPatientSpaceSlice = (
  volume: NrrdVolume,
  plane: NrrdPlane,
  requestedIndex: number,
  window: [number, number] = volume.suggestedWindow,
  options: PatientSpaceReformatOptions = {},
): PatientSpaceSlice => {
  const layout = patientPlaneLayout(volume, plane, options);
  const mapping = patientSpaceSliceMapping(volume, plane, requestedIndex, options);
  const pixels = new Uint8ClampedArray(layout.width * layout.height);
  const [low, high] = window;
  const scale = high > low ? 255 / (high - low) : 1;
  const originVoxel = lpsToVoxel(volume, mapping.originLps);
  const horizontalVoxelStep = applyMatrix(
    normalizedLpsGeometry(volume).inverse,
    mapping.horizontalDirectionLps.map(
      (value) => value * mapping.pixelSpacingMm[0],
    ) as LpsPoint,
  );
  const verticalVoxelStep = applyMatrix(
    normalizedLpsGeometry(volume).inverse,
    mapping.verticalDirectionLps.map(
      (value) => value * mapping.pixelSpacingMm[1],
    ) as LpsPoint,
  );
  for (let vertical = 0; vertical < layout.height; vertical += 1) {
    const rowStart: LpsPoint = [
      originVoxel[0] + verticalVoxelStep[0] * vertical,
      originVoxel[1] + verticalVoxelStep[1] * vertical,
      originVoxel[2] + verticalVoxelStep[2] * vertical,
    ];
    for (let horizontal = 0; horizontal < layout.width; horizontal += 1) {
      const value = sampleNrrdAtVoxel(volume, [
        rowStart[0] + horizontalVoxelStep[0] * horizontal,
        rowStart[1] + horizontalVoxelStep[1] * horizontal,
        rowStart[2] + horizontalVoxelStep[2] * horizontal,
      ]);
      pixels[horizontal + layout.width * vertical] =
        value === undefined
          ? 0
          : Math.max(0, Math.min(255, Math.round((value - low) * scale)));
    }
  }
  return { width: layout.width, height: layout.height, pixels, mapping };
};

const sliceDimensions = (
  volume: NrrdVolume,
  plane: NrrdPlane,
): [number, number] =>
  plane === 'axial'
    ? [volume.sizes[0], volume.sizes[1]]
    : plane === 'coronal'
      ? [volume.sizes[0], volume.sizes[2]]
      : [volume.sizes[1], volume.sizes[2]];

export const extractNrrdSlice = (
  volume: NrrdVolume,
  plane: NrrdPlane,
  requestedIndex: number,
  window: [number, number] = volume.suggestedWindow,
): NrrdSlice => {
  const length = planeLength(volume, plane);
  const index = Math.max(0, Math.min(length - 1, Math.round(requestedIndex)));
  const [width, height] = sliceDimensions(volume, plane);
  const pixels = new Uint8ClampedArray(width * height);
  const [low, high] = window;
  const scale = high > low ? 255 / (high - low) : 1;
  const [sizeX, sizeY] = volume.sizes;
  for (let vertical = 0; vertical < height; vertical += 1) {
    for (let horizontal = 0; horizontal < width; horizontal += 1) {
      const voxel = slicePointToVoxel(volume, plane, index, horizontal, vertical);
      const linear = voxel[0] + sizeX * (voxel[1] + sizeY * voxel[2]);
      const value = valueAt(volume, linear);
      pixels[horizontal + width * vertical] = Number.isFinite(value)
        ? Math.max(0, Math.min(255, Math.round((value - low) * scale)))
        : 0;
    }
  }
  return { width, height, pixels };
};

const edgeMap = (slice: NrrdSlice, threshold: number): Uint8ClampedArray => {
  const output = new Uint8ClampedArray(slice.pixels.length);
  const { width, height, pixels } = slice;
  for (let y = 1; y < height - 1; y += 1) {
    for (let x = 1; x < width - 1; x += 1) {
      const at = (dx: number, dy: number) => pixels[x + dx + width * (y + dy)];
      const gradientX =
        -at(-1, -1) - 2 * at(-1, 0) - at(-1, 1) +
        at(1, -1) + 2 * at(1, 0) + at(1, 1);
      const gradientY =
        -at(-1, -1) - 2 * at(0, -1) - at(1, -1) +
        at(-1, 1) + 2 * at(0, 1) + at(1, 1);
      output[x + width * y] = Math.hypot(gradientX, gradientY) >= threshold ? 255 : 0;
    }
  }
  return output;
};

export const composeQaSlice = (
  fixed: NrrdSlice,
  registered: NrrdSlice,
  mode: QaCompositeMode,
  options: {
    opacity: number;
    checkerSize: number;
    edgeThreshold: number;
    swipePosition: number;
  },
): QaCompositeSlice => {
  if (fixed.width !== registered.width || fixed.height !== registered.height) {
    throw new Error('QA composite requires fixed-space matched slice dimensions.');
  }
  const rgba = new Uint8ClampedArray(fixed.pixels.length * 4);
  const fixedEdges = mode === 'edges' ? edgeMap(fixed, options.edgeThreshold) : undefined;
  const movingEdges =
    mode === 'edges' ? edgeMap(registered, options.edgeThreshold) : undefined;
  const opacity = Math.max(0, Math.min(1, options.opacity));
  const checker = Math.max(2, Math.round(options.checkerSize));
  const swipe = Math.max(0, Math.min(1, options.swipePosition));
  for (let pixelIndex = 0; pixelIndex < fixed.pixels.length; pixelIndex += 1) {
    const fixedValue = fixed.pixels[pixelIndex];
    const movingValue = registered.pixels[pixelIndex];
    const x = pixelIndex % fixed.width;
    const y = Math.floor(pixelIndex / fixed.width);
    let red: number;
    let green: number;
    let blue: number;
    if (mode === 'checkerboard') {
      const useMoving = (Math.floor(x / checker) + Math.floor(y / checker)) % 2 === 1;
      red = green = blue = useMoving ? movingValue : fixedValue;
    } else if (mode === 'swipe') {
      red = green = blue = x / Math.max(1, fixed.width - 1) < swipe ? fixedValue : movingValue;
    } else if (mode === 'edges') {
      const background = Math.round(movingValue * 0.45);
      red = Math.max(background, fixedEdges?.[pixelIndex] ?? 0);
      green = Math.max(background, movingEdges?.[pixelIndex] ?? 0);
      blue = Math.max(background, movingEdges?.[pixelIndex] ?? 0);
    } else {
      red = Math.round(fixedValue * (1 - opacity) + movingValue * opacity * 0.9);
      green = Math.round(fixedValue * (1 - opacity) + movingValue * opacity);
      blue = Math.round(fixedValue * (1 - opacity) + movingValue * opacity);
    }
    const target = pixelIndex * 4;
    rgba[target] = red;
    rgba[target + 1] = green;
    rgba[target + 2] = blue;
    rgba[target + 3] = 255;
  }
  return { data: rgba, width: fixed.width, height: fixed.height };
};

export const landmarkResidual = (
  fixed: [number, number, number],
  registered: [number, number, number],
): number => Math.hypot(
  fixed[0] - registered[0],
  fixed[1] - registered[1],
  fixed[2] - registered[2],
);
