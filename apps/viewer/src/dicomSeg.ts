type DicomItem = Record<string, unknown>;

export type DicomSegSourceGeometry = {
  sopClassUid: string;
  imagePositionPatient: [number, number, number];
  imageOrientationPatient: [number, number, number, number, number, number];
  pixelSpacing: [number, number];
  sliceThickness: number;
  sourceIndex: number;
};

const DERIVATION_CODE = {
  CodeValue: '113076',
  CodingSchemeDesignator: 'DCM',
  CodeMeaning: 'Segmentation',
} as const;

const PURPOSE_CODE = {
  CodeValue: '121322',
  CodingSchemeDesignator: 'DCM',
  CodeMeaning: 'Source Image for Image Processing Operation',
} as const;

const sequenceItems = (value: unknown): DicomItem[] => {
  if (Array.isArray(value)) {
    return value.filter(
      (item): item is DicomItem => Boolean(item) && typeof item === 'object' && !Array.isArray(item),
    );
  }
  return value && typeof value === 'object' ? [value as DicomItem] : [];
};

const completeCodeSequence = (
  owner: DicomItem,
  key: string,
  expected: DicomItem,
): void => {
  if (owner[key] === undefined) {
    owner[key] = { ...expected };
    return;
  }
  const items = sequenceItems(owner[key]);
  if (
    items.length !== 1 ||
    Object.entries(expected).some(([name, value]) => items[0][name] !== value)
  ) {
    throw new Error(`The DICOM SEG adapter produced a conflicting ${key}.`);
  }
};

const numericValuesMatch = (left: number[], right: number[], tolerance = 1e-4): boolean =>
  left.length === right.length &&
  left.every((value, index) => Math.abs(value - right[index]) <= tolerance);

const repackBinaryPixelData = (dataset: DicomItem): void => {
  const rows = Number(dataset.Rows);
  const columns = Number(dataset.Columns);
  const frameCount = Number(dataset.NumberOfFrames);
  const source = dataset.PixelData;
  const bytes =
    source instanceof ArrayBuffer
      ? new Uint8Array(source)
      : ArrayBuffer.isView(source)
        ? new Uint8Array(source.buffer, source.byteOffset, source.byteLength)
        : undefined;
  if (
    !Number.isSafeInteger(rows) ||
    !Number.isSafeInteger(columns) ||
    !Number.isSafeInteger(frameCount) ||
    rows < 1 ||
    columns < 1 ||
    frameCount < 1 ||
    !bytes
  ) {
    throw new Error('The DICOM SEG adapter produced invalid binary pixel dimensions.');
  }
  const bitsPerFrame = rows * columns;
  const adapterFrameBytes = Math.ceil(bitsPerFrame / 8);
  const adapterPayloadBytes = adapterFrameBytes * frameCount;
  if (
    bytes.byteLength < adapterPayloadBytes ||
    bytes.byteLength > adapterPayloadBytes + 1 ||
    (bytes.byteLength === adapterPayloadBytes + 1 && bytes[bytes.byteLength - 1] !== 0)
  ) {
    throw new Error('The DICOM SEG adapter produced an invalid binary pixel payload.');
  }
  if (bitsPerFrame % 8 === 0) return;

  const packedBytes = Math.ceil((bitsPerFrame * frameCount) / 8);
  const output = new Uint8Array(packedBytes + (packedBytes % 2));
  for (let frameIndex = 0; frameIndex < frameCount; frameIndex += 1) {
    for (let pixelIndex = 0; pixelIndex < bitsPerFrame; pixelIndex += 1) {
      const sourceBit = frameIndex * adapterFrameBytes * 8 + pixelIndex;
      const value = (bytes[sourceBit >> 3] >> (sourceBit & 7)) & 1;
      const outputBit = frameIndex * bitsPerFrame + pixelIndex;
      output[outputBit >> 3] |= value << (outputBit & 7);
    }
  }
  dataset.PixelData = output.buffer;
};

/**
 * Cornerstone adapters 5.8.2 drops ReferencedSOPClassUID while rebuilding the
 * per-frame SourceImageSequence. Restore it from the complete series-level
 * reference set, and fail closed if the two reference locations disagree.
 */
