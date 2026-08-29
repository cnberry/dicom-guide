import { useEffect, useRef, useState, type RefObject } from 'react';
import {
  createMprViewports,
  type MprOrientation,
  type MprTool,
  type MprViewportController,
  type NormalizedMprPoint,
} from '../cornerstone';
import { formatDicomDate, type DicomSeries } from '../dicom';
import { loadLocalServiceCatalog } from '../localService';
import {
  fetchNativeBoundaryMask,
  nativeBoundaryMaskCentroid,
  type NativeBoundaryDisplayContext,
  type NativeBoundaryRole,
  type NativeBoundaryTimepoint,
} from '../nativeBoundaryDisplayService';

type Props = {
  context: NativeBoundaryDisplayContext;
  onExit: () => void;
};

type LoadedTimepoint = {
  timepoint: NativeBoundaryTimepoint;
  series: DicomSeries;
  mask: Uint8Array;
  centroid: NormalizedMprPoint;
};

type LoadedComparison = {
  baseline: LoadedTimepoint;
  followup: LoadedTimepoint;
};

const orientations: Array<{ id: MprOrientation; label: string }> = [
  { id: 'axial', label: 'Axial' },
  { id: 'coronal', label: 'Coronal' },
  { id: 'sagittal', label: 'Sagittal' },
];

const orderedSeries = (
  series: DicomSeries[],
  timepoint: NativeBoundaryTimepoint,
): DicomSeries => {
  const candidate = series.find(
    (item) => item.id === timepoint.series_id && item.studyId === timepoint.study_id,
  );
  if (
    !candidate ||
    candidate.sourceKind !== 'loopback-service' ||
    candidate.patientContextId !== timepoint.patient_context_id ||
    candidate.frameOfReferenceId !== timepoint.frame_of_reference_id ||
    candidate.modality !== timepoint.modality ||
    candidate.acquisitionDate !== timepoint.acquisition_date ||
    candidate.geometry.columns !== timepoint.dimensions[0] ||
    candidate.geometry.rows !== timepoint.dimensions[1] ||
    candidate.instances.length !== timepoint.dimensions[2]
  ) {
    throw new Error(
      `${timepoint.role} reviewed boundary does not match one exact live local series.`,
    );
  }
  const byId = new Map(candidate.instances.map((instance) => [instance.instanceId, instance]));
  const instances = timepoint.ordered_instance_ids.map((instanceId) => byId.get(instanceId));
  if (
    instances.some((instance) => !instance) ||
    new Set(timepoint.ordered_instance_ids).size !== candidate.instances.length
  ) {
    throw new Error(`${timepoint.role} reviewed source order changed.`);
  }
  return { ...candidate, instances: instances as DicomSeries['instances'] };
};

const normalizedLabel = (point?: NormalizedMprPoint): string =>
  point
    ? point.map((value) => `${(value * 100).toFixed(1)}%`).join(' · ')
    : 'Waiting for native volume';

