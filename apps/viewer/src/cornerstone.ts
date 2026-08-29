import { adaptersSEG } from '@cornerstonejs/adapters';
import {
  Enums,
  RenderingEngine,
  cache,
  eventTarget,
  init as initCore,
  metaData,
  setVolumesForViewports,
  type Types,
  volumeLoader,
} from '@cornerstonejs/core';
import {
  init as initDicomImageLoader,
  wadouri,
} from '@cornerstonejs/dicom-image-loader';
import {
  BidirectionalTool,
  BrushTool,
  CrosshairsTool,
  EllipticalROITool,
  Enums as ToolEnums,
  LengthTool,
  PanTool,
  StackScrollTool,
  ToolGroupManager,
  WindowLevelTool,
  ZoomTool,
  addTool,
  annotation,
  init as initTools,
  segmentation,
  utilities as toolUtilities,
} from '@cornerstonejs/tools';
import dcmjs from 'dcmjs';
import { assessLesionVolumeEligibility, type DicomSeries } from './dicom';
import { repairDicomSegFrameSourceClasses } from './dicomSeg';
import {
  buildMeasurementEvidencePacket,
  type ImageSourceReference,
  type MeasurementEvidencePacket,
  type RawMeasurementAnnotation,
} from './measurements';
import {
  calculateMprCropFit,
  mprCrosshairConfiguration,
  reorderDenseMaskSlices,
  type MprCanvasPoint,
  type MprPatientPoint,
} from './mpr';
import {
  MAX_MANUAL_LABELMAP_VOXELS,
  buildLesionVolumeArchive,
  type LesionVolumeArchive,
  type ManualSegmentationStats,
} from './lesionVolume';

let initialization: Promise<void> | undefined;
const imageReferences = new Map<string, ImageSourceReference>();
const instanceImageIds = new Map<string, string>();

export type ViewerTool = 'window' | 'pan' | 'zoom' | 'length' | 'bidirectional' | 'roi';

const toolClasses = {
  window: WindowLevelTool,
  pan: PanTool,
  zoom: ZoomTool,
  length: LengthTool,
  bidirectional: BidirectionalTool,
  roi: EllipticalROITool,
} as const;

export type ViewportToolController = {
  setPrimaryTool: (tool: ViewerTool) => void;
  destroy: () => void;
};

export type MprTool = 'crosshairs' | 'window' | 'pan' | 'zoom' | 'crop' | 'paint' | 'erase';
export type MprOrientation = 'axial' | 'coronal' | 'sagittal';
export type NormalizedMprPoint = [number, number, number];
export type ReadonlyMprSegmentation = {
  mask: Uint8Array;
  foregroundVoxels: number;
  label: string;
  orderedInstanceIds: string[];
};
export type MprViewportController = {
  setPrimaryTool: (tool: MprTool) => void;
  subscribeToPatientPoint: (listener: (point: MprPatientPoint) => void) => () => void;
  subscribeToNormalizedPoint: (
    listener: (point: NormalizedMprPoint) => void,
  ) => () => void;
  setPatientPoint: (point: MprPatientPoint) => void;
  setNormalizedPoint: (point: NormalizedMprPoint) => void;
  fitToCanvasRectangle: (
    orientation: MprOrientation,
    start: MprCanvasPoint,
    end: MprCanvasPoint,
  ) => boolean;
  reset: () => void;
  setBrushSize: (size: number) => void;
  clearSegmentation: () => void;
  subscribeToSegmentationStats: (
    listener: (stats: ManualSegmentationStats) => void,
  ) => () => void;
  exportSegmentationEvidence: (
    label: string,
    targetDefinition: string,
  ) => Promise<LesionVolumeArchive>;
  hasSegmentationDraft: () => boolean;
  resize: () => void;
  destroy: () => void;
};

export const initializeCornerstone = (): Promise<void> => {
  if (!initialization) {
    initialization = (async () => {
      await initCore();
      await initDicomImageLoader({
        maxWebWorkers: Math.max(1, Math.min(4, navigator.hardwareConcurrency || 1)),
      });
      initTools();
      Object.values(toolClasses).forEach((toolClass) => addTool(toolClass));
      addTool(StackScrollTool);
      addTool(CrosshairsTool);
      addTool(BrushTool);
    })();
  }
  return initialization;
};

const measurementTypeForToolName = (
  toolName?: string,
): RawMeasurementAnnotation['type'] | undefined =>
  toolName === BidirectionalTool.toolName
    ? 'bidirectional'
    : toolName === EllipticalROITool.toolName
      ? 'elliptical_roi'
      : toolName === LengthTool.toolName
        ? 'length'
        : undefined;

const annotationTrackingId = (toolName?: string, annotationId?: string): string | undefined => {
  const type = measurementTypeForToolName(toolName);
  if (!type || !annotationId) return undefined;
  return annotationId.startsWith(`${type}:`) ? annotationId : `${type}:${annotationId}`;
};

const imageIdsForSeries = (series: DicomSeries): string[] =>
  series.instances.map((instance) => {
    const existing = instanceImageIds.get(instance.instanceId);
    if (existing) return existing;
    const imageId = instance.file
      ? wadouri.fileManager.add(instance.file)
      : instance.imageUrl
        ? `wadouri:${instance.imageUrl}`
        : undefined;
    if (!imageId) {
      throw new Error(`Instance ${instance.instanceId} has no local pixel source.`);
    }
    imageReferences.set(imageId, {
      seriesId: series.id,
      instanceId: instance.instanceId,
      frameOfReferenceId: series.frameOfReferenceId,
      spacingTrusted: Boolean(
        series.geometry.pixelSpacing?.length === 2 &&
          series.geometry.pixelSpacing.every((value) => Number.isFinite(value) && value > 0),
      ),
    });
    instanceImageIds.set(instance.instanceId, imageId);
    return imageId;
  });

