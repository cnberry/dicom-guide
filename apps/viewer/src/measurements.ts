export type ImageSourceReference = {
  seriesId: string;
  instanceId: string;
  frameOfReferenceId?: string;
  spacingTrusted: boolean;
};

export type RawLengthAnnotation = {
  annotationId?: string;
  referencedImageId?: string;
  worldPoints?: number[][];
};

export type LengthMeasurementEvidence = {
  tracking_id: string;
  type: 'length';
  review_status: 'unreviewed';
  source: {
    series_id: string;
    instance_id: string;
    frame_of_reference_id?: string;
  };
  geometry: {
    coordinate_system: 'DICOM patient LPS';
    world_points: number[][];
  };
  result: {
    value?: number;
    unit: 'mm' | 'unknown';
  };
  method: {
    name: 'manual_two_point_length';
    implementation: 'Cornerstone3D LengthTool';
  };
  limitations: string[];
};

export type MeasurementEvidencePacket = {
  schema_version: '1.0.0';
  created_at: string;
  review_status: 'unreviewed';
  measurements: LengthMeasurementEvidence[];
  limitations: string[];
};

const isPoint3 = (point: number[] | undefined): point is [number, number, number] =>
  Boolean(point && point.length === 3 && point.every(Number.isFinite));

const distance = (left: number[], right: number[]): number =>
  Math.sqrt(left.reduce((sum, value, index) => sum + (value - right[index]) ** 2, 0));

export const buildMeasurementEvidencePacket = (
  annotations: RawLengthAnnotation[],
  imageReferences: ReadonlyMap<string, ImageSourceReference>,
  createdAt = new Date().toISOString(),
): MeasurementEvidencePacket => {
  let excludedAnnotations = 0;
  const measurements = annotations.flatMap((annotation, index) => {
    const points = annotation.worldPoints;
    if (!points || points.length !== 2 || !isPoint3(points[0]) || !isPoint3(points[1])) {
      excludedAnnotations += 1;
      return [];
    }
    const source = annotation.referencedImageId
      ? imageReferences.get(annotation.referencedImageId)
      : undefined;
    if (!source) {
      excludedAnnotations += 1;
      return [];
    }
    const limitations = [
      'Manual measurement; verify endpoints and intended tumor component with a qualified clinician.',
    ];
    if (!source.spacingTrusted) {
      limitations.push('Pixel spacing was unavailable; no physical length value is reported.');
    }
    return [
      {
        tracking_id: annotation.annotationId?.startsWith('length:')
          ? annotation.annotationId
          : `length:${annotation.annotationId ?? `export-${index + 1}`}`,
        type: 'length' as const,
        review_status: 'unreviewed' as const,
        source: {
          series_id: source.seriesId,
          instance_id: source.instanceId,
          frame_of_reference_id: source.frameOfReferenceId,
        },
        geometry: {
          coordinate_system: 'DICOM patient LPS' as const,
          world_points: points,
        },
        result: {
          value: source.spacingTrusted ? distance(points[0], points[1]) : undefined,
          unit: source.spacingTrusted ? ('mm' as const) : ('unknown' as const),
        },
        method: {
          name: 'manual_two_point_length' as const,
          implementation: 'Cornerstone3D LengthTool' as const,
        },
        limitations,
      },
    ];
  });
  const limitations = [
    'This packet contains unreviewed derived measurements, not a diagnosis or treatment-response conclusion.',
    'The copied DICOM instances remain the authoritative source.',
  ];
  if (excludedAnnotations) {
    limitations.push(
      `${excludedAnnotations} annotation${excludedAnnotations === 1 ? ' was' : 's were'} excluded because valid geometry or source provenance was unavailable.`,
    );
  }
  return {
    schema_version: '1.0.0',
    created_at: createdAt,
    review_status: 'unreviewed',
    measurements,
    limitations,
  };
};

const isRecord = (value: unknown): value is Record<string, unknown> =>
  Boolean(value && typeof value === 'object' && !Array.isArray(value));

const isOpaqueId = (value: unknown): value is string =>
  typeof value === 'string' && /^[0-9a-f]{16}$/.test(value);

const hasOnlyKeys = (value: Record<string, unknown>, allowed: string[]): boolean =>
  Object.keys(value).every((key) => allowed.includes(key));

