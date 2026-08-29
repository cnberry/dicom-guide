import { useEffect, useMemo, useRef, useState } from 'react';
import { DicomViewport, type DicomViewportHandle } from './components/DicomViewport';
import { MeasurementWorkspace } from './components/MeasurementWorkspace';
import { MprPanel } from './components/MprPanel';
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
import {
  buildViewerStatePublication,
  clearViewerState,
  createViewerStatePublisherId,
  publishViewerState,
  VIEWER_STATE_HEARTBEAT_MS,
} from './viewerStateService';

type ImportState = { processed: number; total: number } | undefined;
type ExportState = 'idle' | 'working' | 'saved' | 'error';
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
  const [agentStateSharing, setAgentStateSharing] = useState(false);
  const [agentStateMessage, setAgentStateMessage] = useState(
    'Agent viewer state is off by default. Enable it to share only expiring opaque positions locally.',
  );

  const baseline = series.find((item) => item.id === baselineId);
  const followup = series.find((item) => item.id === followupId);
  const mprSeries = series.find((item) => item.id === mprSeriesId);
  const compatibility = useMemo(
    () => assessCompatibility(baseline, followup),
    [baseline, followup],
  );
  const linkStrategy = useMemo(() => getLinkStrategy(baseline, followup), [baseline, followup]);
  const visibleMeasurements = liveMeasurementPacket
    ? liveMeasurementPacket.measurements
    : (measurementPacket?.measurements ?? []);
  const visitPacketUsesLoopback = Boolean(
    baseline?.sourceKind === 'loopback-service' && followup?.sourceKind === 'loopback-service',
  );
  const visitPacketReady = Boolean(
    baseline && followup && visitPacketUsesLoopback && compatibility.level !== 'incompatible',
  );
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
    visitPacketState === 'working' || comparisonReviewState === 'working';
  const viewerStatePublication = useMemo(
    () =>
      buildViewerStatePublication({
        publisherId: agentPublisherId,
        activeTool,
        synchronized,
        linkStrategy,
        baseline,
        baselineIndex,
        followup,
        followupIndex,
        mprSeries,
        measurementCount: visibleMeasurements.length,
        comparisonDraftPresent: Boolean(measurementComparisonDraft),
      }),
    [
      activeTool,
      agentPublisherId,
      baseline,
      baselineIndex,
      followup,
      followupIndex,
      linkStrategy,
      measurementComparisonDraft,
      mprSeries,
      synchronized,
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
        'Agent viewer state stopped: it is available only through the authenticated local launcher.',
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
  }, [active, agentPublisherId, agentStateSharing, viewerStatePublication]);

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
      if (synchronized && baseline && followup) {
        setFollowupIndex(mapLinkedIndex(next, baseline, followup).index);
      }
    } else {
      setFollowupIndex(next);
      if (synchronized && baseline && followup) {
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
            <p>Longitudinal imaging workspace</p>
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
              label="Baseline series"
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
              className={`sync-button ${synchronized && baseline && followup ? 'active' : ''}`}
              onClick={() => setSynchronized((value) => !value)}
              aria-pressed={Boolean(synchronized && baseline && followup)}
              disabled={!baseline || !followup}
            >
              {!baseline || !followup
                ? 'Link after pairing'
                : synchronized
                  ? linkStrategy === 'patient-position'
                    ? 'Patient-position linked'
                    : 'Approximate index link'
                  : 'Independent slices'}
            </button>
            <SeriesSelect
              label="Follow-up series"
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
                    : 'Available only through the authenticated local launcher'
                }
                onClick={toggleAgentStateSharing}
              >
                Agent state: {agentStateSharing ? 'on' : 'off'}
              </button>
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
            </div>
            <p>
              Primary drag:{' '}
              {['length', 'bidirectional', 'roi'].includes(activeTool)
                ? 'unreviewed measurement'
                : activeTool}{' '}
              · wheel: slices · {!baseline || !followup
                ? 'choose a follow-up to link'
                : linkStrategy === 'patient-position'
                  ? 'shared-frame physical linking'
                  : 'index linking is approximate'}<br />
              {measurementMessage}<br />
              {visitPacketMessage}<br />
              {comparisonReviewMessage}<br />
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
              label="Baseline"
              series={baseline}
              index={baselineIndex}
              onIndexChange={(index) => updateIndex('baseline', index)}
              activeTool={activeTool}
              resetNonce={resetNonce}
              measurementPacket={measurementPacket}
              onOpenMpr={() => baseline && setMprSeriesId(baseline.id)}
            />
            <DicomViewport
              ref={followupViewportRef}
              id="followup"
              label="Follow-up"
              series={followup}
              index={followupIndex}
              onIndexChange={(index) => updateIndex('followup', index)}
              activeTool={activeTool}
              resetNonce={resetNonce}
              measurementPacket={measurementPacket}
              onOpenMpr={() => followup && setMprSeriesId(followup.id)}
            />
          </section>

          {mprSeries && <MprPanel series={mprSeries} onClose={() => setMprSeriesId(undefined)} />}

          <section className="review-grid">
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
            <article className="locked-card">
              <div className="lock-icon" aria-hidden="true">×</div>
              <div>
                <span className="eyebrow">Derived comparison locked</span>
                <h2>Registration review required</h2>
                <p>
                  Overlay, swipe, and subtraction remain disabled until a spatial transform is created
                  and explicitly accepted for display. CT and MRI intensities are never subtracted.
                </p>
              </div>
            </article>
          </section>
          <MeasurementWorkspace
            measurements={visibleMeasurements}
            baseline={baseline}
            followup={followup}
            compatibilityLevel={compatibility.level}
            onDeleteMeasurement={removeMeasurementAnnotation}
            onComparisonDraftChange={setMeasurementComparisonDraft}
          />
        </>
      )}

      <footer>
        <span>ScanView 0.1 · local-first prototype</span>
        <span>Every automated result is unreviewed until a qualified clinician accepts it.</span>
      </footer>
    </main>
  );
}
