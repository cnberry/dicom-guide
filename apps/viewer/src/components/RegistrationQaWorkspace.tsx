import { useEffect, useMemo, useRef, useState } from 'react';
import {
  composeQaSlice,
  extractPatientSpaceSlice,
  landmarkResidual,
  lpsToPatientSlicePixel,
  parseNrrd,
  patientSlicePixelToLps,
  patientSpacePlaneLength,
  planeOrientationLabels,
  type LpsPoint,
  type NrrdPlane,
  type NrrdSlice,
  type NrrdVolume,
  type PatientSpaceSlice,
  type PlaneOrientationLabels,
  type QaCompositeMode,
} from '../nrrd';
import {
  downloadRegistrationReview,
  fetchRegistrationQaVolume,
  MAX_REGISTRATION_QA_ENCODED_TOTAL_BYTES,
  submitRegistrationReview,
  type LandmarkPairDraft,
  type RegistrationQaContext,
  type RegistrationReviewRequest,
  type RegistrationVolumeGeometry,
} from '../registrationQaService';

type LoadedVolumes = {
  fixed: NrrdVolume;
  moving: NrrdVolume;
  registered: NrrdVolume;
};

type LandmarkPair = LandmarkPairDraft & {
  id: string;
  residualMm: number;
};

type Marker = { x: number; y: number; label: string; color: string };
type ReviewPhase = 'pending' | 'submitting' | 'saved' | 'error';

const formatDate = (value: string): string =>
  /^\d{8}$/.test(value)
    ? `${value.slice(0, 4)}-${value.slice(4, 6)}-${value.slice(6, 8)}`
    : value;

const arraysClose = (left: unknown, right: unknown, tolerance = 1e-5): boolean => {
  if (Array.isArray(left) && Array.isArray(right) && left.length === right.length) {
    return left.every((item, index) => arraysClose(item, right[index], tolerance));
  }
  return (
    typeof left === 'number' &&
    typeof right === 'number' &&
    Number.isFinite(left) &&
    Number.isFinite(right) &&
    Math.abs(left - right) <= tolerance
  );
};

const volumeMatchesDescriptor = (
  volume: NrrdVolume,
  descriptor: RegistrationVolumeGeometry,
): boolean =>
  arraysClose(volume.sizes, descriptor.sizes, 0) &&
  volume.space === descriptor.coordinate_system &&
  arraysClose(volume.spaceDirections, descriptor.space_directions) &&
  arraysClose(volume.spaceOrigin, descriptor.space_origin);

const windowFromPercent = (
  volume: NrrdVolume,
  lowPercent: number,
  highPercent: number,
): [number, number] => {
  const [minimum, maximum] = volume.sampledRange;
  const span = maximum > minimum ? maximum - minimum : 1;
  return [
    minimum + (span * lowPercent) / 100,
    minimum + (span * Math.max(lowPercent + 0.1, highPercent)) / 100,
  ];
};

const markerForLps = (
  point: LpsPoint,
  slice: PatientSpaceSlice | undefined,
  label: string,
  color: string,
): Marker | undefined => {
  if (!slice) return undefined;
  const projection = lpsToPatientSlicePixel(slice.mapping, point);
  if (Math.abs(projection.distanceFromPlaneMm) > slice.mapping.sliceSpacingMm / 2) {
    return undefined;
  }
  return {
    x: projection.horizontal,
    y: projection.vertical,
    label,
    color,
  };
};

