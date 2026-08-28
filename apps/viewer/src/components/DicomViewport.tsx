import { useEffect, useRef, useState } from 'react';
import type { RenderingEngine, Types } from '@cornerstonejs/core';
import {
  createStackViewport,
  restoreMeasurementEvidencePacket,
  type ViewerTool,
  type ViewportToolController,
} from '../cornerstone';
import type { DicomSeries } from '../dicom';
import type { MeasurementEvidencePacket } from '../measurements';

type Props = {
  id: 'baseline' | 'followup';
  label: string;
  series?: DicomSeries;
  index: number;
  onIndexChange: (index: number) => void;
  activeTool: ViewerTool;
  resetNonce: number;
  measurementPacket?: MeasurementEvidencePacket;
};

export function DicomViewport({
  id,
  label,
  series,
  index,
  onIndexChange,
  activeTool,
  resetNonce,
  measurementPacket,
}: Props) {
  const elementRef = useRef<HTMLDivElement>(null);
  const engineRef = useRef<RenderingEngine | undefined>(undefined);
  const viewportRef = useRef<Types.IStackViewport | undefined>(undefined);
  const toolsRef = useRef<ViewportToolController | undefined>(undefined);
  const [status, setStatus] = useState('Choose a series');

  useEffect(() => {
    const element = elementRef.current;
    if (!element) return;
    if (!series) {
      setStatus('Choose a series');
      return;
    }

    let cancelled = false;
    let ownedEngine: RenderingEngine | undefined;
    let ownedTools: ViewportToolController | undefined;
    setStatus('Loading pixels locally…');
    engineRef.current?.destroy();

    createStackViewport(
      `scanview-${id}-${series.id}-${crypto.randomUUID()}`,
      `viewport-${id}`,
      element,
      series,
      activeTool,
    )
      .then(({ engine, viewport, tools }) => {
        ownedEngine = engine;
        ownedTools = tools;
        if (cancelled) {
          tools.destroy();
          engine.destroy();
          return;
        }
        engineRef.current = engine;
        viewportRef.current = viewport;
        toolsRef.current = tools;
        restoreMeasurementEvidencePacket(`viewport-${id}`, series.id, measurementPacket);
        viewport.render();
        setStatus('');
        onIndexChange(Math.floor(series.instances.length / 2));
      })
      .catch((error: unknown) => {
        setStatus(error instanceof Error ? error.message : 'Unable to render this series.');
      });

    const observer = new ResizeObserver(() => engineRef.current?.resize(true, false));
    observer.observe(element);
    return () => {
      cancelled = true;
      observer.disconnect();
      ownedTools?.destroy();
      ownedEngine?.destroy();
      if (engineRef.current === ownedEngine) {
        engineRef.current = undefined;
        viewportRef.current = undefined;
        toolsRef.current = undefined;
      }
    };
  }, [id, series?.id]);

  useEffect(() => {
    toolsRef.current?.setPrimaryTool(activeTool);
  }, [activeTool]);

  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport || resetNonce === 0) return;
    viewport.resetProperties();
    viewport.resetCamera();
    viewport.render();
  }, [resetNonce]);

  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport || !series) return;
    const boundedIndex = Math.max(0, Math.min(index, series.instances.length - 1));
    if (viewport.getCurrentImageIdIndex() !== boundedIndex) {
      viewport.setImageIdIndex(boundedIndex).then(() => viewport.render());
    }
  }, [index, series]);

  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport || !series || !measurementPacket) return;
    if (restoreMeasurementEvidencePacket(`viewport-${id}`, series.id, measurementPacket)) {
      viewport.render();
    }
  }, [id, measurementPacket, series]);

  const maxIndex = Math.max(0, (series?.instances.length ?? 1) - 1);

  return (
    <section className="viewport-shell" aria-label={`${label} DICOM viewport`}>
      <div className="viewport-heading">
        <div>
          <span className="eyebrow">{label}</span>
          <strong>{series?.description ?? 'No series selected'}</strong>
        </div>
        <span className="native-badge">
          {series
            ? `Native source · ${series.sourceKind === 'loopback-service' ? 'local service' : 'folder'}`
            : 'Native source'}
        </span>
      </div>
      <div
        className="dicom-viewport"
        onWheel={(event) => {
          if (!series) return;
          event.preventDefault();
          onIndexChange(Math.max(0, Math.min(maxIndex, index + Math.sign(event.deltaY))));
        }}
      >
        <div ref={elementRef} className="cornerstone-host" />
        {status && <div className="viewport-status">{status}</div>}
      </div>
      <div className="slice-control">
        <input
          aria-label={`${label} slice`}
          type="range"
          min={0}
          max={maxIndex}
          value={Math.min(index, maxIndex)}
          disabled={!series}
          onChange={(event) => onIndexChange(Number(event.target.value))}
        />
        <span>
          {series ? `${Math.min(index, maxIndex) + 1} / ${series.instances.length}` : '—'}
        </span>
      </div>
    </section>
  );
}
