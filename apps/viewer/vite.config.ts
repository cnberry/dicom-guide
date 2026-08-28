import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 4173,
    strictPort: true,
  },
  preview: {
    host: '127.0.0.1',
    port: 4173,
    strictPort: true,
  },
  resolve: {
    // xmlbuilder2 (used by Cornerstone adapters) expects EventEmitter. Vite 8
    // otherwise externalizes the Node builtin to an empty browser shim.
    alias: {
      events: 'events/',
    },
  },
  optimizeDeps: {
    exclude: ['@cornerstonejs/dicom-image-loader'],
  },
});