export const readMeasurementEvidencePacket = (
  value: unknown,
): { packet?: MeasurementEvidencePacket; errors: string[] } => {
  const errors: string[] = [];
  if (!isRecord(value)) return { errors: ['Measurement packet must be a JSON object.'] };
  if (
    !hasOnlyKeys(value, [
      'schema_version',
      'created_at',
      'review_status',
      'measurements',
      'limitations',
    ])
  ) {
    errors.push('Measurement packet contains unsupported fields.');
  }
  if (value.schema_version !== '1.0.0') errors.push('Unsupported measurement schema version.');
  if (value.review_status !== 'unreviewed') errors.push('Measurement packet must be unreviewed.');
  if (typeof value.created_at !== 'string' || !value.created_at) {
    errors.push('Measurement packet is missing its creation time.');
  } else if (!Number.isFinite(Date.parse(value.created_at))) {
    errors.push('Measurement packet creation time is invalid.');
  }
  if (
    !Array.isArray(value.limitations) ||
    value.limitations.length === 0 ||
    !value.limitations.every((item) => typeof item === 'string' && item.length > 0)
  ) {
    errors.push('Measurement packet limitations are invalid.');
  }
  if (!Array.isArray(value.measurements)) {
    errors.push('Measurement packet measurements must be an array.');
  } else {
    const trackingIds = new Set<string>();
    value.measurements.forEach((item, index) => {
      if (!isRecord(item)) {
        errors.push(`Measurement ${index + 1} is not an object.`);
        return;
      }
      if (
        !hasOnlyKeys(item, [
          'tracking_id',
          'type',
          'review_status',
          'source',
          'geometry',
          'result',
          'method',
          'limitations',
        ])
      ) {
        errors.push(`Measurement ${index + 1} contains unsupported fields.`);
      }
      const source = item.source;
      const geometry = item.geometry;
      const points = isRecord(geometry) ? geometry.world_points : undefined;
      const result = item.result;
      const method = item.method;
      if (
        item.type !== 'length' ||
        item.review_status !== 'unreviewed' ||
        typeof item.tracking_id !== 'string' ||
        !item.tracking_id
      ) {
        errors.push(`Measurement ${index + 1} has invalid identity or review state.`);
      } else if (trackingIds.has(item.tracking_id)) {
        errors.push(`Measurement ${index + 1} has a duplicate tracking ID.`);
      } else {
        trackingIds.add(item.tracking_id);
      }
      if (
        !isRecord(source) ||
        !isOpaqueId(source.series_id) ||
        !isOpaqueId(source.instance_id) ||
        (source.frame_of_reference_id !== undefined && !isOpaqueId(source.frame_of_reference_id))
      ) {
        errors.push(`Measurement ${index + 1} has invalid source provenance.`);
      } else if (!hasOnlyKeys(source, ['series_id', 'instance_id', 'frame_of_reference_id'])) {
        errors.push(`Measurement ${index + 1} source contains unsupported fields.`);
      }
      if (
        !isRecord(geometry) ||
        geometry.coordinate_system !== 'DICOM patient LPS' ||
        !Array.isArray(points) ||
        points.length !== 2 ||
        !points.every(
          (point) =>
            Array.isArray(point) &&
            point.length === 3 &&
            point.every((coordinate) => Number.isFinite(coordinate)),
        )
      ) {
        errors.push(`Measurement ${index + 1} has invalid patient-space geometry.`);
      } else if (!hasOnlyKeys(geometry, ['coordinate_system', 'world_points'])) {
        errors.push(`Measurement ${index + 1} geometry contains unsupported fields.`);
      }
      if (
        !isRecord(result) ||
        !['mm', 'unknown'].includes(String(result.unit)) ||
        (result.unit === 'mm' &&
          (typeof result.value !== 'number' || !Number.isFinite(result.value) || result.value < 0))
      ) {
        errors.push(`Measurement ${index + 1} has an invalid result.`);
      } else if (!hasOnlyKeys(result, ['value', 'unit'])) {
        errors.push(`Measurement ${index + 1} result contains unsupported fields.`);
      }
      if (
        !isRecord(method) ||
        method.name !== 'manual_two_point_length' ||
        method.implementation !== 'Cornerstone3D LengthTool'
      ) {
        errors.push(`Measurement ${index + 1} has an unsupported method.`);
      } else if (!hasOnlyKeys(method, ['name', 'implementation'])) {
        errors.push(`Measurement ${index + 1} method contains unsupported fields.`);
      }
      if (
        !Array.isArray(item.limitations) ||
        item.limitations.length === 0 ||
        !item.limitations.every(
          (limitation) => typeof limitation === 'string' && limitation.length > 0,
        )
      ) {
        errors.push(`Measurement ${index + 1} has invalid limitations.`);
      }
    });
  }
  return errors.length
    ? { errors }
    : { packet: value as MeasurementEvidencePacket, errors: [] };
};
