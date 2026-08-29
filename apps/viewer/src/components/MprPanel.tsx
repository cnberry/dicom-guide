import { useEffect, useRef, useState } from 'react';
import {
  createMprViewports,
  type MprOrientation,
  type MprTool,
  type MprViewportController,
} from '../cornerstone';
import {
  assessLesionVolumeEligibility,
  assessMprEligibility,
  formatDicomDate,
  type DicomSeries,
} from '../dicom';
import { formatMprPatientPoint, type MprPatientPoint } from '../mpr';
import type { ManualSegmentationStats } from '../lesionVolume';

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
  const [activeTool, setActiveTool] = useState<MprTool>('crosshairs');
  const [patientPoint, setPatientPoint] = useState<MprPatientPoint>();
  const [status, setStatus] = useState('Building local volume from source slices…');
  const [brushSize, setBrushSize] = useState(12);
  const [segmentationStats, setSegmentationStats] = useState<ManualSegmentationStats>({
    foregroundVoxels: 0,
    voxelVolumeMm3: 0,
    volumeMm3: 0,
    volumeMl: 0,
  });
  const [regionLabel, setRegionLabel] = useState('Manual region draft');
  const [targetDefinition, setTargetDefinition] = useState(
    'Person-painted boundary for review; represented tissue, lesion identity, and inclusion/exclusion criteria are not established.',
  );
  const [exporting, setExporting] = useState(false);
  const [exportStatus, setExportStatus] = useState('');
  const eligibility = assessMprEligibility(series);
  const evidenceEligibility = assessLesionVolumeEligibility(series);

  useEffect(() => {
    if (
      !evidenceEligibility.eligible &&
      (activeTool === 'paint' || activeTool === 'erase')
    ) {
      setActiveTool('crosshairs');
    }
  }, [evidenceEligibility.eligible, activeTool]);

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
    let unsubscribePatientPoint: (() => void) | undefined;
    let unsubscribeSegmentationStats: (() => void) | undefined;
    setPatientPoint(undefined);
    setStatus('Building local volume from source slices…');
    void createMprViewports(
      `scanview-mpr-${series.id}-${crypto.randomUUID()}`,
      elements,
      series,
      'crosshairs',
    )
      .then((controller) => {
        ownedController = controller;
        if (cancelled) {
          controller.destroy();
          return;
        }
        controllerRef.current = controller;
        unsubscribePatientPoint = controller.subscribeToPatientPoint(setPatientPoint);
        unsubscribeSegmentationStats = controller.subscribeToSegmentationStats(
          setSegmentationStats,
        );
        controller.setBrushSize(brushSize);
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
      unsubscribePatientPoint?.();
      unsubscribeSegmentationStats?.();
      ownedController?.destroy();
      if (controllerRef.current === ownedController) controllerRef.current = undefined;
    };
  }, [series.id]);

  useEffect(() => {
    controllerRef.current?.setPrimaryTool(activeTool);
  }, [activeTool]);

  useEffect(() => {
    controllerRef.current?.setBrushSize(brushSize);
  }, [brushSize]);

  const downloadSegmentationEvidence = async () => {
    const controller = controllerRef.current;
    if (!controller) return;
    setExporting(true);
    setExportStatus('Re-reading source bytes and building local DICOM SEG evidence…');
    try {
      const archive = await controller.exportSegmentationEvidence(
        regionLabel,
        targetDefinition,
      );
      const ownedBytes = new Uint8Array(archive.bytes.byteLength);
      ownedBytes.set(archive.bytes);
      const url = URL.createObjectURL(new Blob([ownedBytes.buffer], { type: 'application/zip' }));
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = archive.filename;
      anchor.click();
      URL.revokeObjectURL(url);
      setExportStatus(
        `Exported source-bound local evidence · ${archive.evidence.measurement.foreground_voxel_count.toLocaleString()} voxels · ${archive.evidence.measurement.volume_ml.toFixed(3)} mL computed, unreviewed`,
      );
    } catch (error) {
      setExportStatus(error instanceof Error ? error.message : 'Unable to export local evidence.');
    } finally {
      setExporting(false);
    }
  };

  const closeWithDraftCheck = () => {
    if (
      (controllerRef.current?.hasSegmentationDraft() || segmentationStats.foregroundVoxels > 0) &&
      !window.confirm('Discard the in-memory unreviewed manual region and close this workspace?')
    ) {
      return;
    }
    onClose();
  };

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
              ['paint', 'Paint ROI'],
              ['erase', 'Erase ROI'],
              ['crosshairs', 'Linked crosshairs'],
              ['window', 'Window / level'],
              ['pan', 'Pan'],
              ['zoom', 'Zoom'],
            ] as const
          ).map(([tool, label]) => (
            <button
              key={tool}
              className={activeTool === tool ? 'active' : ''}
              aria-pressed={activeTool === tool}
              disabled={
                Boolean(status) ||
                ((tool === 'paint' || tool === 'erase') && !evidenceEligibility.eligible)
              }
              onClick={() => setActiveTool(tool)}
            >
              {label}
            </button>
          ))}
          <button disabled={Boolean(status)} onClick={() => controllerRef.current?.reset()}>
            Reset MPR
          </button>
          <button onClick={closeWithDraftCheck}>Close MPR</button>
        </div>
      </div>
      <div className="mpr-warning">
        DERIVED INTERPOLATED DISPLAY · MANUAL ROI STORED ON THE NATIVE GRID · UNREVIEWED ·
        NOT REGISTERED · NOT FOR DIAGNOSIS
      </div>
      <div className="mpr-segmentation-controls" aria-label="Manual lesion ROI evidence controls">
        <div>
          <strong>One local person-painted region draft</strong>
          <span>
            Paint or erase in any plane. The overlay is one binary native-grid labelmap shared by
            all three views.
          </span>
        </div>
        {!evidenceEligibility.eligible && (
          <output className="mpr-export-status">
            Manual ROI evidence is disabled: {evidenceEligibility.reason}
          </output>
        )}
        <label>
          Brush size
          <output>{brushSize} mm radius</output>
          <input
            type="range"
            min="1"
            max="50"
            value={brushSize}
            disabled={!evidenceEligibility.eligible}
            onChange={(event) => setBrushSize(Number(event.target.value))}
          />
        </label>
        <label>
          Working region label
          <input
            value={regionLabel}
            maxLength={64}
            disabled={!evidenceEligibility.eligible}
            onChange={(event) => setRegionLabel(event.target.value)}
          />
        </label>
        <label className="mpr-target-definition">
          Target definition
          <textarea
            value={targetDefinition}
            maxLength={300}
            rows={2}
            disabled={!evidenceEligibility.eligible}
            onChange={(event) => setTargetDefinition(event.target.value)}
          />
        </label>
        <div className="mpr-segmentation-result" aria-live="polite">
          <strong>
            {segmentationStats.foregroundVoxels.toLocaleString()} voxels ·{' '}
            {segmentationStats.volumeMl.toFixed(3)} mL
          </strong>
          <span>Computed, unreviewed · boundary uncertainty not quantified</span>
        </div>
        <div className="mpr-segmentation-actions">
          <button
            disabled={
              Boolean(status) ||
              !evidenceEligibility.eligible ||
              segmentationStats.foregroundVoxels === 0
            }
            onClick={() => {
              if (window.confirm('Clear every painted voxel in this in-memory manual region?')) {
                controllerRef.current?.clearSegmentation();
              }
            }}
          >
            Clear region
          </button>
          <button
            disabled={
              Boolean(status) ||
              !evidenceEligibility.eligible ||
              exporting ||
              segmentationStats.foregroundVoxels === 0 ||
              !regionLabel.trim() ||
              !targetDefinition.trim()
            }
            onClick={() => void downloadSegmentationEvidence()}
          >
            {exporting ? 'Building local evidence…' : 'Export DICOM SEG evidence'}
          </button>
        </div>
        {exportStatus && <output className="mpr-export-status">{exportStatus}</output>}
      </div>
      <div className="mpr-link-note">
        <strong>One patient-space point, three planes.</strong> With Linked crosshairs selected,
        click or drag in any pane to move the same DICOM patient-coordinate location in all three.
        The tool does not align different scans.
        {patientPoint && (
          <output aria-label="Current DICOM patient coordinate">
            {' '}Current LPS point: {formatMprPatientPoint(patientPoint)}
            {' '}· +X left, +Y posterior, +Z head
          </output>
        )}
      </div>
      <div className="mpr-grid">
        {orientationLabels.map(({ id, label }) => (
          <article className="mpr-viewport-card" key={id}>
            <header>
              <strong>{label}</strong>
              <span>
                Patient-axis reslice ·{' '}
                {activeTool === 'crosshairs'
                  ? 'click to link'
                  : activeTool === 'paint' || activeTool === 'erase'
                    ? 'manual native-grid edit'
                    : 'wheel to navigate'}
              </span>
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
        These planes are reconstructed locally from one source series. A painted region is only a
        reviewer-defined lesion ROI draft; it does not establish tumor identity, included tissue,
        longitudinal alignment, or treatment response. Export rehashes exact source instances and
        includes an uncompressed DICOM SEG plus a strict local evidence sidecar for independent
        validation.
      </p>
    </section>
  );
}
