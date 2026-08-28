import { Enums, RenderingEngine, init as initCore, type Types } from '@cornerstonejs/core';
import {
  init as initDicomImageLoader,
  wadouri,
} from '@cornerstonejs/dicom-image-loader';
import type { DicomSeries } from './dicom';

let initialization: Promise<void> | undefined;

export const initializeCornerstone = (): Promise<void> => {
  if (!initialization) {
    initialization = (async () => {
      await initCore();
      await initDicomImageLoader({
        maxWebWorkers: Math.max(1, Math.min(4, navigator.hardwareConcurrency || 1)),
      });
    })();
  }
  return initialization;
};

export const createStackViewport = async (
  engineId: string,
  viewportId: string,
  element: HTMLDivElement,
  series: DicomSeries,
): Promise<{ engine: RenderingEngine; viewport: Types.IStackViewport; imageIds: string[] }> => {
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
  const imageIds = series.instances.map((instance) => wadouri.fileManager.add(instance.file));
  await viewport.setStack(imageIds, Math.floor(imageIds.length / 2));
  viewport.render();
  return { engine, viewport, imageIds };
};
