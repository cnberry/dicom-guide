import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { DicomViewport, type DicomViewportHandle } from './components/DicomViewport';
import { MeasurementWorkspace } from './components/MeasurementWorkspace';
import { MprPanel } from './components/MprPanel';
import { LesionVolumeComparisonPanel } from './components/LesionVolumeComparisonPanel';
import { PresentationStatePanel } from './components/PresentationStatePanel';
import { SourceSegmentationPanel } from './components/SourceSegmentationPanel';
import {
  createMeasurementEvidencePacket,
  removeMeasurementAnnotation,
  resetLocalImagingSession,
  subscribeToMeasurementChanges,
  type ViewerTool,
} from './cornerstone';
import {
  assessCompatibility,
  formatDicomDate,
  getLinkStrategy,
  isConsultationSourcePair,
  mapLinkedIndex,
  parseDicomFiles,
  type DicomSeries,
} from './dicom';
import {
  readMeasurementEvidencePacket,
  type MeasurementEvidencePacket,
} from './measurements';
import {
  saveComparisonReview as saveLocalComparisonReview,
} from './comparisonReviewService';
import {
  comparisonSourcesAreVisible,
  findComparisonSourceIndexes,
  type MeasurementComparisonDraft,
} from './measurementComparison';
import { loadLocalServiceCatalog } from './localService';
import {
  parseNavigationFragment,
  resolveNavigationIntent,
  type NavigationParseResult,
} from './navigationIntent';
import { saveVisitPacket as saveLocalVisitPacket } from './visitPacketService';
import { saveConsultationPacket as saveLocalConsultationPacket } from './consultationPacketService';
import {
  CONSULTATION_BOARD_MAX_LABEL_CHARACTERS,
  CONSULTATION_BOARD_MAX_ITEMS,
  CONSULTATION_BOARD_MIN_ITEMS,
  consultationBoardLabelError,
  saveConsultationBoard as saveLocalConsultationBoard,
} from './consultationBoardService';
import {
  buildViewerStatePublication,
  clearViewerState,
  createViewerStatePublisherId,
  publishViewerState,
  VIEWER_STATE_HEARTBEAT_MS,
} from './viewerStateService';
import {
  readinessRequirementText,
  summarizeLongitudinalReadiness,
} from './longitudinalReadiness';
import {
  loadAgentConsultationPlan,
  type ResolvedAgentConsultationPlan,
  type ResolvedAgentConsultationPlanItem,
} from './agentConsultationPlan';
import {
  loadPresentationStateCatalog,
  type AppliedPresentationState,
  type PresentationStateTarget,
  type ResolvedPresentationState,
  type ResolvedPresentationStateCatalog,
} from './presentationStates';
import {
  loadSourceSegmentationCatalog,
  loadSourceSegmentationMask,
  type LoadedSourceSegmentation,
  type ResolvedSourceSegmentation,
  type ResolvedSourceSegmentationCatalog,
  type SourceSegment,
} from './sourceSegmentations';

type ImportState = { processed: number; total: number } | undefined;
type ExportState = 'idle' | 'working' | 'saved' | 'error';
type ConsultationBoardDraftItem = {
  id: string;
  selectionSlot: 'view_a' | 'view_b';
  discussionLabel: string;
  archive: Uint8Array;
  studyId: string;
  instanceId: string;
  patientContextId: string;
  modality: string;
  seriesDescription: string;
  stackPosition: number;
  stackCount: number;
};
const maxPastedMeasurementBytes = 2_000_000;

const SeriesSelect = ({
  label,
  value,
  series,
  onChange,
  disabled = false,
}: {
  label: string;
  value?: string;
  series: DicomSeries[];
  onChange: (id: string) => void;
  disabled?: boolean;
}) => (
  <label className="series-select">
    <span>{label}</span>
    <select
      value={value ?? ''}
      disabled={disabled}
      onChange={(event) => onChange(event.target.value)}
    >
      <option value="" disabled>
        Choose a series
      </option>
      {series.map((item) => (
        <option key={item.id} value={item.id}>
          {formatDicomDate(item.acquisitionDate)} · {item.modality} · {item.description} ·{' '}
          {item.instances.length} images
        </option>
      ))}
    </select>
  </label>
);