function NativeBoundaryMpr({
  loaded,
  activeTool,
  onController,
  onPoint,
}: {
  loaded: LoadedTimepoint;
  activeTool: MprTool;
  onController: (role: NativeBoundaryRole, controller?: MprViewportController) => void;
  onPoint: (role: NativeBoundaryRole, point: NormalizedMprPoint) => void;
}) {
  const axialRef = useRef<HTMLDivElement>(null);
  const coronalRef = useRef<HTMLDivElement>(null);
  const sagittalRef = useRef<HTMLDivElement>(null);
  const controllerRef = useRef<MprViewportController | undefined>(undefined);
  const [status, setStatus] = useState('Building exact native volume and reviewed overlay…');

  useEffect(() => {
    const axial = axialRef.current;
    const coronal = coronalRef.current;
    const sagittal = sagittalRef.current;
    if (!axial || !coronal || !sagittal) return;
    const elements: Record<MprOrientation, HTMLDivElement> = { axial, coronal, sagittal };
    let cancelled = false;
    let owned: MprViewportController | undefined;
    let unsubscribe: (() => void) | undefined;
    let firstCenterFrame: number | undefined;
    let secondCenterFrame: number | undefined;
    setStatus('Building exact native volume and reviewed overlay…');
    void createMprViewports(
      `scanview-reviewed-native-${loaded.timepoint.role}-${crypto.randomUUID()}`,
      elements,
      loaded.series,
      activeTool,
      {
        mask: loaded.mask,
        foregroundVoxels: loaded.timepoint.foreground_voxel_count,
        label: `${loaded.timepoint.role} accepted reviewed boundary`,
      },
    )
      .then((controller) => {
        owned = controller;
        if (cancelled) {
          controller.destroy();
          return;
        }
        controllerRef.current = controller;
        controller.setNormalizedPoint(loaded.centroid);
        onController(loaded.timepoint.role, controller);
        unsubscribe = controller.subscribeToNormalizedPoint((point) =>
          onPoint(loaded.timepoint.role, point),
        );
        firstCenterFrame = window.requestAnimationFrame(() => {
          secondCenterFrame = window.requestAnimationFrame(() => {
            if (cancelled) return;
            controller.setNormalizedPoint(loaded.centroid);
            onPoint(loaded.timepoint.role, loaded.centroid);
          });
        });
        setStatus('');
      })
      .catch((error: unknown) => {
        setStatus(
          error instanceof Error
            ? error.message
            : 'Unable to build this reviewed native volume.',
        );
      });
    const observer = new ResizeObserver(() => controllerRef.current?.resize());
    Object.values(elements).forEach((element) => observer.observe(element));
    return () => {
      cancelled = true;
      if (firstCenterFrame !== undefined) window.cancelAnimationFrame(firstCenterFrame);
      if (secondCenterFrame !== undefined) window.cancelAnimationFrame(secondCenterFrame);
      observer.disconnect();
      unsubscribe?.();
      onController(loaded.timepoint.role, undefined);
      owned?.destroy();
      if (controllerRef.current === owned) controllerRef.current = undefined;
    };
  }, [loaded.series.id, loaded.mask, loaded.centroid]);

  useEffect(() => controllerRef.current?.setPrimaryTool(activeTool), [activeTool]);

  const refs: Record<MprOrientation, RefObject<HTMLDivElement | null>> = {
    axial: axialRef,
    coronal: coronalRef,
    sagittal: sagittalRef,
  };
  return (
    <section className={`native-boundary-timepoint ${loaded.timepoint.role}`}>
      <header>
        <div>
          <p className="eyebrow">{loaded.timepoint.role} · exact native DICOM</p>
          <h2>{loaded.timepoint.series_description}</h2>
          <p>
            {formatDicomDate(loaded.timepoint.acquisition_date)} · {loaded.timepoint.modality} ·{' '}
            {loaded.timepoint.dimensions.join(' × ')} voxels
          </p>
        </div>
        <div className="native-boundary-volume">
          <strong>{loaded.timepoint.reviewed_volume_ml.toFixed(3)} mL</strong>
          <span>reviewed manual ROI · uncertainty not quantified</span>
        </div>
      </header>
      <div className="native-boundary-mpr-grid">
        {orientations.map(({ id, label }) => (
          <article className="mpr-viewport-card" key={id}>
            <header>
              <strong>{label}</strong>
              <span>native + read-only accepted boundary</span>
            </header>
            <div className="mpr-host" ref={refs[id]} />
            {status && <div className="mpr-status">{status}</div>}
          </article>
        ))}
      </div>
      <dl className="native-boundary-definition">
        <div>
          <dt>Represented tissue</dt>
          <dd>{loaded.timepoint.boundary_review.represented_tissue}</dd>
        </div>
        <div>
          <dt>Included</dt>
          <dd>{loaded.timepoint.boundary_review.inclusion_criteria}</dd>
        </div>
        <div>
          <dt>Excluded</dt>
          <dd>{loaded.timepoint.boundary_review.exclusion_criteria}</dd>
        </div>
      </dl>
    </section>
  );
}

