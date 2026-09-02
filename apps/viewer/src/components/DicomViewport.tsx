import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
  type CSSProperties,
  type PointerEvent as ReactPointerEvent,
} from 'react';
import { Enums, type RenderingEngine, type Types } from '@cornerstonejs/core';
import {
  createMeasurementEvidencePacket,
  createStackViewport,
  restoreMeasurementEvidencePacket,
  type ViewerTool,
  type ViewportToolController,
} from '../cornerstone';
import { assessMprEligibility, getPatientOrientationLabels, type DicomSeries } from '../dicom';
import type { MprPatientPoint } from '../mpr';
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
import type {
  AppliedPresentationState,
  PresentationStatePoint,
} from '../presentationStates';
import { presentationPixelPointToImageIndex } from '../presentationStates';
import {
  DISCUSSION_MARK_COLORS,
  MAX_DISCUSSION_MARKS,
  MAX_DISCUSSION_MARK_POINTS,
  discussionOrientationForImage,
  roundedPatientPoint,
  type DiscussionMark,
  type DiscussionMarkColor,
} from '../discussionMarkup';

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
  presentationState?: AppliedPresentationState;
  onPresentationStateError?: (message: string) => void;
  interactionLocked?: boolean;
  simple?: boolean;
  onPatientPointChange?: (point?: MprPatientPoint) => void;
  patientPoint?: MprPatientPoint;
  onRenderStatusChange?: (status: 'loading' | 'ready' | 'error') => void;
  controlRevision?: number;
  discussionMarks?: DiscussionMark[];
  onDiscussionMarksChange?: (marks: DiscussionMark[]) => void;
  onPersonInteraction?: () => void;
};

type CanvasPresentationOverlay = {
  width: number;
  height: number;
  instanceId: string;
  graphics: Array<{ id: string; points: PresentationStatePoint[] }>;
  texts: Array<{
    id: string;
    point: PresentationStatePoint;
    visible: boolean;
    lines: string[];
  }>;
};

