import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react';
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
import {
  formatMprPatientPoint,
  type MprCanvasPoint,
  type MprPatientPoint,
} from '../mpr';
import type { ManualSegmentationStats } from '../lesionVolume';
import {
  LESION_VOLUME_REVIEW_ATTESTATION,
  LESION_VOLUME_REVIEW_ROLES,
  buildLesionVolumeReviewArchive,
  type AcquisitionSuitability,
  type LesionVolumeReviewChecklist,
  type LesionVolumeReviewDecision,
  type LesionVolumeReviewerRole,
} from '../lesionVolumeReview';
import type { LoadedSourceSegmentation } from '../sourceSegmentations';
import {
  SOURCE_SEGMENTATION_REVIEW_ATTESTATION,
  requestSourceSegmentationReview,
  type SourceSegmentationReviewChecklist,
} from '../sourceSegmentationReview';

type Props = {
  series: DicomSeries;
  readonlySourceSegmentation?: LoadedSourceSegmentation;
  sourceSegmentationCatalogSha256?: string;
  onReadonlyReady?: () => void;
  onReadonlyError?: (message: string) => void;
  onClose: () => void;
  simple?: boolean;
  onPatientPointChange?: (point?: MprPatientPoint) => void;
  requestedPatientPoint?: MprPatientPoint;
  requestedTool?: Extract<MprTool, 'crosshairs' | 'window' | 'pan' | 'zoom' | 'crop'>;
  resetNonce?: number;
  onRenderStatusChange?: (status: 'loading' | 'ready' | 'error') => void;
  onPersonInteraction?: () => void;
  controlRevision?: number;
};

const orientationLabels: Array<{ id: MprOrientation; label: string }> = [
  { id: 'axial', label: 'Axial' },
  { id: 'coronal', label: 'Coronal' },
  { id: 'sagittal', label: 'Sagittal' },
];

type CropSelection = {
  orientation: MprOrientation;
  pointerId: number | null;
  start: MprCanvasPoint;
  end: MprCanvasPoint;
};

const reviewChecklistLabels: Array<[keyof LesionVolumeReviewChecklist, string]> = [
  ['original_images_reviewed', 'Original source images reviewed'],
  ['full_boundary_reviewed', 'Complete boundary reviewed, not selected slices only'],
  ['all_three_planes_reviewed', 'Boundary traversed in axial, coronal, and sagittal planes'],
  ['source_overlay_reviewed', 'Mask overlay checked against source pixels'],
  ['motion_considered', 'Motion and other image artifacts considered'],
  ['partial_volume_considered', 'Partial-volume effects considered'],
  ['treatment_effect_considered', 'Treatment effect and non-tumor tissue considered'],
  ['acquisition_protocol_considered', 'Sequence and acquisition protocol considered'],
];

const emptyReviewChecklist = (): LesionVolumeReviewChecklist => ({
  original_images_reviewed: false,
  full_boundary_reviewed: false,
  all_three_planes_reviewed: false,
  source_overlay_reviewed: false,
  motion_considered: false,
  partial_volume_considered: false,
  treatment_effect_considered: false,
  acquisition_protocol_considered: false,
});

const sourceReviewChecklistLabels: Array<[keyof SourceSegmentationReviewChecklist, string]> = [
  ['original_images_reviewed', 'Original local source images reviewed'],
  ['full_source_boundary_reviewed', 'Complete source-carried boundary reviewed, not selected slices only'],
  ['all_three_planes_reviewed', 'Boundary traversed in axial, coronal, and sagittal planes'],
  ['mask_to_source_alignment_reviewed', 'Decoded mask alignment checked against source pixels'],
  ['source_segment_metadata_treated_as_unverified', 'Source label and coded metadata treated as unverified'],
  ['creator_and_algorithm_treated_as_unverified', 'Source creator and algorithm treated as unauthenticated and unverified'],
  ['motion_considered', 'Motion and other image artifacts considered'],
  ['partial_volume_considered', 'Partial-volume effects considered'],
  ['treatment_effect_considered', 'Treatment effect and non-tumor tissue considered'],
  ['acquisition_protocol_considered', 'Sequence and acquisition protocol considered'],
];

