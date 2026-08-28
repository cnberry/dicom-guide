export type ImageSourceReference = {
  seriesId: string;
  instanceId: string;
  frameOfReferenceId?: string;
  spacingTrusted: boolean;
};

export type MeasurementType = 'length' | 'bidirectional' | 'elliptical_roi';

export type RawMeasurementAnnotation = {
  annotationId?: string;
  type: MeasurementType;
  referencedImageId?: string;
  worldPoints?: number[][];
};

type MeasurementSource = {
  series_id: string;
  instance_id: string;
  frame_of_reference_id?: string;
};

type MeasurementGeometry = {
  coordinate_system: 'DICOM patient LPS';
  world_points: number[][];
};

type MeasurementBase = {
  tracking_id: string;
  review_status: 'unreviewed';
  source: MeasurementSource;
  geometry: MeasurementGeometry;
  limitations: string[];
};

export type LengthMeasurementEvidence = MeasurementBase & {
  type: 'length';
  result: {
    value?: number;
    unit: 'mm' | 'unknown';
  };
  method: {
    name: 'manual_two_point_length';
    implementation: 'Cornerstone3D LengthTool';
  };
};

export type BidirectionalMeasurementEvidence = MeasurementBase & {
  type: 'bidirectional';
  result: {
    long_axis?: number;
    short_axis?: number;
    product?: number;
    unit: 'mm' | 'unknown';
    product_unit: 'mm2' | 'unknown';
  };
  method: {
    name: 'manual_perpendicular_bidirectional';
    implementation: 'Cornerstone3D BidirectionalTool';
  };
};

export type EllipticalRoiMeasurementEvidence = MeasurementBase & {
  type: 'elliptical_roi';
  result: {
    major_axis?: number;
    minor_axis?: number;
    area?: number;
    unit: 'mm' | 'unknown';
    area_unit: 'mm2' | 'unknown';
  };
  method: {
    name: 'manual_elliptical_roi';
    implementation: 'Cornerstone3D EllipticalROITool';
  };
};

export type MeasurementEvidence =
  | LengthMeasurementEvidence
  | BidirectionalMeasurementEvidence
  | EllipticalRoiMeasurementEvidence;

export type MeasurementEvidencePacket = {
  schema_version: '1.0.0' | '2.0.0' | '3.0.0';
  created_at: string;
  review_status: 'unreviewed';
  measurements: MeasurementEvidence[];
  limitations: string[];
};

const isPoint3 = (point: number[] | undefined): point is [number, number, number] =>
  Boolean(point && point.length === 3 && point.every(Number.isFinite));

const distance = (left: number[], right: number[]): number =>
  Math.sqrt(left.reduce((sum, value, index) => sum + (value - right[index]) ** 2, 0));

const trackingId = (annotation: RawMeasurementAnnotation, index: number): string => {
  const prefix = `${annotation.type}:`;
  return annotation.annotationId?.startsWith(prefix)
    ? annotation.annotationId
    : `${prefix}${annotation.annotationId ?? `export-${index + 1}`}`;
};

