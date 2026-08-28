import { describe, expect, it } from 'vitest';
import indexHtml from '../index.html?raw';

const runtimeSources = import.meta.glob(
  ['./**/*.ts', './**/*.tsx', '!./**/*.test.ts', '!./**/*.test.tsx'],
  { eager: true, import: 'default', query: '?raw' },
) as Record<string, string>;

describe('local-only runtime boundary', () => {
  it('contains no hard-coded external HTTP or WebSocket endpoint', () => {
    for (const [path, source] of Object.entries({ ...runtimeSources, '../index.html': indexHtml })) {
      expect(source, path).not.toMatch(/\b(?:https?|wss?):\/\//i);
    }
  });
});
