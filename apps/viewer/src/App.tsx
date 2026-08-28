import { useMemo, useRef, useState } from 'react';
import { DicomViewport } from './components/DicomViewport';
import type { ViewerTool } from './cornerstone';
import {
  assessCompatibility,
  formatDicomDate,
  mapNormalizedIndex,
  parseDicomFiles,
  type DicomSeries,
} from './dicom';

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

  const baseline = series.find((item) => item.id === baselineId);
  const followup = series.find((item) => item.id === followupId);
  const compatibility = useMemo(
    () => assessCompatibility(baseline, followup),
    [baseline, followup],
  );
  const studies = new Set(series.map((item) => item.studyId)).size;

  const chooseFiles = async (fileList: FileList | null) => {
    if (!fileList?.length) return;
    const files = Array.from(fileList).filter((file) => !file.name.startsWith('.'));
    setImportState({ processed: 0, total: files.length });
    setImportMessage('Reading DICOM headers in this browser only…');
    const imported = await parseDicomFiles(files, (processed, total) =>
      setImportState({ processed, total }),
    );
    setSeries(imported);
    setImportState(undefined);
    setImportMessage(
      imported.length
        ? `${studies || new Set(imported.map((item) => item.studyId)).size} studies · ${imported.length} series · no upload`
        : 'No readable DICOM image series found.',
    );
    if (imported[0]) setBaselineId(imported[0].id);
    if (imported[1]) setFollowupId(imported[1].id);
  };

  const updateIndex = (side: 'baseline' | 'followup', next: number) => {
    if (side === 'baseline') {
      setBaselineIndex(next);
      if (synchronized && baseline && followup) {
        setFollowupIndex(mapNormalizedIndex(next, baseline.instances.length, followup.instances.length));
      }
    } else {
      setFollowupIndex(next);
      if (synchronized && baseline && followup) {
        setBaselineIndex(mapNormalizedIndex(next, followup.instances.length, baseline.instances.length));
      }
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
        <button className="import-button" onClick={() => inputRef.current?.click()}>
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
            ScanView reads headers and pixels locally. It does not upload studies, modify source files,
            or claim a clinical interpretation.
          </p>
          <button className="primary-action" onClick={() => inputRef.current?.click()}>
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
              className={`sync-button ${synchronized ? 'active' : ''}`}
              onClick={() => setSynchronized((value) => !value)}
              aria-pressed={synchronized}
            >
              {synchronized ? 'Linked slices' : 'Independent slices'}
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
            </div>
            <p>
              Primary drag: {activeTool === 'length' ? 'unreviewed measurement' : activeTool} · wheel:
              slices · measurements require valid pixel spacing
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
            />
            <DicomViewport
              id="followup"
              label="Follow-up"
              series={followup}
              index={followupIndex}
              onIndexChange={(index) => updateIndex('followup', index)}
              activeTool={activeTool}
              resetNonce={resetNonce}
            />
          </section>

          <section className="review-grid">
            <article className={`compatibility-card ${compatibility.level}`}>
              <div className="card-heading">
                <div>
                  <span className="eyebrow">Pairing suggestion · never auto-approved</span>
                  <h2>{compatibility.level === 'compatible' ? 'Plausibly comparable' : 'Review compatibility'}</h2>
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
