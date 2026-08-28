import { useEffect, useRef, useState } from 'react';
import {
  createMprViewports,
  type MprOrientation,
  type MprTool,
  type MprViewportController,
} from '../cornerstone';
import { assessMprEligibility, formatDicomDate, type DicomSeries } from '../dicom';

type Props = {
  series: DicomSeries;
  onClose: () => void;
};

const orientationLabels: Array<{ id: MprOrientation; label: string }> = [
  { id: 'axial', label: 'Axial' },
  { id: 'coronal', label: 'Coronal' },
  { id: 'sagittal', label: 'Sagittal' },
];

export function MprPanel({ series, onClose }: Props) {
  const axialRef = useRef<HTMLDivElement>(null);
  const coronalRef = useRef<HTMLDivElement>(null);
  const sagittalRef = useRef<HTMLDivElement>(null);
  const controllerRef = useRef<MprViewportController | undefined>(undefined);
  const [activeTool, setActiveTool] = useState<MprTool>('window');
  const [status, setStatus] = useState('Building local volume from source slices…');
  const eligibility = assessMprEligibility(series);

  useEffect(() => {
    const axial = axialRef.current;
    const coronal = coronalRef.current;
    const sagittal = sagittalRef.current;
    if (!axial || !coronal || !sagittal || !eligibility.eligible) {
      setStatus(eligibility.reason);
      return;
    }
    const elements: Record<MprOrientation, HTMLDivElement> = { axial, coronal, sagittal };
    let cancelled = false;
    let ownedController: MprViewportController | undefined;
    setStatus('Building local volume from source slices…');
    void createMprViewports(
      `scanview-mpr-${series.id}-${crypto.randomUUID()}`,
      elements,
      series,
      'window',
    )
      .then((controller) => {
        ownedController = controller;
        if (cancelled) {
          controller.destroy();
          return;
        }
        controllerRef.current = controller;
        setStatus('');
      })
      .catch((error: unknown) => {
        setStatus(error instanceof Error ? error.message : 'Unable to build this local volume.');
      });
    const observer = new ResizeObserver(() => controllerRef.current?.resize());
    Object.values(elements).forEach((element) => observer.observe(element));
    return () => {
      cancelled = true;
      observer.disconnect();
      ownedController?.destroy();
      if (controllerRef.current === ownedController) controllerRef.current = undefined;
    };
  }, [series.id]);

  useEffect(() => {
    controllerRef.current?.setPrimaryTool(activeTool);
  }, [activeTool]);

  return (
    <section className="mpr-panel" aria-label={`MPR view for ${series.description}`}>
      <div className="mpr-heading">
        <div>
          <span className="eyebrow">Single-series local MPR · derived navigation view</span>
          <h2>{series.description}</h2>
          <p>
            {formatDicomDate(series.acquisitionDate)} · {series.modality} ·{' '}
            {series.instances.length} source slices ·{' '}
            {eligibility.sliceSpacingMm?.toFixed(2) ?? '—'} mm median spacing
          </p>
        </div>
        <div className="mpr-actions">
          {(
            [
              ['window', 'Window / level'],
              ['pan', 'Pan'],
              ['zoom', 'Zoom'],
            ] as const
          ).map(([tool, label]) => (
            <button
              key={tool}
              className={activeTool === tool ? 'active' : ''}
              aria-pressed={activeTool === tool}
              disabled={Boolean(status)}
              onClick={() => setActiveTool(tool)}
            >
              {label}
            </button>
          ))}
          <button disabled={Boolean(status)} onClick={() => controllerRef.current?.reset()}>
            Reset MPR
          </button>
          <button onClick={onClose}>Close MPR</button>
        </div>
      </div>
      <div className="mpr-warning">
        DERIVED INTERPOLATED RESLICES · NOT REGISTERED · NOT FOR DIAGNOSIS · ORIGINAL DICOM
        REMAINS AUTHORITATIVE
      </div>
      <div className="mpr-grid">
        {orientationLabels.map(({ id, label }) => (
          <article className="mpr-viewport-card" key={id}>
            <header>
              <strong>{label}</strong>
              <span>Patient-axis reslice · wheel to navigate</span>
            </header>
            <div
              ref={id === 'axial' ? axialRef : id === 'coronal' ? coronalRef : sagittalRef}
              className="mpr-host"
            />
            {status && <div className="mpr-status">{status}</div>}
          </article>
        ))}
      </div>
      <p className="mpr-footnote">
        These planes are reconstructed locally from one source series. They are not a longitudinal
        alignment, tumor segmentation, or treatment-response result. Save evidence from the native
        source panes until a dedicated derived-image provenance contract is implemented.
      </p>
    </section>
  );
}