const applySourcePresentation = (
  viewport: Types.IStackViewport,
  series: DicomSeries,
  application?: AppliedPresentationState,
) => {
  viewport.resetProperties();
  viewport.resetCamera();
  if (
    application &&
    application.target.seriesId === series.id &&
    application.state.referenced_series.some((item) => item.series_id === series.id)
  ) {
    viewport.setProperties({
      VOILUTFunction: Enums.VOILUTFunctionType.LINEAR,
      invert: false,
      voiRange: {
        lower: application.state.presentation.voi_range.lower,
        upper: application.state.presentation.voi_range.upper,
      },
    });
  }
  viewport.render();
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
    presentationState,
    onPresentationStateError,
    interactionLocked = false,
    simple = false,
    onPatientPointChange,
    patientPoint,
    onRenderStatusChange,
    controlRevision,
    discussionMarks = [],
    onDiscussionMarksChange,
    onPersonInteraction,
  }: Props,
  ref,
) {
  const elementRef = useRef<HTMLDivElement>(null);
  const engineRef = useRef<RenderingEngine | undefined>(undefined);
  const viewportRef = useRef<Types.IStackViewport | undefined>(undefined);
  const toolsRef = useRef<ViewportToolController | undefined>(undefined);
  const presentationStateRef = useRef(presentationState);
  presentationStateRef.current = presentationState;
  const presentationStateErrorRef = useRef(onPresentationStateError);
  presentationStateErrorRef.current = onPresentationStateError;
  const patientPointChangeRef = useRef(onPatientPointChange);
  patientPointChangeRef.current = onPatientPointChange;
  const renderStatusChangeRef = useRef(onRenderStatusChange);
  renderStatusChangeRef.current = onRenderStatusChange;
  const [status, setStatus] = useState('Choose a series');
  const [keyImageState, setKeyImageState] = useState<'idle' | 'working' | 'saved' | 'error'>(
    'idle',
  );
  const [keyImageError, setKeyImageError] = useState('');
  const [sourceOverlay, setSourceOverlay] = useState<CanvasPresentationOverlay>();
  const [pinnedCanvasPoint, setPinnedCanvasPoint] = useState<[number, number]>();
  const [discussionColor, setDiscussionColor] = useState<DiscussionMarkColor>('yellow');
  const [draftDiscussionMark, setDraftDiscussionMark] = useState<DiscussionMark>();
  const draftDiscussionMarkRef = useRef<DiscussionMark | undefined>(undefined);
  const discussionPointerIdRef = useRef<number | undefined>(undefined);
  const [, setDiscussionOverlayRevision] = useState(0);
  const presentationLocked = interactionLocked || Boolean(presentationState);

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
    renderStatusChangeRef.current?.('loading');
    setKeyImageState('idle');
    setKeyImageError('');
    engineRef.current?.destroy();

    createStackViewport(
      `dicom-guide-${id}-${series.id}-${crypto.randomUUID()}`,
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
        applySourcePresentation(viewport, series, presentationStateRef.current);
        setStatus('');
        renderStatusChangeRef.current?.('ready');
      })
      .catch((error: unknown) => {
        setStatus(error instanceof Error ? error.message : 'Unable to render this series.');
        renderStatusChangeRef.current?.('error');
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
  }, [id, series]);

  useEffect(() => {
    toolsRef.current?.setPrimaryTool(activeTool);
  }, [activeTool]);

  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport || !series || resetNonce === 0) return;
    applySourcePresentation(viewport, series, presentationStateRef.current);
  }, [resetNonce, series]);

  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport || !series) return;
    applySourcePresentation(viewport, series, presentationState);
  }, [presentationState, series]);

  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport || !series) return;
    const boundedIndex = Math.max(0, Math.min(index, series.instances.length - 1));
    if (viewport.getCurrentImageIdIndex() !== boundedIndex) {
      renderStatusChangeRef.current?.('loading');
      viewport
        .setImageIdIndex(boundedIndex)
        .then(() => {
          viewport.render();
          renderStatusChangeRef.current?.('ready');
        })
        .catch(() => renderStatusChangeRef.current?.('error'));
    }
  }, [index, series]);

  useEffect(() => {
    if (!controlRevision || !series) return;
    const viewport = viewportRef.current;
    const tools = toolsRef.current;
    const boundedIndex = Math.max(0, Math.min(index, series.instances.length - 1));
    if (!viewport || !tools || viewport.getCurrentImageIdIndex() !== boundedIndex) return;
    try {
      tools.setPrimaryTool(activeTool);
      viewport.render();
      renderStatusChangeRef.current?.('ready');
    } catch {
      renderStatusChangeRef.current?.('error');
    }
  }, [activeTool, controlRevision, index, series]);

  useEffect(() => {
    const element = elementRef.current;
    if (!element) return;
    const update = () => {
      const viewport = viewportRef.current;
      if (!viewport || !patientPoint) {
        setPinnedCanvasPoint(undefined);
        return;
      }
      try {
        const canvas = viewport.worldToCanvas(patientPoint as Types.Point3);
        if (
          canvas.length === 2 &&
          canvas.every(Number.isFinite) &&
          canvas[0] >= 0 &&
          canvas[0] <= element.clientWidth &&
          canvas[1] >= 0 &&
          canvas[1] <= element.clientHeight
        ) {
          setPinnedCanvasPoint([canvas[0], canvas[1]]);
        } else {
          setPinnedCanvasPoint(undefined);
        }
      } catch {
        setPinnedCanvasPoint(undefined);
      }
    };
    element.addEventListener(Enums.Events.IMAGE_RENDERED, update);
    const observer = new ResizeObserver(update);
    observer.observe(element);
    update();
    return () => {
      element.removeEventListener(Enums.Events.IMAGE_RENDERED, update);
      observer.disconnect();
    };
  }, [patientPoint, series?.id, index]);

  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport || !series || !measurementPacket) return;
    if (restoreMeasurementEvidencePacket(`viewport-${id}`, series.id, measurementPacket)) {
      viewport.render();
    }
  }, [id, measurementPacket, series]);

  useEffect(() => {
    const element = elementRef.current;
    if (!element) return;
    const update = () => {
      const viewport = viewportRef.current;
      const currentIndex = viewport?.getCurrentImageIdIndex();
      const instance =
        viewport && series && currentIndex !== undefined
          ? series.instances[currentIndex]
          : undefined;
      if (
        !viewport ||
        !series ||
        !instance ||
        !presentationState ||
        presentationState.target.seriesId !== series.id
      ) {
        setSourceOverlay(undefined);
        return;
      }
      const annotations = presentationState.state.annotations.filter((annotation) =>
        annotation.referenced_instance_ids.includes(instance.instanceId),
      );
      if (annotations.length === 0) {
        setSourceOverlay({
          width: element.clientWidth,
          height: element.clientHeight,
          instanceId: instance.instanceId,
          graphics: [],
          texts: [],
        });
        return;
      }
      const imageData = viewport.getImageData();
      const vtkImageData = imageData?.imageData;
      const indexToWorld = vtkImageData?.indexToWorld;
      if (
        !vtkImageData ||
        typeof indexToWorld !== 'function' ||
        element.clientWidth < 1 ||
        element.clientHeight < 1
      ) {
        setSourceOverlay(undefined);
        presentationStateErrorRef.current?.(
          `${label} GSPS display was locked because its source coordinates could not be projected atomically. Nothing from that state remains applied.`,
        );
        return;
      }
      const project = (source: PresentationStatePoint): PresentationStatePoint | undefined => {
        try {
          // DICOM PIXEL annotations use the top-left corner of the top-left pixel as
          // (0, 0), while image-data index (0, 0) identifies that pixel's center.
          const world = indexToWorld.call(
            vtkImageData,
            presentationPixelPointToImageIndex(source),
          ) as Types.Point3;
          const canvas = viewport.worldToCanvas(world);
          return canvas.every(Number.isFinite) ? [canvas[0], canvas[1]] : undefined;
        } catch {
          return undefined;
        }
      };
      const graphics: CanvasPresentationOverlay['graphics'] = [];
      const texts: CanvasPresentationOverlay['texts'] = [];
      for (const annotation of annotations) {
        for (const graphic of annotation.graphics) {
          const points = graphic.points.map(project);
          if (!points.every((point): point is PresentationStatePoint => Boolean(point))) {
            setSourceOverlay(undefined);
            presentationStateErrorRef.current?.(
              `${label} GSPS display was locked because a source polyline could not be projected atomically. No partial annotation was displayed.`,
            );
            return;
          }
          graphics.push({
            id: `${annotation.annotation_id}-${graphic.graphic_id}`,
            points,
          });
        }
        for (const text of annotation.texts) {
          const canvas = project(text.anchor_point);
          if (!canvas) {
            setSourceOverlay(undefined);
            presentationStateErrorRef.current?.(
              `${label} GSPS display was locked because a source text anchor could not be projected atomically. No partial annotation was displayed.`,
            );
            return;
          }
          texts.push({
            id: `${annotation.annotation_id}-${text.text_id}`,
            point: canvas,
            visible: text.anchor_point_visible,
            lines: text.unformatted_text.split(/\r\n|\r|\n/),
          });
        }
      }
      setSourceOverlay({
        width: element.clientWidth,
        height: element.clientHeight,
        instanceId: instance.instanceId,
        graphics,
        texts,
      });
    };
    element.addEventListener(Enums.Events.IMAGE_RENDERED, update);
    const observer = new ResizeObserver(update);
    observer.observe(element);
    update();
    return () => {
      element.removeEventListener(Enums.Events.IMAGE_RENDERED, update);
      observer.disconnect();
    };
  }, [label, presentationState, series]);

  useEffect(() => {
    const element = elementRef.current;
    if (!element) return;
    const update = () => setDiscussionOverlayRevision((value) => value + 1);
    element.addEventListener(Enums.Events.IMAGE_RENDERED, update);
    const observer = new ResizeObserver(update);
    observer.observe(element);
    return () => {
      element.removeEventListener(Enums.Events.IMAGE_RENDERED, update);
      observer.disconnect();
    };
  }, [series?.id]);

  const updateDraftDiscussionMark = (mark?: DiscussionMark) => {
    draftDiscussionMarkRef.current = mark;
    setDraftDiscussionMark(mark);
  };

  const pointInViewport = (
    element: HTMLDivElement,
    event: ReactPointerEvent<HTMLDivElement>,
  ): [number, number] => {
    const bounds = element.getBoundingClientRect();
    return [
      Math.max(0, Math.min(bounds.width, event.clientX - bounds.left)),
      Math.max(0, Math.min(bounds.height, event.clientY - bounds.top)),
    ];
  };

  const startDiscussionMark = (event: ReactPointerEvent<HTMLDivElement>) => {
    const viewport = viewportRef.current;
    const orientation = discussionOrientationForImage(series?.geometry.orientation);
    if ((event.target as Element).closest('.discussion-palette')) return;
    if (
      activeTool !== 'highlight' ||
      event.button !== 0 ||
      !viewport ||
      !orientation ||
      discussionMarks.length >= MAX_DISCUSSION_MARKS
    ) {
      return;
    }
    const point = viewport.canvasToWorld(pointInViewport(event.currentTarget, event));
    if (point.length !== 3 || !point.every(Number.isFinite)) return;
    onPersonInteraction?.();
    event.preventDefault();
    event.stopPropagation();
    event.currentTarget.setPointerCapture(event.pointerId);
    discussionPointerIdRef.current = event.pointerId;
    updateDraftDiscussionMark({
      id: `mark_${crypto.randomUUID().replaceAll('-', '').slice(0, 20)}`,
      orientation,
      color: discussionColor,
      author: 'person',
      points_lps_mm: [roundedPatientPoint(point as MprPatientPoint)],
    });
  };

  const moveDiscussionMark = (event: ReactPointerEvent<HTMLDivElement>) => {
    const viewport = viewportRef.current;
    const draft = draftDiscussionMarkRef.current;
    if (
      activeTool !== 'highlight' ||
      discussionPointerIdRef.current !== event.pointerId ||
      !viewport ||
      !draft
    ) {
      return;
    }
    const point = viewport.canvasToWorld(pointInViewport(event.currentTarget, event));
    if (point.length !== 3 || !point.every(Number.isFinite)) return;
    event.preventDefault();
    const rounded = roundedPatientPoint(point as MprPatientPoint);
    const previous = draft.points_lps_mm.at(-1)!;
    if (
      draft.points_lps_mm.length >= MAX_DISCUSSION_MARK_POINTS ||
      Math.hypot(...rounded.map((coordinate, axis) => coordinate - previous[axis])) < 1.2
    ) {
      return;
    }
    updateDraftDiscussionMark({
      ...draft,
      points_lps_mm: [...draft.points_lps_mm, rounded],
    });
  };

  const finishDiscussionMark = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (discussionPointerIdRef.current !== event.pointerId) return;
    event.preventDefault();
    event.stopPropagation();
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    const draft = draftDiscussionMarkRef.current;
    if (draft && discussionMarks.length < MAX_DISCUSSION_MARKS) {
      onDiscussionMarksChange?.([...discussionMarks, draft]);
    }
    updateDraftDiscussionMark(undefined);
    discussionPointerIdRef.current = undefined;
  };

  const cancelDiscussionMark = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (discussionPointerIdRef.current !== event.pointerId) return;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    updateDraftDiscussionMark(undefined);
    discussionPointerIdRef.current = undefined;
  };

  const discussionCanvasPoints = (mark: DiscussionMark): Array<[number, number]> => {
    const viewport = viewportRef.current;
    const orientation = discussionOrientationForImage(series?.geometry.orientation);
    if (!viewport || !orientation || mark.orientation !== orientation) return [];
    const camera = viewport.getCamera();
    const normal = camera.viewPlaneNormal;
    const focalPoint = camera.focalPoint;
    if (!normal || !focalPoint) return [];
    const tolerance = Math.max(0.5, Math.abs(series?.geometry.sliceThickness ?? 1) * 0.8);
    return mark.points_lps_mm
      .filter((point) => {
        const distance = Math.abs(
          point.reduce(
            (sum, coordinate, axis) => sum + (coordinate - focalPoint[axis]) * normal[axis],
            0,
          ),
        );
        return Number.isFinite(distance) && distance <= tolerance;
      })
      .map((point) => viewport.worldToCanvas(point as Types.Point3))
      .filter(
        (point): point is [number, number] =>
          point.length === 2 && point.every(Number.isFinite),
      );
  };

  const renderDiscussionMark = (mark: DiscussionMark) => {
    const points = discussionCanvasPoints(mark);
    if (points.length === 0) return null;
    const color = DISCUSSION_MARK_COLORS[mark.color];
    if (points.length === 1) {
      return <circle key={mark.id} cx={points[0][0]} cy={points[0][1]} r="11" fill={color} fillOpacity="0.55" />;
    }
    return (
      <path
        key={mark.id}
        d={points.map((point, index) => `${index === 0 ? 'M' : 'L'} ${point[0]} ${point[1]}`).join(' ')}
        fill="none"
        stroke={color}
        strokeWidth="22"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeOpacity="0.55"
      />
    );
  };

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
    if (presentationStateRef.current) {
      throw new Error(
        `${label} uses a source-carried GSPS state. Clear it before evidence export.`,
      );
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
              ? simple
                ? 'Local DICOM'
                : `Native source · ${series.sourceKind === 'loopback-service' ? 'local service' : 'folder'}`
              : simple
                ? 'Local DICOM'
                : 'Native source'}
          </span>
          {presentationState && (
            <span className="source-presentation-badge">
              GSPS display active · supported subset · creator not authenticated
            </span>
          )}
          {onOpenMpr && (
            <button
              className="key-image-button"
              disabled={!mprEligibility.eligible || Boolean(status) || presentationLocked}
              title={
                presentationLocked
                  ? 'Clear all active source-carried GSPS states before opening MPR.'
                  : mprEligibility.reason
              }
              onClick={onOpenMpr}
            >
              {simple ? '3-plane view' : 'Open MPR'}
            </button>
          )}
          {!simple && (
            <>
              <button
                className={`key-image-button ${keyImageState}`}
                disabled={
                  !series ||
                  keyImageState === 'working' ||
                  Boolean(status) ||
                  presentationLocked
                }
                title={
                  keyImageError ||
                  (presentationLocked
                    ? 'Clear all active source-carried GSPS states before export; this evidence schema does not encode GSPS provenance.'
                    : consultationSelectionSlot
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
            </>
          )}
        </div>
      </div>
      <div
        className={`dicom-viewport ${activeTool === 'highlight' ? 'highlight-active' : ''}`}
        onPointerDown={startDiscussionMark}
        onPointerMove={moveDiscussionMark}
        onPointerUp={finishDiscussionMark}
        onPointerCancel={cancelDiscussionMark}
        onClick={(event) => {
          const viewport = viewportRef.current;
          if (!series || !viewport || presentationLocked || activeTool === 'highlight') return;
          const rect = event.currentTarget.getBoundingClientRect();
          try {
            const world = viewport.canvasToWorld([
              event.clientX - rect.left,
              event.clientY - rect.top,
            ]);
            if (world.length === 3 && world.every(Number.isFinite)) {
              patientPointChangeRef.current?.([...world] as MprPatientPoint);
            }
          } catch {
            return;
          }
        }}
        onWheel={(event) => {
          if (!series || presentationLocked) return;
          event.preventDefault();
          onIndexChange(Math.max(0, Math.min(maxIndex, index + Math.sign(event.deltaY))));
        }}
      >
        <div
          ref={elementRef}
          className={`cornerstone-host ${presentationLocked ? 'presentation-locked' : ''}`}
        />
        {activeTool === 'highlight' && (
          <div className="discussion-palette" aria-label="Discussion highlight colors">
            {(Object.keys(DISCUSSION_MARK_COLORS) as DiscussionMarkColor[]).map((color) => (
              <button
                key={color}
                className={discussionColor === color ? 'active' : ''}
                aria-label={`${color} highlight`}
                aria-pressed={discussionColor === color}
                style={{ '--mark-color': DISCUSSION_MARK_COLORS[color] } as CSSProperties}
                onClick={(event) => {
                  event.stopPropagation();
                  setDiscussionColor(color);
                }}
              />
            ))}
            <button
              className="discussion-text-button"
              disabled={discussionMarks.length === 0}
              onClick={(event) => {
                event.stopPropagation();
                onPersonInteraction?.();
                onDiscussionMarksChange?.(discussionMarks.slice(0, -1));
              }}
            >
              Undo
            </button>
            <button
              className="discussion-text-button"
              disabled={discussionMarks.length === 0}
              onClick={(event) => {
                event.stopPropagation();
                onPersonInteraction?.();
                onDiscussionMarksChange?.([]);
              }}
            >
              Clear
            </button>
          </div>
        )}
        <svg className="discussion-overlay" aria-hidden="true">
          {[...discussionMarks, ...(draftDiscussionMark ? [draftDiscussionMark] : [])].map(
            renderDiscussionMark,
          )}
        </svg>
        {pinnedCanvasPoint && (
          <div
            className="native-point-marker"
            style={{ left: pinnedCanvasPoint[0], top: pinnedCanvasPoint[1] }}
            aria-label="Pinned patient-space point"
          />
        )}
        {presentationState && sourceOverlay && (
          <svg
            className="presentation-state-overlay"
            viewBox={`0 0 ${sourceOverlay.width} ${sourceOverlay.height}`}
            aria-label={`Read-only source-carried DICOM presentation-state overlay with ${sourceOverlay.graphics.length} polylines and ${sourceOverlay.texts.length} text objects`}
          >
            {sourceOverlay.graphics.map((graphic) => (
              <polyline
                key={graphic.id}
                points={graphic.points.map((point) => point.join(',')).join(' ')}
              />
            ))}
            {sourceOverlay.texts.map((text) => (
              <g key={text.id}>
                {text.visible && <circle cx={text.point[0]} cy={text.point[1]} r="3.5" />}
                <text x={text.point[0] + 7} y={text.point[1] - 7}>
                  {text.lines.map((line, lineIndex) => (
                    <tspan
                      key={`${text.id}-${lineIndex}`}
                      x={text.point[0] + 7}
                      dy={lineIndex === 0 ? 0 : 15}
                    >
                      {line}
                    </tspan>
                  ))}
                </text>
              </g>
            ))}
          </svg>
        )}
        {presentationState && (
          <div className="presentation-state-viewport-note">
            SOURCE GSPS COORDINATES/TEXT · DICOM_GUIDE HIGH-CONTRAST RENDER · CREATOR NOT AUTHENTICATED
          </div>
        )}
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
          disabled={!series || presentationLocked}
          onChange={(event) => onIndexChange(Number(event.target.value))}
        />
        <span>
          {series ? `${Math.min(index, maxIndex) + 1} / ${series.instances.length}` : '—'}
        </span>
      </div>
    </section>
  );
});
