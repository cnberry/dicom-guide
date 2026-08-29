import { useEffect, useMemo, useRef, useState } from 'react';
import { DicomViewport, type DicomViewportHandle } from './components/DicomViewport';
import { MeasurementWorkspace } from './components/MeasurementWorkspace';
import { MprPanel } from './components/MprPanel';
import { LesionVolumeComparisonPanel } from './components/LesionVolumeComparisonPanel';
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
}: {
  label: string;
  value?: string;
  series: DicomSeries[];
  onChange: (id: string) => void;
}) => (
  <label className="series-select">
    <span>{label}</span>
    <select value={value ?? ''} onChange={(event) => onChange(event.target.value)}>
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
  const [agentStateSharing, setAgentStateSharing] = useState(false);
  const [agentStateMessage, setAgentStateMessage] = useState(
    'Agent viewer state is off by default. Enable it to share only expiring opaque positions locally.',
  );

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
  const visitPacketUsesLoopback = Boolean(
    baseline?.sourceKind === 'loopback-service' && followup?.sourceKind === 'loopback-service',
  );
  const visitPacketReady = Boolean(
    !consultPrepMode &&
      baseline &&
      followup &&
      visitPacketUsesLoopback &&
      compatibility.level !== 'incompatible',
  );
  const consultationPacketReady = Boolean(
    consultPrepMode &&
      visitPacketUsesLoopback &&
      isConsultationSourcePair(baseline, followup),
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
    consultationBoardHasTwoStudies;
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
      if (consultPrepMode) return undefined;
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
      consultPrepMode
        ? 'Live agent state is unavailable in Consult Prep because the current state schema uses timepoint roles. Use the neutral consultation packet for agent evidence.'
        : 'Agent viewer state is off by default. Enable it to share only expiring opaque positions locally.',
    );
  }, [agentStateSharing, consultPrepMode]);

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
        consultPrepMode
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
  }, [active, agentPublisherId, agentStateSharing, consultPrepMode, viewerStatePublication]);

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
    void loadLocalServiceCatalog(controller.signal).then((catalog) => {
      if (controller.signal.aborted || generation !== sourceGenerationRef.current) {
        return;
      }
      if (!catalog) {
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
      setSourceReady(true);
    });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!pendingNavigation || !sourceReady) return;
    if (pendingNavigation.intent) {
      const resolved = resolveNavigationIntent(pendingNavigation.intent, series);
      if (resolved.navigation) {
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
    const files = Array.from(fileList).filter((file) => !file.name.startsWith('.'));
    setSeries([]);
    setSourceReady(false);
    setBaselineId(undefined);
    setFollowupId(undefined);
    setMprSeriesId(undefined);
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
        'Agent viewer state requires scans opened through the authenticated local launcher.',
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
              onChange={(id) => {
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
              onChange={(id) => {
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
                  onClick={() => setActiveTool(tool)}
                >
                  {label}
                </button>
              ))}
              <button onClick={() => setResetNonce((value) => value + 1)}>Reset views</button>
              <button onClick={exportMeasurementDraft}>Export measurement draft</button>
              <button onClick={openMeasurementDraft}>Open measurement draft</button>
              <button
                aria-expanded={measurementPasteOpen}
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
                    !baseline || !followup
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
                      !baseline || !followup
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
                      !measurementComparisonDraft
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
              consultationSelectionSlot={consultPrepMode ? 'view_a' : undefined}
              onOpenMpr={() => baseline && setMprSeriesId(baseline.id)}
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
              consultationSelectionSlot={consultPrepMode ? 'view_b' : undefined}
              onOpenMpr={() => followup && setMprSeriesId(followup.id)}
            />
          </section>

          {mprSeries && <MprPanel series={mprSeries} onClose={() => setMprSeriesId(undefined)} />}

          {!consultPrepMode && (
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
          {consultPrepMode && (
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
          <MeasurementWorkspace
            measurements={visibleMeasurements}
            baseline={baseline}
            followup={followup}
            compatibilityLevel={compatibility.level}
            allowLongitudinalPairing={!consultPrepMode}
            onDeleteMeasurement={removeMeasurementAnnotation}
            onComparisonDraftChange={setMeasurementComparisonDraft}
          />
        </>
      )}

      <footer>
        <span>ScanView 0.7 · local-first prototype</span>
        <span>Every automated result is unreviewed until a qualified clinician accepts it.</span>
      </footer>
    </main>
  );
}