const emptySourceReviewChecklist = (): SourceSegmentationReviewChecklist => ({
  original_images_reviewed: false,
  full_source_boundary_reviewed: false,
  all_three_planes_reviewed: false,
  mask_to_source_alignment_reviewed: false,
  source_segment_metadata_treated_as_unverified: false,
  creator_and_algorithm_treated_as_unverified: false,
  motion_considered: false,
  partial_volume_considered: false,
  treatment_effect_considered: false,
  acquisition_protocol_considered: false,
});

export function MprPanel({
  series,
  readonlySourceSegmentation,
  sourceSegmentationCatalogSha256,
  onReadonlyReady,
  onReadonlyError,
  onClose,
  simple = false,
  onPatientPointChange,
  requestedPatientPoint,
  requestedTool,
  resetNonce = 0,
  onRenderStatusChange,
  onPersonInteraction,
  controlRevision,
}: Props) {
  const axialRef = useRef<HTMLDivElement>(null);
  const coronalRef = useRef<HTMLDivElement>(null);
  const sagittalRef = useRef<HTMLDivElement>(null);
  const controllerRef = useRef<MprViewportController | undefined>(undefined);
  const patientPointChangeRef = useRef(onPatientPointChange);
  patientPointChangeRef.current = onPatientPointChange;
  const requestedPatientPointRef = useRef(requestedPatientPoint);
  requestedPatientPointRef.current = requestedPatientPoint;
  const requestedToolRef = useRef(requestedTool);
  requestedToolRef.current = requestedTool;
  const renderStatusChangeRef = useRef(onRenderStatusChange);
  renderStatusChangeRef.current = onRenderStatusChange;
  const [activeTool, setActiveTool] = useState<MprTool>('crosshairs');
  const activeToolRef = useRef<MprTool>('crosshairs');
  activeToolRef.current = activeTool;
  const [patientPoint, setPatientPoint] = useState<MprPatientPoint>();
  const [cropSelection, setCropSelection] = useState<CropSelection>();
  const cropSelectionRef = useRef<CropSelection | undefined>(undefined);
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
  const [reviewerName, setReviewerName] = useState('');
  const [reviewerRole, setReviewerRole] = useState<LesionVolumeReviewerRole | ''>('');
  const [reviewerOrganization, setReviewerOrganization] = useState('');
  const [reviewDecision, setReviewDecision] =
    useState<LesionVolumeReviewDecision>('revision_requested');
  const [acquisitionSuitability, setAcquisitionSuitability] =
    useState<AcquisitionSuitability>('uncertain');
  const [representedTissue, setRepresentedTissue] = useState('');
  const [inclusionCriteria, setInclusionCriteria] = useState('');
  const [exclusionCriteria, setExclusionCriteria] = useState('');
  const [reviewNote, setReviewNote] = useState('');
  const [reviewChecklist, setReviewChecklist] =
    useState<LesionVolumeReviewChecklist>(emptyReviewChecklist);
  const [reviewAttested, setReviewAttested] = useState(false);
  const [reviewExporting, setReviewExporting] = useState(false);
  const [reviewExportStatus, setReviewExportStatus] = useState('');
  const [sourceReviewChecklist, setSourceReviewChecklist] =
    useState<SourceSegmentationReviewChecklist>(emptySourceReviewChecklist);
  const [sourceReviewExporting, setSourceReviewExporting] = useState(false);
  const [sourceReviewExportStatus, setSourceReviewExportStatus] = useState('');
  const eligibility = assessMprEligibility(series);
  const evidenceEligibility = assessLesionVolumeEligibility(series);
  const displayTool = simple ? (requestedTool ?? 'crosshairs') : activeTool;

  useEffect(() => {
    patientPointChangeRef.current?.(patientPoint);
  }, [patientPoint]);

  useEffect(() => {
    if (requestedTool) controllerRef.current?.setPrimaryTool(requestedTool);
  }, [requestedTool]);

  useEffect(() => {
    const controller = controllerRef.current;
    if (!controller || !requestedPatientPoint) return;
    try {
      controller.setPatientPoint(requestedPatientPoint);
    } catch {
      renderStatusChangeRef.current?.('error');
    }
  }, [requestedPatientPoint]);

  useEffect(() => {
    if (resetNonce > 0) controllerRef.current?.reset();
  }, [resetNonce]);

  useEffect(() => {
    cropSelectionRef.current = undefined;
    setCropSelection(undefined);
  }, [displayTool, resetNonce, series.id]);

  useEffect(() => {
    if (!controlRevision) return;
    const controller = controllerRef.current;
    if (!controller) return;
    try {
      controller.setPrimaryTool(requestedTool ?? activeToolRef.current);
      if (requestedPatientPoint) controller.setPatientPoint(requestedPatientPoint);
      renderStatusChangeRef.current?.('ready');
    } catch {
      renderStatusChangeRef.current?.('error');
    }
  }, [controlRevision, requestedPatientPoint, requestedTool]);

  useEffect(
    () => () => {
      patientPointChangeRef.current?.(undefined);
    },
    [],
  );

  useEffect(() => {
    if (
      (!evidenceEligibility.eligible || readonlySourceSegmentation) &&
      (activeTool === 'paint' || activeTool === 'erase')
    ) {
      setActiveTool('crosshairs');
    }
  }, [evidenceEligibility.eligible, readonlySourceSegmentation, activeTool]);

  useEffect(() => {
    const axial = axialRef.current;
    const coronal = coronalRef.current;
    const sagittal = sagittalRef.current;
    if (!axial || !coronal || !sagittal || !eligibility.eligible) {
      setStatus(eligibility.reason);
      if (readonlySourceSegmentation) onReadonlyError?.(eligibility.reason);
      return;
    }
    const elements: Record<MprOrientation, HTMLDivElement> = { axial, coronal, sagittal };
    let cancelled = false;
    let ownedController: MprViewportController | undefined;
    let unsubscribePatientPoint: (() => void) | undefined;
    let unsubscribeSegmentationStats: (() => void) | undefined;
    setPatientPoint(undefined);
    setStatus('Building local volume from source slices…');
    renderStatusChangeRef.current?.('loading');
    void createMprViewports(
      `scanview-mpr-${series.id}-${crypto.randomUUID()}`,
      elements,
      series,
      'crosshairs',
      readonlySourceSegmentation
        ? {
            mask: readonlySourceSegmentation.mask,
            foregroundVoxels: readonlySourceSegmentation.segment.marked_voxel_count,
            label: `Source DICOM SEG · ${readonlySourceSegmentation.segment.segment_label}`,
            orderedInstanceIds:
              readonlySourceSegmentation.state.referenced_series.ordered_instance_ids,
          }
        : undefined,
    )
      .then((controller) => {
        ownedController = controller;
        if (cancelled) {
          controller.destroy();
          return;
        }
        controllerRef.current = controller;
        controller.setPrimaryTool(requestedToolRef.current ?? activeToolRef.current);
        unsubscribePatientPoint = controller.subscribeToPatientPoint(setPatientPoint);
        unsubscribeSegmentationStats = controller.subscribeToSegmentationStats(
          setSegmentationStats,
        );
        if (!readonlySourceSegmentation) controller.setBrushSize(brushSize);
        if (requestedPatientPointRef.current) {
          controller.setPatientPoint(requestedPatientPointRef.current);
        }
        setStatus('');
        renderStatusChangeRef.current?.('ready');
        if (readonlySourceSegmentation) onReadonlyReady?.();
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        const message = error instanceof Error ? error.message : 'Unable to build this local volume.';
        setStatus(message);
        renderStatusChangeRef.current?.('error');
        if (readonlySourceSegmentation) onReadonlyError?.(message);
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
  }, [
    series.id,
    readonlySourceSegmentation?.state.segmentation_id,
    readonlySourceSegmentation?.segment.segment_number,
    onReadonlyReady,
    onReadonlyError,
  ]);

  useEffect(() => {
    controllerRef.current?.setPrimaryTool(activeTool);
  }, [activeTool]);

  useEffect(() => {
    if (!readonlySourceSegmentation) controllerRef.current?.setBrushSize(brushSize);
  }, [brushSize, readonlySourceSegmentation]);

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

  const pointInHost = (
    element: HTMLDivElement,
    event: ReactPointerEvent<HTMLDivElement>,
  ): MprCanvasPoint => {
    const bounds = element.getBoundingClientRect();
    return [
      Math.max(0, Math.min(bounds.width, event.clientX - bounds.left)),
      Math.max(0, Math.min(bounds.height, event.clientY - bounds.top)),
    ];
  };

  const updateCropSelection = (selection?: CropSelection) => {
    cropSelectionRef.current = selection;
    setCropSelection(selection);
  };

  const startCrop = (
    orientation: MprOrientation,
    event: ReactPointerEvent<HTMLDivElement>,
  ) => {
    onPersonInteraction?.();
    if (displayTool !== 'crop' || event.button !== 0) return;
    event.preventDefault();
    event.stopPropagation();
    const point = pointInHost(event.currentTarget, event);
    event.currentTarget.setPointerCapture(event.pointerId);
    const current = cropSelectionRef.current;
    updateCropSelection(
      current?.orientation === orientation && current.pointerId === null
        ? { ...current, pointerId: event.pointerId, end: point }
        : { orientation, pointerId: event.pointerId, start: point, end: point },
    );
  };

  const moveCrop = (
    orientation: MprOrientation,
    event: ReactPointerEvent<HTMLDivElement>,
  ) => {
    if (
      displayTool !== 'crop' ||
      !cropSelectionRef.current ||
      cropSelectionRef.current.orientation !== orientation ||
      cropSelectionRef.current.pointerId !== event.pointerId
    ) {
      return;
    }
    event.preventDefault();
    updateCropSelection({
      ...cropSelectionRef.current,
      end: pointInHost(event.currentTarget, event),
    });
  };

  const finishCrop = (
    orientation: MprOrientation,
    event: ReactPointerEvent<HTMLDivElement>,
  ) => {
    if (
      displayTool !== 'crop' ||
      !cropSelectionRef.current ||
      cropSelectionRef.current.orientation !== orientation ||
      cropSelectionRef.current.pointerId !== event.pointerId
    ) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    const end = pointInHost(event.currentTarget, event);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    const current = cropSelectionRef.current;
    const selected = controllerRef.current?.fitToCanvasRectangle(
      orientation,
      current.start,
      end,
    );
    updateCropSelection(
      selected
        ? undefined
        : { orientation, pointerId: null, start: current.start, end: current.start },
    );
  };

  const cancelCrop = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (cropSelectionRef.current?.pointerId !== event.pointerId) return;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    updateCropSelection(undefined);
  };

  const downloadBoundaryReview = async () => {
    const controller = controllerRef.current;
    if (!controller || !reviewerRole) return;
    setReviewExporting(true);
    setReviewExportStatus('Re-reading exact source bytes and binding the current boundary review…');
    try {
      const evidenceArchive = await controller.exportSegmentationEvidence(
        regionLabel,
        targetDefinition,
      );
      const archive = await buildLesionVolumeReviewArchive({
        evidenceArchive,
        reviewerName,
        reviewerRole,
        reviewerOrganization,
        decision: reviewDecision,
        acquisitionSuitability,
        representedTissue,
        inclusionCriteria,
        exclusionCriteria,
        note: reviewNote,
        checklist: reviewChecklist,
        attested: reviewAttested,
      });
      const ownedBytes = new Uint8Array(archive.bytes.byteLength);
      ownedBytes.set(archive.bytes);
      const url = URL.createObjectURL(new Blob([ownedBytes.buffer], { type: 'application/zip' }));
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = archive.filename;
      anchor.click();
      URL.revokeObjectURL(url);
      setReviewExportStatus(
        archive.record.review_status === 'accepted_for_discussion'
          ? 'Exported self-attested boundary review for discussion only · future pairing still requires a separate review'
          : `Exported ${archive.record.review_status.replaceAll('_', ' ')} boundary record · no future pairing eligibility`,
      );
    } catch (error) {
      setReviewExportStatus(
        error instanceof Error ? error.message : 'Unable to export the local boundary review.',
      );
    } finally {
      setReviewExporting(false);
    }
  };

  const downloadSourceSegmentationReview = async () => {
    if (!readonlySourceSegmentation || !sourceSegmentationCatalogSha256 || !reviewerRole) return;
    setSourceReviewExporting(true);
    setSourceReviewExportStatus(
      'Revalidating the exact local source SEG, referenced source bytes, and decoded mask…',
    );
    try {
      const archive = await requestSourceSegmentationReview({
        catalogContentSha256: sourceSegmentationCatalogSha256,
        segmentationId: readonlySourceSegmentation.state.segmentation_id,
        segmentNumber: readonlySourceSegmentation.segment.segment_number,
        reviewerName,
        reviewerRole,
        reviewerOrganization,
        decision: reviewDecision,
        acquisitionSuitability,
        representedTissue,
        inclusionCriteria,
        exclusionCriteria,
        note: reviewNote,
        checklist: sourceReviewChecklist,
        attested: reviewAttested,
      });
      const ownedBytes = new Uint8Array(archive.bytes.byteLength);
      ownedBytes.set(archive.bytes);
      const url = URL.createObjectURL(new Blob([ownedBytes.buffer], { type: 'application/zip' }));
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = archive.filename;
      anchor.click();
      URL.revokeObjectURL(url);
      setSourceReviewExportStatus(
        reviewDecision === 'accepted_for_discussion'
          ? 'Exported an exact source-bound self-attested review for discussion only · future pairing still requires a separate review · protect the downloaded file and its permissions'
          : `Exported ${reviewDecision.replaceAll('_', ' ')} source-SEG record · no future pairing eligibility · protect the downloaded file and its permissions`,
      );
    } catch (error) {
      setSourceReviewExportStatus(
        error instanceof Error ? error.message : 'Unable to export the local source-SEG review.',
      );
    } finally {
      setSourceReviewExporting(false);
    }
  };

  const closeWithDraftCheck = () => {
    if (readonlySourceSegmentation) {
      onClose();
      return;
    }
    if (
      (controllerRef.current?.hasSegmentationDraft() || segmentationStats.foregroundVoxels > 0) &&
      !window.confirm('Discard the in-memory unreviewed manual region and close this workspace?')
    ) {
      return;
    }
    onClose();
  };

  if (simple) {
    return (
      <section
        className={`mpr-panel simple-mpr ${displayTool === 'crop' ? 'crop-active' : ''}`}
        aria-label={`3-plane view for ${series.description}`}
      >
        <div className="mpr-grid">
          {orientationLabels.map(({ id, label }) => (
            <article className="mpr-viewport-card" key={id}>
              <header>
                <strong>{label}</strong>
                <span>{activeTool === 'crosshairs' ? 'click to move' : 'wheel for slices'}</span>
              </header>
              <div className="mpr-host-shell">
                <div
                  ref={id === 'axial' ? axialRef : id === 'coronal' ? coronalRef : sagittalRef}
                  className="mpr-host"
                  onPointerDown={(event) => startCrop(id, event)}
                  onPointerMove={(event) => moveCrop(id, event)}
                  onPointerUp={(event) => finishCrop(id, event)}
                  onPointerCancel={cancelCrop}
                />
                {cropSelection?.orientation === id && (
                  <div
                    className="mpr-crop-selection"
                    style={{
                      left: Math.min(cropSelection.start[0], cropSelection.end[0]),
                      top: Math.min(cropSelection.start[1], cropSelection.end[1]),
                      width: Math.abs(cropSelection.end[0] - cropSelection.start[0]),
                      height: Math.abs(cropSelection.end[1] - cropSelection.start[1]),
                    }}
                    aria-hidden="true"
                  />
                )}
              </div>
              {status && <div className="mpr-status">{status}</div>}
            </article>
          ))}
        </div>
        <span className="simple-mpr-note">Local MPR · not aligned</span>
      </section>
    );
  }

  return (
    <section
      className={`mpr-panel ${displayTool === 'crop' ? 'crop-active' : ''}`}
      aria-label={`MPR view for ${series.description}`}
    >
      <div className="mpr-heading">
        <div>
          <span className="eyebrow">
            {readonlySourceSegmentation
              ? 'Source-carried DICOM SEG · read-only native-grid overlay'
              : 'Single-series local MPR · derived navigation view'}
          </span>
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
              ...(!readonlySourceSegmentation
                ? ([['paint', 'Paint ROI'], ['erase', 'Erase ROI']] as const)
                : []),
              ['crosshairs', 'Linked crosshairs'],
              ['window', 'Window / level'],
              ['pan', 'Pan'],
              ['zoom', 'Zoom'],
              ['crop', 'Crop to box'],
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
          <button disabled={exporting || reviewExporting || sourceReviewExporting} onClick={closeWithDraftCheck}>
            Close MPR
          </button>
        </div>
      </div>
      <div className="mpr-warning">
        {readonlySourceSegmentation
          ? 'SOURCE-CARRIED DICOM SEG · READ-ONLY NATIVE-GRID MASK · CREATOR NOT AUTHENTICATED · MEANING NOT ASSESSED · NO CROSS-TIMEPOINT REGISTRATION · NOT FOR DIAGNOSIS'
          : 'DERIVED INTERPOLATED DISPLAY · MANUAL ROI STORED ON THE NATIVE GRID · UNREVIEWED · NOT REGISTERED · NOT FOR DIAGNOSIS'}
      </div>
      {readonlySourceSegmentation ? (
        <div className="mpr-source-segmentation-controls" aria-label="Read-only source DICOM segmentation">
          <div>
            <strong>
              Segment {readonlySourceSegmentation.segment.segment_number} ·{' '}
              {readonlySourceSegmentation.segment.segment_label}
            </strong>
            <span>
              Source coded property: {readonlySourceSegmentation.segment.property_type.meaning}{' '}
              ({readonlySourceSegmentation.segment.property_type.scheme}{' '}
              {readonlySourceSegmentation.segment.property_type.value})
            </span>
          </div>
          <div>
            <strong>
              {readonlySourceSegmentation.segment.marked_voxel_count.toLocaleString()} marked voxels ·{' '}
              {readonlySourceSegmentation.segment.computed_volume_ml.toFixed(3)} mL
            </strong>
            <span>Technical native-grid arithmetic · unreviewed · boundary uncertainty not quantified</span>
          </div>
          <div>
            <strong>
              {readonlySourceSegmentation.segment.algorithm_type.toLowerCase()}
              {readonlySourceSegmentation.segment.algorithm_name
                ? ` · ${readonlySourceSegmentation.segment.algorithm_name}`
                : ''}
            </strong>
            <span>
              Creator identity is not authenticated; algorithm identity and accuracy are not
              verified. Editing, conversion into ScanView manual measurement evidence,
              longitudinal linking, and response assessment are disabled.
            </span>
          </div>
          <details className="mpr-boundary-review">
            <summary>Qualified source-SEG boundary review record</summary>
            <p>
              This form records a qualified person’s review of this exact source-carried mask on
              its original local images. The returned sensitive ZIP embeds the original DICOM SEG
              and decoded mask and may contain direct identifiers. It never leaves this local
              loopback service unless you deliberately move the downloaded file.
            </p>
            <p>
              Identity and credentials are self-asserted. The source label, codes, creator,
              algorithm, accuracy, and clinical meaning remain unauthenticated or unverified.
              Acceptance means suitable for discussion only—not a finding, diagnosis, response
              conclusion, or longitudinal lesion link.
            </p>
            <div className="mpr-review-fields">
              <label>
                Reviewer name
                <input value={reviewerName} maxLength={120} onChange={(event) => setReviewerName(event.target.value)} />
              </label>
              <label>
                Qualified role
                <select value={reviewerRole} onChange={(event) => setReviewerRole(event.target.value as LesionVolumeReviewerRole | '')}>
                  <option value="">Select role</option>
                  {LESION_VOLUME_REVIEW_ROLES.map((role) => <option value={role} key={role}>{role.replaceAll('_', ' ')}</option>)}
                </select>
              </label>
              <label>
                Organization (optional)
                <input value={reviewerOrganization} maxLength={160} onChange={(event) => setReviewerOrganization(event.target.value)} />
              </label>
              <label>
                Boundary decision
                <select value={reviewDecision} onChange={(event) => setReviewDecision(event.target.value as LesionVolumeReviewDecision)}>
                  <option value="revision_requested">Revision requested</option>
                  <option value="rejected">Rejected</option>
                  <option value="accepted_for_discussion">Accepted for discussion</option>
                </select>
              </label>
              <label>
                Acquisition suitability
                <select value={acquisitionSuitability} onChange={(event) => setAcquisitionSuitability(event.target.value as AcquisitionSuitability)}>
                  <option value="uncertain">Uncertain</option>
                  <option value="not_suitable">Not suitable</option>
                  <option value="suitable">Suitable</option>
                </select>
              </label>
              <label className="mpr-review-wide">
                Reviewer-defined represented tissue
                <textarea rows={2} maxLength={500} value={representedTissue} onChange={(event) => setRepresentedTissue(event.target.value)} />
              </label>
              <label className="mpr-review-wide">
                Inclusion criteria
                <textarea rows={2} maxLength={1000} value={inclusionCriteria} onChange={(event) => setInclusionCriteria(event.target.value)} />
              </label>
              <label className="mpr-review-wide">
                Exclusion criteria
                <textarea rows={2} maxLength={1000} value={exclusionCriteria} onChange={(event) => setExclusionCriteria(event.target.value)} />
              </label>
              <label className="mpr-review-wide">
                Review note (optional)
                <textarea rows={2} maxLength={2000} value={reviewNote} onChange={(event) => setReviewNote(event.target.value)} />
              </label>
            </div>
            <fieldset className="mpr-review-checklist">
              <legend>Source-SEG boundary review checklist</legend>
              {sourceReviewChecklistLabels.map(([key, label]) => (
                <label key={key}>
                  <input
                    type="checkbox"
                    checked={sourceReviewChecklist[key]}
                    onChange={(event) => setSourceReviewChecklist((current) => ({ ...current, [key]: event.target.checked }))}
                  />
                  {label}
                </label>
              ))}
            </fieldset>
            <label className="mpr-review-attestation">
              <input type="checkbox" checked={reviewAttested} onChange={(event) => setReviewAttested(event.target.checked)} />
              {SOURCE_SEGMENTATION_REVIEW_ATTESTATION}
            </label>
            {!sourceSegmentationCatalogSha256 && (
              <output className="mpr-export-status">Exact source-segmentation catalog binding is unavailable; reopen this overlay from the current source catalog.</output>
            )}
            <button
              disabled={
                Boolean(status) ||
                sourceReviewExporting ||
                !sourceSegmentationCatalogSha256 ||
                !reviewerName.trim() ||
                !reviewerRole ||
                !representedTissue.trim() ||
                !inclusionCriteria.trim() ||
                !exclusionCriteria.trim() ||
                (reviewDecision === 'accepted_for_discussion' &&
                  (acquisitionSuitability !== 'suitable' ||
                    Object.values(sourceReviewChecklist).some((value) => value !== true))) ||
                !reviewAttested
              }
              onClick={() => void downloadSourceSegmentationReview()}
            >
              {sourceReviewExporting ? 'Validating and building local review…' : 'Export source-SEG review archive'}
            </button>
            {sourceReviewExportStatus && <output className="mpr-export-status">{sourceReviewExportStatus}</output>}
          </details>
        </div>
      ) : (
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
        <details className="mpr-boundary-review">
          <summary>Qualified boundary review record</summary>
          <p>
            This form is for a clinician or medical physicist who has reviewed the complete
            painted boundary on the original local source images. Identity and credentials are
            self-asserted, not authenticated. Acceptance means suitable for discussion only.
          </p>
          <div className="mpr-review-fields">
            <label>
              Reviewer name
              <input
                value={reviewerName}
                maxLength={120}
                onChange={(event) => setReviewerName(event.target.value)}
              />
            </label>
            <label>
              Qualified role
              <select
                value={reviewerRole}
                onChange={(event) =>
                  setReviewerRole(event.target.value as LesionVolumeReviewerRole | '')
                }
              >
                <option value="">Select role</option>
                {LESION_VOLUME_REVIEW_ROLES.map((role) => (
                  <option value={role} key={role}>{role.replaceAll('_', ' ')}</option>
                ))}
              </select>
            </label>
            <label>
              Organization (optional)
              <input
                value={reviewerOrganization}
                maxLength={160}
                onChange={(event) => setReviewerOrganization(event.target.value)}
              />
            </label>
            <label>
              Boundary decision
              <select
                value={reviewDecision}
                onChange={(event) =>
                  setReviewDecision(event.target.value as LesionVolumeReviewDecision)
                }
              >
                <option value="revision_requested">Revision requested</option>
                <option value="rejected">Rejected</option>
                <option value="accepted_for_discussion">Accepted for discussion</option>
              </select>
            </label>
            <label>
              Acquisition suitability
              <select
                value={acquisitionSuitability}
                onChange={(event) =>
                  setAcquisitionSuitability(event.target.value as AcquisitionSuitability)
                }
              >
                <option value="uncertain">Uncertain</option>
                <option value="not_suitable">Not suitable</option>
                <option value="suitable">Suitable</option>
              </select>
            </label>
            <label className="mpr-review-wide">
              Represented tissue
              <textarea
                rows={2}
                maxLength={500}
                value={representedTissue}
                onChange={(event) => setRepresentedTissue(event.target.value)}
              />
            </label>
            <label className="mpr-review-wide">
              Inclusion criteria
              <textarea
                rows={2}
                maxLength={1000}
                value={inclusionCriteria}
                onChange={(event) => setInclusionCriteria(event.target.value)}
              />
            </label>
            <label className="mpr-review-wide">
              Exclusion criteria
              <textarea
                rows={2}
                maxLength={1000}
                value={exclusionCriteria}
                onChange={(event) => setExclusionCriteria(event.target.value)}
              />
            </label>
            <label className="mpr-review-wide">
              Review note (optional)
              <textarea
                rows={2}
                maxLength={2000}
                value={reviewNote}
                onChange={(event) => setReviewNote(event.target.value)}
              />
            </label>
          </div>
          <fieldset className="mpr-review-checklist">
            <legend>Boundary review checklist</legend>
            {reviewChecklistLabels.map(([key, label]) => (
              <label key={key}>
                <input
                  type="checkbox"
                  checked={reviewChecklist[key]}
                  onChange={(event) =>
                    setReviewChecklist((current) => ({
                      ...current,
                      [key]: event.target.checked,
                    }))
                  }
                />
                {label}
              </label>
            ))}
          </fieldset>
          <label className="mpr-review-attestation">
            <input
              type="checkbox"
              checked={reviewAttested}
              onChange={(event) => setReviewAttested(event.target.checked)}
            />
            {LESION_VOLUME_REVIEW_ATTESTATION}
          </label>
          <button
            disabled={
              Boolean(status) ||
              !evidenceEligibility.eligible ||
              reviewExporting ||
              segmentationStats.foregroundVoxels === 0 ||
              !regionLabel.trim() ||
              !targetDefinition.trim() ||
              !reviewerName.trim() ||
              !reviewerRole ||
              !representedTissue.trim() ||
              !inclusionCriteria.trim() ||
              !exclusionCriteria.trim() ||
              (reviewDecision === 'accepted_for_discussion' &&
                (acquisitionSuitability !== 'suitable' ||
                  Object.values(reviewChecklist).some((value) => value !== true))) ||
              !reviewAttested
            }
            onClick={() => void downloadBoundaryReview()}
          >
            {reviewExporting ? 'Building review archive…' : 'Export boundary review archive'}
          </button>
          {reviewExportStatus && (
            <output className="mpr-export-status">{reviewExportStatus}</output>
          )}
        </details>
      </div>
      )}
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
                  : activeTool === 'crop'
                    ? 'drag a box to fit'
                  : activeTool === 'paint' || activeTool === 'erase'
                    ? 'manual native-grid edit'
                    : 'wheel to navigate'}
              </span>
            </header>
            <div className="mpr-host-shell">
              <div
                ref={id === 'axial' ? axialRef : id === 'coronal' ? coronalRef : sagittalRef}
                className="mpr-host"
                onPointerDown={(event) => startCrop(id, event)}
                onPointerMove={(event) => moveCrop(id, event)}
                onPointerUp={(event) => finishCrop(id, event)}
                onPointerCancel={cancelCrop}
              />
              {cropSelection?.orientation === id && (
                <div
                  className="mpr-crop-selection"
                  style={{
                    left: Math.min(cropSelection.start[0], cropSelection.end[0]),
                    top: Math.min(cropSelection.start[1], cropSelection.end[1]),
                    width: Math.abs(cropSelection.end[0] - cropSelection.start[0]),
                    height: Math.abs(cropSelection.end[1] - cropSelection.start[1]),
                  }}
                  aria-hidden="true"
                />
              )}
            </div>
            {status && <div className="mpr-status">{status}</div>}
          </article>
        ))}
      </div>
      <p className="mpr-footnote">
        {readonlySourceSegmentation
          ? 'These planes are reconstructed locally from the exact referenced source series. The overlay is a locally decoded, source-byte-anchored dense reconstruction of one DICOM SEG segment. Its label, coded meaning, algorithm declaration, and boundary are source content—not a ScanView measurement, finding, diagnosis, response label, or clinical conclusion. Confirm the original DICOM objects in the clinical imaging system.'
          : 'These planes are reconstructed locally from one source series. A painted region is only a person-painted manual region draft; it does not establish tumor identity, included tissue, longitudinal alignment, or treatment response. Export rehashes exact source instances and includes an uncompressed DICOM SEG plus a strict local evidence sidecar for independent validation. A separate self-attested boundary review can qualify that one timepoint for discussion, but cannot link it to another scan or calculate treatment response.'}
      </p>
    </section>
  );
}
