import { useMemo, useRef, useState } from 'react';
import { DicomViewport } from './components/DicomViewport';
import {
  createMeasurementEvidencePacket,
  resetLocalImagingSession,
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

type ImportState = { processed: number; total: number } | undefined;

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

export default function App() {
  const inputRef = useRef<HTMLInputElement>(null);
  const measurementInputRef = useRef<HTMLInputElement>(null);
  const [series, setSeries] = useState<DicomSeries[]>([]);
  const [baselineId, setBaselineId] = useState<string>();
  const [followupId, setFollowupId] = useState<string>();
  const [baselineIndex, setBaselineIndex] = useState(0);
  const [followupIndex, setFollowupIndex] = useState(0);
  const [synchronized, setSynchronized] = useState(true);
  const [activeTool, setActiveTool] = useState<ViewerTool>('window');
  const [resetNonce, setResetNonce] = useState(0);
  const [importState, setImportState] = useState<ImportState>();
  const [importMessage, setImportMessage] = useState('No scan folder loaded');
  const [measurementMessage, setMeasurementMessage] = useState(
    'Measurement drafts stay local and require clinician review.',
  );
  const [measurementPacket, setMeasurementPacket] = useState<MeasurementEvidencePacket>();

  const baseline = series.find((item) => item.id === baselineId);
  const followup = series.find((item) => item.id === followupId);
  const compatibility = useMemo(
    () => assessCompatibility(baseline, followup),
    [baseline, followup],
  );
  const linkStrategy = useMemo(() => getLinkStrategy(baseline, followup), [baseline, followup]);
  const openFolder = () => {
    if (!inputRef.current) return;
    inputRef.current.value = '';
    inputRef.current.click();
  };

  const chooseFiles = async (fileList: FileList | null) => {
    if (!fileList?.length) return;
    const files = Array.from(fileList).filter((file) => !file.name.startsWith('.'));
    setSeries([]);
    setBaselineId(undefined);
    setFollowupId(undefined);
    setMeasurementPacket(undefined);
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
    setImportMessage(
      imported.length
        ? `${importedStudies} studies · ${imported.length} series · follow-up not auto-selected · no upload`
        : 'No readable DICOM image series found.',
    );
    setBaselineId(imported[0]?.id);
    setFollowupId(undefined);
    setBaselineIndex(0);
    setFollowupIndex(0);
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

  const exportMeasurementDraft = () => {
    const packet = createMeasurementEvidencePacket();
    if (packet.measurements.length === 0) {
      setMeasurementMessage(
        'No length measurements to export. Draw one with the Length tool first.',
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
      const parsed = readMeasurementEvidencePacket(JSON.parse(await file.text()));
      if (!parsed.packet) {
        setMeasurementPacket(undefined);
        setMeasurementMessage(`Measurement draft rejected: ${parsed.errors.join(' ')}`);
        return;
      }
      setMeasurementPacket(parsed.packet);
      setMeasurementMessage(
        `Loaded ${parsed.packet.measurements.length} unreviewed source-linked measurement${parsed.packet.measurements.length === 1 ? '' : 's'}; matching selected series are restored.`,
      );
    } catch {
      setMeasurementPacket(undefined);
      setMeasurementMessage('Measurement draft rejected: file is not valid JSON.');
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
                setBaselineIndex(0);
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
                setFollowupIndex(0);
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
            </div>
            <p>
              Primary drag: {activeTool === 'length' ? 'unreviewed measurement' : activeTool} · wheel:
              slices · {!baseline || !followup
                ? 'choose a follow-up to link'
                : linkStrategy === 'patient-position'
                  ? 'shared-frame physical linking'
                  : 'index linking is approximate'}<br />
              {measurementMessage}
            </p>
          </section>

          <section className="viewport-grid">
            <DicomViewport
              id="baseline"
              label="Baseline"
              series={baseline}
              index={baselineIndex}
              onIndexChange={(index) => updateIndex('baseline', index)}
              activeTool={activeTool}
              resetNonce={resetNonce}
              measurementPacket={measurementPacket}
            />
            <DicomViewport
              id="followup"
              label="Follow-up"
              series={followup}
              index={followupIndex}
              onIndexChange={(index) => updateIndex('followup', index)}
              activeTool={activeTool}
              resetNonce={resetNonce}
              measurementPacket={measurementPacket}
            />
          </section>

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
        </>
      )}

      <footer>
        <span>ScanView 0.1 · local-first prototype</span>
        <span>Every automated result is unreviewed until a qualified clinician accepts it.</span>
      </footer>
    </main>
  );
}
