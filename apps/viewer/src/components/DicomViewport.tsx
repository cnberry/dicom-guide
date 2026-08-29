import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from 'react';
import type { RenderingEngine, Types } from '@cornerstonejs/core';
import {
  createMeasurementEvidencePacket,
  createStackViewport,
  restoreMeasurementEvidencePacket,
  type ViewerTool,
  type ViewportToolController,
} from '../cornerstone';
import { assessMprEligibility, getPatientOrientationLabels, type DicomSeries } from '../dicom';
import {
  createConsultationKeyImageArchive,
  createKeyImageArchive,
  downloadArchive,
  type ConsultationKeyImageArchive,
  type ConsultationSelectionSlot,
  type KeyImageArchive,
  type KeyImageArchiveInput,
  type KeyImagePresentation,
} from '../keyImages';
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
  onOpenMpr?: () => void;
  consultationSelectionSlot?: ConsultationSelectionSlot;
};

export type DicomViewportHandle = {
  createKeyImageArchive: (createdAt?: string) => Promise<KeyImageArchive>;
  createConsultationKeyImageArchive: (
    selectionSlot: ConsultationSelectionSlot,
    createdAt?: string,
  ) => Promise<ConsultationKeyImageArchive>;
};

export const DicomViewport = forwardRef<DicomViewportHandle, Props>(function DicomViewport(
  {
    id,
    label,
    series,
    index,
    onIndexChange,
    activeTool,
    resetNonce,
    measurementPacket,
    onOpenMpr,
    consultationSelectionSlot,
  }: Props,
  ref,
) {
  const elementRef = useRef<HTMLDivElement>(null);
  const engineRef = useRef<RenderingEngine | undefined>(undefined);
  const viewportRef = useRef<Types.IStackViewport | undefined>(undefined);
  const toolsRef = useRef<ViewportToolController | undefined>(undefined);
  const [status, setStatus] = useState('Choose a series');
  const [keyImageState, setKeyImageState] = useState<'idle' | 'working' | 'saved' | 'error'>(
    'idle',
  );
  const [keyImageError, setKeyImageError] = useState('');

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
    setKeyImageState('idle');
    setKeyImageError('');
    engineRef.current?.destroy();

    createStackViewport(
      `scanview-${id}-${series.id}-${crypto.randomUUID()}`,
      `viewport-${id}`,
      element,
      series,
      activeTool,
      index,
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
  const orientationLabels = getPatientOrientationLabels(series?.geometry.orientation);
  const mprEligibility = assessMprEligibility(series);
  const buildKeyImageInput = (
    createdAt?: string,
  ): Omit<KeyImageArchiveInput, 'viewportRole'> => {
    const viewport = viewportRef.current;
    const element = elementRef.current;
    if (!viewport || !element || !series) {
      throw new Error(`${label} image is not ready for evidence export.`);
    }
    const actualIndex = viewport.getCurrentImageIdIndex();
    const instance = series.instances[actualIndex];
    if (!instance) throw new Error(`${label} source image is unavailable.`);
    const patientContextId = series.patientContextId;
    if (!patientContextId) {
      throw new Error('Patient context is unavailable; evidence export is disabled.');
    }
    const properties = viewport.getProperties();
    const presentation: KeyImagePresentation = {
      invert: properties.invert,
      zoom: viewport.getZoom(),
      pan: viewport.getPan(),
    };
    if (
      properties.voiRange &&
      Number.isFinite(properties.voiRange.lower) &&
      Number.isFinite(properties.voiRange.upper) &&
      properties.voiRange.upper > properties.voiRange.lower
    ) {
      presentation.voi_range = {
        lower: properties.voiRange.lower,
        upper: properties.voiRange.upper,
      };
    }
    return {
      viewportCanvas: viewport.getCanvas(),
      annotationSvg: element.querySelector<SVGSVGElement>('svg.svg-layer') ?? undefined,
      orientationLabels,
      source: {
        study_id: series.studyId,
        series_id: series.id,
        instance_id: instance.instanceId,
        patient_context_id: patientContextId,
        frame_of_reference_id: series.frameOfReferenceId,
        modality: series.modality,
        acquisition_date: series.acquisitionDate,
        series_description: series.description,
        instance_number: instance.instanceNumber,
      },
      display: {
        stack_position: actualIndex + 1,
        stack_count: series.instances.length,
        source_kind: series.sourceKind,
        presentation,
      },
      measurementPacket: createMeasurementEvidencePacket(),
      createdAt,
    };
  };

  const buildKeyImage = async (createdAt?: string): Promise<KeyImageArchive> =>
    createKeyImageArchive({
      ...buildKeyImageInput(createdAt),
      viewportRole: id,
    });

  const buildConsultationKeyImage = async (
    selectionSlot: ConsultationSelectionSlot,
    createdAt?: string,
  ): Promise<ConsultationKeyImageArchive> =>
    createConsultationKeyImageArchive({
      ...buildKeyImageInput(createdAt),
      selectionSlot,
    });

  useImperativeHandle(ref, () => ({
    createKeyImageArchive: buildKeyImage,
    createConsultationKeyImageArchive: buildConsultationKeyImage,
  }));

  const saveKeyImage = async () => {
    setKeyImageState('working');
    setKeyImageError('');
    try {
      const result = consultationSelectionSlot
        ? await buildConsultationKeyImage(consultationSelectionSlot)
        : await buildKeyImage();
      downloadArchive(result.bytes, result.filename);
      const viewport = viewportRef.current;
      setKeyImageState(
        viewport &&
          result.packet.source.instance_id ===
            series?.instances[viewport.getCurrentImageIdIndex()]?.instanceId
          ? 'saved'
          : 'idle',
      );
    } catch (error) {
      setKeyImageError(error instanceof Error ? error.message : 'Key-image export failed.');
      setKeyImageState('error');
    }
  };

  return (
    <section className="viewport-shell" aria-label={`${label} DICOM viewport`}>
      <div className="viewport-heading">
        <div>
          <span className="eyebrow">{label}</span>
          <strong>{series?.description ?? 'No series selected'}</strong>
        </div>
        <div className="viewport-actions">
          <span className="native-badge">
            {series
              ? `Native source · ${series.sourceKind === 'loopback-service' ? 'local service' : 'folder'}`
              : 'Native source'}
          </span>
          <button
            className="key-image-button"
            disabled={!mprEligibility.eligible || Boolean(status)}
            title={mprEligibility.reason}
            onClick={onOpenMpr}
          >
            Open MPR
          </button>
          <button
            className={`key-image-button ${keyImageState}`}
            disabled={!series || keyImageState === 'working' || Boolean(status)}
            title={
              keyImageError ||
              (consultationSelectionSlot
                ? 'Save a neutral local reference-view ZIP with PNG, provenance, and measurements'
                : 'Save a local ZIP with PNG, provenance, and measurements')
            }
            onClick={() => void saveKeyImage()}
          >
            {keyImageState === 'working'
              ? 'Saving…'
              : keyImageState === 'saved'
                ? consultationSelectionSlot
                  ? 'Saved reference view'
                  : 'Saved key image'
                : keyImageState === 'error'
                  ? 'Export failed'
                  : consultationSelectionSlot
                    ? 'Save reference view'
                    : 'Save key image'}
          </button>
          <span className="sr-only" aria-live="polite">
            {keyImageState === 'saved'
              ? consultationSelectionSlot
                ? 'Local neutral reference-view archive saved.'
                : 'Local key-image archive saved.'
              : keyImageState === 'error'
                ? keyImageError
                : ''}
          </span>
        </div>
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
        {orientationLabels && (
          <div
            className="orientation-labels"
            aria-label={`DICOM patient orientation: left ${orientationLabels.left}, right ${orientationLabels.right}, top ${orientationLabels.top}, bottom ${orientationLabels.bottom}`}
          >
            <span className="orientation-left" aria-hidden="true">
              {orientationLabels.left}
            </span>
            <span className="orientation-right" aria-hidden="true">
              {orientationLabels.right}
            </span>
            <span className="orientation-top" aria-hidden="true">
              {orientationLabels.top}
            </span>
            <span className="orientation-bottom" aria-hidden="true">
              {orientationLabels.bottom}
            </span>
          </div>
        )}
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
});
