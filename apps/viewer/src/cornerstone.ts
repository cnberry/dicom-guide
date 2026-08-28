import { Enums, RenderingEngine, init as initCore, type Types } from '@cornerstonejs/core';
import {
  init as initDicomImageLoader,
  wadouri,
} from '@cornerstonejs/dicom-image-loader';
import {
  Enums as ToolEnums,
  LengthTool,
  PanTool,
  ToolGroupManager,
  WindowLevelTool,
  ZoomTool,
  addTool,
  init as initTools,
} from '@cornerstonejs/tools';
import type { DicomSeries } from './dicom';

let initialization: Promise<void> | undefined;

export type ViewerTool = 'window' | 'pan' | 'zoom' | 'length';

const toolClasses = {
  window: WindowLevelTool,
  pan: PanTool,
  zoom: ZoomTool,
  length: LengthTool,
} as const;

export type ViewportToolController = {
  setPrimaryTool: (tool: ViewerTool) => void;
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
    })();
  }
  return initialization;
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

  const imageIds = series.instances.map((instance) => wadouri.fileManager.add(instance.file));
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
