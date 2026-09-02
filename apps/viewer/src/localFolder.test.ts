import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  collectLocalDirectoryFiles,
  directoryHandleForSession,
  pickLocalDirectory,
  restoreDirectoryHandle,
  supportsLocalDirectoryPicker,
  type LocalDirectoryHandle,
  type LocalFileHandle,
} from './localFolder';

const fileHandle = (name: string): LocalFileHandle => ({
  kind: 'file',
  name,
  getFile: vi.fn(async () => ({ name } as File)),
});

const directoryHandle = (
  name: string,
  entries: Array<LocalDirectoryHandle | LocalFileHandle>,
): LocalDirectoryHandle => ({
  kind: 'directory',
  name,
  async *values() {
    yield* entries;
  },
});

describe('local folder selection', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('uses the local directory picker when the browser provides it', async () => {
    const handle = directoryHandle('scan', [fileHandle('image.dcm')]);
    const showDirectoryPicker = vi.fn(async () => handle);
    vi.stubGlobal('window', { showDirectoryPicker });
    const progress: number[] = [];

    expect(supportsLocalDirectoryPicker()).toBe(true);
    await expect(pickLocalDirectory((count) => progress.push(count))).resolves.toMatchObject({
      handle,
      files: [{ name: 'image.dcm' }],
    });
    expect(showDirectoryPicker).toHaveBeenCalledWith({ mode: 'read' });
    expect(progress).toEqual([1]);
  });

  it('treats cancelling the local directory picker as a no-op', async () => {
    const showDirectoryPicker = vi.fn(async () => {
      throw new DOMException('Cancelled', 'AbortError');
    });
    vi.stubGlobal('window', { showDirectoryPicker });

    await expect(pickLocalDirectory(() => undefined)).resolves.toBeUndefined();
  });

  it('walks nested local folders without treating them as uploads', async () => {
    const root = directoryHandle('scan', [
      fileHandle('DICOMDIR'),
      directoryHandle('series', [fileHandle('image-2.dcm'), fileHandle('image-1.dcm')]),
    ]);
    const progress: number[] = [];

    const files = await collectLocalDirectoryFiles(root, (count) => progress.push(count));

    expect(files.map((file) => file.name)).toEqual([
      'DICOMDIR',
      'image-2.dcm',
      'image-1.dcm',
    ]);
    expect(progress).toEqual([1, 2, 3]);
  });

  it('skips hidden files and hidden directory trees', async () => {
    const hiddenFile = fileHandle('.DS_Store');
    const hiddenImage = fileHandle('hidden-image.dcm');
    const root = directoryHandle('scan', [
      hiddenFile,
      directoryHandle('.cache', [hiddenImage]),
      fileHandle('visible.dcm'),
    ]);

    const files = await collectLocalDirectoryFiles(root, () => undefined);

    expect(files.map((file) => file.name)).toEqual(['visible.dcm']);
    expect(hiddenFile.getFile).not.toHaveBeenCalled();
    expect(hiddenImage.getFile).not.toHaveBeenCalled();
  });

  it('restores a remembered folder only while its local read permission remains granted', async () => {
    const granted = {
      ...directoryHandle('scan', [fileHandle('image.dcm')]),
      queryPermission: vi.fn(async () => 'granted' as PermissionState),
    };
    const prompt = {
      ...directoryHandle('scan', [fileHandle('image.dcm')]),
      queryPermission: vi.fn(async () => 'prompt' as PermissionState),
    };

    await expect(restoreDirectoryHandle(granted, () => undefined)).resolves.toMatchObject({
      handle: granted,
      files: [{ name: 'image.dcm' }],
    });
    await expect(restoreDirectoryHandle(prompt, () => undefined)).resolves.toBeUndefined();
  });

  it('does not restore a folder remembered by a different local viewer session', () => {
    const handle = directoryHandle('scan', []);

    expect(directoryHandleForSession({ sessionKey: 'current', handle }, 'current')).toBe(handle);
    expect(directoryHandleForSession({ sessionKey: 'previous', handle }, 'current')).toBeUndefined();
  });
});