export const createMeasurementEvidencePacket = (): MeasurementEvidencePacket => {
  const measurements: RawMeasurementAnnotation[] = annotation.state.getAllAnnotations()
    .filter((item) =>
      [LengthTool.toolName, BidirectionalTool.toolName, EllipticalROITool.toolName].includes(
        item.metadata?.toolName ?? '',
      ),
    )
    .map((item) => {
      const toolName = item.metadata?.toolName;
      const type = measurementTypeForToolName(toolName);
      if (!type) throw new Error('Unsupported measurement annotation type.');
      return {
        annotationId: item.annotationUID,
        type,
        referencedImageId: item.metadata?.referencedImageId,
        worldPoints: item.data.handles?.points?.map((point) => Array.from(point)),
      };
    });
  return buildMeasurementEvidencePacket(measurements, imageReferences);
};

export const removeMeasurementAnnotation = (trackingId: string): boolean => {
  const target = annotation.state
    .getAllAnnotations()
    .find(
      (item) =>
        annotationTrackingId(item.metadata?.toolName, item.annotationUID) === trackingId,
    );
  if (!target?.annotationUID) return false;
  annotation.state.removeAnnotation(target.annotationUID);
  return true;
};

export const resetLocalImagingSession = (): void => {
  annotation.state.removeAllAnnotations();
  imageReferences.clear();
  instanceImageIds.clear();
  cache.purgeCache();
  wadouri.dataSetCacheManager.purge();
  wadouri.fileManager.purge();
};

export const subscribeToMeasurementChanges = (listener: () => void): (() => void) => {
  const events = [
    ToolEnums.Events.ANNOTATION_COMPLETED,
    ToolEnums.Events.ANNOTATION_MODIFIED,
    ToolEnums.Events.ANNOTATION_REMOVED,
  ];
  let animationFrame: number | undefined;
  const notify = () => {
    if (animationFrame !== undefined) return;
    animationFrame = requestAnimationFrame(() => {
      animationFrame = undefined;
      listener();
    });
  };
  events.forEach((eventName) => eventTarget.addEventListener(eventName, notify));
  return () => {
    if (animationFrame !== undefined) cancelAnimationFrame(animationFrame);
    events.forEach((eventName) => eventTarget.removeEventListener(eventName, notify));
  };
};

export const restoreMeasurementEvidencePacket = (
  viewportId: string,
  seriesId: string,
  packet?: MeasurementEvidencePacket,
): number => {
  if (!packet) return 0;
  const existing = new Set(
    annotation.state.getAllAnnotations().map((item) => item.annotationUID).filter(Boolean),
  );
  let restored = 0;
  packet.measurements.forEach((measurement) => {
    if (measurement.source.series_id !== seriesId || existing.has(measurement.tracking_id)) return;
    const referencedImageId = instanceImageIds.get(measurement.source.instance_id);
    if (!referencedImageId) return;
    if (measurement.type === 'bidirectional') {
      const points = measurement.geometry.world_points as [
        Types.Point3,
        Types.Point3,
        Types.Point3,
        Types.Point3,
      ];
      BidirectionalTool.hydrate(viewportId, [[points[0], points[1]], [points[2], points[3]]], {
        annotationUID: measurement.tracking_id,
        referencedImageId,
      });
    } else if (measurement.type === 'elliptical_roi') {
      EllipticalROITool.hydrate(
        viewportId,
        measurement.geometry.world_points as [
          Types.Point3,
          Types.Point3,
          Types.Point3,
          Types.Point3,
        ],
        {
          annotationUID: measurement.tracking_id,
          referencedImageId,
        },
      );
    } else {
      LengthTool.hydrate(
        viewportId,
        measurement.geometry.world_points as [Types.Point3, Types.Point3],
        {
          annotationUID: measurement.tracking_id,
          referencedImageId,
        },
      );
    }
    existing.add(measurement.tracking_id);
    restored += 1;
  });
  return restored;
};

export const createStackViewport = async (
  engineId: string,
  viewportId: string,
  element: HTMLDivElement,
  series: DicomSeries,
  primaryTool: ViewerTool,
  initialIndex?: number,
): Promise<{
  engine: RenderingEngine;
  viewport: Types.IStackViewport;
  imageIds: string[];
  tools: ViewportToolController;
}> => {
  await initializeCornerstone();
  const engine = new RenderingEngine(engineId);
  engine.enableElement({
    viewportId,
    type: Enums.ViewportType.STACK,
    element,
    defaultOptions: {
      background: [0.02, 0.03, 0.05] as Types.Point3,
    },
  });
  const viewport = engine.getViewport(viewportId) as Types.IStackViewport;
  const toolGroupId = `${engineId}-tools`;
  const toolGroup = ToolGroupManager.createToolGroup(toolGroupId);
  if (!toolGroup) throw new Error('Unable to create the local viewer tool group.');
  Object.values(toolClasses).forEach((toolClass) => toolGroup.addTool(toolClass.toolName));
  toolGroup.addViewport(viewportId, engineId);

  const setPrimaryTool = (tool: ViewerTool) => {
    Object.values(toolClasses).forEach((toolClass) =>
      toolGroup.setToolPassive(toolClass.toolName, { removeAllBindings: true }),
    );
    toolGroup.setToolActive(toolClasses[tool].toolName, {
      bindings: [{ mouseButton: ToolEnums.MouseBindings.Primary }],
    });
  };
  setPrimaryTool(primaryTool);

  const imageIds = imageIdsForSeries(series);
  const startIndex =
    initialIndex === undefined
      ? Math.floor(imageIds.length / 2)
      : Math.max(0, Math.min(Math.trunc(initialIndex), imageIds.length - 1));
  await viewport.setStack(imageIds, startIndex);
  viewport.render();
  return {
    engine,
    viewport,
    imageIds,
    tools: {
      setPrimaryTool,
      destroy: () => ToolGroupManager.destroyToolGroup(toolGroupId),
    },
  };
};