export default function App({ active = true }: { active?: boolean } = {}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const measurementInputRef = useRef<HTMLInputElement>(null);
  const baselineViewportRef = useRef<DicomViewportHandle>(null);
  const followupViewportRef = useRef<DicomViewportHandle>(null);
  const consultationBoardOperationRef = useRef(false);
  const sourceGenerationRef = useRef(0);
  const sourceSegmentationOperationRef = useRef(0);
  const sourceSegmentationAbortRef = useRef<AbortController | undefined>(undefined);
  const sourceSummaryRef = useRef('No scan folder loaded');
  const [agentPublisherId, setAgentPublisherId] = useState(createViewerStatePublisherId);
  const agentPublisherIdRef = useRef(agentPublisherId);
  const agentStateSharingRef = useRef(false);
  const agentPublishQueueRef = useRef<Promise<void>>(Promise.resolve());
  const [series, setSeries] = useState<DicomSeries[]>([]);
  const [baselineId, setBaselineId] = useState<string>();
  const [followupId, setFollowupId] = useState<string>();
  const [baselineIndex, setBaselineIndex] = useState(0);
  const [followupIndex, setFollowupIndex] = useState(0);
  const [mprSeriesId, setMprSeriesId] = useState<string>();
  const [synchronized, setSynchronized] = useState(true);
  const [activeTool, setActiveTool] = useState<ViewerTool>('window');
  const [resetNonce, setResetNonce] = useState(0);
  const [importState, setImportState] = useState<ImportState>();
  const [importMessage, setImportMessage] = useState('No scan folder loaded');
  const [sourceReady, setSourceReady] = useState(false);
  const [pendingNavigation, setPendingNavigation] = useState<NavigationParseResult>();
  const [measurementMessage, setMeasurementMessage] = useState(
    'Measurement drafts stay local and require clinician review.',
  );
  const [measurementPacket, setMeasurementPacket] = useState<MeasurementEvidencePacket>();
  const [liveMeasurementPacket, setLiveMeasurementPacket] = useState<MeasurementEvidencePacket>();
  const [measurementPasteOpen, setMeasurementPasteOpen] = useState(false);
  const [measurementPasteValue, setMeasurementPasteValue] = useState('');
  const [measurementComparisonDraft, setMeasurementComparisonDraft] =
    useState<MeasurementComparisonDraft>();
  const [visitPacketState, setVisitPacketState] = useState<ExportState>('idle');
  const [visitPacketMessage, setVisitPacketMessage] = useState(
    'Visit packets require two dated, same-patient MR or CT studies in the unified local workspace.',
  );
  const [comparisonReviewState, setComparisonReviewState] = useState<ExportState>('idle');
  const [comparisonReviewMessage, setComparisonReviewMessage] = useState(
    'Build an explicit numeric preview to enable one-click local review export.',
  );
  const [consultationPacketState, setConsultationPacketState] = useState<ExportState>('idle');
  const [consultationPacketMessage, setConsultationPacketMessage] = useState(
    'Select two local reference views to prepare a neutral clinician discussion packet.',
  );
  const [consultationBoardItems, setConsultationBoardItems] = useState<
    ConsultationBoardDraftItem[]
  >([]);
  const [consultationBoardLabel, setConsultationBoardLabel] = useState('');
  const [consultationBoardState, setConsultationBoardState] =
    useState<ExportState>('idle');
  const [consultationBoardMessage, setConsultationBoardMessage] = useState(
    'Add 2–8 explicitly labeled MR/CT source views. Labels remain unreviewed discussion headings.',
  );
  const [agentConsultationPlanText, setAgentConsultationPlanText] = useState('');
  const [agentConsultationPlan, setAgentConsultationPlan] =
    useState<ResolvedAgentConsultationPlan>();
  const [agentConsultationPlanState, setAgentConsultationPlanState] =
    useState<ExportState>('idle');
  const [agentConsultationPlanMessage, setAgentConsultationPlanMessage] = useState(
    'Paste a locally created agent consultation plan. Nothing opens or captures automatically.',
  );
  const [agentStateSharing, setAgentStateSharing] = useState(false);
  const [agentStateMessage, setAgentStateMessage] = useState(
    'Agent viewer state is off by default. Enable it to share only expiring opaque positions locally.',
  );
  const [presentationStateCatalog, setPresentationStateCatalog] =
    useState<ResolvedPresentationStateCatalog>();
  const [presentationStateLoading, setPresentationStateLoading] = useState(true);
  const [presentationStateMessage, setPresentationStateMessage] = useState(
    'Checking source DICOM presentation states locally…',
  );
  const [baselinePresentationState, setBaselinePresentationState] =
    useState<AppliedPresentationState>();
  const [followupPresentationState, setFollowupPresentationState] =
    useState<AppliedPresentationState>();
  const [sourceSegmentationCatalog, setSourceSegmentationCatalog] =
    useState<ResolvedSourceSegmentationCatalog>();
  const [sourceSegmentationLoading, setSourceSegmentationLoading] = useState(true);
  const [sourceSegmentationOpening, setSourceSegmentationOpening] = useState(false);
  const [sourceSegmentationMessage, setSourceSegmentationMessage] = useState(
    'Checking source-carried DICOM segmentations locally…',
  );
  const [loadedSourceSegmentation, setLoadedSourceSegmentation] =
    useState<LoadedSourceSegmentation>();

  useEffect(() => () => sourceSegmentationAbortRef.current?.abort(), []);

  const baseline = series.find((item) => item.id === baselineId);
  const followup = series.find((item) => item.id === followupId);
  const mprSeries = series.find((item) => item.id === mprSeriesId);
  const longitudinalReadiness = useMemo(
    () => summarizeLongitudinalReadiness(series),
    [series],
  );
  const consultPrepMode =
    series.length > 0 && longitudinalReadiness.candidatePairCount === 0;
  const compatibility = useMemo(
    () => assessCompatibility(baseline, followup),
    [baseline, followup],
  );
  const linkStrategy = useMemo(() => getLinkStrategy(baseline, followup), [baseline, followup]);
  const effectiveSynchronized =
    synchronized && (!consultPrepMode || linkStrategy === 'patient-position');
  const visibleMeasurements = liveMeasurementPacket
    ? liveMeasurementPacket.measurements
    : (measurementPacket?.measurements ?? []);
  const presentationStateActive = Boolean(
    baselinePresentationState || followupPresentationState,
  );
  const sourceSegmentationActive = Boolean(loadedSourceSegmentation) || sourceSegmentationOpening;
  const visitPacketUsesLoopback = Boolean(
    baseline?.sourceKind === 'loopback-service' && followup?.sourceKind === 'loopback-service',
  );
  const visitPacketReady = Boolean(
    !consultPrepMode &&
      baseline &&
      followup &&
      visitPacketUsesLoopback &&
      compatibility.level !== 'incompatible' &&
      !presentationStateActive,
  );
  const consultationPacketReady = Boolean(
      consultPrepMode &&
      visitPacketUsesLoopback &&
      isConsultationSourcePair(baseline, followup) &&
      !presentationStateActive,
  );
  const consultationBoardModalities = new Set(
    consultationBoardItems.map((item) => item.modality),
  );
  const consultationBoardStudies = new Set(
    consultationBoardItems.map((item) => item.studyId),
  );
  const consultationBoardHasMinimum =
    consultationBoardItems.length >= CONSULTATION_BOARD_MIN_ITEMS;
  const consultationBoardHasMR = consultationBoardModalities.has('MR');
  const consultationBoardHasCT = consultationBoardModalities.has('CT');
  const consultationBoardHasTwoStudies = consultationBoardStudies.size >= 2;
  const consultationBoardLabelMessage = consultationBoardLabelError(
    consultationBoardLabel,
  );
  const consultationBoardReady =
    consultPrepMode &&
    consultationBoardHasMinimum &&
    consultationBoardItems.length <= CONSULTATION_BOARD_MAX_ITEMS &&
    consultationBoardHasMR &&
    consultationBoardHasCT &&
    consultationBoardHasTwoStudies &&
    !presentationStateActive;
  const comparisonSourceIndexes = useMemo(() => {
    return findComparisonSourceIndexes(measurementComparisonDraft, baseline, followup);
  }, [baseline, followup, measurementComparisonDraft]);
  const comparisonSourcesVisible = comparisonSourcesAreVisible(
    comparisonSourceIndexes,
    baselineIndex,
    followupIndex,
  );
  const comparisonReviewReady = Boolean(
    visitPacketReady && measurementComparisonDraft && comparisonSourcesVisible,
  );
  const evidenceExportWorking =
    visitPacketState === 'working' ||
    comparisonReviewState === 'working' ||
    consultationPacketState === 'working' ||
    consultationBoardState === 'working';
  const viewerStatePublication = useMemo(
    () => {
      if (consultPrepMode || presentationStateActive || sourceSegmentationActive) return undefined;
      return buildViewerStatePublication({
        publisherId: agentPublisherId,
        activeTool,
        synchronized: effectiveSynchronized,
        linkStrategy,
        baseline,
        baselineIndex,
        followup,
        followupIndex,
        mprSeries,
        measurementCount: visibleMeasurements.length,
        comparisonDraftPresent: Boolean(measurementComparisonDraft),
      });
    },
    [
      activeTool,
      agentPublisherId,
      baseline,
      baselineIndex,
      followup,
      followupIndex,
      consultPrepMode,
      linkStrategy,
      measurementComparisonDraft,
      mprSeries,
      presentationStateActive,
      sourceSegmentationActive,
      effectiveSynchronized,
      visibleMeasurements.length,
    ],
  );

  useEffect(() => {
    setVisitPacketState('idle');
    setVisitPacketMessage(
      'Visit packets require two dated, same-patient MR or CT studies in the unified local workspace.',
    );
  }, [baselineId, baselineIndex, followupId, followupIndex]);

  useEffect(() => {
    setConsultationPacketState('idle');
    setConsultationPacketMessage(
      'Select two local reference views to prepare a neutral clinician discussion packet.',
    );
  }, [baselineId, baselineIndex, followupId, followupIndex]);

  useEffect(() => {
    if (consultPrepMode || consultationBoardItems.length === 0) return;
    setConsultationBoardItems([]);
    setConsultationBoardLabel('');
    setConsultationBoardState('idle');
    setConsultationBoardMessage(
      'The in-memory consultation board was cleared because this dataset has a longitudinal source pair.',
    );
  }, [consultPrepMode, consultationBoardItems.length]);

  useEffect(() => {
    setComparisonReviewState('idle');
    if (!measurementComparisonDraft) {
      setComparisonReviewMessage(
        'Build an explicit numeric preview to enable one-click local review export.',
      );
    } else if (!visitPacketUsesLoopback) {
      setComparisonReviewMessage(
        'Use the unified local launcher for one-click comparison-review assembly.',
      );
    } else if (!comparisonSourcesVisible) {
      setComparisonReviewMessage(
        'Return both panes to the exact selected measurement source slices before review export.',
      );
    } else {
      setComparisonReviewMessage(
        'Ready to bind both displayed source images to this unreviewed numeric comparison locally.',
      );
    }
  }, [
    baselineId,
    baselineIndex,
    comparisonSourcesVisible,
    followupId,
    followupIndex,
    measurementComparisonDraft,
    visitPacketUsesLoopback,
  ]);

  useEffect(() => {
    if (!comparisonSourceIndexes) return;
    if (comparisonSourceIndexes.baseline >= 0) {
      setBaselineIndex(comparisonSourceIndexes.baseline);
    }
    if (comparisonSourceIndexes.followup >= 0) {
      setFollowupIndex(comparisonSourceIndexes.followup);
    }
  }, [comparisonSourceIndexes]);

  useEffect(() => {
    agentStateSharingRef.current = agentStateSharing;
  }, [agentStateSharing]);

  useEffect(() => {
    if (agentStateSharing) return;
    setAgentStateMessage(
      presentationStateActive
        ? 'Live agent state is unavailable while a source-carried GSPS presentation is active because the current state schema does not encode GSPS provenance.'
        : sourceSegmentationActive
          ? 'Live agent state is unavailable while a source-carried DICOM SEG mask is open because the current state schema does not encode SEG provenance.'
        : consultPrepMode
        ? 'Live agent state is unavailable in Consult Prep because the current state schema uses timepoint roles. Use the neutral consultation packet for agent evidence.'
        : 'Agent viewer state is off by default. Enable it to share only expiring opaque positions locally.',
    );
  }, [agentStateSharing, consultPrepMode, presentationStateActive, sourceSegmentationActive]);

  useEffect(() => {
    agentPublisherIdRef.current = agentPublisherId;
  }, [agentPublisherId]);

  useEffect(() => {
    if (active || !agentStateSharing) return;
    const revokedPublisherId = agentPublisherIdRef.current;
    agentStateSharingRef.current = false;
    setAgentStateSharing(false);
    setAgentPublisherId(createViewerStatePublisherId());
    setAgentStateMessage(
      'Agent viewer state stopped while the ordinary DICOM surface is hidden.',
    );
    void clearViewerState(revokedPublisherId).catch(() => undefined);
  }, [active, agentStateSharing]);

  useEffect(() => {
    if (!active || !agentStateSharing) return;
    if (!viewerStatePublication) {
      agentStateSharingRef.current = false;
      setAgentStateSharing(false);
      setAgentStateMessage(
        presentationStateActive
          ? 'Agent viewer state stopped because the active source-carried GSPS presentation is not represented by the current state schema.'
          : sourceSegmentationActive
            ? 'Agent viewer state stopped because the active source-carried DICOM SEG mask is not represented by the current state schema.'
          : consultPrepMode
          ? 'Agent viewer state stopped because Consult Prep does not publish timepoint-role state. Use the neutral consultation packet instead.'
          : 'Agent viewer state stopped: it is available only through the authenticated local launcher.',
      );
      const revokedPublisherId = agentPublisherId;
      setAgentPublisherId(createViewerStatePublisherId());
      void clearViewerState(revokedPublisherId).catch(() => undefined);
      return;
    }
    let effectActive = true;
    const send = async () => {
      let published = false;
      try {
        const queued = agentPublishQueueRef.current
          .catch(() => undefined)
          .then(async () => {
            if (
              !agentStateSharingRef.current ||
              agentPublisherIdRef.current !== viewerStatePublication.publisher_id
            ) {
              return;
            }
            await publishViewerState(viewerStatePublication);
            published = true;
          });
        agentPublishQueueRef.current = queued.catch(() => undefined);
        await queued;
        if (effectActive && published) {
          setAgentStateMessage(
            'Sharing opaque viewer state with bearer-authorized local agents · memory-only · expires within 30 seconds.',
          );
        }
      } catch (error) {
        if (effectActive) {
          setAgentStateMessage(
            `${error instanceof Error ? error.message : 'Local viewer-state update failed.'} Any previous state expires automatically.`,
          );
        }
      }
    };
    const initial = window.setTimeout(() => void send(), 100);
    const heartbeat = window.setInterval(() => void send(), VIEWER_STATE_HEARTBEAT_MS);
    return () => {
      effectActive = false;
      window.clearTimeout(initial);
      window.clearInterval(heartbeat);
    };
  }, [
    active,
    agentPublisherId,
    agentStateSharing,
    consultPrepMode,
    presentationStateActive,
    sourceSegmentationActive,
    viewerStatePublication,
  ]);

  useEffect(() => {
    const clearPublishedState = () => {
      if (!agentStateSharingRef.current) return;
      void clearViewerState(agentPublisherIdRef.current, true).catch(() => undefined);
    };
    window.addEventListener('pagehide', clearPublishedState);
    return () => {
      window.removeEventListener('pagehide', clearPublishedState);
      clearPublishedState();
    };
  }, []);

  useEffect(
    () =>
      subscribeToMeasurementChanges(() => {
        setLiveMeasurementPacket(createMeasurementEvidencePacket());
      }),
    [],
  );

  useEffect(() => {
    const consumeFragment = () => {
      const parsed = parseNavigationFragment(window.location.hash);
      if (!parsed.present) return;
      try {
        window.history.replaceState(
          window.history.state,
          '',
          `${window.location.pathname}${window.location.search}`,
        );
      } catch {
        // Navigation still remains local if an embedded browser withholds history access.
      }
      setPendingNavigation(parsed);
    };
    consumeFragment();
    window.addEventListener('hashchange', consumeFragment);
    return () => window.removeEventListener('hashchange', consumeFragment);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const generation = sourceGenerationRef.current;
    void loadLocalServiceCatalog(controller.signal).then(async (catalog) => {
      if (controller.signal.aborted || generation !== sourceGenerationRef.current) {
        return;
      }
      if (!catalog) {
        setPresentationStateLoading(false);
        setPresentationStateMessage(
          'Source-carried GSPS states are available only through the authenticated local launcher.',
        );
        setSourceSegmentationLoading(false);
        setSourceSegmentationMessage(
          'Source-carried DICOM SEG masks are available only through the authenticated local launcher.',
        );
        setSourceReady(true);
        return;
      }
      setSeries(catalog.series);
      const catalogMessage = catalog.series.length
        ? `${catalog.studyCount} studies · ${catalog.series.length} renderable series · ${catalog.instanceCount.toLocaleString()} indexed instances · local loopback service · no upload`
        : `${catalog.studyCount} studies · no renderable MR/CT pixel series · local loopback service`;
      sourceSummaryRef.current = catalogMessage;
      setImportMessage(catalogMessage);
      setBaselineId(catalog.series[0]?.id);
      setFollowupId(undefined);
      setBaselineIndex(Math.floor((catalog.series[0]?.instances.length ?? 1) / 2));
      setFollowupIndex(0);
      setBaselinePresentationState(undefined);
      setFollowupPresentationState(undefined);
      setPresentationStateLoading(true);
      try {
        const presentationStates = await loadPresentationStateCatalog(
          catalog.series,
          controller.signal,
        );
        if (controller.signal.aborted || generation !== sourceGenerationRef.current) return;
        setPresentationStateCatalog(presentationStates);
        const supported = presentationStates.catalog.supported_state_count;
        const unsupported = presentationStates.catalog.unsupported_state_count;
        setPresentationStateMessage(
          supported > 0
            ? `Recognized ${supported} supported GSPS ${supported === 1 ? 'state' : 'states'} from source-bound local DICOM bytes; ${unsupported} unsupported ${unsupported === 1 ? 'state remains' : 'states remain'} locked.`
            : unsupported > 0
              ? `No supported GSPS states; ${unsupported} ${unsupported === 1 ? 'state failed' : 'states failed'} closed.`
              : 'No DICOM GSPS presentation states were found in this local workspace.',
        );
      } catch (error) {
        if (controller.signal.aborted || generation !== sourceGenerationRef.current) return;
        setPresentationStateCatalog(undefined);
        setPresentationStateMessage(
          error instanceof Error
            ? error.message
            : 'Source-carried GSPS states are unavailable. Nothing was displayed.',
        );
      } finally {
        if (!controller.signal.aborted && generation === sourceGenerationRef.current) {
          setPresentationStateLoading(false);
        }
      }
      setSourceSegmentationLoading(true);
      try {
        const sourceSegmentations = await loadSourceSegmentationCatalog(
          catalog.series,
          controller.signal,
        );
        if (controller.signal.aborted || generation !== sourceGenerationRef.current) return;
        setSourceSegmentationCatalog(sourceSegmentations);
        const supported = sourceSegmentations.catalog.supported_segmentation_count;
        const unsupported = sourceSegmentations.catalog.unsupported_segmentation_count;
        const segments = sourceSegmentations.catalog.segment_count;
        setSourceSegmentationMessage(
          supported > 0
            ? `Recognized ${supported} supported source DICOM SEG ${supported === 1 ? 'object' : 'objects'} with ${segments} ${segments === 1 ? 'segment' : 'segments'}; ${unsupported} unsupported ${unsupported === 1 ? 'object remains' : 'objects remain'} locked.`
            : unsupported > 0
              ? `No supported source DICOM SEG objects; ${unsupported} ${unsupported === 1 ? 'object failed' : 'objects failed'} closed.`
              : 'No DICOM Segmentation objects were found in this local workspace.',
        );
      } catch (error) {
        if (controller.signal.aborted || generation !== sourceGenerationRef.current) return;
        setSourceSegmentationCatalog(undefined);
        setSourceSegmentationMessage(
          error instanceof Error
            ? error.message
            : 'Source-carried DICOM segmentations are unavailable. No mask was displayed.',
        );
      } finally {
        if (!controller.signal.aborted && generation === sourceGenerationRef.current) {
          setSourceSegmentationLoading(false);
        }
      }
      setSourceReady(true);
    });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!pendingNavigation || !sourceReady) return;
    if (pendingNavigation.intent) {
      const resolved = resolveNavigationIntent(pendingNavigation.intent, series);
      if (resolved.navigation) {
        setBaselinePresentationState(undefined);
        setFollowupPresentationState(undefined);
        setBaselineId(resolved.navigation.baseline.seriesId);
        setBaselineIndex(resolved.navigation.baseline.instanceIndex);
        setFollowupId(resolved.navigation.followup?.seriesId);
        setFollowupIndex(resolved.navigation.followup?.instanceIndex ?? 0);
        setImportMessage(
          `${sourceSummaryRef.current} · exact local source navigation applied · pairing remains unreviewed`,
        );
      } else {
        setImportMessage(
          `${sourceSummaryRef.current} · ${resolved.error ?? 'Local navigation rejected.'}`,
        );
      }
    } else {
      setImportMessage(
        `${sourceSummaryRef.current} · ${pendingNavigation.error ?? 'Local navigation rejected.'}`,
      );
    }
    setPendingNavigation(undefined);
  }, [pendingNavigation, series, sourceReady]);

  const openFolder = () => {
    if (!inputRef.current) return;
    inputRef.current.value = '';
    inputRef.current.click();
  };

  const chooseFiles = async (fileList: FileList | null) => {
    if (!fileList?.length) return;
    sourceGenerationRef.current += 1;
    sourceSegmentationOperationRef.current += 1;
    sourceSegmentationAbortRef.current?.abort();
    sourceSegmentationAbortRef.current = undefined;
    const files = Array.from(fileList).filter((file) => !file.name.startsWith('.'));
    setSeries([]);
    setSourceReady(false);
    setBaselineId(undefined);
    setFollowupId(undefined);
    setMprSeriesId(undefined);
    setLoadedSourceSegmentation(undefined);
    setSourceSegmentationCatalog(undefined);
    setSourceSegmentationLoading(false);
    setSourceSegmentationOpening(false);
    setSourceSegmentationMessage(
      'Source-carried DICOM SEG masks are available only through the authenticated local launcher.',
    );
    setPresentationStateCatalog(undefined);
    setPresentationStateLoading(false);
    setPresentationStateMessage(
      'Source-saved views are available only through the authenticated local launcher.',
    );
    setBaselinePresentationState(undefined);
    setFollowupPresentationState(undefined);
    setMeasurementPacket(undefined);
    setLiveMeasurementPacket(undefined);
    setMeasurementPasteOpen(false);
    setMeasurementPasteValue('');
    setMeasurementComparisonDraft(undefined);
    setMeasurementMessage('Measurement drafts stay local and require clinician review.');
    setConsultationBoardItems([]);
    setConsultationBoardLabel('');
    setConsultationBoardState('idle');
    setConsultationBoardMessage(
      'Add 2–8 explicitly labeled MR/CT source views. Labels remain unreviewed discussion headings.',
    );
    setAgentConsultationPlanText('');
    setAgentConsultationPlan(undefined);
    setAgentConsultationPlanState('idle');
    setAgentConsultationPlanMessage(
      'Paste a locally created agent consultation plan. Nothing opens or captures automatically.',
    );
    await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
    resetLocalImagingSession();
    setImportState({ processed: 0, total: files.length });
    setImportMessage('Reading DICOM headers in this browser only…');
    const imported = await parseDicomFiles(files, (processed, total) =>
      setImportState({ processed, total }),
    );
    setSeries(imported);
    setImportState(undefined);
    const importedStudies = new Set(imported.map((item) => item.studyId)).size;
    const importedMessage = imported.length
      ? `${importedStudies} studies · ${imported.length} series · follow-up not auto-selected · no upload`
      : 'No readable DICOM image series found.';
    sourceSummaryRef.current = importedMessage;
    setImportMessage(importedMessage);
    setBaselineId(imported[0]?.id);
    setFollowupId(undefined);
    setBaselineIndex(Math.floor((imported[0]?.instances.length ?? 1) / 2));
    setFollowupIndex(0);
    setSourceReady(true);
  };

  const updateIndex = (side: 'baseline' | 'followup', next: number) => {
    setBaselinePresentationState(undefined);
    setFollowupPresentationState(undefined);
    if (side === 'baseline') {
      setBaselineIndex(next);
      if (effectiveSynchronized && baseline && followup) {
        setFollowupIndex(mapLinkedIndex(next, baseline, followup).index);
      }
    } else {
      setFollowupIndex(next);
      if (effectiveSynchronized && baseline && followup) {
        setBaselineIndex(mapLinkedIndex(next, followup, baseline).index);
      }
    }
  };

  const toggleAgentStateSharing = () => {
    if (agentStateSharing) {
      const revokedPublisherId = agentPublisherId;
      agentStateSharingRef.current = false;
      setAgentStateSharing(false);
      setAgentPublisherId(createViewerStatePublisherId());
      setAgentStateMessage(
        'Agent viewer state is off. The memory-only publication has been cleared locally.',
      );
      void clearViewerState(revokedPublisherId).catch((error) => {
        setAgentStateMessage(
          `${error instanceof Error ? error.message : 'Local viewer-state cleanup failed.'} Any state still expires within 30 seconds.`,
        );
      });
      return;
    }
    if (!viewerStatePublication) {
      setAgentStateMessage(
        presentationStateActive
          ? 'Clear source-carried GSPS states before sharing viewer state; the current state schema does not encode GSPS provenance.'
          : sourceSegmentationActive
            ? 'Close the source-carried DICOM SEG mask before sharing viewer state; the current state schema does not encode SEG provenance.'
          : 'Agent viewer state requires scans opened through the authenticated local launcher.',
      );
      return;
    }
    agentStateSharingRef.current = true;
    setAgentStateSharing(true);
    setAgentStateMessage('Starting the memory-only local viewer-state bridge…');
  };

  const exportMeasurementDraft = () => {
    const packet = createMeasurementEvidencePacket();
    if (packet.measurements.length === 0) {
      setMeasurementMessage(
        'No measurements to export. Draw a Length, Bidirectional, or Ellipse ROI measurement first.',
      );
      return;
    }
    const url = URL.createObjectURL(
      new Blob([`${JSON.stringify(packet, null, 2)}\n`], { type: 'application/json' }),
    );
    const link = document.createElement('a');
    link.href = url;
    link.download = `scanview-measurements-${new Date().toISOString().slice(0, 10)}.json`;
    link.click();
    URL.revokeObjectURL(url);
    setMeasurementMessage(
      `Exported ${packet.measurements.length} unreviewed source-linked measurement${packet.measurements.length === 1 ? '' : 's'}.`,
    );
  };

  const openMeasurementDraft = () => {
    if (!measurementInputRef.current) return;
    measurementInputRef.current.value = '';
    measurementInputRef.current.click();
  };

  const loadMeasurementDraft = async (fileList: FileList | null) => {
    const file = fileList?.[0];
    if (!file) return;
    try {
      acceptMeasurementDraft(JSON.parse(await file.text()));
    } catch {
      setMeasurementPacket(undefined);
      setMeasurementMessage('Measurement draft rejected: file is not valid JSON.');
    }
  };

  const acceptMeasurementDraft = (value: unknown): boolean => {
    const parsed = readMeasurementEvidencePacket(value);
    if (!parsed.packet) {
      setMeasurementPacket(undefined);
      setLiveMeasurementPacket(undefined);
      setMeasurementMessage(`Measurement draft rejected: ${parsed.errors.join(' ')}`);
      return false;
    }
    setLiveMeasurementPacket(undefined);
    setMeasurementPacket(parsed.packet);
    setMeasurementMessage(
      `Loaded ${parsed.packet.measurements.length} unreviewed source-linked measurement${parsed.packet.measurements.length === 1 ? '' : 's'}; matching selected series are restored.`,
    );
    return true;
  };

  const importPastedMeasurementDraft = () => {
    if (new TextEncoder().encode(measurementPasteValue).byteLength > maxPastedMeasurementBytes) {
      setMeasurementMessage('Measurement draft rejected: pasted JSON exceeds the 2 MB limit.');
      return;
    }
    try {
      if (acceptMeasurementDraft(JSON.parse(measurementPasteValue))) {
        setMeasurementPasteOpen(false);
        setMeasurementPasteValue('');
      }
    } catch {
      setMeasurementMessage('Measurement draft rejected: pasted text is not valid JSON.');
    }
  };

  const exportVisitPacket = async () => {
    if (!baseline || !followup) {
      setVisitPacketState('error');
      setVisitPacketMessage('Choose both a baseline and follow-up series first.');
      return;
    }
    if (!visitPacketUsesLoopback) {
      setVisitPacketState('error');
      setVisitPacketMessage('Use the unified local launcher for one-click visit-packet assembly.');
      return;
    }
    if (compatibility.level === 'incompatible') {
      setVisitPacketState('error');
      setVisitPacketMessage('This pair fails the local longitudinal safety gates.');
      return;
    }
    const baselineViewport = baselineViewportRef.current;
    const followupViewport = followupViewportRef.current;
    if (!baselineViewport || !followupViewport) {
      setVisitPacketState('error');
      setVisitPacketMessage('Both displayed images must finish rendering before export.');
      return;
    }
    setVisitPacketState('working');
    setVisitPacketMessage('Capturing both displayed source images and validating locally…');
    try {
      const createdAt = new Date().toISOString();
      const [baselineArchive, followupArchive] = await Promise.all([
        baselineViewport.createKeyImageArchive(createdAt),
        followupViewport.createKeyImageArchive(createdAt),
      ]);
      const result = await saveLocalVisitPacket(
        baselineArchive.bytes,
        followupArchive.bytes,
      );
      setVisitPacketState('saved');
      setVisitPacketMessage(
        `Saved ${result.filename}: unreviewed side-by-side evidence, no response conclusion.`,
      );
    } catch (error) {
      setVisitPacketState('error');
      setVisitPacketMessage(
        error instanceof Error ? error.message : 'Local visit-packet export failed.',
      );
    }
  };

  const exportConsultationPacket = async () => {
    if (!baseline || !followup) {
      setConsultationPacketState('error');
      setConsultationPacketMessage('Choose both Image A and Image B first.');
      return;
    }
    if (!visitPacketUsesLoopback) {
      setConsultationPacketState('error');
      setConsultationPacketMessage(
        'Use the unified local launcher for source-verified consultation assembly.',
      );
      return;
    }
    if (!isConsultationSourcePair(baseline, followup)) {
      setConsultationPacketState('error');
      setConsultationPacketMessage(
        'Choose one MR and one CT view from distinct studies with one matching opaque patient context.',
      );
      return;
    }
    const viewA = baselineViewportRef.current;
    const viewB = followupViewportRef.current;
    if (!viewA || !viewB) {
      setConsultationPacketState('error');
      setConsultationPacketMessage('Both selected images must finish rendering before export.');
      return;
    }
    setConsultationPacketState('working');
    setConsultationPacketMessage(
      'Capturing both selected images and verifying their exact local DICOM sources…',
    );
    try {
      const createdAt = new Date().toISOString();
      const [viewAArchive, viewBArchive] = await Promise.all([
        viewA.createConsultationKeyImageArchive('view_a', createdAt),
        viewB.createConsultationKeyImageArchive('view_b', createdAt),
      ]);
      const result = await saveLocalConsultationPacket(viewAArchive.bytes, viewBArchive.bytes);
      setConsultationPacketState('saved');
      setConsultationPacketMessage(
        `Saved ${result.filename}: reference views only, no temporal or response conclusion.`,
      );
    } catch (error) {
      setConsultationPacketState('error');
      setConsultationPacketMessage(
        error instanceof Error ? error.message : 'Local consultation-packet export failed.',
      );
    }
  };

  const validateAgentConsultationPlan = async () => {
    if (agentConsultationPlanState === 'working') return;
    if (!consultPrepMode) {
      setAgentConsultationPlanState('error');
      setAgentConsultationPlanMessage(
        'Agent consultation plans are available only in the neutral Consult Prep workspace.',
      );
      return;
    }
    if (!agentConsultationPlanText.trim()) {
      setAgentConsultationPlanState('error');
      setAgentConsultationPlanMessage('Paste an agent consultation plan first.');
      return;
    }
    setAgentConsultationPlanState('working');
    setAgentConsultationPlanMessage(
      'Checking the plan against this exact local catalog and resolving every native source…',
    );
    try {
      const loaded = await loadAgentConsultationPlan(
        agentConsultationPlanText,
        series,
      );
      setAgentConsultationPlan(loaded);
      setAgentConsultationPlanState('saved');
      setAgentConsultationPlanMessage(
        `Validated ${loaded.items.length} unreviewed agent proposals. Open each deliberately; nothing has been captured or interpreted.`,
      );
    } catch (error) {
      setAgentConsultationPlan(undefined);
      setAgentConsultationPlanState('error');
      setAgentConsultationPlanMessage(
        error instanceof Error
          ? error.message
          : 'The local agent consultation plan could not be validated.',
      );
    }
  };

  const openPresentationState = (
    resolved: ResolvedPresentationState,
    target: PresentationStateTarget,
    slot: 'image_a' | 'image_b',
  ) => {
    sourceSegmentationOperationRef.current += 1;
    sourceSegmentationAbortRef.current?.abort();
    sourceSegmentationAbortRef.current = undefined;
    setSourceSegmentationOpening(false);
    const application: AppliedPresentationState = {
      state: resolved.state,
      target,
    };
    setActiveTool('window');
    setMprSeriesId(undefined);
    setLoadedSourceSegmentation(undefined);
    if (slot === 'image_a') {
      setBaselineId(target.seriesId);
      setBaselineIndex(target.instanceIndex);
      setBaselinePresentationState(application);
    } else {
      setFollowupId(target.seriesId);
      setFollowupIndex(target.instanceIndex);
      setFollowupPresentationState(application);
    }
    setPresentationStateMessage(
      `Opened a supported GSPS subset on exact referenced ${target.modality} image ${target.stackPosition} / ${target.stackCount} in ${slot === 'image_a' ? 'Image A' : 'Image B'}. Creator identity and source-text meaning are not assessed. No ScanView measurement, finding, diagnosis, or conclusion was created.`,
    );
  };

  const openSourceSegmentation = async (
    resolved: ResolvedSourceSegmentation,
    segment: SourceSegment,
  ) => {
    const generation = sourceGenerationRef.current;
    const operation = sourceSegmentationOperationRef.current + 1;
    sourceSegmentationOperationRef.current = operation;
    sourceSegmentationAbortRef.current?.abort();
    const controller = new AbortController();
    sourceSegmentationAbortRef.current = controller;
    setSourceSegmentationOpening(true);
    setSourceSegmentationMessage(
      'Fetching, rehashing, and checking the browser-session-only dense binary mask locally…',
    );
    try {
      const loaded = await loadSourceSegmentationMask(resolved, segment, controller.signal);
      if (
        controller.signal.aborted ||
        generation !== sourceGenerationRef.current ||
        operation !== sourceSegmentationOperationRef.current
      ) return;
      setBaselinePresentationState(undefined);
      setFollowupPresentationState(undefined);
      setLoadedSourceSegmentation(loaded);
      setMprSeriesId(loaded.series.id);
      setSourceSegmentationMessage(
        `Rehashed read-only segment ${segment.segment_number}; building its exact ${loaded.series.modality} native-grid display locally…`,
      );
    } catch (error) {
      if (
        controller.signal.aborted ||
        generation !== sourceGenerationRef.current ||
        operation !== sourceSegmentationOperationRef.current
      ) return;
      setSourceSegmentationOpening(false);
      setSourceSegmentationMessage(
        error instanceof Error
          ? error.message
          : 'Source-carried DICOM segmentation could not be opened. No mask was displayed.',
      );
    }
  };

  const finishSourceSegmentationOpen = useCallback(() => {
    sourceSegmentationAbortRef.current = undefined;
    setSourceSegmentationOpening(false);
    setSourceSegmentationMessage(
      'Opened the rehashed read-only source DICOM SEG mask on its exact native grid. Creator identity, algorithm accuracy, boundary accuracy, and source clinical meaning are not assessed.',
    );
  }, []);

  const failSourceSegmentationOpen = useCallback((message: string) => {
    sourceSegmentationOperationRef.current += 1;
    sourceSegmentationAbortRef.current?.abort();
    sourceSegmentationAbortRef.current = undefined;
    setLoadedSourceSegmentation(undefined);
    setMprSeriesId(undefined);
    setSourceSegmentationOpening(false);
    setSourceSegmentationMessage(`${message} No source DICOM SEG mask was displayed.`);
  }, []);

  const closeSourceSegmentation = () => {
    sourceSegmentationOperationRef.current += 1;
    sourceSegmentationAbortRef.current?.abort();
    sourceSegmentationAbortRef.current = undefined;
    setLoadedSourceSegmentation(undefined);
    setMprSeriesId(undefined);
    setSourceSegmentationOpening(false);
    setSourceSegmentationMessage(
      'Closed the read-only source DICOM SEG display. Original DICOM images and segmentation objects were not changed.',
    );
  };

  const clearPresentationState = (slot: 'image_a' | 'image_b') => {
    if (slot === 'image_a') {
      setBaselinePresentationState(undefined);
    } else {
      setFollowupPresentationState(undefined);
    }
    setPresentationStateMessage(
      `Cleared the local GSPS-derived display from ${slot === 'image_a' ? 'Image A' : 'Image B'}. Native DICOM and source presentation objects were not changed.`,
    );
  };

  const lockPresentationState = (
    slot: 'image_a' | 'image_b',
    message: string,
  ) => {
    if (slot === 'image_a') {
      setBaselinePresentationState(undefined);
    } else {
      setFollowupPresentationState(undefined);
    }
    setPresentationStateMessage(message);
  };

  const openAgentConsultationPlanItem = (
    item: ResolvedAgentConsultationPlanItem,
    slot: 'view_a' | 'view_b',
  ) => {
    if (!agentConsultationPlan || !consultPrepMode) return;
    if (slot === 'view_a') {
      setBaselinePresentationState(undefined);
      setBaselineId(item.seriesId);
      setBaselineIndex(item.instanceIndex);
    } else {
      setFollowupPresentationState(undefined);
      setFollowupId(item.seriesId);
      setFollowupIndex(item.instanceIndex);
    }
    setConsultationBoardLabel(item.discussionHeading);
    setAgentConsultationPlanState('saved');
    setAgentConsultationPlanMessage(
      `Opened ${item.itemId.replace('_', ' ')} in ${slot === 'view_a' ? 'Image A' : 'Image B'} and copied its unreviewed heading into the board form. Inspect the native image before deciding whether to capture it.`,
    );
  };

  const clearAgentConsultationPlan = () => {
    setAgentConsultationPlanText('');
    setAgentConsultationPlan(undefined);
    setAgentConsultationPlanState('idle');
    setAgentConsultationPlanMessage(
      'Cleared the in-memory plan. Native DICOM and consultation-board captures were not changed.',
    );
  };

  const addConsultationBoardView = async (slot: 'view_a' | 'view_b') => {
    if (consultationBoardOperationRef.current) return;
    const label = consultationBoardLabel;
    const labelError = consultationBoardLabelError(label);
    if (labelError) {
      setConsultationBoardState('error');
      setConsultationBoardMessage(labelError);
      return;
    }
    if (!consultPrepMode) {
      setConsultationBoardState('error');
      setConsultationBoardMessage('Consultation boards are available only in Consult Prep.');
      return;
    }
    if (consultationBoardItems.length >= CONSULTATION_BOARD_MAX_ITEMS) {
      setConsultationBoardState('error');
      setConsultationBoardMessage(
        `A consultation board can contain at most ${CONSULTATION_BOARD_MAX_ITEMS} views.`,
      );
      return;
    }
    const selectedSeries = slot === 'view_a' ? baseline : followup;
    const sourcePresentation =
      slot === 'view_a' ? baselinePresentationState : followupPresentationState;
    if (sourcePresentation) {
      setConsultationBoardState('error');
      setConsultationBoardMessage(
        `Clear the source-carried GSPS state from ${slot === 'view_a' ? 'Image A' : 'Image B'} before capturing board evidence.`,
      );
      return;
    }
    const viewport =
      slot === 'view_a' ? baselineViewportRef.current : followupViewportRef.current;
    if (!selectedSeries || !viewport) {
      setConsultationBoardState('error');
      setConsultationBoardMessage(
        `Choose and finish rendering ${slot === 'view_a' ? 'Image A' : 'Image B'} first.`,
      );
      return;
    }
    if (selectedSeries.sourceKind !== 'loopback-service') {
      setConsultationBoardState('error');
      setConsultationBoardMessage(
        'Use the unified local launcher so every board item can be rebound to exact DICOM bytes.',
      );
      return;
    }
    consultationBoardOperationRef.current = true;
    setConsultationBoardState('working');
    setConsultationBoardMessage(
      `Capturing ${slot === 'view_a' ? 'Image A' : 'Image B'} locally and binding its source…`,
    );
    try {
      const capture = await viewport.createConsultationKeyImageArchive(
        slot,
        new Date().toISOString(),
      );
      const source = capture.packet.source;
      if (
        consultationBoardItems.some((item) => item.instanceId === source.instance_id)
      ) {
        throw new Error(
          'That exact source instance is already on the board. Choose another slice or remove the existing item.',
        );
      }
      const existingContext = consultationBoardItems[0]?.patientContextId;
      if (existingContext && existingContext !== source.patient_context_id) {
        throw new Error('All board views must use one matching opaque patient context.');
      }
      const nextItems = [
        ...consultationBoardItems,
        {
          id: crypto.randomUUID(),
          selectionSlot: slot,
          discussionLabel: label,
          archive: capture.bytes,
          studyId: source.study_id,
          instanceId: source.instance_id,
          patientContextId: source.patient_context_id,
          modality: source.modality,
          seriesDescription: source.series_description,
          stackPosition: capture.packet.display.stack_position,
          stackCount: capture.packet.display.stack_count,
        },
      ];
      setConsultationBoardItems(nextItems);
      setConsultationBoardLabel('');
      setConsultationBoardState('idle');
      const nextModalities = new Set(nextItems.map((item) => item.modality));
      const nextStudies = new Set(nextItems.map((item) => item.studyId));
      const missingRequirements = [
        nextItems.length < CONSULTATION_BOARD_MIN_ITEMS ? 'at least two views' : undefined,
        !nextModalities.has('MR') ? 'an MR view' : undefined,
        !nextModalities.has('CT') ? 'a CT view' : undefined,
        nextStudies.size < 2 ? 'a second study' : undefined,
      ].filter((value): value is string => Boolean(value));
      setConsultationBoardMessage(
        missingRequirements.length === 0
          ? `Added “${label}” in memory. The ordered board is ready to save locally.`
          : `Added “${label}” in memory. Still needed: ${missingRequirements.join(', ')}.`,
      );
    } catch (error) {
      setConsultationBoardState('error');
      setConsultationBoardMessage(
        error instanceof Error ? error.message : 'Local consultation-board capture failed.',
      );
    } finally {
      consultationBoardOperationRef.current = false;
    }
  };

  const removeConsultationBoardItem = (id: string) => {
    if (consultationBoardOperationRef.current) return;
    setConsultationBoardItems((current) => current.filter((item) => item.id !== id));
    setConsultationBoardState('idle');
    setConsultationBoardMessage(
      'Removed the in-memory capture. Original DICOM and previously downloaded files were not changed.',
    );
  };

  const moveConsultationBoardItem = (id: string, offset: -1 | 1) => {
    if (consultationBoardOperationRef.current) return;
    setConsultationBoardItems((current) => {
      const index = current.findIndex((item) => item.id === id);
      const targetIndex = index + offset;
      if (index < 0 || targetIndex < 0 || targetIndex >= current.length) return current;
      const reordered = [...current];
      [reordered[index], reordered[targetIndex]] = [
        reordered[targetIndex],
        reordered[index],
      ];
      return reordered;
    });
    setConsultationBoardState('idle');
    setConsultationBoardMessage(
      'Updated the board order in memory. Order is preserved in the saved evidence board.',
    );
  };

  const clearConsultationBoard = () => {
    if (consultationBoardOperationRef.current) return;
    setConsultationBoardItems([]);
    setConsultationBoardLabel('');
    setConsultationBoardState('idle');
    setConsultationBoardMessage(
      'Cleared all in-memory board captures. Original DICOM was not changed.',
    );
  };

  const exportConsultationBoard = async () => {
    if (consultationBoardOperationRef.current) return;
    if (!consultationBoardReady) {
      setConsultationBoardState('error');
      setConsultationBoardMessage(
        'Add 2–8 distinct source views containing both MR and CT from at least two studies.',
      );
      return;
    }
    consultationBoardOperationRef.current = true;
    setConsultationBoardState('working');
    setConsultationBoardMessage(
      'Rehashing every exact local DICOM source and assembling the board in memory…',
    );
    try {
      const result = await saveLocalConsultationBoard(
        consultationBoardItems.map((item) => ({
          discussionLabel: item.discussionLabel,
          archive: item.archive,
        })),
      );
      setConsultationBoardState('saved');
      setConsultationBoardMessage(
        `Saved ${result.filename}: ${consultationBoardItems.length} unreviewed reference views, no comparison or response conclusion.`,
      );
    } catch (error) {
      setConsultationBoardState('error');
      setConsultationBoardMessage(
        error instanceof Error ? error.message : 'Local consultation-board export failed.',
      );
    } finally {
      consultationBoardOperationRef.current = false;
    }
  };

  const exportComparisonReview = async () => {
    if (!measurementComparisonDraft) {
      setComparisonReviewState('error');
      setComparisonReviewMessage('Build an explicit numeric preview before review export.');
      return;
    }
    if (!baseline || !followup) {
      setComparisonReviewState('error');
      setComparisonReviewMessage('Choose both a baseline and follow-up series first.');
      return;
    }
    if (!visitPacketUsesLoopback) {
      setComparisonReviewState('error');
      setComparisonReviewMessage(
        'Use the unified local launcher for one-click comparison-review assembly.',
      );
      return;
    }
    if (compatibility.level === 'incompatible') {
      setComparisonReviewState('error');
      setComparisonReviewMessage('This pair fails the local longitudinal safety gates.');
      return;
    }
    if (!comparisonSourcesVisible) {
      setComparisonReviewState('error');
      setComparisonReviewMessage(
        'Both panes must display the exact source slices for the selected measurements.',
      );
      return;
    }
    const baselineViewport = baselineViewportRef.current;
    const followupViewport = followupViewportRef.current;
    if (!baselineViewport || !followupViewport) {
      setComparisonReviewState('error');
      setComparisonReviewMessage('Both displayed images must finish rendering before export.');
      return;
    }
    setComparisonReviewState('working');
    setComparisonReviewMessage(
      'Capturing the exact selected source slices and assembling the review archive locally…',
    );
    try {
      const createdAt = new Date().toISOString();
      const [baselineArchive, followupArchive] = await Promise.all([
        baselineViewport.createKeyImageArchive(createdAt),
        followupViewport.createKeyImageArchive(createdAt),
      ]);
      const result = await saveLocalComparisonReview(
        baselineArchive.bytes,
        followupArchive.bytes,
        measurementComparisonDraft,
      );
      setComparisonReviewState('saved');
      setComparisonReviewMessage(
        `Saved ${result.filename}: exact local visual/numeric evidence, still unreviewed.`,
      );
    } catch (error) {
      setComparisonReviewState('error');
      setComparisonReviewMessage(
        error instanceof Error ? error.message : 'Local comparison-review export failed.',
      );
    }
  };

  return (
    <main>
      <header className="app-header">
        <div className="brand">
          <div className="brand-mark" aria-hidden="true">
            SV
          </div>
          <div>
            <h1>ScanView</h1>
            <p>{consultPrepMode ? 'Consult preparation workspace' : 'Longitudinal imaging workspace'}</p>
          </div>
        </div>
        <div className="safety-banner">
          <strong>Research &amp; communication tool</strong>
          <span>Not validated for diagnosis. Clinician review is required.</span>
        </div>
        <button className="import-button" onClick={openFolder}>
          Open DICOM folder
        </button>
        <input
          ref={inputRef}
          className="hidden-input"
          type="file"
          multiple
          // Supported by current Chromium and Safari; React's type omits the attribute.
          {...({ webkitdirectory: '' } as Record<string, string>)}
          onChange={(event) => void chooseFiles(event.target.files)}
        />
        <input
          ref={measurementInputRef}
          className="hidden-input"
          type="file"
          accept="application/json,.json"
          onChange={(event) => void loadMeasurementDraft(event.target.files)}
        />
      </header>

      <section className="workspace-summary">
        <div>
          <span className={`status-dot ${series.length ? 'ready' : ''}`} />
          {importState
            ? `Reading ${importState.processed.toLocaleString()} of ${importState.total.toLocaleString()} files`
            : importMessage}
        </div>
        <div className="privacy-note">Local processing · no telemetry · originals remain unchanged</div>
      </section>

      {series.length === 0 ? (
        <section className="empty-state">
          <div className="empty-orbit" aria-hidden="true">
            <span />
          </div>
          <span className="eyebrow">Start with source fidelity</span>
          <h2>Open a copied DICOM folder</h2>
          <p>
            ScanView reads headers and pixels locally. It does not upload studies, modify source
            files, or claim a clinical interpretation.
          </p>
          <button className="primary-action" onClick={openFolder}>
            Choose folder
          </button>
          <div className="empty-steps">
            <span><b>1</b> Inventory studies</span>
            <span><b>2</b> Pair comparable series</span>
            <span><b>3</b> Review native images</span>
          </div>
        </section>
      ) : (
        <>
          <section className="selection-panel">
            <SeriesSelect
              label={consultPrepMode ? 'Image A series' : 'Baseline series'}
              value={baselineId}
              series={series}
              disabled={presentationStateActive}
              onChange={(id) => {
                setBaselinePresentationState(undefined);
                setBaselineId(id);
                setBaselineIndex(
                  Math.floor((series.find((item) => item.id === id)?.instances.length ?? 1) / 2),
                );
                setMeasurementComparisonDraft(undefined);
              }}
            />
            <button
              className={`sync-button ${effectiveSynchronized && baseline && followup ? 'active' : ''}`}
              onClick={() => setSynchronized((value) => !value)}
              aria-pressed={Boolean(effectiveSynchronized && baseline && followup)}
              disabled={
                !baseline ||
                !followup ||
                presentationStateActive ||
                (consultPrepMode && linkStrategy !== 'patient-position')
              }
            >
              {!baseline || !followup
                ? 'Link after pairing'
                : consultPrepMode && linkStrategy !== 'patient-position'
                  ? 'Independent reference views'
                : effectiveSynchronized
                  ? linkStrategy === 'patient-position'
                    ? 'Patient-position linked'
                    : 'Approximate index link'
                  : 'Independent slices'}
            </button>
            <SeriesSelect
              label={consultPrepMode ? 'Image B series' : 'Follow-up series'}
              value={followupId}
              series={series}
              disabled={presentationStateActive}
              onChange={(id) => {
                setFollowupPresentationState(undefined);
                setFollowupId(id);
                setFollowupIndex(
                  Math.floor((series.find((item) => item.id === id)?.instances.length ?? 1) / 2),
                );
                setMeasurementComparisonDraft(undefined);
              }}
            />
          </section>

          <section className="viewer-toolbar" aria-label="Viewer tools">
            <div className="tool-buttons">
              {([
                ['window', 'Window / level'],
                ['pan', 'Pan'],
                ['zoom', 'Zoom'],
                ['length', 'Length'],
                ['bidirectional', 'Bidirectional'],
                ['roi', 'Ellipse ROI'],
              ] as const).map(([tool, label]) => (
                <button
                  key={tool}
                  className={activeTool === tool ? 'active' : ''}
                  aria-pressed={activeTool === tool}
                  disabled={presentationStateActive}
                  onClick={() => setActiveTool(tool)}
                >
                  {label}
                </button>
              ))}
              <button
                onClick={() => {
                  setBaselinePresentationState(undefined);
                  setFollowupPresentationState(undefined);
                  setResetNonce((value) => value + 1);
                }}
              >
                Reset views
              </button>
              <button disabled={presentationStateActive} onClick={exportMeasurementDraft}>
                Export measurement draft
              </button>
              <button disabled={presentationStateActive} onClick={openMeasurementDraft}>
                Open measurement draft
              </button>
              <button
                aria-expanded={measurementPasteOpen}
                disabled={presentationStateActive}
                onClick={() => setMeasurementPasteOpen((value) => !value)}
              >
                Paste measurement JSON
              </button>
              <button
                className={agentStateSharing ? 'active' : ''}
                aria-pressed={agentStateSharing}
                disabled={!viewerStatePublication}
                title={
                    viewerStatePublication
                      ? 'Opt in to an expiring, privacy-minimized state for bearer-authorized local agents'
                      : presentationStateActive
                      ? 'Unavailable until source-carried GSPS states are cleared'
                      : sourceSegmentationActive
                        ? 'Unavailable until the source-carried DICOM SEG mask is closed'
                      : consultPrepMode
                      ? 'Live agent state is unavailable because its current schema uses longitudinal pane roles; use a consultation packet instead'
                    : 'Available only through the authenticated local launcher'
                }
                onClick={toggleAgentStateSharing}
              >
                Agent state: {agentStateSharing ? 'on' : 'off'}
              </button>
              {consultPrepMode ? (
                <button
                  className={`visit-packet-button ${consultationPacketState}`}
                  disabled={!consultationPacketReady || evidenceExportWorking}
                  title={
                    presentationStateActive
                      ? 'Clear source-carried GSPS states before evidence export'
                      : !baseline || !followup
                      ? 'Choose Image A and Image B'
                      : !visitPacketUsesLoopback
                        ? 'Available through the unified local launcher'
                        : !isConsultationSourcePair(baseline, followup)
                          ? 'Choose one MR and one CT from distinct studies with one matching patient context'
                          : 'Save source-verified reference views for a clinician discussion'
                  }
                  onClick={() => void exportConsultationPacket()}
                >
                  {consultationPacketState === 'working'
                    ? 'Building consultation packet…'
                    : consultationPacketState === 'saved'
                      ? 'Saved consultation packet'
                      : consultationPacketState === 'error'
                        ? 'Consultation packet failed'
                        : 'Save consultation packet'}
                </button>
              ) : (
                <>
                  <button
                    className={`visit-packet-button ${visitPacketState}`}
                    disabled={!visitPacketReady || evidenceExportWorking}
                    title={
                      presentationStateActive
                        ? 'Clear source-carried GSPS states before evidence export'
                        : !baseline || !followup
                        ? 'Choose a baseline and follow-up series'
                        : !visitPacketUsesLoopback
                          ? 'Available through the unified local launcher'
                          : compatibility.level === 'incompatible'
                            ? 'The selected pair fails longitudinal safety gates'
                            : 'Capture both displayed images and save one locally validated visit packet'
                    }
                    onClick={() => void exportVisitPacket()}
                  >
                    {visitPacketState === 'working'
                      ? 'Building visit packet…'
                      : visitPacketState === 'saved'
                        ? 'Saved visit packet'
                        : visitPacketState === 'error'
                          ? 'Visit packet failed'
                          : 'Save visit packet'}
                  </button>
                  <button
                    className={`review-packet-button ${comparisonReviewState}`}
                    disabled={!comparisonReviewReady || evidenceExportWorking}
                    title={
                      presentationStateActive
                        ? 'Clear source-carried GSPS states before evidence export'
                        : !measurementComparisonDraft
                        ? 'Build an explicit numeric preview first'
                        : !visitPacketUsesLoopback
                          ? 'Available through the unified local launcher'
                          : compatibility.level === 'incompatible'
                            ? 'The selected pair fails longitudinal safety gates'
                            : !comparisonSourcesVisible
                              ? 'Display the exact selected measurement source slices'
                              : 'Bind both displayed images and the numeric pair into one local review ZIP'
                    }
                    onClick={() => void exportComparisonReview()}
                  >
                    {comparisonReviewState === 'working'
                      ? 'Building review packet…'
                      : comparisonReviewState === 'saved'
                        ? 'Saved review packet'
                        : comparisonReviewState === 'error'
                          ? 'Review packet failed'
                          : 'Save review packet'}
                  </button>
                </>
              )}
            </div>
            <p>
              Primary drag:{' '}
              {['length', 'bidirectional', 'roi'].includes(activeTool)
                ? 'unreviewed measurement'
                : activeTool}{' '}
              · wheel: slices · {consultPrepMode
                ? linkStrategy === 'patient-position' && baseline && followup
                  ? 'optional patient-position linking; no registration implied'
                  : 'reference views remain independent'
                : !baseline || !followup
                  ? 'choose a follow-up to link'
                  : linkStrategy === 'patient-position'
                    ? 'shared-frame physical linking'
                    : 'index linking is approximate'}<br />
              {measurementMessage}<br />
              {consultPrepMode ? (
                <>{consultationPacketMessage}<br /></>
              ) : (
                <>{visitPacketMessage}<br />{comparisonReviewMessage}<br /></>
              )}
              {agentStateMessage}
            </p>
          </section>

          {measurementPasteOpen && (
            <section className="measurement-paste-panel" aria-label="Paste local measurement JSON">
              <div>
                <span className="eyebrow">Agent-friendly local import · strict validation</span>
                <h2>Paste a ScanView measurement draft</h2>
                <p>
                  The text stays in this browser session. Unsupported fields, altered arithmetic,
                  reviewed state, and invalid source provenance are rejected.
                </p>
              </div>
              <textarea
                aria-label="Measurement draft JSON"
                value={measurementPasteValue}
                maxLength={maxPastedMeasurementBytes}
                spellCheck={false}
                placeholder="Paste versioned ScanView measurement JSON"
                onChange={(event) => setMeasurementPasteValue(event.target.value)}
              />
              <div className="measurement-paste-actions">
                <button className="primary-action" onClick={importPastedMeasurementDraft}>
                  Validate and load locally
                </button>
                <button onClick={() => setMeasurementPasteOpen(false)}>Cancel</button>
              </div>
            </section>
          )}

          <section className="viewport-grid">
            <DicomViewport
              ref={baselineViewportRef}
              id="baseline"
              label={consultPrepMode ? 'Image A' : 'Baseline'}
              series={baseline}
              index={baselineIndex}
              onIndexChange={(index) => updateIndex('baseline', index)}
              activeTool={activeTool}
              resetNonce={resetNonce}
              measurementPacket={measurementPacket}
              presentationState={baselinePresentationState}
              interactionLocked={presentationStateActive || sourceSegmentationOpening}
              onPresentationStateError={(message) =>
                lockPresentationState('image_a', message)
              }
              consultationSelectionSlot={consultPrepMode ? 'view_a' : undefined}
              onOpenMpr={() => {
                sourceSegmentationOperationRef.current += 1;
                sourceSegmentationAbortRef.current?.abort();
                sourceSegmentationAbortRef.current = undefined;
                setSourceSegmentationOpening(false);
                setLoadedSourceSegmentation(undefined);
                if (baseline) setMprSeriesId(baseline.id);
              }}
            />
            <DicomViewport
              ref={followupViewportRef}
              id="followup"
              label={consultPrepMode ? 'Image B' : 'Follow-up'}
              series={followup}
              index={followupIndex}
              onIndexChange={(index) => updateIndex('followup', index)}
              activeTool={activeTool}
              resetNonce={resetNonce}
              measurementPacket={measurementPacket}
              presentationState={followupPresentationState}
              interactionLocked={presentationStateActive || sourceSegmentationOpening}
              onPresentationStateError={(message) =>
                lockPresentationState('image_b', message)
              }
              consultationSelectionSlot={consultPrepMode ? 'view_b' : undefined}
              onOpenMpr={() => {
                sourceSegmentationOperationRef.current += 1;
                sourceSegmentationAbortRef.current?.abort();
                sourceSegmentationAbortRef.current = undefined;
                setSourceSegmentationOpening(false);
                setLoadedSourceSegmentation(undefined);
                if (followup) setMprSeriesId(followup.id);
              }}
            />
          </section>

          {mprSeries && (
            <MprPanel
              series={mprSeries}
              readonlySourceSegmentation={loadedSourceSegmentation}
              onReadonlyReady={finishSourceSegmentationOpen}
              onReadonlyError={failSourceSegmentationOpen}
              onClose={() => {
                if (loadedSourceSegmentation) closeSourceSegmentation();
                else setMprSeriesId(undefined);
              }}
            />
          )}

          {!presentationStateActive && !consultPrepMode && (
            <LesionVolumeComparisonPanel
              series={series}
              selectedBaselineSeriesId={baselineId}
              selectedFollowupSeriesId={followupId}
            />
          )}

          <section className="review-grid">
            {consultPrepMode ? (
              <article className="compatibility-card review">
                <div className="card-heading">
                  <div>
                    <span className="eyebrow">Follow-up readiness · metadata only</span>
                    <h2>No same-modality follow-up pair</h2>
                  </div>
                  <span className="unreviewed-badge">
                    {longitudinalReadiness.candidatePairCount} candidates
                  </span>
                </div>
                <div className="readiness-counts" aria-label="Local modality inventory">
                  {longitudinalReadiness.modalityReadiness.map((item) => (
                    <span key={item.modality}>
                      <strong>{item.modality}</strong>{' '}
                      {item.studyCount} {item.studyCount === 1 ? 'study' : 'studies'} ·{' '}
                      {item.eligibleSeriesCount} eligible series
                    </span>
                  ))}
                </div>
                <ul>
                  {longitudinalReadiness.missingData.map((requirement) => (
                    <li key={requirement}>{readinessRequirementText(requirement)}</li>
                  ))}
                  <li>
                    {isConsultationSourcePair(baseline, followup)
                      ? 'The selected MR and CT use one matching opaque patient context and distinct source studies, but they are consultation references—not a longitudinal pair.'
                      : 'A consultation board may use one MR and one CT from distinct studies with one matching opaque patient context; those views still do not form a longitudinal pair.'}
                  </li>
                  <li>
                    Even after a candidate appears, a person must confirm identity, clinical timepoint
                    roles, sequence, contrast, coverage, artifact, and lesion/tissue definitions.
                  </li>
                  <li>
                    Current MR and CT images remain unregistered reference views; no chronological,
                    anatomical, intensity, same-lesion, response, or treatment-effect claim is made.
                  </li>
                </ul>
              </article>
            ) : (
              <article className={`compatibility-card ${compatibility.level}`}>
                <div className="card-heading">
                  <div>
                    <span className="eyebrow">Pairing suggestion · never auto-approved</span>
                    <h2>
                      {compatibility.level === 'compatible'
                        ? 'Plausibly comparable'
                        : 'Review compatibility'}
                    </h2>
                  </div>
                  <div className="score">{compatibility.score}<small>/100</small></div>
                </div>
                <ul>
                  {compatibility.reasons.map((reason) => <li key={reason}>{reason}</li>)}
                </ul>
              </article>
            )}
            <article className="locked-card">
              <div className="lock-icon" aria-hidden="true">×</div>
              <div>
                <span className="eyebrow">
                  {consultPrepMode ? 'Comparison unavailable' : 'Derived comparison locked'}
                </span>
                <h2>
                  {consultPrepMode ? 'Use these views for discussion only' : 'Registration review required'}
                </h2>
                <p>
                  {consultPrepMode
                    ? 'This workspace does not compute change, pair lesions, register images, or generate a treatment-response conclusion.'
                    : 'Overlay, swipe, and subtraction remain disabled until a spatial transform is created and explicitly accepted for display. CT and MRI intensities are never subtracted.'}
                </p>
              </div>
            </article>
          </section>
          {series.some((item) => item.sourceKind === 'loopback-service') && (
            <>
              <PresentationStatePanel
                catalog={presentationStateCatalog}
                message={presentationStateMessage}
                loading={presentationStateLoading}
                disabled={evidenceExportWorking || sourceSegmentationOpening}
                imageA={baselinePresentationState}
                imageB={followupPresentationState}
                onOpen={openPresentationState}
                onClear={clearPresentationState}
              />
              <SourceSegmentationPanel
                catalog={sourceSegmentationCatalog}
                message={sourceSegmentationMessage}
                loading={sourceSegmentationLoading}
                opening={sourceSegmentationOpening}
                active={loadedSourceSegmentation}
                disabled={
                  evidenceExportWorking || presentationStateActive || Boolean(mprSeriesId)
                }
                onOpen={(segmentation, segment) =>
                  void openSourceSegmentation(segmentation, segment)}
                onClear={closeSourceSegmentation}
              />
            </>
          )}
          {!presentationStateActive && consultPrepMode && (
            <section
              className="agent-consultation-plan-panel"
              aria-labelledby="agent-consultation-plan-heading"
            >
              <div className="agent-consultation-plan-heading">
                <div>
                  <span className="eyebrow">Agent → person handoff · exact native sources</span>
                  <h2 id="agent-consultation-plan-heading">
                    Review an agent-proposed consultation plan
                  </h2>
                  <p>
                    Paste a plan created locally with <code>scanview-agent</code>. The
                    local service must match its catalog hash and every exact source before
                    navigation controls appear.
                  </p>
                </div>
                <span className="unreviewed-badge">
                  {agentConsultationPlan?.items.length ?? 0} proposals
                </span>
              </div>
              <div className="agent-consultation-plan-input">
                <label>
                  <span>Agent consultation plan JSON</span>
                  <textarea
                    rows={7}
                    value={agentConsultationPlanText}
                    placeholder="Paste scanview.agent-consultation-plan JSON"
                    disabled={agentConsultationPlanState === 'working'}
                    onChange={(event) => {
                      setAgentConsultationPlanText(event.target.value);
                      setAgentConsultationPlan(undefined);
                      setAgentConsultationPlanState('idle');
                      setAgentConsultationPlanMessage(
                        'Plan text changed. Validate it against the exact local catalog before opening a proposal.',
                      );
                    }}
                  />
                </label>
                <div className="agent-consultation-plan-actions">
                  <button
                    type="button"
                    className="primary-action"
                    disabled={
                      !agentConsultationPlanText.trim() ||
                      agentConsultationPlanState === 'working' ||
                      evidenceExportWorking
                    }
                    onClick={() => void validateAgentConsultationPlan()}
                  >
                    {agentConsultationPlanState === 'working'
                      ? 'Validating locally…'
                      : agentConsultationPlan
                        ? 'Revalidate plan'
                        : 'Validate local plan'}
                  </button>
                  <button
                    type="button"
                    disabled={
                      (!agentConsultationPlanText && !agentConsultationPlan) ||
                      agentConsultationPlanState === 'working'
                    }
                    onClick={clearAgentConsultationPlan}
                  >
                    Clear in-memory plan
                  </button>
                </div>
              </div>
              {agentConsultationPlan ? (
                <ol className="agent-consultation-plan-items">
                  {agentConsultationPlan.items.map((item) => (
                    <li key={item.itemId}>
                      <div>
                        <span className="agent-proposal-label">
                          {item.itemId.replace('_', ' ')} · software agent unverified ·
                          unreviewed
                        </span>
                        <strong>{item.discussionHeading}</strong>
                        <span>
                          {item.modality} · {item.seriesDescription} · exact native slice{' '}
                          {item.stackPosition} / {item.stackCount}
                        </span>
                      </div>
                      <div className="agent-consultation-plan-item-actions">
                        <button
                          type="button"
                          disabled={evidenceExportWorking}
                          onClick={() => openAgentConsultationPlanItem(item, 'view_a')}
                        >
                          Open in Image A
                        </button>
                        <button
                          type="button"
                          disabled={evidenceExportWorking}
                          onClick={() => openAgentConsultationPlanItem(item, 'view_b')}
                        >
                          Open in Image B
                        </button>
                      </div>
                    </li>
                  ))}
                </ol>
              ) : null}
              <p
                className={agentConsultationPlanState === 'error' ? 'error' : undefined}
                role={agentConsultationPlanState === 'error' ? 'alert' : 'status'}
                aria-live="polite"
              >
                {agentConsultationPlanMessage}
              </p>
              <p className="agent-consultation-plan-safety">
                A validated plan authorizes exact local navigation only. It does not
                authenticate the agent, open a view automatically, capture evidence, establish
                relevance, assign chronology, link a lesion, diagnose, or assess treatment
                response. A person must inspect each native image and explicitly decide what to
                retain.
              </p>
            </section>
          )}
          {!presentationStateActive && consultPrepMode && (
            <section
              className="consultation-board-panel"
              aria-labelledby="consultation-board-heading"
            >
              <div className="consultation-board-heading">
                <div>
                  <span className="eyebrow">Local consultation evidence · 2–8 views</span>
                  <h2 id="consultation-board-heading">Build a source-bound discussion board</h2>
                  <p>
                    Add the currently rendered Image A or Image B with an explicit heading.
                    Headings are unreviewed prompts, not findings. Captures stay in memory unless
                    you clear the board or load another folder.
                  </p>
                </div>
                <span className="unreviewed-badge">
                  {consultationBoardItems.length} / {CONSULTATION_BOARD_MAX_ITEMS} views
                </span>
              </div>
              <div className="consultation-board-controls">
                <label>
                  <span>Discussion heading</span>
                  <input
                    value={consultationBoardLabel}
                    maxLength={CONSULTATION_BOARD_MAX_LABEL_CHARACTERS}
                    placeholder="Example: MRI overview — ask which feature matters"
                    disabled={evidenceExportWorking}
                    aria-invalid={
                      consultationBoardLabel.length > 0 &&
                      Boolean(consultationBoardLabelMessage)
                    }
                    aria-describedby="consultation-board-label-help"
                    onChange={(event) => {
                      setConsultationBoardLabel(event.target.value);
                      if (consultationBoardState !== 'working') {
                        setConsultationBoardState('idle');
                      }
                    }}
                  />
                  <small
                    id="consultation-board-label-help"
                    className={
                      consultationBoardLabel.length > 0 && consultationBoardLabelMessage
                        ? 'error'
                        : undefined
                    }
                  >
                    {consultationBoardLabel.length === 0
                      ? `Required · 1–${CONSULTATION_BOARD_MAX_LABEL_CHARACTERS} characters · saved as an unreviewed heading`
                      : consultationBoardLabelMessage ??
                        `${consultationBoardLabel.length} / ${CONSULTATION_BOARD_MAX_LABEL_CHARACTERS} characters · ready to capture`}
                  </small>
                </label>
                <div>
                  <button
                    type="button"
                    disabled={
                      evidenceExportWorking ||
                      !baseline ||
                      Boolean(baselinePresentationState) ||
                      consultationBoardItems.length >= CONSULTATION_BOARD_MAX_ITEMS ||
                      Boolean(consultationBoardLabelMessage)
                    }
                    onClick={() => void addConsultationBoardView('view_a')}
                  >
                    Add current Image A
                  </button>
                  <button
                    type="button"
                    disabled={
                      evidenceExportWorking ||
                      !followup ||
                      Boolean(followupPresentationState) ||
                      consultationBoardItems.length >= CONSULTATION_BOARD_MAX_ITEMS ||
                      Boolean(consultationBoardLabelMessage)
                    }
                    onClick={() => void addConsultationBoardView('view_b')}
                  >
                    Add current Image B
                  </button>
                </div>
              </div>
              <div className="consultation-board-readiness" aria-label="Board requirements">
                <span className={consultationBoardHasMinimum ? 'ready' : undefined}>
                  {consultationBoardHasMinimum ? '✓' : '○'} 2–8 views
                </span>
                <span className={consultationBoardHasMR ? 'ready' : undefined}>
                  {consultationBoardHasMR ? '✓' : '○'} MR included
                </span>
                <span className={consultationBoardHasCT ? 'ready' : undefined}>
                  {consultationBoardHasCT ? '✓' : '○'} CT included
                </span>
                <span className={consultationBoardHasTwoStudies ? 'ready' : undefined}>
                  {consultationBoardHasTwoStudies ? '✓' : '○'} 2+ studies
                </span>
              </div>
              {consultationBoardItems.length > 0 ? (
                <ol className="consultation-board-items">
                  {consultationBoardItems.map((item, index) => (
                    <li key={item.id}>
                      <div className="consultation-board-item-copy">
                        <strong>{item.discussionLabel}</strong>
                        <span>
                          {item.selectionSlot === 'view_a' ? 'Image A' : 'Image B'} capture ·{' '}
                          {item.modality} · {item.seriesDescription} · source slice{' '}
                          {item.stackPosition} / {item.stackCount}
                        </span>
                      </div>
                      <div className="consultation-board-item-actions">
                        <button
                          type="button"
                          disabled={evidenceExportWorking || index === 0}
                          aria-label={`Move “${item.discussionLabel}” up`}
                          title="Move up in saved display order"
                          onClick={() => moveConsultationBoardItem(item.id, -1)}
                        >
                          ↑
                        </button>
                        <button
                          type="button"
                          disabled={
                            evidenceExportWorking ||
                            index === consultationBoardItems.length - 1
                          }
                          aria-label={`Move “${item.discussionLabel}” down`}
                          title="Move down in saved display order"
                          onClick={() => moveConsultationBoardItem(item.id, 1)}
                        >
                          ↓
                        </button>
                        <button
                          type="button"
                          disabled={evidenceExportWorking}
                          onClick={() => removeConsultationBoardItem(item.id)}
                        >
                          Remove
                        </button>
                      </div>
                    </li>
                  ))}
                </ol>
              ) : (
                <p className="consultation-board-empty">
                  No captures yet. Select a source slice, enter a heading, then add Image A or B.
                </p>
              )}
              <div className="consultation-board-actions">
                <button
                  type="button"
                  className="primary-action"
                  disabled={!consultationBoardReady || evidenceExportWorking}
                  title={
                    consultationBoardReady
                      ? 'Rehash every exact source and save one local agent-verifiable board'
                      : 'Add 2–8 distinct views containing both MR and CT from at least two studies'
                  }
                  onClick={() => void exportConsultationBoard()}
                >
                  {consultationBoardState === 'working'
                    ? 'Working locally…'
                    : consultationBoardState === 'saved'
                      ? 'Saved evidence board'
                      : 'Save evidence board'}
                </button>
                <button
                  type="button"
                  disabled={
                    consultationBoardItems.length === 0 ||
                    evidenceExportWorking
                  }
                  onClick={clearConsultationBoard}
                >
                  Clear in-memory board
                </button>
                <p
                  className={consultationBoardState === 'error' ? 'error' : undefined}
                  role={consultationBoardState === 'error' ? 'alert' : 'status'}
                  aria-live="polite"
                >
                  {consultationBoardMessage}
                </p>
              </div>
              <p className="consultation-board-safety">
                Export requires one matching opaque patient context, both MR and CT, at least two
                studies, distinct source instances, and live source rehashing. Order and labels do
                not establish chronology, alignment, lesion identity, diagnosis, or response. The
                downloaded ZIP is sensitive; move it to a protected local folder and verify its
                permissions before retaining it.
              </p>
            </section>
          )}
          {!presentationStateActive && (
            <MeasurementWorkspace
              measurements={visibleMeasurements}
              baseline={baseline}
              followup={followup}
              compatibilityLevel={compatibility.level}
              allowLongitudinalPairing={!consultPrepMode}
              onDeleteMeasurement={removeMeasurementAnnotation}
              onComparisonDraftChange={setMeasurementComparisonDraft}
            />
          )}
        </>
      )}

      <footer>
        <span>ScanView 0.10 · local-first prototype</span>
        <span>Every automated result is unreviewed until a qualified clinician accepts it.</span>
      </footer>
    </main>
  );
}
