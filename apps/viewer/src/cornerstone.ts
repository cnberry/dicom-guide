import {
  Enums,
  RenderingEngine,
  cache,
  eventTarget,
  init as initCore,
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
} from '@cornerstonejs/tools';
import type { DicomSeries } from './dicom';
import {
  buildMeasurementEvidencePacket,
  type ImageSourceReference,
  type MeasurementEvidencePacket,
  type RawMeasurementAnnotation,
} from './measurements';

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

export type MprTool = 'window' | 'pan' | 'zoom';
export type MprOrientation = 'axial' | 'coronal' | 'sagittal';
export type MprViewportController = {
  setPrimaryTool: (tool: MprTool) => void;
  reset: () => void;
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
    })();
  }
  return initialization;
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
      return {
        annotationId: item.annotationUID,
        type:
          toolName === BidirectionalTool.toolName
            ? 'bidirectional'
            : toolName === EllipticalROITool.toolName
              ? 'elliptical_roi'
              : 'length',
        referencedImageId: item.metadata?.referencedImageId,
        worldPoints: item.data.handles?.points?.map((point) => Array.from(point)),
      };
    });
  return buildMeasurementEvidencePacket(measurements, imageReferences);
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
  await viewport.setStack(imageIds, Math.floor(imageIds.length / 2));
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

export const createMprViewports = async (
  engineId: string,
  elements: Record<MprOrientation, HTMLDivElement>,
  series: DicomSeries,
  primaryTool: MprTool,
): Promise<MprViewportController> => {
  await initializeCornerstone();
  const engine = new RenderingEngine(engineId);
  const volumeId = `cornerstoneStreamingImageVolume:${engineId}-volume`;
  const toolGroupId = `${engineId}-tools`;
  const removeVolume = () => {
    if (cache.getVolumeLoadObject(volumeId)) cache.removeVolumeLoadObject(volumeId);
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
    volume.load();
    const viewportIds = orientations.map(({ id }) => `${engineId}-${id}`);
    await setVolumesForViewports(engine, [{ volumeId }], viewportIds);

    const toolGroup = ToolGroupManager.createToolGroup(toolGroupId);
    if (!toolGroup) throw new Error('Unable to create the local MPR tool group.');
    [WindowLevelTool, PanTool, ZoomTool, StackScrollTool].forEach((toolClass) =>
      toolGroup.addTool(toolClass.toolName),
    );
    viewportIds.forEach((viewportId) => toolGroup.addViewport(viewportId, engineId));
    toolGroup.setToolActive(StackScrollTool.toolName, {
      bindings: [{ mouseButton: ToolEnums.MouseBindings.Wheel }],
    });
    const mprToolClasses = {
      window: WindowLevelTool,
      pan: PanTool,
      zoom: ZoomTool,
    } as const;
    const setPrimaryTool = (tool: MprTool) => {
      Object.values(mprToolClasses).forEach((toolClass) =>
        toolGroup.setToolPassive(toolClass.toolName, { removeAllBindings: true }),
      );
      toolGroup.setToolActive(mprToolClasses[tool].toolName, {
        bindings: [{ mouseButton: ToolEnums.MouseBindings.Primary }],
      });
    };
    setPrimaryTool(primaryTool);
    const viewports = viewportIds.map(
      (viewportId) => engine.getViewport(viewportId) as Types.IVolumeViewport,
    );
    viewports.forEach((viewport) => {
      viewport.resetCamera();
      viewport.render();
    });
    return {
      setPrimaryTool,
      reset: () => {
        viewports.forEach((viewport) => {
          viewport.resetProperties();
          viewport.resetCamera();
          viewport.render();
        });
      },
      resize: () => engine.resize(true, false),
      destroy: () => {
        ToolGroupManager.destroyToolGroup(toolGroupId);
        engine.destroy();
        removeVolume();
      },
    };
  } catch (error) {
    ToolGroupManager.destroyToolGroup(toolGroupId);
    engine.destroy();
    removeVolume();
    throw error;
  }
};