const QaCanvas = ({
  title,
  slice,
  markers = [],
  onPoint,
  derived = false,
  orientation,
}: {
  title: string;
  slice?: NrrdSlice;
  markers?: Marker[];
  onPoint?: (horizontal: number, vertical: number) => void;
  derived?: boolean;
  orientation?: PlaneOrientationLabels;
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !slice) return;
    canvas.width = slice.width;
    canvas.height = slice.height;
    const context = canvas.getContext('2d');
    if (!context) return;
    const rgba = new Uint8ClampedArray(slice.pixels.length * 4);
    slice.pixels.forEach((value, index) => {
      const target = index * 4;
      rgba[target] = value;
      rgba[target + 1] = value;
      rgba[target + 2] = value;
      rgba[target + 3] = 255;
    });
    context.putImageData(new ImageData(rgba, slice.width, slice.height), 0, 0);
  }, [slice]);

  return (
    <section className="qa-image-card">
      <header>
        <strong>{title}</strong>
        <span>{derived ? 'DERIVED · RESAMPLED' : 'NATIVE-INTENSITY VOLUME'}</span>
      </header>
      <div className="qa-canvas-wrap">
        <div
          className="qa-canvas-stage"
          style={
            slice
              ? {
                  aspectRatio: `${slice.width} / ${slice.height}`,
                  maxWidth: `min(100%, ${(560 * slice.width) / slice.height}px)`,
                }
              : undefined
          }
        >
          <canvas
            ref={canvasRef}
            aria-label={title}
            onClick={(event) => {
              if (!onPoint || !slice) return;
              const bounds = event.currentTarget.getBoundingClientRect();
              onPoint(
                ((event.clientX - bounds.left) / bounds.width) * Math.max(0, slice.width - 1),
                ((event.clientY - bounds.top) / bounds.height) * Math.max(0, slice.height - 1),
              );
            }}
          />
          {markers.map((marker) => (
            <span
              className="qa-marker"
              key={`${marker.label}-${marker.x}-${marker.y}`}
              title={marker.label}
              style={{
                left: `${(marker.x / Math.max(1, (slice?.width ?? 1) - 1)) * 100}%`,
                top: `${(marker.y / Math.max(1, (slice?.height ?? 1) - 1)) * 100}%`,
                borderColor: marker.color,
              }}
            />
          ))}
          {orientation && (
            <>
              <span className="sr-only">
                Orientation: left {orientation.left}, right {orientation.right}, top{' '}
                {orientation.top}, bottom {orientation.bottom}.
              </span>
              <div className="qa-orientation" aria-hidden="true">
                <span className="qa-orientation-left">{orientation.left}</span>
                <span className="qa-orientation-right">{orientation.right}</span>
                <span className="qa-orientation-top">{orientation.top}</span>
                <span className="qa-orientation-bottom">{orientation.bottom}</span>
              </div>
            </>
          )}
        </div>
      </div>
    </section>
  );
};

const CompositeCanvas = ({
  fixed,
  registered,
  mode,
  opacity,
  checkerSize,
  edgeThreshold,
  swipePosition,
  orientation,
}: {
  fixed?: NrrdSlice;
  registered?: NrrdSlice;
  mode: QaCompositeMode;
  opacity: number;
  checkerSize: number;
  edgeThreshold: number;
  swipePosition: number;
  orientation?: PlaneOrientationLabels;
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !fixed || !registered) return;
    const composite = composeQaSlice(fixed, registered, mode, {
      opacity,
      checkerSize,
      edgeThreshold,
      swipePosition,
    });
    canvas.width = composite.width;
    canvas.height = composite.height;
    canvas
      .getContext('2d')
      ?.putImageData(
        new ImageData(
          new Uint8ClampedArray(composite.data),
          composite.width,
          composite.height,
        ),
        0,
        0,
      );
  }, [checkerSize, edgeThreshold, fixed, mode, opacity, registered, swipePosition]);
  return (
    <section className="qa-image-card qa-composite-card">
      <header>
        <strong>{mode.replace('_', ' ').toUpperCase()}</strong>
        <span>QA PREVIEW ONLY · NEVER A NATIVE SOURCE</span>
      </header>
      <div className="qa-canvas-wrap">
        <div
          className="qa-canvas-stage"
          style={
            fixed
              ? {
                  aspectRatio: `${fixed.width} / ${fixed.height}`,
                  maxWidth: `min(100%, ${(560 * fixed.width) / fixed.height}px)`,
                }
              : undefined
          }
        >
          <canvas ref={canvasRef} aria-label={`${mode} registration QA view`} />
          {orientation && (
            <div className="qa-orientation" aria-hidden="true">
              <span className="qa-orientation-left">{orientation.left}</span>
              <span className="qa-orientation-right">{orientation.right}</span>
              <span className="qa-orientation-top">{orientation.top}</span>
              <span className="qa-orientation-bottom">{orientation.bottom}</span>
            </div>
          )}
        </div>
      </div>
    </section>
  );
};