const MPR_PAINT_TOOL = 'ScanViewManualPaint';
const MPR_ERASE_TOOL = 'ScanViewManualErase';

const normalizeDICOMText = (value: string, name: string, maximum: number): string => {
  const normalized = value.trim().replace(/\s+/g, ' ');
  if (!normalized) throw new Error(`${name} is required.`);
  if (normalized.length > maximum) throw new Error(`${name} must be ${maximum} characters or fewer.`);
  if (/[\\\u0000-\u001f\u007f]/u.test(normalized)) {
    throw new Error(`${name} cannot contain a backslash or control character.`);
  }
  return normalized;
};

const waitForVolumeLoad = (
  volume: Types.IImageVolume,
  signal: AbortSignal,
): Promise<void> => {
  if (volume.loadStatus?.loaded) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const imageIds = new Set(volume.imageIds);
    const cleanup = () => {
      clearTimeout(timeout);
      eventTarget.removeEventListener(Enums.Events.IMAGE_VOLUME_LOADING_COMPLETED, onCompleted);
      eventTarget.removeEventListener(Enums.Events.IMAGE_LOAD_ERROR, onError);
      signal.removeEventListener('abort', onAbort);
    };
    const finish = (error?: Error) => {
      cleanup();
      if (error) reject(error);
      else resolve();
    };
    const onCompleted = (event: Event) => {
      const detail = (event as CustomEvent<{ volumeId?: string }>).detail;
      if (detail?.volumeId !== volume.volumeId) return;
      finish();
    };
    const onError = (event: Event) => {
      const detail = (event as CustomEvent<{ imageId?: string }>).detail;
      if (!detail?.imageId || !imageIds.has(detail.imageId)) return;
      finish(new Error('A native source frame could not be loaded for DICOM SEG export.'));
    };
    const onAbort = () => finish(new Error('Native source loading was cancelled.'));
    eventTarget.addEventListener(Enums.Events.IMAGE_VOLUME_LOADING_COMPLETED, onCompleted);
    eventTarget.addEventListener(Enums.Events.IMAGE_LOAD_ERROR, onError);
    signal.addEventListener('abort', onAbort, { once: true });
    const timeout = window.setTimeout(
      () => finish(new Error('Timed out while loading native source frames for DICOM SEG export.')),
      120_000,
    );
    volume.load();
    if (volume.loadStatus?.loaded) {
      finish();
    }
  });
};

const scalarMask = (volume: Types.IImageVolume): ArrayLike<number> => {
  const values =
    volume.voxelManager?.getCompleteScalarDataArray?.() ??
    volume.voxelManager?.getScalarData();
  if (!values) throw new Error('The local manual labelmap is unavailable.');
  return values as ArrayLike<number>;
};

const segmentationStats = (
  values: ArrayLike<number>,
  voxelVolumeMm3: number,
): ManualSegmentationStats => {
  let foregroundVoxels = 0;
  for (let index = 0; index < values.length; index += 1) {
    const value = Number(values[index]);
    if (value !== 0 && value !== 1) {
      throw new Error('The v1 manual labelmap must remain strictly binary.');
    }
    foregroundVoxels += value;
  }
  const volumeMm3 = foregroundVoxels * voxelVolumeMm3;
  return {
    foregroundVoxels,
    voxelVolumeMm3,
    volumeMm3,
    volumeMl: volumeMm3 / 1000,
  };
};

