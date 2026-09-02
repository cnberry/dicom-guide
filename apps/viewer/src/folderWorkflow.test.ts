import { describe, expect, it } from 'vitest';
import {
  folderLoadMessage,
  folderViewSelection,
  resetAfterFolderViewTeardown,
} from './folderWorkflow';
import type { DicomSeries } from './dicom';

const series = (id: string, instanceCount: number, eligible = true): DicomSeries => ({
  id,
  studyId: `study-${id}`,
  patientContextId: 'patient-context',
  modality: 'CT',
  description: id,
  imageType: ['ORIGINAL', 'PRIMARY'],
  sourceKind: 'browser-folder',
  frameOfReferenceId: eligible ? `frame-${id}` : undefined,
  geometry: {
    rows: 16,
    columns: 16,
    pixelSpacing: [1, 1],
    sliceThickness: 1,
    orientation: [1, 0, 0, 0, 1, 0],
  },
  instances: Array.from({ length: instanceCount }, (_, index) => ({
    instanceId: `${id}-${index}`,
    instanceNumber: index,
    imagePosition: [0, 0, index],
    rows: 16,
    columns: 16,
    pixelSpacing: [1, 1],
    sliceThickness: 1,
    orientation: [1, 0, 0, 0, 1, 0],
    numberOfFrames: 1,
  })),
});

describe('folder loading workflow', () => {
  it('keeps 3-plane active when an eligible replacement folder finishes loading', () => {
    const selection = folderViewSelection([series('small', 3), series('mpr', 8)], true);

    expect(selection.series?.id).toBe('mpr');
    expect(selection.instanceIndex).toBe(4);
    expect(selection.mprSeriesId).toBe('mpr');
  });

  it('does not enter 3-plane for an ineligible replacement series', () => {
    const selection = folderViewSelection([series('single', 2, false)], true);

    expect(selection.series?.id).toBe('single');
    expect(selection.mprSeriesId).toBeUndefined();
  });

  it('tells the person to wait during both collection and header reading', () => {
    expect(folderLoadMessage({ phase: 'collecting', fileCount: 12, restoring: false })).toBe(
      'Preparing 12 local files…',
    );
    expect(folderLoadMessage({ phase: 'reading', processed: 4, total: 12, restoring: false })).toBe(
      'Reading 4 of 12 local files…',
    );
  });

  it('resets imaging only after mounted folder views have had two frames to tear down', async () => {
    const callbacks: FrameRequestCallback[] = [];
    const scheduleFrame = (callback: FrameRequestCallback) => {
      callbacks.push(callback);
      return callbacks.length;
    };
    let reset = false;

    const pending = resetAfterFolderViewTeardown(() => {
      reset = true;
    }, scheduleFrame);

    expect(reset).toBe(false);
    expect(callbacks).toHaveLength(1);
    callbacks.shift()?.(0);
    expect(reset).toBe(false);
    expect(callbacks).toHaveLength(1);
    callbacks.shift()?.(16);
    await pending;
    expect(reset).toBe(true);
  });

  it('rejects a reset failure after teardown so the folder workflow can handle it', async () => {
    const scheduleFrame = (callback: FrameRequestCallback) => {
      callback(0);
      return 1;
    };

    await expect(
      resetAfterFolderViewTeardown(() => {
        throw new Error('reset failed');
      }, scheduleFrame),
    ).rejects.toThrow('reset failed');
  });
});