export const buildMeasurementEvidencePacket = (
  annotations: RawMeasurementAnnotation[],
  imageReferences: ReadonlyMap<string, ImageSourceReference>,
  createdAt = new Date().toISOString(),
): MeasurementEvidencePacket => {
  let excludedAnnotations = 0;
  const measurements = annotations.flatMap<MeasurementEvidence>((annotation, index) => {
    const points = annotation.worldPoints;
    const expectedPoints = annotation.type === 'length' ? 2 : 4;
    if (
      !points ||
      points.length !== expectedPoints ||
      !points.every((point) => isPoint3(point))
    ) {
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
    const sourceEvidence: MeasurementSource = {
      series_id: source.seriesId,
      instance_id: source.instanceId,
      frame_of_reference_id: source.frameOfReferenceId,
    };
    const geometry: MeasurementGeometry = {
      coordinate_system: 'DICOM patient LPS',
      world_points: points,
    };
    const limitations = [
      'Manual measurement; verify endpoints, image selection, and intended tumor component with a qualified clinician.',
    ];
    if (!source.spacingTrusted) {
      limitations.push('Pixel spacing was unavailable; no physical measurement value is reported.');
    }
    if (annotation.type === 'length') {
      return [
        {
          tracking_id: trackingId(annotation, index),
          type: 'length',
          review_status: 'unreviewed',
          source: sourceEvidence,
          geometry,
          result: {
            value: source.spacingTrusted ? distance(points[0], points[1]) : undefined,
            unit: source.spacingTrusted ? 'mm' : 'unknown',
          },
          method: {
            name: 'manual_two_point_length',
            implementation: 'Cornerstone3D LengthTool',
          },
          limitations,
        },
      ];
    }
    const firstAxis = distance(points[0], points[1]);
    const secondAxis = distance(points[2], points[3]);
    const longAxis = Math.max(firstAxis, secondAxis);
    const shortAxis = Math.min(firstAxis, secondAxis);
    if (annotation.type === 'elliptical_roi') {
      return [
        {
          tracking_id: trackingId(annotation, index),
          type: 'elliptical_roi',
          review_status: 'unreviewed',
          source: sourceEvidence,
          geometry,
          result: {
            major_axis: source.spacingTrusted ? longAxis : undefined,
            minor_axis: source.spacingTrusted ? shortAxis : undefined,
            area: source.spacingTrusted ? Math.PI * (longAxis / 2) * (shortAxis / 2) : undefined,
            unit: source.spacingTrusted ? 'mm' : 'unknown',
            area_unit: source.spacingTrusted ? 'mm2' : 'unknown',
          },
          method: {
            name: 'manual_elliptical_roi',
            implementation: 'Cornerstone3D EllipticalROITool',
          },
          limitations: [
            ...limitations,
            'A 2D ellipse is not a segmentation, volume estimate, or treatment-response conclusion.',
          ],
        },
      ];
    }
    return [
      {
        tracking_id: trackingId(annotation, index),
        type: 'bidirectional',
        review_status: 'unreviewed',
        source: sourceEvidence,
        geometry,
        result: {
          long_axis: source.spacingTrusted ? longAxis : undefined,
          short_axis: source.spacingTrusted ? shortAxis : undefined,
          product: source.spacingTrusted ? longAxis * shortAxis : undefined,
          unit: source.spacingTrusted ? 'mm' : 'unknown',
          product_unit: source.spacingTrusted ? 'mm2' : 'unknown',
        },
        method: {
          name: 'manual_perpendicular_bidirectional',
          implementation: 'Cornerstone3D BidirectionalTool',
        },
        limitations,
      },
    ];
  });
  const limitations = [
    'This packet contains unreviewed derived measurements, not a diagnosis or treatment-response conclusion.',
    'The copied DICOM instances remain the authoritative source.',
    'A numeric change must not be converted into a response category without the diagnosis-specific criteria and required clinical context.',
  ];
  if (excludedAnnotations) {
    limitations.push(
      `${excludedAnnotations} annotation${excludedAnnotations === 1 ? ' was' : 's were'} excluded because valid geometry or source provenance was unavailable.`,
    );
  }
  return {
    schema_version: '3.0.0',
    created_at: createdAt,
    review_status: 'unreviewed',
    measurements,
    limitations,
  };
};

const isRecord = (value: unknown): value is Record<string, unknown> =>
  Boolean(value && typeof value === 'object' && !Array.isArray(value));

const isOpaqueId = (
  value: unknown,
  kind: 'series' | 'instance' | 'frame',
): value is string =>
  typeof value === 'string' &&
  (/^[0-9a-f]{16}$/.test(value) || new RegExp(`^${kind}_[0-9a-f]{20}$`).test(value));

const hasOnlyKeys = (value: Record<string, unknown>, allowed: string[]): boolean =>
  Object.keys(value).every((key) => allowed.includes(key));

const isFiniteNonNegative = (value: unknown): value is number =>
  typeof value === 'number' && Number.isFinite(value) && value >= 0;

const approximatelyEqual = (left: number, right: number): boolean =>
  Math.abs(left - right) <= Math.max(0.001, Math.abs(right) * 0.001);

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
  const schemaVersion = value.schema_version;
  if (!['1.0.0', '2.0.0', '3.0.0'].includes(String(schemaVersion))) {
    errors.push('Unsupported measurement schema version.');
  }
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
      const measurementType = item.type;
      if (
        !['length', 'bidirectional', 'elliptical_roi'].includes(String(measurementType)) ||
        (schemaVersion === '1.0.0' && measurementType !== 'length') ||
        (schemaVersion === '2.0.0' && measurementType === 'elliptical_roi') ||
        item.review_status !== 'unreviewed' ||
        typeof item.tracking_id !== 'string' ||
        !item.tracking_id
      ) {
        errors.push(`Measurement ${index + 1} has invalid identity, type, or review state.`);
      } else if (trackingIds.has(item.tracking_id)) {
        errors.push(`Measurement ${index + 1} has a duplicate tracking ID.`);
      } else {
        trackingIds.add(item.tracking_id);
      }

      const source = item.source;
      if (
        !isRecord(source) ||
        !isOpaqueId(source.series_id, 'series') ||
        !isOpaqueId(source.instance_id, 'instance') ||
        (source.frame_of_reference_id !== undefined &&
          !isOpaqueId(source.frame_of_reference_id, 'frame'))
      ) {
        errors.push(`Measurement ${index + 1} has invalid source provenance.`);
      } else if (!hasOnlyKeys(source, ['series_id', 'instance_id', 'frame_of_reference_id'])) {
        errors.push(`Measurement ${index + 1} source contains unsupported fields.`);
      }

      const geometry = item.geometry;
      const points = isRecord(geometry) ? geometry.world_points : undefined;
      const expectedPoints = measurementType === 'length' ? 2 : 4;
      const validPoints =
        Array.isArray(points) &&
        points.length === expectedPoints &&
        points.every(
          (point) =>
            Array.isArray(point) &&
            point.length === 3 &&
            point.every((coordinate) => Number.isFinite(coordinate)),
        );
      if (
        !isRecord(geometry) ||
        geometry.coordinate_system !== 'DICOM patient LPS' ||
        !validPoints
      ) {
        errors.push(`Measurement ${index + 1} has invalid patient-space geometry.`);
      } else if (!hasOnlyKeys(geometry, ['coordinate_system', 'world_points'])) {
        errors.push(`Measurement ${index + 1} geometry contains unsupported fields.`);
      }

      const result = item.result;
      if (!isRecord(result) || !['mm', 'unknown'].includes(String(result.unit))) {
        errors.push(`Measurement ${index + 1} has an invalid result.`);
      } else if (measurementType === 'bidirectional') {
        const physicalResult =
          result.unit === 'mm' &&
          result.product_unit === 'mm2' &&
          isFiniteNonNegative(result.long_axis) &&
          isFiniteNonNegative(result.short_axis) &&
          isFiniteNonNegative(result.product);
        const unknownResult = result.unit === 'unknown' && result.product_unit === 'unknown';
        if (!physicalResult && !unknownResult) {
          errors.push(`Measurement ${index + 1} has invalid bidirectional values.`);
        }
        if (
          unknownResult &&
          [result.long_axis, result.short_axis, result.product].some(
            (measurement) => measurement !== undefined,
          )
        ) {
          errors.push(`Measurement ${index + 1} reports values with unknown units.`);
        }
        if (physicalResult && validPoints) {
          const typedPoints = points as number[][];
          const axes = [
            distance(typedPoints[0], typedPoints[1]),
            distance(typedPoints[2], typedPoints[3]),
          ].sort((left, right) => right - left);
          if (
            !approximatelyEqual(result.long_axis as number, axes[0]) ||
            !approximatelyEqual(result.short_axis as number, axes[1]) ||
            !approximatelyEqual(result.product as number, axes[0] * axes[1])
          ) {
            errors.push(`Measurement ${index + 1} result disagrees with its geometry.`);
          }
        }
        if (
          !hasOnlyKeys(result, [
            'long_axis',
            'short_axis',
            'product',
            'unit',
            'product_unit',
          ])
        ) {
          errors.push(`Measurement ${index + 1} result contains unsupported fields.`);
        }
      } else if (measurementType === 'elliptical_roi') {
        const physicalResult =
          result.unit === 'mm' &&
          result.area_unit === 'mm2' &&
          isFiniteNonNegative(result.major_axis) &&
          isFiniteNonNegative(result.minor_axis) &&
          isFiniteNonNegative(result.area);
        const unknownResult = result.unit === 'unknown' && result.area_unit === 'unknown';
        if (!physicalResult && !unknownResult) {
          errors.push(`Measurement ${index + 1} has invalid elliptical ROI values.`);
        }
        if (
          unknownResult &&
          [result.major_axis, result.minor_axis, result.area].some(
            (measurement) => measurement !== undefined,
          )
        ) {
          errors.push(`Measurement ${index + 1} reports values with unknown units.`);
        }
        if (physicalResult && validPoints) {
          const typedPoints = points as number[][];
          const axes = [
            distance(typedPoints[0], typedPoints[1]),
            distance(typedPoints[2], typedPoints[3]),
          ].sort((left, right) => right - left);
          if (
            !approximatelyEqual(result.major_axis as number, axes[0]) ||
            !approximatelyEqual(result.minor_axis as number, axes[1]) ||
            !approximatelyEqual(result.area as number, Math.PI * (axes[0] / 2) * (axes[1] / 2))
          ) {
            errors.push(`Measurement ${index + 1} result disagrees with its geometry.`);
          }
        }
        if (!hasOnlyKeys(result, ['major_axis', 'minor_axis', 'area', 'unit', 'area_unit'])) {
          errors.push(`Measurement ${index + 1} result contains unsupported fields.`);
        }
      } else {
        if (result.unit === 'mm' && !isFiniteNonNegative(result.value)) {
          errors.push(`Measurement ${index + 1} has an invalid length value.`);
        }
        if (result.unit === 'unknown' && result.value !== undefined) {
          errors.push(`Measurement ${index + 1} reports a value with unknown units.`);
        }
        if (
          result.unit === 'mm' &&
          isFiniteNonNegative(result.value) &&
          validPoints &&
          !approximatelyEqual(result.value, distance((points as number[][])[0], (points as number[][])[1]))
        ) {
          errors.push(`Measurement ${index + 1} result disagrees with its geometry.`);
        }
        if (!hasOnlyKeys(result, ['value', 'unit'])) {
          errors.push(`Measurement ${index + 1} result contains unsupported fields.`);
        }
      }

      const method = item.method;
      const expectedMethod =
        measurementType === 'bidirectional'
          ? ['manual_perpendicular_bidirectional', 'Cornerstone3D BidirectionalTool']
          : measurementType === 'elliptical_roi'
            ? ['manual_elliptical_roi', 'Cornerstone3D EllipticalROITool']
            : ['manual_two_point_length', 'Cornerstone3D LengthTool'];
      if (
        !isRecord(method) ||
        method.name !== expectedMethod[0] ||
        method.implementation !== expectedMethod[1]
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
