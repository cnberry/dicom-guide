export type LocalFileHandle = {
  kind: 'file';
  name: string;
  getFile: () => Promise<File>;
};

export type LocalDirectoryHandle = {
  kind: 'directory';
  name: string;
  values: () => AsyncIterable<LocalFileHandle | LocalDirectoryHandle>;
  queryPermission?: (options: { mode: 'read' }) => Promise<PermissionState>;
};

export type LocalDirectorySelection = {
  handle: LocalDirectoryHandle;
  files: File[];
};

type LocalDirectoryPicker = (options: { mode: 'read' }) => Promise<LocalDirectoryHandle>;
type PickerWindow = Window & { showDirectoryPicker?: LocalDirectoryPicker };
type RememberedDirectory = { sessionKey: string; handle: LocalDirectoryHandle };

const databaseName = 'dicom-guide-local-folder';
const databaseVersion = 1;
const handleStoreName = 'handles';
const currentHandleKey = 'current';

const isAbortError = (error: unknown): boolean =>
  error instanceof DOMException && error.name === 'AbortError';

const openHandleDatabase = async (): Promise<IDBDatabase | undefined> => {
  if (typeof indexedDB === 'undefined') return undefined;
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(databaseName, databaseVersion);
    request.onupgradeneeded = () => {
      if (!request.result.objectStoreNames.contains(handleStoreName)) {
        request.result.createObjectStore(handleStoreName);
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error('Local folder memory is unavailable.'));
  });
};

const currentSessionKey = async (): Promise<string> => {
  const sessionAddress = `${window.location.origin}${window.location.pathname}${window.location.search}`;
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(sessionAddress));
  return Array.from(new Uint8Array(digest), (value) => value.toString(16).padStart(2, '0')).join('');
};

const readRememberedDirectory = async (): Promise<RememberedDirectory | undefined> => {
  const database = await openHandleDatabase();
  if (!database) return undefined;
  try {
    return await new Promise((resolve, reject) => {
      const request = database
        .transaction(handleStoreName, 'readonly')
        .objectStore(handleStoreName)
        .get(currentHandleKey);
      request.onsuccess = () => resolve(request.result as RememberedDirectory | undefined);
      request.onerror = () => reject(request.error ?? new Error('Local folder memory is unavailable.'));
    });
  } finally {
    database.close();
  }
};

export const supportsLocalDirectoryPicker = (): boolean =>
  typeof (window as PickerWindow).showDirectoryPicker === 'function';

export const collectLocalDirectoryFiles = async (
  root: LocalDirectoryHandle,
  onProgress: (fileCount: number) => void,
): Promise<File[]> => {
  const files: File[] = [];
  const visit = async (directory: LocalDirectoryHandle): Promise<void> => {
    for await (const entry of directory.values()) {
      if (entry.name.startsWith('.')) continue;
      if (entry.kind === 'directory') {
        await visit(entry);
      } else {
        files.push(await entry.getFile());
        onProgress(files.length);
      }
    }
  };
  await visit(root);
  return files;
};

export const pickLocalDirectory = async (
  onProgress: (fileCount: number) => void,
): Promise<LocalDirectorySelection | undefined> => {
  const picker = (window as PickerWindow).showDirectoryPicker;
  if (!picker) return undefined;
  try {
    const handle = await picker({ mode: 'read' });
    return { handle, files: await collectLocalDirectoryFiles(handle, onProgress) };
  } catch (error) {
    if (isAbortError(error)) return undefined;
    throw error;
  }
};

export const rememberLocalDirectory = async (handle: LocalDirectoryHandle): Promise<void> => {
  const database = await openHandleDatabase();
  if (!database) return;
  try {
    const remembered: RememberedDirectory = { sessionKey: await currentSessionKey(), handle };
    await new Promise<void>((resolve, reject) => {
      const request = database
        .transaction(handleStoreName, 'readwrite')
        .objectStore(handleStoreName)
        .put(remembered, currentHandleKey);
      request.onsuccess = () => resolve();
      request.onerror = () => reject(request.error ?? new Error('Local folder memory is unavailable.'));
    });
  } finally {
    database.close();
  }
};

export const restoreDirectoryHandle = async (
  handle: LocalDirectoryHandle | undefined,
  onProgress: (fileCount: number) => void,
): Promise<LocalDirectorySelection | undefined> => {
  if (!handle || handle.kind !== 'directory') return undefined;
  const permission = await handle.queryPermission?.({ mode: 'read' });
  if (permission !== 'granted') return undefined;
  return { handle, files: await collectLocalDirectoryFiles(handle, onProgress) };
};

export const directoryHandleForSession = (
  remembered: RememberedDirectory | undefined,
  sessionKey: string,
): LocalDirectoryHandle | undefined =>
  remembered?.sessionKey === sessionKey ? remembered.handle : undefined;

export const restoreLocalDirectory = async (
  onProgress: (fileCount: number) => void,
): Promise<LocalDirectorySelection | undefined> => {
  const remembered = await readRememberedDirectory();
  const handle = directoryHandleForSession(remembered, await currentSessionKey());
  return restoreDirectoryHandle(handle, onProgress);
};