export function NativeBoundaryComparisonWorkspace({ context, onExit }: Props) {
  const [loaded, setLoaded] = useState<LoadedComparison>();
  const [loadError, setLoadError] = useState('');
  const [activeTool, setActiveTool] = useState<MprTool>('crosshairs');
  const [linked, setLinked] = useState<boolean>(context.navigation_policy.default_linked);
  const [points, setPoints] = useState<Partial<Record<NativeBoundaryRole, NormalizedMprPoint>>>({});
  const [controllerEpoch, setControllerEpoch] = useState(0);
  const controllers = useRef<Partial<Record<NativeBoundaryRole, MprViewportController>>>({});
  const linkedRef = useRef(linked);
  linkedRef.current = linked;

  useEffect(() => {
    const controller = new AbortController();
    void (async () => {
      try {
        const [catalog, baselineMask, followupMask] = await Promise.all([
          loadLocalServiceCatalog(controller.signal),
          fetchNativeBoundaryMask(context.timepoints.baseline, controller.signal),
          fetchNativeBoundaryMask(context.timepoints.followup, controller.signal),
        ]);
        if (controller.signal.aborted) return;
        if (!catalog) throw new Error('The exact live local DICOM catalog is unavailable.');
        setLoaded({
          baseline: {
            timepoint: context.timepoints.baseline,
            series: orderedSeries(catalog.series, context.timepoints.baseline),
            mask: baselineMask,
            centroid: nativeBoundaryMaskCentroid(
              baselineMask,
              context.timepoints.baseline.dimensions,
            ),
          },
          followup: {
            timepoint: context.timepoints.followup,
            series: orderedSeries(catalog.series, context.timepoints.followup),
            mask: followupMask,
            centroid: nativeBoundaryMaskCentroid(
              followupMask,
              context.timepoints.followup.dimensions,
            ),
          },
        });
      } catch (error) {
        if (controller.signal.aborted) return;
        setLoadError(
          error instanceof Error ? error.message : 'Reviewed native-boundary display failed closed.',
        );
      }
    })();
    return () => controller.abort();
  }, [context.comparison_id]);

  const registerController = (
    role: NativeBoundaryRole,
    controller?: MprViewportController,
  ) => {
    if (controller) {
      controllers.current[role] = controller;
      setControllerEpoch((current) => current + 1);
    } else {
      delete controllers.current[role];
    }
  };

  useEffect(() => {
    if (!loaded || !controllers.current.baseline || !controllers.current.followup) return;
    let secondFrame: number | undefined;
    const firstFrame = window.requestAnimationFrame(() => {
      secondFrame = window.requestAnimationFrame(() => {
        const baseline = controllers.current.baseline;
        const followup = controllers.current.followup;
        if (!baseline || !followup) return;
        baseline.setNormalizedPoint(loaded.baseline.centroid);
        followup.setNormalizedPoint(loaded.followup.centroid);
        setPoints({
          baseline: loaded.baseline.centroid,
          followup: loaded.followup.centroid,
        });
      });
    });
    return () => {
      window.cancelAnimationFrame(firstFrame);
      if (secondFrame !== undefined) window.cancelAnimationFrame(secondFrame);
    };
  }, [controllerEpoch, loaded]);

  const receivePoint = (role: NativeBoundaryRole, point: NormalizedMprPoint) => {
    setPoints((current) => ({ ...current, [role]: point }));
    if (!linkedRef.current) return;
    const peer = role === 'baseline' ? 'followup' : 'baseline';
    try {
      controllers.current[peer]?.setNormalizedPoint(point);
      setPoints((current) => ({ ...current, [peer]: point }));
    } catch {
      setLinked(false);
    }
  };

  const changeLink = (next: boolean) => {
    setLinked(next);
    if (!next) return;
    const sourcePoint = points.baseline ?? points.followup;
    if (!sourcePoint) return;
    try {
      controllers.current.baseline?.setNormalizedPoint(sourcePoint);
      controllers.current.followup?.setNormalizedPoint(sourcePoint);
      setPoints({ baseline: sourcePoint, followup: sourcePoint });
    } catch {
      setLinked(false);
    }
  };

  const comparison = context.comparison;
  return (
    <main className="native-boundary-workspace">
      <header className="native-boundary-header">
        <div>
          <p className="eyebrow">Reviewed manual ROI comparison · local only</p>
          <h1>Two accepted boundaries, two native spaces</h1>
          <p>
            {context.timepoints.baseline.modality} ·{' '}
            {formatDicomDate(context.timepoints.baseline.acquisition_date)} to{' '}
            {formatDicomDate(context.timepoints.followup.acquisition_date)} ·{' '}
            {comparison.elapsed_days} days
          </p>
        </div>
        <div className="native-boundary-header-actions">
          <strong>{context.display_label}</strong>
          <button type="button" onClick={onExit}>Open ordinary DICOM workspace</button>
        </div>
      </header>
      <div className="native-boundary-safety" role="note">
        <strong>Not registered. No spatial correspondence.</strong> Boundaries cannot be overlaid or
        subtracted. Normalized linking mirrors only fractional grid location and cannot localize
        change. This is not a response classification, diagnosis, or treatment conclusion.
      </div>
      <section className="native-boundary-summary" aria-label="Reviewed volume arithmetic">
        <div><span>Baseline reviewed ROI</span><strong>{comparison.baseline_volume_ml.toFixed(3)} mL</strong></div>
        <div><span>Follow-up reviewed ROI</span><strong>{comparison.followup_volume_ml.toFixed(3)} mL</strong></div>
        <div><span>Arithmetic difference</span><strong>{comparison.absolute_change_ml >= 0 ? '+' : ''}{comparison.absolute_change_ml.toFixed(3)} mL</strong></div>
        <div><span>Percent arithmetic</span><strong>{comparison.percent_change >= 0 ? '+' : ''}{comparison.percent_change.toFixed(1)}%</strong></div>
        <p>Discussion-only manual ROI arithmetic · boundary uncertainty not quantified · response assessment not performed.</p>
      </section>
      <section className="native-boundary-controls">
        <div>
          <span>Interaction</span>
          {(['crosshairs', 'window', 'pan', 'zoom'] as const).map((tool) => (
            <button
              type="button"
              key={tool}
              className={activeTool === tool ? 'active' : ''}
              onClick={() => setActiveTool(tool)}
            >
              {tool === 'crosshairs' ? 'Navigate' : tool}
            </button>
          ))}
        </div>
        <label>
          <input
            type="checkbox"
            checked={linked}
            onChange={(event) => changeLink(event.target.checked)}
          />
          <span>
            Mirror normalized grid location
            <small>Approximate navigation only — not alignment or correspondence</small>
          </span>
        </label>
        <div className="native-boundary-location">
          <span>Baseline fraction: {normalizedLabel(points.baseline)}</span>
          <span>Follow-up fraction: {normalizedLabel(points.followup)}</span>
        </div>
        <button
          type="button"
          onClick={() => {
            controllers.current.baseline?.reset();
            controllers.current.followup?.reset();
            if (loaded) {
              controllers.current.baseline?.setNormalizedPoint(loaded.baseline.centroid);
              controllers.current.followup?.setNormalizedPoint(loaded.followup.centroid);
              setPoints({
                baseline: loaded.baseline.centroid,
                followup: loaded.followup.centroid,
              });
            }
          }}
        >
          Center each reviewed boundary
        </button>
      </section>
      {loadError ? (
        <section className="native-boundary-load-error" role="alert">
          <strong>Reviewed boundary display failed closed.</strong>
          <p>{loadError}</p>
          <p>No boundary pixels were displayed.</p>
        </section>
      ) : !loaded ? (
        <section className="qa-loading">Validating local masks and exact native DICOM sources…</section>
      ) : (
        <div className="native-boundary-timepoints">
          <NativeBoundaryMpr
            loaded={loaded.baseline}
            activeTool={activeTool}
            onController={registerController}
            onPoint={receivePoint}
          />
          <NativeBoundaryMpr
            loaded={loaded.followup}
            activeTool={activeTool}
            onController={registerController}
            onPoint={receivePoint}
          />
        </div>
      )}
      <section className="native-boundary-limitations">
        <div>
          <p className="eyebrow">Pairing scope</p>
          <h2>Person-attested, discussion only</h2>
          <p>
            Same lesion: {context.review.same_lesion_identity} · same represented tissue:{' '}
            {context.review.same_represented_tissue} · reviewer role:{' '}
            {context.review.reviewer_role.replaceAll('_', ' ')} · identity unverified
          </p>
          {context.review.limitation_note && <p>{context.review.limitation_note}</p>}
        </div>
        <ul>{context.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
      </section>
    </main>
  );
}