export const RegistrationQaWorkspace = ({
  context,
}: {
  context: RegistrationQaContext;
}) => {
  const [volumes, setVolumes] = useState<LoadedVolumes>();
  const [loadError, setLoadError] = useState<string>();
  const [plane, setPlane] = useState<NrrdPlane>('axial');
  const [inspectedPlanes, setInspectedPlanes] = useState<
    Partial<Record<NrrdPlane, { normalized_min: number; normalized_max: number }>>
  >({});
  const [sliceIndex, setSliceIndex] = useState(0);
  const [mode, setMode] = useState<QaCompositeMode>('opacity');
  const [inspectedModes, setInspectedModes] = useState<Set<QaCompositeMode>>(new Set());
  const [fixedWindow, setFixedWindow] = useState<[number, number]>([1, 99]);
  const [movingWindow, setMovingWindow] = useState<[number, number]>([1, 99]);
  const [opacity, setOpacity] = useState(0.5);
  const [checkerSize, setCheckerSize] = useState(24);
  const [edgeThreshold, setEdgeThreshold] = useState(180);
  const [swipePosition, setSwipePosition] = useState(0.5);
  const [landmarkLabel, setLandmarkLabel] = useState(context.landmark_options[0] ?? 'landmark');
  const [pendingFixed, setPendingFixed] = useState<{
    physical: LpsPoint;
  }>();
  const [landmarkPairs, setLandmarkPairs] = useState<LandmarkPair[]>([]);
  const [landmarkMessage, setLandmarkMessage] = useState(
    'Choose a landmark, click it in fixed, then click the corresponding point in registered moving.',
  );
  const [checks, setChecks] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(context.qualitative_checks.map((item) => [item.id, false])),
  );
  const [observations, setObservations] = useState<
    Record<string, '' | 'aligned' | 'uncertain' | 'misaligned' | 'not_visible'>
  >({});
  const [reviewerName, setReviewerName] = useState('');
  const [reviewerRole, setReviewerRole] =
    useState<RegistrationReviewRequest['reviewer']['role']>('patient_or_family');
  const [organization, setOrganization] = useState('');
  const [trainingStatus, setTrainingStatus] =
    useState<RegistrationReviewRequest['reviewer']['training_status']>(
      'self_attested_not_trained',
    );
  const [region, setRegion] = useState('');
  const [quantitativeStatus, setQuantitativeStatus] =
    useState<'recorded' | 'unavailable'>('unavailable');
  const [unavailableReason, setUnavailableReason] = useState('');
  const [defects, setDefects] = useState('');
  const [note, setNote] = useState('');
  const [attest, setAttest] = useState(false);
  const [decision, setDecision] =
    useState<RegistrationReviewRequest['decision']>('rejected');
  const [phase, setPhase] = useState<ReviewPhase>('pending');
  const [reviewMessage, setReviewMessage] = useState(
    'No decision has been recorded. The registration remains locked outside this QA preview.',
  );

  useEffect(() => {
    const controller = new AbortController();
    void (async () => {
      const encodedTotal = Object.values(context.volumes).reduce(
        (total, descriptor) => total + descriptor.bytes,
        0,
      );
      if (encodedTotal > MAX_REGISTRATION_QA_ENCODED_TOTAL_BYTES) {
        throw new Error('Registration QA volumes exceed the aggregate browser safety limit.');
      }
      const fixedBytes = await fetchRegistrationQaVolume(
        context.volumes.fixed,
        controller.signal,
      );
      const fixed = parseNrrd(fixedBytes);
      const registeredBytes = await fetchRegistrationQaVolume(
        context.volumes.registered_moving,
        controller.signal,
      );
      const registered = parseNrrd(registeredBytes);
      const movingBytes = await fetchRegistrationQaVolume(
        context.volumes.moving,
        controller.signal,
      );
      const moving = parseNrrd(movingBytes);
        const loaded = {
          fixed,
          moving,
          registered,
        };
        if (
          !volumeMatchesDescriptor(loaded.fixed, context.volumes.fixed.geometry) ||
          !volumeMatchesDescriptor(loaded.moving, context.volumes.moving.geometry) ||
          !volumeMatchesDescriptor(
            loaded.registered,
            context.volumes.registered_moving.geometry,
          ) ||
          !arraysClose(loaded.fixed.sizes, loaded.registered.sizes, 0) ||
          loaded.fixed.space !== loaded.registered.space ||
          !arraysClose(loaded.fixed.spaceDirections, loaded.registered.spaceDirections) ||
          !arraysClose(loaded.fixed.spaceOrigin, loaded.registered.spaceOrigin)
        ) {
          throw new Error('Validated QA geometry disagrees with the loaded local volumes.');
        }
        if (controller.signal.aborted) return;
        setVolumes(loaded);
        const axialCount = patientSpacePlaneLength(loaded.fixed, 'axial');
        const initialSlice = Math.floor(axialCount / 2);
        const normalized = axialCount <= 1 ? 0.5 : initialSlice / (axialCount - 1);
        setSliceIndex(initialSlice);
        setInspectedPlanes({
          axial: { normalized_min: normalized, normalized_max: normalized },
        });
        setInspectedModes(new Set(['opacity']));
    })()
      .catch((error) => {
        if (controller.signal.aborted) return;
        setLoadError(
          error instanceof Error ? error.message : 'Local registration QA volumes could not load.',
        );
      });
    return () => controller.abort();
  }, [context]);

  const fixedSlice = useMemo(
    () =>
      volumes
        ? extractPatientSpaceSlice(
            volumes.fixed,
            plane,
            sliceIndex,
            windowFromPercent(volumes.fixed, fixedWindow[0], fixedWindow[1]),
          )
        : undefined,
    [fixedWindow, plane, sliceIndex, volumes],
  );
  const registeredSlice = useMemo(
    () =>
      volumes
        ? extractPatientSpaceSlice(
            volumes.registered,
            plane,
            sliceIndex,
            windowFromPercent(volumes.registered, movingWindow[0], movingWindow[1]),
          )
        : undefined,
    [movingWindow, plane, sliceIndex, volumes],
  );
  const movingNativeSlice = useMemo(() => {
    if (!volumes) return undefined;
    const fixedLength = patientSpacePlaneLength(volumes.fixed, plane);
    const movingLength = patientSpacePlaneLength(volumes.moving, plane);
    const proportional =
      fixedLength <= 1 ? 0 : Math.round((sliceIndex / (fixedLength - 1)) * (movingLength - 1));
    return extractPatientSpaceSlice(
      volumes.moving,
      plane,
      proportional,
      windowFromPercent(volumes.moving, movingWindow[0], movingWindow[1]),
    );
  }, [movingWindow, plane, sliceIndex, volumes]);

  const fixedMarkers = useMemo(
    () =>
      landmarkPairs.flatMap((pair, index) => {
        const marker = markerForLps(
          pair.fixed_physical_mm,
          fixedSlice,
          pair.label,
          '#ff8d84',
        );
        return marker ? [{ ...marker, label: `${index + 1}. ${marker.label}` }] : [];
      }),
    [fixedSlice, landmarkPairs],
  );
  const fixedOrientation = volumes ? planeOrientationLabels(volumes.fixed, plane) : undefined;
  const movingOrientation = volumes ? planeOrientationLabels(volumes.moving, plane) : undefined;
  const registeredMarkers = useMemo(
    () =>
      landmarkPairs.flatMap((pair, index) => {
        const marker = markerForLps(
          pair.registered_moving_physical_mm,
          registeredSlice,
          pair.label,
          '#6ee7c2',
        );
        return marker ? [{ ...marker, label: `${index + 1}. ${marker.label}` }] : [];
      }),
    [landmarkPairs, registeredSlice],
  );

  const recordSliceVisit = (nextPlane: NrrdPlane, index: number, count: number) => {
    const normalized = count <= 1 ? 0.5 : index / (count - 1);
    setInspectedPlanes((current) => {
      const previous = current[nextPlane];
      return {
        ...current,
        [nextPlane]: {
          normalized_min: Math.min(previous?.normalized_min ?? normalized, normalized),
          normalized_max: Math.max(previous?.normalized_max ?? normalized, normalized),
        },
      };
    });
  };

  const choosePlane = (next: NrrdPlane) => {
    setPlane(next);
    if (volumes) {
      const count = patientSpacePlaneLength(volumes.fixed, next);
      const center = Math.floor(count / 2);
      setSliceIndex(center);
      recordSliceVisit(next, center, count);
    }
  };

  const chooseMode = (next: QaCompositeMode) => {
    setMode(next);
    if (volumes) setInspectedModes((current) => new Set([...current, next]));
  };

  const selectFixedLandmark = (horizontal: number, vertical: number) => {
    if (!fixedSlice) return;
    const physical = patientSlicePixelToLps(fixedSlice.mapping, horizontal, vertical);
    setPendingFixed({ physical });
    setLandmarkMessage(
      'Fixed 3-D point selected. Navigate any plane/slice, then click the corresponding registered-moving point.',
    );
  };

  const selectRegisteredLandmark = (horizontal: number, vertical: number) => {
    if (!registeredSlice || !pendingFixed) {
      setLandmarkMessage('Select the fixed landmark first.');
      return;
    }
    const physical = patientSlicePixelToLps(
      registeredSlice.mapping,
      horizontal,
      vertical,
    );
    const label = `${landmarkLabel}-${landmarkPairs.length + 1}`;
    setLandmarkPairs((current) => [
      ...current,
      {
        id: crypto.randomUUID(),
        label,
        fixed_physical_mm: pendingFixed.physical,
        registered_moving_physical_mm: physical,
        residualMm: landmarkResidual(pendingFixed.physical, physical),
      },
    ]);
    setPendingFixed(undefined);
    setLandmarkMessage(`Recorded ${label}. Residual is supplemental and does not prove accuracy.`);
  };

  const observationList = Object.entries(observations).flatMap(([landmark, status]) =>
    status ? [{ landmark, status, note: '' }] : [],
  );
  const allChecks = Object.values(checks).every(Boolean);
  const acceptedObservationsReady =
    observationList.length >= 3 &&
    observationList.every((item) => item.status === 'aligned');
  const toleranceMm = Math.max(...context.volumes.fixed.geometry.voxel_spacing_mm);
  const toleranceBasis =
    'Maximum fixed-volume voxel spacing from validated registration bundle geometry.';
  const quantitativeCanRecord = landmarkPairs.length >= 3;
  const landmarkPairsSpanThreeDimensions = (
    ['fixed_physical_mm', 'registered_moving_physical_mm'] as const
  ).every((field) =>
    ([0, 1, 2] as const).every((axis) => {
      const coordinates = landmarkPairs.map((item) => item[field][axis]);
      return coordinates.length >= 3 && Math.max(...coordinates) - Math.min(...coordinates) > 1e-6;
    }),
  );
  const quantitativeReady =
    quantitativeStatus === 'recorded'
      ? quantitativeCanRecord &&
        Math.max(...landmarkPairs.map((item) => item.residualMm)) <= toleranceMm
      : unavailableReason.trim().length > 0;
  const inspectionReady =
    (['axial', 'coronal', 'sagittal'] as const).every((item) => {
      const coverage = inspectedPlanes[item];
      return Boolean(
        coverage && coverage.normalized_min <= 0.05 && coverage.normalized_max >= 0.95,
      );
    }) && inspectedModes.size === 4;
  const qualifiedReviewer =
    trainingStatus === 'self_attested_trained' &&
    (reviewerRole === 'clinician' || reviewerRole === 'medical_physicist');
  const defectsList = defects
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
  const commonReady =
    reviewerName.trim().length > 0 &&
    region.trim().length > 0 &&
    note.trim().length > 0 &&
    attest;
  const decisionReady =
    phase !== 'submitting' &&
    phase !== 'saved' &&
    Boolean(volumes) &&
    commonReady &&
    (decision === 'rejected' ||
      (qualifiedReviewer &&
        allChecks &&
        acceptedObservationsReady &&
        quantitativeStatus === 'recorded' &&
        quantitativeReady &&
        landmarkPairsSpanThreeDimensions &&
        defectsList.length === 0 &&
        inspectionReady));

  const submitReview = async () => {
    if (!decisionReady) return;
    const request: RegistrationReviewRequest = {
      schema_version: '1.0.0',
      reviewer: {
        name: reviewerName.trim(),
        role: reviewerRole,
        organization: organization.trim() || null,
        training_status: trainingStatus,
      },
      attest: true,
      decision,
      region_of_importance: region.trim(),
      qualitative_checks: checks,
      inspection_evidence: {
        planes: inspectedPlanes,
        modes: [...inspectedModes].sort(),
      },
      landmark_observations: observationList,
      quantitative_assessment:
        quantitativeStatus === 'recorded' && quantitativeCanRecord
          ? {
              status: 'recorded',
              tolerance_mm: toleranceMm,
              tolerance_basis: toleranceBasis,
              pairs: landmarkPairs.map(
                ({ label, fixed_physical_mm, registered_moving_physical_mm }) => ({
                  label,
                  fixed_physical_mm,
                  registered_moving_physical_mm,
                }),
              ),
              unavailable_reason: null,
            }
          : {
              status: 'unavailable',
              tolerance_mm: null,
              tolerance_basis: null,
              pairs: [],
              unavailable_reason:
                unavailableReason.trim() ||
                'Registration was rejected before quantitative landmark assessment.',
            },
      regional_defects: defectsList,
      note: note.trim(),
    };
    setPhase('submitting');
    setReviewMessage('Building the local hash-bound QA record…');
    try {
      const response = await submitRegistrationReview(request);
      downloadRegistrationReview(response.bytes, response.filename);
      setPhase('saved');
      setReviewMessage(
        decision === 'rejected'
          ? 'Rejected QA record downloaded. All registered display uses remain locked.'
          : 'Accepted exploratory overlay/swipe QA record downloaded. Subtraction, segmentation, measurements, propagation, and response conclusions remain locked.',
      );
    } catch (error) {
      setPhase('error');
      setReviewMessage(
        error instanceof Error ? error.message : 'Local registration QA record failed.',
      );
    }
  };

  const sliceCount = volumes ? patientSpacePlaneLength(volumes.fixed, plane) : 1;
  if (loadError) {
    return (
      <main className="qa-workspace qa-error-state">
        <p className="eyebrow">Registration QA unavailable</p>
        <h1>Validated local volumes could not be opened</h1>
        <p>{loadError}</p>
        <p>No registration display has been unlocked.</p>
      </main>
    );
  }

  return (
    <main className="qa-workspace">
      <header className="qa-header">
        <div>
          <p className="eyebrow">Human-only local registration review</p>
          <h1>Rigid registration QA</h1>
          <p>
            {context.source.modality} · {formatDate(context.source.fixed.acquisition_date)} earlier
            {' → '}
            {formatDate(context.source.moving.acquisition_date)} later · identity unverified
          </p>
        </div>
        <div className="qa-watermark">{context.watermark}</div>
      </header>

      <section className="qa-safety-strip">
        <strong>Investigational preview.</strong> Registered moving is interpolated. Native images
        stay visible. No measurement, screenshot export, agent-state publishing, subtraction,
        segmentation, mask propagation, or response conclusion is available here.
      </section>

      <section className="qa-controls" aria-label="Registration QA display controls">
        <div className="qa-control-group">
          <span>Plane</span>
          {(['axial', 'coronal', 'sagittal'] as const).map((item) => (
            <button
              aria-pressed={plane === item}
              className={plane === item ? 'active' : ''}
              disabled={!volumes}
              key={item}
              onClick={() => choosePlane(item)}
              type="button"
            >
              {item}
            </button>
          ))}
        </div>
        <label className="qa-slice-slider">
          <span>
            Slice {sliceIndex + 1} / {sliceCount}
          </span>
          <input
            max={Math.max(0, sliceCount - 1)}
            min="0"
            onChange={(event) => {
              const next = Number(event.target.value);
              setSliceIndex(next);
              recordSliceVisit(plane, next, sliceCount);
            }}
            disabled={!volumes}
            type="range"
            value={Math.min(sliceIndex, sliceCount - 1)}
          />
        </label>
        <div className="qa-control-group">
          <span>QA mode</span>
          {(['opacity', 'swipe', 'checkerboard', 'edges'] as const).map((item) => (
            <button
              aria-pressed={mode === item}
              className={mode === item ? 'active' : ''}
              disabled={!volumes}
              key={item}
              onClick={() => chooseMode(item)}
              type="button"
            >
              {item}
            </button>
          ))}
        </div>
      </section>

      {!volumes ? (
        <section className="qa-loading">Verifying hashes and decoding local NRRD volumes…</section>
      ) : (
        <>
          <section className="qa-native-grid">
            <QaCanvas
              orientation={fixedOrientation}
              title="Fixed earlier · native-intensity"
              slice={fixedSlice}
            />
            <QaCanvas
              orientation={movingOrientation}
              title="Moving later · native-intensity · approximate stack fraction"
              slice={movingNativeSlice}
            />
            <QaCanvas
              derived
              markers={registeredMarkers}
              onPoint={selectRegisteredLandmark}
              orientation={fixedOrientation}
              slice={registeredSlice}
              title="Moving later · registered to fixed"
            />
          </section>
          <section className="qa-comparison-grid">
            <QaCanvas
              markers={fixedMarkers}
              onPoint={selectFixedLandmark}
              orientation={fixedOrientation}
              slice={fixedSlice}
              title="Fixed landmark pane"
            />
            <CompositeCanvas
              checkerSize={checkerSize}
              edgeThreshold={edgeThreshold}
              fixed={fixedSlice}
              mode={mode}
              opacity={opacity}
              orientation={fixedOrientation}
              registered={registeredSlice}
              swipePosition={swipePosition}
            />
          </section>
        </>
      )}

      <section className="qa-adjustments">
        <label>
          Fixed black / white
          <span>
            <input
              max="98"
              min="0"
              onChange={(event) => setFixedWindow([Number(event.target.value), fixedWindow[1]])}
              type="range"
              value={fixedWindow[0]}
            />
            <input
              max="100"
              min="2"
              onChange={(event) => setFixedWindow([fixedWindow[0], Number(event.target.value)])}
              type="range"
              value={fixedWindow[1]}
            />
          </span>
        </label>
        <label>
          Moving black / white
          <span>
            <input
              max="98"
              min="0"
              onChange={(event) => setMovingWindow([Number(event.target.value), movingWindow[1]])}
              type="range"
              value={movingWindow[0]}
            />
            <input
              max="100"
              min="2"
              onChange={(event) => setMovingWindow([movingWindow[0], Number(event.target.value)])}
              type="range"
              value={movingWindow[1]}
            />
          </span>
        </label>
        {mode === 'opacity' && (
          <label>
            Registered opacity {Math.round(opacity * 100)}%
            <input
              max="1"
              min="0"
              onChange={(event) => setOpacity(Number(event.target.value))}
              step="0.01"
              type="range"
              value={opacity}
            />
          </label>
        )}
        {mode === 'checkerboard' && (
          <label>
            Checker size {checkerSize}px
            <input
              max="80"
              min="2"
              onChange={(event) => setCheckerSize(Number(event.target.value))}
              type="range"
              value={checkerSize}
            />
          </label>
        )}
        {mode === 'edges' && (
          <label>
            Edge threshold {edgeThreshold}
            <input
              max="1000"
              min="10"
              onChange={(event) => setEdgeThreshold(Number(event.target.value))}
              type="range"
              value={edgeThreshold}
            />
          </label>
        )}
        {mode === 'swipe' && (
          <label>
            Swipe position {Math.round(swipePosition * 100)}%
            <input
              max="1"
              min="0"
              onChange={(event) => setSwipePosition(Number(event.target.value))}
              step="0.01"
              type="range"
              value={swipePosition}
            />
          </label>
        )}
      </section>

      <section className="qa-landmarks">
        <div>
          <p className="eyebrow">Supplemental target-registration error</p>
          <h2>Independent landmark pairs</h2>
          <p>{landmarkMessage}</p>
          <label>
            Landmark
            <select value={landmarkLabel} onChange={(event) => setLandmarkLabel(event.target.value)}>
              {context.landmark_options.map((item) => (
                <option key={item} value={item}>
                  {item.replaceAll('_', ' ')}
                </option>
              ))}
            </select>
          </label>
          {pendingFixed && (
            <button onClick={() => setPendingFixed(undefined)} type="button">
              Clear pending fixed point
            </button>
          )}
        </div>
        <div className="qa-landmark-table-wrap">
          <table>
            <thead>
              <tr>
                <th>Pair</th>
                <th>Residual</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {landmarkPairs.length === 0 ? (
                <tr>
                  <td colSpan={3}>No independent point pairs recorded.</td>
                </tr>
              ) : (
                landmarkPairs.map((pair) => (
                  <tr key={pair.id}>
                    <td>{pair.label.replaceAll('_', ' ')}</td>
                    <td>{pair.residualMm.toFixed(2)} mm</td>
                    <td>
                      <button
                        onClick={() =>
                          setLandmarkPairs((current) =>
                            current.filter((item) => item.id !== pair.id),
                          )
                        }
                        type="button"
                      >
                        Remove
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="qa-review-form">
        <div className="qa-form-heading">
          <div>
            <p className="eyebrow">Hash-bound local evidence</p>
            <h2>Record accept or reject</h2>
          </div>
          <p>
            Traversed planes:{' '}
            {Object.entries(inspectedPlanes)
              .map(
                ([name, coverage]) =>
                  `${name} ${Math.round(coverage.normalized_min * 100)}–${Math.round(
                    coverage.normalized_max * 100,
                  )}%`,
              )
              .join(', ') || 'none'}{' '}
            · modes:{' '}
            {[...inspectedModes].join(', ')}
          </p>
        </div>

        <div className="qa-checklist">
          {context.qualitative_checks.map((item) => (
            <label key={item.id}>
              <input
                checked={checks[item.id] ?? false}
                onChange={(event) =>
                  setChecks((current) => ({ ...current, [item.id]: event.target.checked }))
                }
                type="checkbox"
              />
              <span>{item.label}</span>
            </label>
          ))}
        </div>

        <div className="qa-observations">
          <h3>Brain landmark observations</h3>
          <p>Acceptance requires at least three recorded observations, all aligned.</p>
          <div>
            {context.landmark_options.map((item) => (
              <label key={item}>
                <span>{item.replaceAll('_', ' ')}</span>
                <select
                  onChange={(event) =>
                    setObservations((current) => ({
                      ...current,
                      [item]: event.target.value as (typeof observations)[string],
                    }))
                  }
                  value={observations[item] ?? ''}
                >
                  <option value="">Not recorded</option>
                  {context.landmark_statuses.map((status) => (
                    <option key={status} value={status}>
                      {status.replaceAll('_', ' ')}
                    </option>
                  ))}
                </select>
              </label>
            ))}
          </div>
        </div>

        <div className="qa-form-grid">
          <label>
            Reviewer name
            <input autoComplete="off" maxLength={120} onChange={(event) => setReviewerName(event.target.value)} spellCheck={false} value={reviewerName} />
          </label>
          <label>
            Reviewer role
            <select
              onChange={(event) =>
                setReviewerRole(event.target.value as RegistrationReviewRequest['reviewer']['role'])
              }
              value={reviewerRole}
            >
              <option value="clinician">Clinician</option>
              <option value="medical_physicist">Medical physicist</option>
              <option value="patient_or_family">Patient or family</option>
              <option value="researcher_or_engineer">Researcher or engineer</option>
              <option value="other">Other</option>
            </select>
          </label>
          <label>
            Organization (optional)
            <input autoComplete="off" maxLength={160} onChange={(event) => setOrganization(event.target.value)} spellCheck={false} value={organization} />
          </label>
          <label>
            Registration QA training
            <select
              onChange={(event) =>
                setTrainingStatus(
                  event.target.value as RegistrationReviewRequest['reviewer']['training_status'],
                )
              }
              value={trainingStatus}
            >
              <option value="self_attested_not_trained">Not trained / family review</option>
              <option value="self_attested_trained">Self-attested training</option>
            </select>
          </label>
          <label className="qa-wide-field">
            Region of greatest importance
            <textarea maxLength={500} onChange={(event) => setRegion(event.target.value)} spellCheck={false} value={region} />
          </label>
          <label>
            Quantitative status
            <select
              onChange={(event) => setQuantitativeStatus(event.target.value as 'recorded' | 'unavailable')}
              value={quantitativeStatus}
            >
              <option value="unavailable">Unavailable — explain</option>
              <option value="recorded">Recorded — at least 3 pairs</option>
            </select>
          </label>
          {quantitativeStatus === 'recorded' ? (
            <div className="qa-wide-field qa-fixed-policy">
              <strong>Fixed tolerance: {toleranceMm.toFixed(3)} mm</strong>
              <span>{toleranceBasis}</span>
              <span>The policy is fixed before landmark capture and cannot be edited.</span>
            </div>
          ) : (
            <label className="qa-wide-field">
              Why quantitative landmark QA is unavailable
              <textarea maxLength={1000} onChange={(event) => setUnavailableReason(event.target.value)} spellCheck={false} value={unavailableReason} />
            </label>
          )}
          <label className="qa-wide-field">
            Regional defects, one per line (acceptance requires none)
            <textarea maxLength={4000} onChange={(event) => setDefects(event.target.value)} spellCheck={false} value={defects} />
          </label>
          <label className="qa-wide-field">
            Decision note
            <textarea maxLength={4000} onChange={(event) => setNote(event.target.value)} spellCheck={false} value={note} />
          </label>
          <label>
            Decision
            <select
              onChange={(event) =>
                setDecision(event.target.value as RegistrationReviewRequest['decision'])
              }
              value={decision}
            >
              <option value="rejected">Reject</option>
              <option
                disabled={!qualifiedReviewer}
                value="accepted_for_shared_coverage_overlay_swipe"
              >
                Accept shared-coverage overlay/swipe — trained clinician/physicist only
              </option>
            </select>
          </label>
        </div>

        <label className="qa-attestation">
          <input checked={attest} onChange={(event) => setAttest(event.target.checked)} type="checkbox" />
          <span>
            I attest this is my self-asserted exploratory QA observation. It is not authenticated
            clinical approval, diagnosis, treatment-response assessment, or proof of lesion identity.
            The downloaded sensitive JSON may be placed in a browser Downloads folder that is
            backed up or cloud-synced; I will move and protect it appropriately.
          </span>
        </label>

        <div className="qa-submit-row">
          <button
            className="primary-action"
            disabled={!decisionReady}
            onClick={() => void submitReview()}
            type="button"
          >
            {phase === 'submitting' ? 'Building local record…' : 'Download hash-bound QA record'}
          </button>
          <p className={phase === 'error' ? 'error' : ''}>{reviewMessage}</p>
        </div>
      </section>
    </main>
  );
};