const buildDicomSeg = async ({
  sourceVolume,
  dimensions,
  maskValues,
  artifactId,
  trackingUid,
  label,
  targetDefinition,
}: {
  sourceVolume: Types.IImageVolume;
  dimensions: Types.Point3;
  maskValues: ArrayLike<number>;
  artifactId: string;
  trackingUid: string;
  label: string;
  targetDefinition: string;
}): Promise<Uint8Array> => {
  const rows = dimensions[1];
  const columns = dimensions[0];
  const frameLength = rows * columns;
  const labelmaps2D = Array.from({ length: dimensions[2] }, (_, frameIndex) => {
    const start = frameIndex * frameLength;
    const pixelData = new Uint8Array(frameLength);
    const segmentsOnLabelmap = new Set<number>();
    for (let index = 0; index < frameLength; index += 1) {
      const value = Number(maskValues[start + index]);
      if (value !== 0 && value !== 1) {
        throw new Error('The v1 DICOM SEG export requires a binary labelmap.');
      }
      pixelData[index] = value;
      if (value === 1) segmentsOnLabelmap.add(1);
    }
    return {
      rows,
      columns,
      pixelData,
      segmentsOnLabelmap: Array.from(segmentsOnLabelmap),
    };
  });
  if (!labelmaps2D.some((frame) => frame.segmentsOnLabelmap.length > 0)) {
    throw new Error('Paint at least one voxel before exporting evidence.');
  }
  const recommendedColor = dcmjs.data.Colors.rgb2DICOMLAB([1, 0.31, 0.47]).map(Math.round);
  const metadata: Array<Record<string, unknown> | undefined> = [];
  metadata[1] = {
    SegmentNumber: '1',
    SegmentLabel: label,
    SegmentDescription: targetDefinition,
    SegmentAlgorithmType: 'MANUAL',
    TrackingID: artifactId,
    TrackingUID: trackingUid,
    RecommendedDisplayCIELabValue: recommendedColor,
    SegmentedPropertyCategoryCodeSequence: {
      CodeValue: '49755003',
      CodingSchemeDesignator: 'SCT',
      CodeMeaning: 'Morphologically Abnormal Structure',
    },
    SegmentedPropertyTypeCodeSequence: {
      CodeValue: '52988006',
      CodingSchemeDesignator: 'SCT',
      CodeMeaning: 'Lesion',
    },
  };
  const labelmap3D = {
    segmentsOnLabelmap: [1],
    metadata,
    labelmaps2D,
  };
  const referencedImages = sourceVolume.getCornerstoneImages();
  if (
    referencedImages.length !== dimensions[2] ||
    referencedImages.some((image) => !image)
  ) {
    throw new Error('Every native source frame must be loaded before DICOM SEG export.');
  }
  const sourceGeometryByInstance = new Map<
    string,
    {
      sopClassUid: string;
      imagePositionPatient: [number, number, number];
      imageOrientationPatient: [number, number, number, number, number, number];
      pixelSpacing: [number, number];
      sliceThickness: number;
      sourceIndex: number;
    }
  >();
  referencedImages.forEach((image, sourceIndex) => {
    const sopCommon = metaData.get(Enums.MetadataModules.SOP_COMMON, image.imageId) as
      | { sopClassUID?: string; sopInstanceUID?: string }
      | undefined;
    const imageData = metaData.get(Enums.MetadataModules.IMAGE_DATA, image.imageId) as
      | { SOPClassUID?: string; SOPInstanceUID?: string }
      | undefined;
    const plane = metaData.get(Enums.MetadataModules.IMAGE_PLANE, image.imageId) as
      | {
          imagePositionPatient?: number[];
          imageOrientationPatient?: number[];
          rowCosines?: number[];
          columnCosines?: number[];
          pixelSpacing?: number[];
          rowPixelSpacing?: number;
          columnPixelSpacing?: number;
          sliceThickness?: number;
        }
      | undefined;
    const sopClassUid = sopCommon?.sopClassUID ?? imageData?.SOPClassUID;
    const sopInstanceUid = sopCommon?.sopInstanceUID ?? imageData?.SOPInstanceUID;
    const position = plane?.imagePositionPatient;
    const orientation =
      plane?.imageOrientationPatient ??
      (plane?.rowCosines?.length === 3 && plane.columnCosines?.length === 3
        ? [...plane.rowCosines, ...plane.columnCosines]
        : undefined);
    const pixelSpacing =
      plane?.pixelSpacing ??
      (Number.isFinite(plane?.rowPixelSpacing) && Number.isFinite(plane?.columnPixelSpacing)
        ? [plane!.rowPixelSpacing!, plane!.columnPixelSpacing!]
        : undefined);
    const sliceThickness = plane?.sliceThickness;
    if (
      !sopClassUid ||
      !sopInstanceUid ||
      position?.length !== 3 ||
      !position.every(Number.isFinite) ||
      orientation?.length !== 6 ||
      !orientation.every(Number.isFinite) ||
      pixelSpacing?.length !== 2 ||
      !pixelSpacing.every((value) => Number.isFinite(value) && value > 0) ||
      !Number.isFinite(sliceThickness) ||
      sliceThickness! <= 0 ||
      sourceGeometryByInstance.has(sopInstanceUid)
    ) {
      throw new Error('Exact loaded source geometry is unavailable for DICOM SEG export.');
    }
    sourceGeometryByInstance.set(sopInstanceUid, {
      sopClassUid,
      imagePositionPatient: [position[0], position[1], position[2]],
      imageOrientationPatient: [
        orientation[0],
        orientation[1],
        orientation[2],
        orientation[3],
        orientation[4],
        orientation[5],
      ],
      pixelSpacing: [pixelSpacing[0], pixelSpacing[1]],
      sliceThickness: sliceThickness!,
      sourceIndex,
    });
  });
  const generated = adaptersSEG.Cornerstone3D.Segmentation.generateSegmentation(
    referencedImages,
    labelmap3D,
    metaData,
    {
      sopClassUID: '1.2.840.10008.5.1.4.1.1.66.4',
      transferSyntaxUid: '1.2.840.10008.1.2.1',
    },
  );
  const dataset = generated.dataset as Record<string, unknown> & {
    SegmentSequence?: Array<Record<string, unknown>> | Record<string, unknown>;
  };
  dataset.SegmentsOverlap = 'NO';
  dataset.SpecificCharacterSet = 'ISO_IR 192';
  dataset.ContentLabel = 'SCANVIEW_SEG';
  dataset.ContentDescription = 'Unreviewed local manual lesion ROI evidence';
  dataset.SeriesDescription = 'ScanView unreviewed manual lesion ROI';
  dataset.Manufacturer = 'ScanView local';
  dataset.ManufacturerModelName = 'ScanView';
  dataset.SoftwareVersions = '0.14.0';
  const segmentItem = Array.isArray(dataset.SegmentSequence)
    ? dataset.SegmentSequence[0]
    : dataset.SegmentSequence;
  if (!segmentItem) throw new Error('The local DICOM SEG adapter omitted its segment description.');
  Object.assign(segmentItem, {
    SegmentNumber: '1',
    SegmentLabel: label,
    SegmentDescription: targetDefinition,
    SegmentAlgorithmType: 'MANUAL',
    TrackingID: artifactId,
    TrackingUID: trackingUid,
  });
  repairDicomSegFrameSourceClasses(dataset, sourceGeometryByInstance);
  return new Uint8Array(dcmjs.data.datasetToDict(dataset).write());
};

