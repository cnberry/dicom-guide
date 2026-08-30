import { describe, expect, it, vi } from 'vitest';
import { applyRequestedPatientPoint } from './mprControl';
import type { MprPatientPoint } from './mpr';

describe('MPR agent control', () => {
  it('publishes the exact requested point after the controller accepts it', () => {
    const events: Array<{ kind: 'controller' | 'observation'; point: MprPatientPoint }> = [
      { kind: 'observation', point: [100, 100, 100] },
    ];
    const controller = {
      setPatientPoint: vi.fn((point: MprPatientPoint) => {
        events.push({ kind: 'controller', point: [...point] as MprPatientPoint });
      }),
    };
    const requested: MprPatientPoint = [1.25, -2.5, 3.75];

    applyRequestedPatientPoint(controller, requested, (point) => {
      events.push({ kind: 'observation', point });
    });

    expect(events).toEqual([
      { kind: 'observation', point: [100, 100, 100] },
      { kind: 'controller', point: requested },
      { kind: 'observation', point: requested },
    ]);
    expect(events.at(-1)?.point).not.toBe(requested);
  });

  it('does not publish a point rejected by the controller', () => {
    const publish = vi.fn();
    const controller = {
      setPatientPoint: () => {
        throw new Error('outside volume');
      },
    };

    expect(() => applyRequestedPatientPoint(controller, [1, 2, 3], publish)).toThrow(
      'outside volume',
    );
    expect(publish).not.toHaveBeenCalled();
  });
});
