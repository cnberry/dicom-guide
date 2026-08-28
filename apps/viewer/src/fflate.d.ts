declare module 'fflate' {
  type ZipOptions = { level?: number };
  type ZipEntry = Uint8Array | [Uint8Array, ZipOptions];

  export const strToU8: (value: string, latin1?: boolean) => Uint8Array;
  export const zipSync: (
    data: Record<string, ZipEntry>,
    options?: ZipOptions,
  ) => Uint8Array;
  export const unzipSync: (data: Uint8Array) => Record<string, Uint8Array>;
}