export const repairDicomSegFrameSourceClasses = (
  dataset: DicomItem,
  sourceGeometryByInstance: ReadonlyMap<string, DicomSegSourceGeometry>,
): void => {
  const sourceClasses = new Map<string, string>();
  const referencedSeries = sequenceItems(dataset.ReferencedSeriesSequence);
  if (referencedSeries.length !== 1) {
    throw new Error('The DICOM SEG adapter did not produce exactly one referenced source series.');
  }
  for (const source of sequenceItems(referencedSeries[0].ReferencedInstanceSequence)) {
    const instanceUid = source.ReferencedSOPInstanceUID;
    const classUid = source.ReferencedSOPClassUID;
    if (typeof instanceUid !== 'string' || !instanceUid || typeof classUid !== 'string' || !classUid) {
      throw new Error('The DICOM SEG adapter produced an incomplete source-instance reference.');
    }
    const prior = sourceClasses.get(instanceUid);
    if (prior && prior !== classUid) {
      throw new Error('The DICOM SEG source reference set assigns conflicting SOP classes.');
    }
    sourceClasses.set(instanceUid, classUid);
  }
  if (sourceClasses.size === 0) {
    throw new Error('The DICOM SEG adapter omitted its complete source reference set.');
  }
  if (
    sourceClasses.size !== sourceGeometryByInstance.size ||
    Array.from(sourceClasses).some(
      ([instanceUid, classUid]) =>
        sourceGeometryByInstance.get(instanceUid)?.sopClassUid !== classUid,
    )
  ) {
    throw new Error('The DICOM SEG adapter source set does not match loaded source geometry.');
  }
  const orderedGeometry = Array.from(sourceGeometryByInstance.values()).sort(
    (left, right) => left.sourceIndex - right.sourceIndex,
  );
  const firstGeometry = orderedGeometry[0];
  if (
    orderedGeometry.some(
      (item, index) =>
        item.sourceIndex !== index ||
        !numericValuesMatch(item.imageOrientationPatient, firstGeometry.imageOrientationPatient) ||
        !numericValuesMatch(item.pixelSpacing, firstGeometry.pixelSpacing) ||
        Math.abs(item.sliceThickness - firstGeometry.sliceThickness) > 0.01,
    )
  ) {
    throw new Error('Loaded source geometry is incomplete or inconsistent for DICOM SEG export.');
  }
  const sharedGroups = sequenceItems(dataset.SharedFunctionalGroupsSequence);
  if (sharedGroups.length !== 1) {
    throw new Error('The DICOM SEG adapter omitted its shared functional group.');
  }
  sharedGroups[0].PixelMeasuresSequence = {
    PixelSpacing: [...firstGeometry.pixelSpacing],
    SliceThickness: firstGeometry.sliceThickness,
  };
  sharedGroups[0].PlaneOrientationSequence = {
    ImageOrientationPatient: [...firstGeometry.imageOrientationPatient],
  };

  const frames = sequenceItems(dataset.PerFrameFunctionalGroupsSequence);
  if (frames.length === 0) {
    throw new Error('The DICOM SEG adapter omitted its per-frame source references.');
  }
  for (const frame of frames) {
    const derivations = sequenceItems(frame.DerivationImageSequence);
    const sources = derivations.flatMap((derivation) =>
      sequenceItems(derivation.SourceImageSequence),
    );
    if (sources.length !== 1) {
      throw new Error('Every v1 DICOM SEG frame must reference exactly one source image.');
    }
    const source = sources[0];
    const instanceUid = source.ReferencedSOPInstanceUID;
    const expectedClassUid =
      typeof instanceUid === 'string' ? sourceClasses.get(instanceUid) : undefined;
    if (!expectedClassUid) {
      throw new Error('A DICOM SEG frame does not match the complete source reference set.');
    }
    const sourceGeometry = sourceGeometryByInstance.get(instanceUid as string);
    if (!sourceGeometry || sourceGeometry.sopClassUid !== expectedClassUid) {
      throw new Error('A DICOM SEG frame does not match loaded source geometry.');
    }
    const observedClassUid = source.ReferencedSOPClassUID;
    if (observedClassUid !== undefined && observedClassUid !== expectedClassUid) {
      throw new Error('A DICOM SEG frame references the wrong source SOP class.');
    }
    source.ReferencedSOPClassUID = expectedClassUid;
    completeCodeSequence(derivations[0], 'DerivationCodeSequence', DERIVATION_CODE);
    completeCodeSequence(source, 'PurposeOfReferenceCodeSequence', PURPOSE_CODE);
    frame.PlanePositionSequence = {
      ImagePositionPatient: [...sourceGeometry.imagePositionPatient],
    };
    const frameContent = sequenceItems(frame.FrameContentSequence);
    if (frameContent.length !== 1) {
      throw new Error('A DICOM SEG frame is missing its dimension-index content.');
    }
    frameContent[0].DimensionIndexValues = [1, sourceGeometry.sourceIndex + 1];
  }
  repackBinaryPixelData(dataset);
};