export const createMprViewports = async (
  engineId: string,
  elements: Record<MprOrientation, HTMLDivElement>,
  series: DicomSeries,
  primaryTool: MprTool,
  readonlySegmentation?: ReadonlyMprSegmentation,
): Promise<MprViewportController> => {
  await initializeCornerstone();
  const engine = new RenderingEngine(engineId);
  const volumeId = `cornerstoneStreamingImageVolume:${engineId}-volume`;
  const segmentationId = `${engineId}-manual-segmentation`;
  const labelmapVolumeId = `${engineId}-manual-labelmap`;
  const toolGroupId = `${engineId}-tools`;
  const evidenceEligibility = assessLesionVolumeEligibility(series);
  const loadAbortController = new AbortController();
  const viewportIds = (['axial', 'coronal', 'sagittal'] as const).map(
    (id) => `${engineId}-${id}`,
  );
  let segmentationAdded = false;
  let labelmapVolume: Types.IImageVolume | undefined;
  const removeVolume = () => {
    if (cache.getVolumeLoadObject(labelmapVolumeId)) cache.removeVolumeLoadObject(labelmapVolumeId);
    if (cache.getVolumeLoadObject(volumeId)) cache.removeVolumeLoadObject(volumeId);
  };
  const removeSegmentation = () => {
    if (!segmentationAdded) return;
    viewportIds.forEach((viewportId) => {
      segmentation.removeLabelmapRepresentation(viewportId, segmentationId, true);
    });
    segmentation.removeSegmentation(segmentationId);
    segmentationAdded = false;
  };
  const orientations: Array<{
    id: MprOrientation;
    axis: Enums.OrientationAxis;
  }> = [
    { id: 'axial', axis: Enums.OrientationAxis.AXIAL },
    { id: 'coronal', axis: Enums.OrientationAxis.CORONAL },
    { id: 'sagittal', axis: Enums.OrientationAxis.SAGITTAL },
  ];
  try {
    engine.setViewports(
      orientations.map(({ id, axis }) => ({
        viewportId: `${engineId}-${id}`,
        type: Enums.ViewportType.ORTHOGRAPHIC,
        element: elements[id],
        defaultOptions: {
          background: [0.02, 0.03, 0.05] as Types.Point3,
          orientation: axis,
        },
      })),
    );
    const imageIds = imageIdsForSeries(series);
    const volume = await volumeLoader.createAndCacheVolume(volumeId, { imageIds });
    let sourceLoadError: Error | undefined;
    const sourceLoaded = evidenceEligibility.eligible
      ? waitForVolumeLoad(volume, loadAbortController.signal).catch((error: unknown) => {
          sourceLoadError =
            error instanceof Error ? error : new Error('A native source frame could not be loaded.');
        })
      : Promise.resolve();
    await setVolumesForViewports(engine, [{ volumeId }], viewportIds);

    if (evidenceEligibility.eligible) {
      await sourceLoaded;
      if (sourceLoadError) throw sourceLoadError;
      if (volume.numVoxels > MAX_MANUAL_LABELMAP_VOXELS) {
        throw new Error('This source exceeds the 64 Mi-voxel manual segmentation safety bound.');
      }
      labelmapVolume = volumeLoader.createAndCacheDerivedLabelmapVolume(volumeId, {
        volumeId: labelmapVolumeId,
      });
      if (readonlySegmentation) {
        if (
          readonlySegmentation.mask.length !== volume.numVoxels ||
          readonlySegmentation.foregroundVoxels < 1 ||
          readonlySegmentation.foregroundVoxels > volume.numVoxels
        ) {
          throw new Error('The read-only native mask does not match the exact source grid.');
        }
        let foreground = 0;
        for (const value of readonlySegmentation.mask) {
          if (value !== 0 && value !== 1) {
            throw new Error('The read-only native mask must remain strictly binary.');
          }
          foreground += value;
        }
        if (foreground !== readonlySegmentation.foregroundVoxels) {
          throw new Error('The read-only native mask foreground count changed.');
        }
        const volumeOrderedInstanceIds = volume.imageIds.map((imageId) => {
          const reference = imageReferences.get(imageId);
          if (!reference || reference.seriesId !== series.id) {
            throw new Error('The read-only mask volume source identity is unavailable.');
          }
          return reference.instanceId;
        });
        const sourceRows = series.geometry.rows;
        const sourceColumns = series.geometry.columns;
        if (
          !Number.isSafeInteger(sourceRows) ||
          !Number.isSafeInteger(sourceColumns) ||
          !sourceRows ||
          !sourceColumns
        ) {
          throw new Error('The read-only mask source matrix is unavailable.');
        }
        const ownedMask = reorderDenseMaskSlices({
          mask: readonlySegmentation.mask,
          rows: sourceRows,
          columns: sourceColumns,
          sourceOrderedInstanceIds: readonlySegmentation.orderedInstanceIds,
          volumeOrderedInstanceIds,
        });
        if (!labelmapVolume.voxelManager?.setCompleteScalarDataArray) {
          throw new Error('The local read-only native-mask labelmap is unavailable.');
        }
        labelmapVolume.voxelManager.setCompleteScalarDataArray(ownedMask);
        labelmapVolume.modified();
      }
      segmentation.addSegmentations([
        {
          segmentationId,
          representation: {
            type: ToolEnums.SegmentationRepresentations.Labelmap,
            data: {
              volumeId: labelmapVolumeId,
              referencedVolumeId: volumeId,
            },
          },
          config: {
            label: readonlySegmentation?.label ?? 'Manual unreviewed region',
            segments: {
              1: {
                label: readonlySegmentation?.label ?? 'Manual region 1',
                active: !readonlySegmentation,
                locked: Boolean(readonlySegmentation),
                cachedStats: {},
              },
            },
          },
        },
      ]);
      segmentationAdded = true;
      viewportIds.forEach((viewportId) => {
        segmentation.addLabelmapRepresentationToViewport(viewportId, [{ segmentationId }]);
        if (!readonlySegmentation) {
          segmentation.activeSegmentation.setActiveSegmentation(viewportId, segmentationId);
        }
      });
      if (readonlySegmentation) {
        segmentation.segmentLocking.setSegmentIndexLocked(segmentationId, 1, true);
        segmentation.triggerSegmentationEvents.triggerSegmentationDataModified(segmentationId);
      } else {
        segmentation.segmentIndex.setActiveSegmentIndex(segmentationId, 1);
      }
    }

    const toolGroup = ToolGroupManager.createToolGroup(toolGroupId);
    if (!toolGroup) throw new Error('Unable to create the local MPR tool group.');
    [WindowLevelTool, PanTool, ZoomTool, StackScrollTool].forEach((toolClass) =>
      toolGroup.addTool(toolClass.toolName),
    );
    toolGroup.addTool(CrosshairsTool.toolName, mprCrosshairConfiguration);
    if (evidenceEligibility.eligible && !readonlySegmentation) {
      toolGroup.addToolInstance(MPR_PAINT_TOOL, BrushTool.toolName, {
        activeStrategy: 'FILL_INSIDE_CIRCLE',
        brushSize: 12,
      });
      toolGroup.addToolInstance(MPR_ERASE_TOOL, BrushTool.toolName, {
        activeStrategy: 'ERASE_INSIDE_CIRCLE',
        brushSize: 12,
      });
    }
    viewportIds.forEach((viewportId) => toolGroup.addViewport(viewportId, engineId));
    const mprToolClasses: Partial<Record<MprTool, string>> = {
      crosshairs: CrosshairsTool.toolName,
      window: WindowLevelTool.toolName,
      pan: PanTool.toolName,
      zoom: ZoomTool.toolName,
      ...(evidenceEligibility.eligible && !readonlySegmentation
        ? { paint: MPR_PAINT_TOOL, erase: MPR_ERASE_TOOL }
        : {}),
    };
    const setPrimaryTool = (tool: MprTool) => {
      toolGroup.setToolPassive(StackScrollTool.toolName, { removeAllBindings: true });
      Object.values(mprToolClasses).forEach((toolName) =>
        toolGroup.setToolPassive(toolName, { removeAllBindings: true }),
      );
      if (tool === 'crop') {
        toolGroup.setToolActive(StackScrollTool.toolName, {
          bindings: [{ mouseButton: ToolEnums.MouseBindings.Wheel }],
        });
        return;
      }
      const toolName = mprToolClasses[tool] ?? CrosshairsTool.toolName;
      toolGroup.setToolActive(toolName, {
        bindings: [
          { mouseButton: ToolEnums.MouseBindings.Primary },
          ...(tool === 'zoom'
            ? [{ mouseButton: ToolEnums.MouseBindings.Wheel }]
            : []),
        ],
      });
      if (tool !== 'zoom') {
        toolGroup.setToolActive(StackScrollTool.toolName, {
          bindings: [{ mouseButton: ToolEnums.MouseBindings.Wheel }],
        });
      }
    };
    setPrimaryTool(primaryTool);
    const viewportsByOrientation = Object.fromEntries(
      orientations.map(({ id }) => [
        id,
        engine.getViewport(`${engineId}-${id}`) as Types.IVolumeViewport,
      ]),
    ) as Record<MprOrientation, Types.IVolumeViewport>;
    const viewports = Object.values(viewportsByOrientation);
    const crosshairs = toolGroup.getToolInstance(CrosshairsTool.toolName) as CrosshairsTool;
    viewports.forEach((viewport) => {
      viewport.resetCamera();
      viewport.render();
    });
    let sharedCrop:
      | {
          center: Types.Point3;
          parallelScale: number;
        }
      | undefined;
    const cropSpacing = volume.spacing.filter((value) => Number.isFinite(value) && value > 0);
    const minimumCropParallelScale = Math.max(
      0.1,
      (cropSpacing.length ? Math.min(...cropSpacing) : 0.1) * 4,
    );
    const applySharedCrop = () => {
      if (!sharedCrop) return;
      viewports.forEach((viewport) => {
        viewport.resetCamera();
        const camera = viewport.getCamera();
        const { focalPoint, position, parallelScale } = camera;
        if (
          !Number.isFinite(parallelScale) ||
          !focalPoint ||
          focalPoint.length !== 3 ||
          !position ||
          position.length !== 3
        ) {
          return;
        }
        const offset = sharedCrop!.center.map((value, axis) => value - focalPoint[axis]);
        viewport.setCamera({
          focalPoint: [...sharedCrop!.center] as Types.Point3,
          position: position.map((value, axis) => value + offset[axis]) as Types.Point3,
          parallelScale: sharedCrop!.parallelScale,
        });
        viewport.render();
      });
    };
    const sliceSpacingMm = series.geometry.pixelSpacing
      ? Math.abs(volume.spacing[2])
      : Number.NaN;
    if (!Number.isFinite(sliceSpacingMm) || sliceSpacingMm <= 0) {
      throw new Error('The native source slice spacing is unavailable.');
    }
    const voxelVolumeMm3 =
      series.geometry.pixelSpacing![0] * series.geometry.pixelSpacing![1] * sliceSpacingMm;
    let segmentationDirty = false;
    const normalizedPoint = (point: MprPatientPoint): NormalizedMprPoint | undefined => {
      const index = volume.imageData?.worldToIndex(point as Types.Point3);
      if (!index || index.length !== 3 || !index.every(Number.isFinite)) return undefined;
      return [0, 1, 2].map((axis) =>
        Math.max(0, Math.min(1, index[axis] / Math.max(1, volume.dimensions[axis] - 1))),
      ) as NormalizedMprPoint;
    };
    const currentStats = () =>
      labelmapVolume
        ? segmentationStats(scalarMask(labelmapVolume), voxelVolumeMm3)
        : { foregroundVoxels: 0, voxelVolumeMm3: 0, volumeMm3: 0, volumeMl: 0 };
    return {
      setPrimaryTool,
      subscribeToPatientPoint: (listener) => {
        const emitCurrentPoint = () => {
          const point = crosshairs.toolCenter;
          if (point?.length === 3 && point.every(Number.isFinite)) {
            listener([point[0], point[1], point[2]]);
          }
        };
        const onCenterChanged = (event: Event) => {
          const detail = (event as CustomEvent<{ toolGroupId?: string }>).detail;
          if (detail?.toolGroupId === toolGroupId) emitCurrentPoint();
        };
        eventTarget.addEventListener(ToolEnums.Events.CROSSHAIR_TOOL_CENTER_CHANGED, onCenterChanged);
        emitCurrentPoint();
        return () =>
          eventTarget.removeEventListener(
            ToolEnums.Events.CROSSHAIR_TOOL_CENTER_CHANGED,
            onCenterChanged,
          );
      },
      subscribeToNormalizedPoint: (listener) => {
        const emitCurrentPoint = () => {
          const point = crosshairs.toolCenter;
          if (point?.length !== 3 || !point.every(Number.isFinite)) return;
          const normalized = normalizedPoint([point[0], point[1], point[2]]);
          if (normalized) listener(normalized);
        };
        const onCenterChanged = (event: Event) => {
          const detail = (event as CustomEvent<{ toolGroupId?: string }>).detail;
          if (detail?.toolGroupId === toolGroupId) emitCurrentPoint();
        };
        eventTarget.addEventListener(ToolEnums.Events.CROSSHAIR_TOOL_CENTER_CHANGED, onCenterChanged);
        emitCurrentPoint();
        return () =>
          eventTarget.removeEventListener(
            ToolEnums.Events.CROSSHAIR_TOOL_CENTER_CHANGED,
            onCenterChanged,
          );
      },
      setPatientPoint: (point) => {
        if (point.length !== 3 || !point.every(Number.isFinite)) {
          throw new Error('Patient-space location must contain three finite LPS coordinates.');
        }
        const index = volume.imageData?.worldToIndex(point as Types.Point3);
        if (
          !index ||
          index.length !== 3 ||
          !index.every(
            (value, axis) =>
              Number.isFinite(value) && value >= -0.5 && value <= volume.dimensions[axis] - 0.5,
          )
        ) {
          throw new Error('Patient-space location is outside this local volume.');
        }
        crosshairs.setToolCenter([point[0], point[1], point[2]], true);
      },
      setNormalizedPoint: (point) => {
        if (
          point.length !== 3 ||
          !point.every((value) => Number.isFinite(value) && value >= 0 && value <= 1)
        ) {
          throw new Error('Normalized native-grid location must remain within zero and one.');
        }
        const world = volume.imageData?.indexToWorld(
          point.map((value, axis) => value * Math.max(1, volume.dimensions[axis] - 1)) as Types.Point3,
        );
        if (!world || world.length !== 3 || !world.every(Number.isFinite)) {
          throw new Error('The normalized native-grid location cannot be resolved.');
        }
        crosshairs.setToolCenter([world[0], world[1], world[2]], true);
      },
      fitToCanvasRectangle: (orientation, start, end) => {
        const viewport = viewportsByOrientation[orientation];
        const element = elements[orientation];
        const camera = viewport.getCamera();
        const { focalPoint, position, parallelScale } = camera;
        if (
          !Number.isFinite(parallelScale) ||
          !focalPoint ||
          focalPoint.length !== 3 ||
          !position ||
          position.length !== 3
        ) {
          return false;
        }
        const fit = calculateMprCropFit({
          start,
          end,
          viewportWidth: element.clientWidth,
          viewportHeight: element.clientHeight,
          parallelScale: parallelScale!,
        });
        if (!fit) return false;
        const centerWorld = viewport.canvasToWorld(fit.center);
        if (centerWorld.length !== 3 || !centerWorld.every(Number.isFinite)) {
          return false;
        }
        sharedCrop = {
          center: [...centerWorld] as Types.Point3,
          parallelScale: Math.max(minimumCropParallelScale, fit.parallelScale),
        };
        crosshairs.setToolCenter([...centerWorld] as Types.Point3, true);
        applySharedCrop();
        return true;
      },
      reset: () => {
        sharedCrop = undefined;
        viewports.forEach((viewport) => {
          viewport.resetCamera();
          viewport.resetProperties();
        });
        crosshairs.resetCrosshairs();
        viewports.forEach((viewport) => viewport.render());
      },
      setBrushSize: (size) => {
        if (!labelmapVolume || readonlySegmentation) return;
        const bounded = Math.max(1, Math.min(50, Math.round(size)));
        toolUtilities.segmentation.setBrushSizeForToolGroup(
          toolGroupId,
          bounded,
          MPR_PAINT_TOOL,
        );
        toolUtilities.segmentation.setBrushSizeForToolGroup(
          toolGroupId,
          bounded,
          MPR_ERASE_TOOL,
        );
      },
      clearSegmentation: () => {
        if (labelmapVolume && !readonlySegmentation) {
          segmentation.helpers.clearSegmentValue(segmentationId, 1);
          segmentationDirty = false;
        }
      },
      subscribeToSegmentationStats: (listener) => {
        if (!labelmapVolume) {
          listener(currentStats());
          return () => undefined;
        }
        let pending: number | undefined;
        const emit = () => {
          if (pending !== undefined) window.clearTimeout(pending);
          pending = window.setTimeout(() => {
            pending = undefined;
            listener(currentStats());
          }, 300);
        };
        const onModified = (event: Event) => {
          const detail = (event as CustomEvent<{ segmentationId?: string }>).detail;
          if (detail?.segmentationId === segmentationId) {
            segmentationDirty = !readonlySegmentation;
            emit();
          }
        };
        eventTarget.addEventListener(ToolEnums.Events.SEGMENTATION_DATA_MODIFIED, onModified);
        listener(
          readonlySegmentation
            ? currentStats()
            : { foregroundVoxels: 0, voxelVolumeMm3, volumeMm3: 0, volumeMl: 0 },
        );
        return () => {
          if (pending !== undefined) window.clearTimeout(pending);
          eventTarget.removeEventListener(
            ToolEnums.Events.SEGMENTATION_DATA_MODIFIED,
            onModified,
          );
        };
      },
      exportSegmentationEvidence: async (label, targetDefinition) => {
        if (readonlySegmentation) {
          throw new Error('Read-only native masks cannot be re-exported as drafts.');
        }
        if (!labelmapVolume || !evidenceEligibility.eligible) {
          throw new Error(evidenceEligibility.reason);
        }
        const normalizedLabel = normalizeDICOMText(label, 'Working region label', 64);
        const normalizedDefinition = normalizeDICOMText(
          targetDefinition,
          'Target definition',
          300,
        );
        await sourceLoaded;
        if (sourceLoadError) throw sourceLoadError;
        const artifactId = `seg_${crypto.randomUUID()}`;
        const trackingUid = dcmjs.data.DicomMetaDictionary.uid();
        const maskValues = scalarMask(labelmapVolume);
        const dicomSegBytes = await buildDicomSeg({
          sourceVolume: volume,
          dimensions: labelmapVolume.dimensions,
          maskValues,
          artifactId,
          trackingUid,
          label: normalizedLabel,
          targetDefinition: normalizedDefinition,
        });
        const orderedInstanceIds = volume.imageIds.map((imageId) => {
          const source = imageReferences.get(imageId);
          if (!source) throw new Error('An ordered native source reference is unavailable.');
          return source.instanceId;
        });
        return buildLesionVolumeArchive({
          series,
          orderedInstanceIds,
          dimensions: [
            labelmapVolume.dimensions[0],
            labelmapVolume.dimensions[1],
            labelmapVolume.dimensions[2],
          ],
          sliceSpacingMm,
          maskValues,
          dicomSegBytes,
          artifactId,
          trackingUid,
          label: normalizedLabel,
          targetDefinition: normalizedDefinition,
        });
      },
      hasSegmentationDraft: () => !readonlySegmentation && segmentationDirty,
      // Preserve ordinary manual cameras across layout changes. A linked crop keeps
      // one physical patient-space field size and center across all three panes.
      resize: () => {
        engine.resize(true, true);
        applySharedCrop();
      },
      destroy: () => {
        loadAbortController.abort();
        removeSegmentation();
        ToolGroupManager.destroyToolGroup(toolGroupId);
        engine.destroy();
        removeVolume();
      },
    };
  } catch (error) {
    loadAbortController.abort();
    removeSegmentation();
    ToolGroupManager.destroyToolGroup(toolGroupId);
    engine.destroy();
    removeVolume();
    throw error;
  }
};
