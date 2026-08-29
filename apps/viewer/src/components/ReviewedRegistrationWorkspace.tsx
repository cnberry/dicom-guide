import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  composeQaSlice,
  extractPatientSpaceSlice,
  parseNrrd,
  patientSpacePlaneLength,
  planeOrientationLabels,
  type NrrdPlane,
  type NrrdSlice,
  type NrrdVolume,
  type PlaneOrientationLabels,
} from '../nrrd';
import {
  fetchReviewedRegistrationVolume,
  MAX_REVIEWED_REGISTRATION_DECODED_TOTAL_BYTES,
  MAX_REVIEWED_REGISTRATION_ENCODED_TOTAL_BYTES,
  type ReviewedRegistrationContext,
  type ReviewedRegistrationGeometry,
  type ReviewedRegistrationMode,
} from '../reviewedRegistrationService';

type LoadedVolumes = {
  fixed: NrrdVolume;
  registered: NrrdVolume;
};

const REVIEWED_PATIENT_SPACE_OPTIONS = {
  maxDimension: 2048,
  maxPixels: 4 * 1024 * 1024,
} as const;

type WindowBoundary = 'lower' | 'upper';

export const updateReviewedWindow = (
  current: [number, number],
  boundary: WindowBoundary,
  requestedValue: number,
): [number, number] => {
  const requested = Number.isFinite(requestedValue)
    ? Math.max(0, Math.min(100, Math.round(requestedValue)))
    : boundary === 'lower'
      ? current[0]
      : current[1];
  if (boundary === 'lower') {
    const upper = Math.max(1, Math.min(100, current[1]));
    return [Math.min(requested, upper - 1), upper];
  }
  const lower = Math.max(0, Math.min(99, current[0]));
  return [lower, Math.max(requested, lower + 1)];
};

const errorMessage = (error: unknown, fallback: string): string =>
  error instanceof Error ? error.message : fallback;

const loadReviewedVolume = async (
  descriptor: ReviewedRegistrationContext['volumes']['fixed'],
  signal: AbortSignal,
  maxDecodedBytes?: number,
): Promise<NrrdVolume> =>
  parseNrrd(await fetchReviewedRegistrationVolume(descriptor, signal), {
    maxDecodedBytes,
  });

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
  descriptor: ReviewedRegistrationGeometry,
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
  if (
    !Number.isFinite(lowPercent) ||
    !Number.isFinite(highPercent) ||
    lowPercent < 0 ||
    highPercent > 100 ||
    highPercent <= lowPercent
  ) {
    throw new Error('Reviewed display window bounds must remain ordered.');
  }
  const [minimum, maximum] = volume.sampledRange;
  const span = maximum > minimum ? maximum - minimum : 1;
  return [
    minimum + (span * lowPercent) / 100,
    minimum + (span * highPercent) / 100,
  ];
};

const orientationDescription = (labels?: PlaneOrientationLabels): string =>
  labels
    ? `Orientation left ${labels.left}, right ${labels.right}, top ${labels.top}, bottom ${labels.bottom}.`
    : 'Patient-space orientation is not available.';

const Orientation = ({ labels }: { labels?: PlaneOrientationLabels }) =>
  labels ? (
    <div className="qa-orientation" aria-hidden="true">
      <span className="qa-orientation-left">{labels.left}</span>
      <span className="qa-orientation-right">{labels.right}</span>
      <span className="qa-orientation-top">{labels.top}</span>
      <span className="qa-orientation-bottom">{labels.bottom}</span>
    </div>
  ) : null;

const SliceCanvas = ({
  title,
  description,
  slice,
  orientation,
  viewContext,
  onRenderError,
}: {
  title: string;
  description: string;
  slice?: NrrdSlice;
  orientation?: PlaneOrientationLabels;
  viewContext: string;
  onRenderError: (message: string) => void;
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !slice) return;
    try {
      canvas.width = slice.width;
      canvas.height = slice.height;
      const rgba = new Uint8ClampedArray(slice.pixels.length * 4);
      slice.pixels.forEach((value, index) => {
        const target = index * 4;
        rgba[target] = value;
        rgba[target + 1] = value;
        rgba[target + 2] = value;
        rgba[target + 3] = 255;
      });
      const renderingContext = canvas.getContext('2d');
      if (!renderingContext) throw new Error('Browser canvas rendering is unavailable.');
      renderingContext.putImageData(
        new ImageData(rgba, slice.width, slice.height),
        0,
        0,
      );
    } catch (error) {
      onRenderError(errorMessage(error, 'Reviewed reference canvas could not render.'));
    }
  }, [onRenderError, slice]);

  const accessibleDescription = `${title}. ${description}. ${viewContext}. ${orientationDescription(orientation)}`;

  return (
    <section className="qa-image-card reviewed-image-card">
      <header>
        <strong>{title}</strong>
        <span>{description}</span>
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
          <canvas ref={canvasRef} role="img" aria-label={accessibleDescription}>
            {accessibleDescription}
          </canvas>
          <Orientation labels={orientation} />
        </div>
      </div>
    </section>
  );
};

const ComparisonCanvas = ({
  fixed,
  registered,
  mode,
  opacity,
  swipePosition,
  orientation,
  viewContext,
  onRenderError,
}: {
  fixed?: NrrdSlice;
  registered?: NrrdSlice;
  mode: ReviewedRegistrationMode;
  opacity: number;
  swipePosition: number;
  orientation?: PlaneOrientationLabels;
  viewContext: string;
  onRenderError: (message: string) => void;
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !fixed || !registered) return;
    try {
      const composite = composeQaSlice(fixed, registered, mode, {
        opacity,
        swipePosition,
        checkerSize: 2,
        edgeThreshold: 255,
      });
      canvas.width = composite.width;
      canvas.height = composite.height;
      const renderingContext = canvas.getContext('2d');
      if (!renderingContext) throw new Error('Browser canvas rendering is unavailable.');
      renderingContext.putImageData(
        new ImageData(
          composite.data as Uint8ClampedArray<ArrayBuffer>,
          composite.width,
          composite.height,
        ),
        0,
        0,
      );
    } catch (error) {
      onRenderError(errorMessage(error, 'Reviewed comparison canvas could not render.'));
    }
  }, [fixed, mode, onRenderError, opacity, registered, swipePosition]);

  const accessibleDescription =
    mode === 'swipe'
      ? `Swipe comparison. Fixed earlier reference is left of the ${Math.round(swipePosition * 100)} percent boundary; registered moving derived resampled volume is right. ${viewContext}. ${orientationDescription(orientation)}`
      : `Opacity overlay of fixed earlier reference and registered moving derived resampled volume at ${Math.round(opacity * 100)} percent registered opacity. ${viewContext}. ${orientationDescription(orientation)}`;

  return (
    <section className="qa-image-card qa-composite-card reviewed-image-card">
      <header>
        <strong>
          {mode === 'opacity'
            ? 'OPACITY OVERLAY'
            : 'SWIPE · FIXED LEFT / REGISTERED MOVING RIGHT'}
        </strong>
        <span>FIXED REFERENCE + REGISTERED MOVING · DERIVED DISPLAY</span>
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
          <canvas ref={canvasRef} role="img" aria-label={accessibleDescription}>
            {accessibleDescription}
          </canvas>
          <Orientation labels={orientation} />
          {mode === 'swipe' && (
            <>
              <span className="reviewed-swipe-legend reviewed-swipe-fixed" aria-hidden="true">
                FIXED REFERENCE
              </span>
              <span className="reviewed-swipe-legend reviewed-swipe-registered" aria-hidden="true">
                REGISTERED MOVING · RESAMPLED
              </span>
              <span
                className="reviewed-swipe-line"
                aria-hidden="true"
                style={{ left: `${swipePosition * 100}%` }}
              />
            </>
          )}
        </div>
      </div>
    </section>
  );
};

export const ReviewedRegistrationWorkspace = ({
  context,
  onExit,
}: {
  context: ReviewedRegistrationContext;
  onExit: () => void;
}) => {
  const [volumes, setVolumes] = useState<LoadedVolumes>();
  const [loadError, setLoadError] = useState<string>();
  const [renderError, setRenderError] = useState<string>();
  const [loadStage, setLoadStage] = useState('Validating fixed earlier reference…');
  const [plane, setPlane] = useState<NrrdPlane>('axial');
  const [sliceIndex, setSliceIndex] = useState(0);
  const [mode, setMode] = useState<ReviewedRegistrationMode>('opacity');
  const [fixedWindow, setFixedWindow] = useState<[number, number]>([1, 99]);
  const [registeredWindow, setRegisteredWindow] = useState<[number, number]>([1, 99]);
  const [opacity, setOpacity] = useState(0.5);
  const [swipePosition, setSwipePosition] = useState(0.5);
  const failRender = useCallback((message: string) => {
    setRenderError((current) => current ?? message);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setVolumes(undefined);
    setLoadError(undefined);
    setRenderError(undefined);
    void (async () => {
      const totalBytes =
        context.volumes.fixed.bytes + context.volumes.registered_moving.bytes;
      if (totalBytes > MAX_REVIEWED_REGISTRATION_ENCODED_TOTAL_BYTES) {
        throw new Error('Accepted exploratory volumes exceed the aggregate browser safety limit.');
      }

      setLoadStage('Loading and verifying fixed earlier reference…');
      const fixed = await loadReviewedVolume(
        context.volumes.fixed,
        controller.signal,
        MAX_REVIEWED_REGISTRATION_DECODED_TOTAL_BYTES,
      );
      if (!volumeMatchesDescriptor(fixed, context.volumes.fixed.geometry)) {
        throw new Error('Fixed earlier reference disagrees with its reviewed geometry.');
      }
      if (fixed.payload.byteLength > MAX_REVIEWED_REGISTRATION_DECODED_TOTAL_BYTES) {
        throw new Error('Fixed earlier reference exceeds the decoded browser safety limit.');
      }

      setLoadStage('Loading and verifying registered moving volume…');
      const remainingDecodedBytes =
        MAX_REVIEWED_REGISTRATION_DECODED_TOTAL_BYTES - fixed.payload.byteLength;
      if (remainingDecodedBytes <= 0) {
        throw new Error('Fixed earlier reference leaves no decoded browser budget for comparison.');
      }
      const registered = await loadReviewedVolume(
        context.volumes.registered_moving,
        controller.signal,
        remainingDecodedBytes,
      );
      if (
        !volumeMatchesDescriptor(
          registered,
          context.volumes.registered_moving.geometry,
        ) ||
        !arraysClose(fixed.sizes, registered.sizes, 0) ||
        fixed.space !== registered.space ||
        !arraysClose(fixed.spaceDirections, registered.spaceDirections) ||
        !arraysClose(fixed.spaceOrigin, registered.spaceOrigin)
      ) {
        throw new Error('Registered moving volume disagrees with reviewed fixed geometry.');
      }
      if (
        fixed.payload.byteLength + registered.payload.byteLength >
        MAX_REVIEWED_REGISTRATION_DECODED_TOTAL_BYTES
      ) {
        throw new Error('Accepted exploratory volumes exceed the decoded browser safety limit.');
      }
      if (controller.signal.aborted) return;
      const initialSlice = Math.floor(
        patientSpacePlaneLength(fixed, 'axial', REVIEWED_PATIENT_SPACE_OPTIONS) / 2,
      );
      setSliceIndex(initialSlice);
      setVolumes({ fixed, registered });
      setLoadStage('Ready');
    })().catch((error) => {
      if (controller.signal.aborted) return;
      setVolumes(undefined);
      setLoadError(
        error instanceof Error
          ? error.message
          : 'Accepted exploratory registration volumes could not load.',
      );
    });
    return () => controller.abort();
  }, [context]);

  const renderedSlices = useMemo(() => {
    if (!volumes) return { sliceCount: 1 };
    try {
      const sliceCount = patientSpacePlaneLength(
        volumes.fixed,
        plane,
        REVIEWED_PATIENT_SPACE_OPTIONS,
      );
      return {
        sliceCount,
        fixedSlice: extractPatientSpaceSlice(
          volumes.fixed,
          plane,
          sliceIndex,
          windowFromPercent(volumes.fixed, fixedWindow[0], fixedWindow[1]),
          REVIEWED_PATIENT_SPACE_OPTIONS,
        ),
        registeredSlice: extractPatientSpaceSlice(
          volumes.registered,
          plane,
          sliceIndex,
          windowFromPercent(
            volumes.registered,
            registeredWindow[0],
            registeredWindow[1],
          ),
          REVIEWED_PATIENT_SPACE_OPTIONS,
        ),
        orientation: planeOrientationLabels(volumes.fixed, plane),
      };
    } catch (error) {
      return {
        sliceCount: 1,
        error: errorMessage(error, 'Reviewed patient-space slices could not render.'),
      };
    }
  }, [fixedWindow, plane, registeredWindow, sliceIndex, volumes]);
  const { fixedSlice, orientation, registeredSlice, sliceCount } = renderedSlices;
  const displayError = loadError ?? renderError ?? renderedSlices.error;
  const displayReady = Boolean(volumes && !displayError);

  const choosePlane = (nextPlane: NrrdPlane) => {
    if (!volumes || displayError) return;
    try {
      const nextLength = patientSpacePlaneLength(
        volumes.fixed,
        nextPlane,
        REVIEWED_PATIENT_SPACE_OPTIONS,
      );
      setPlane(nextPlane);
      setSliceIndex(Math.floor(nextLength / 2));
    } catch (error) {
      failRender(errorMessage(error, 'Reviewed patient-space plane could not render.'));
    }
  };

  return (
    <main className="reviewed-workspace">
      <header className="reviewed-header">
        <div>
          <p className="eyebrow">Accepted exploratory registration · {context.source.modality}</p>
          <h1>Reviewed fixed-space comparison</h1>
          <p>
            {formatDate(context.source.fixed.acquisition_date)} fixed reference →{' '}
            {formatDate(context.source.moving.acquisition_date)} registered moving
          </p>
        </div>
        <div className="reviewed-header-actions">
          <div className="reviewed-accepted-badge">
            ACCEPTED FOR EXPLORATORY SHARED-COVERAGE OVERLAY / SWIPE
          </div>
          <button type="button" className="reviewed-exit-button" autoFocus onClick={onExit}>
            Switch to ordinary DICOM viewer
          </button>
        </div>
      </header>

      <section className="reviewed-label-strip" aria-label="Registration safety status">
        <strong>{context.display_label}</strong>
        <span>SELF-ATTESTED · UNVERIFIED REVIEWER IDENTITY</span>
        <span>REGISTERED MOVING IS RESAMPLED</span>
        <span>NOT FOR DIAGNOSIS OR TREATMENT PLANNING</span>
      </section>
      <section className="reviewed-coverage-warning" role="note">
        <strong>Shared coverage is visual-only.</strong> Authorization applies only where both
        derived volumes contain anatomy. This UI has no machine-generated overlap mask and does
        not enforce exact shared coverage pixel by pixel.
      </section>

      <section className="qa-controls" aria-label="Accepted exploratory display controls">
        <div className="qa-control-group">
          <span>Patient-space plane</span>
          {(['axial', 'coronal', 'sagittal'] as NrrdPlane[]).map((item) => (
            <button
              type="button"
              key={item}
              className={plane === item ? 'active' : ''}
              aria-pressed={plane === item}
              disabled={!displayReady}
              onClick={() => choosePlane(item)}
            >
              {item.toUpperCase()}
            </button>
          ))}
        </div>
        <label className="qa-slice-slider">
          <span>
            Slice {Math.min(sliceCount, sliceIndex + 1)} / {sliceCount}
          </span>
          <input
            type="range"
            min="0"
            max={Math.max(0, sliceCount - 1)}
            value={Math.min(sliceIndex, Math.max(0, sliceCount - 1))}
            disabled={!displayReady}
            onChange={(event) => setSliceIndex(Number(event.target.value))}
          />
        </label>
        <div className="qa-control-group">
          <span>Permitted comparison mode</span>
          {(['opacity', 'swipe'] as ReviewedRegistrationMode[]).map((item) => (
            <button
              type="button"
              key={item}
              className={mode === item ? 'active' : ''}
              aria-pressed={mode === item}
              disabled={!displayReady}
              onClick={() => setMode(item)}
            >
              {item.toUpperCase()}
            </button>
          ))}
        </div>
      </section>

      {displayError ? (
        <section className="qa-loading reviewed-load-error" role="alert">
          <div>
            <strong>Registered display failed closed.</strong>
            <p>{displayError}</p>
            <p>No registered pixels are displayed. Use the ordinary DICOM viewer instead.</p>
          </div>
        </section>
      ) : !volumes ? (
        <section className="qa-loading" aria-live="polite">
          {loadStage} Files are fetched, capped, hashed, and decoded one at a time.
        </section>
      ) : (
        <>
          <section className="reviewed-image-grid">
            <SliceCanvas
              title="FIXED EARLIER REFERENCE"
              description="DERIVED NRRD IN FIXED GEOMETRY · NOT NATIVE DICOM"
              slice={fixedSlice}
              orientation={orientation}
              viewContext={`${plane} patient-space slice ${sliceIndex + 1} of ${sliceCount}`}
              onRenderError={failRender}
            />
            <SliceCanvas
              title="REGISTERED MOVING"
              description="DERIVED · RESAMPLED INTO FIXED REFERENCE GEOMETRY"
              slice={registeredSlice}
              orientation={orientation}
              viewContext={`${plane} patient-space slice ${sliceIndex + 1} of ${sliceCount}`}
              onRenderError={failRender}
            />
            <ComparisonCanvas
              fixed={fixedSlice}
              registered={registeredSlice}
              mode={mode}
              opacity={opacity}
              swipePosition={swipePosition}
              orientation={orientation}
              viewContext={`${plane} patient-space slice ${sliceIndex + 1} of ${sliceCount}`}
              onRenderError={failRender}
            />
          </section>
          <section className="reviewed-adjustments">
            <label>
              Fixed reference window {fixedWindow[0]}–{fixedWindow[1]}%
              <span>
                <input
                  aria-label="Fixed reference lower window percentile"
                  type="range"
                  min="0"
                  max={fixedWindow[1] - 1}
                  value={fixedWindow[0]}
                  onChange={(event) =>
                    setFixedWindow(
                      updateReviewedWindow(
                        fixedWindow,
                        'lower',
                        Number(event.target.value),
                      ),
                    )
                  }
                />
                <input
                  aria-label="Fixed reference upper window percentile"
                  type="range"
                  min={fixedWindow[0] + 1}
                  max="100"
                  value={fixedWindow[1]}
                  onChange={(event) =>
                    setFixedWindow(
                      updateReviewedWindow(
                        fixedWindow,
                        'upper',
                        Number(event.target.value),
                      ),
                    )
                  }
                />
              </span>
            </label>
            <label>
              Registered moving window {registeredWindow[0]}–{registeredWindow[1]}%
              <span>
                <input
                  aria-label="Registered moving lower window percentile"
                  type="range"
                  min="0"
                  max={registeredWindow[1] - 1}
                  value={registeredWindow[0]}
                  onChange={(event) =>
                    setRegisteredWindow(
                      updateReviewedWindow(
                        registeredWindow,
                        'lower',
                        Number(event.target.value),
                      ),
                    )
                  }
                />
                <input
                  aria-label="Registered moving upper window percentile"
                  type="range"
                  min={registeredWindow[0] + 1}
                  max="100"
                  value={registeredWindow[1]}
                  onChange={(event) =>
                    setRegisteredWindow(
                      updateReviewedWindow(
                        registeredWindow,
                        'upper',
                        Number(event.target.value),
                      ),
                    )
                  }
                />
              </span>
            </label>
            {mode === 'opacity' ? (
              <label>
                Registered opacity {Math.round(opacity * 100)}%
                <input
                  aria-label="Registered moving opacity"
                  type="range"
                  min="0"
                  max="1"
                  step="0.01"
                  value={opacity}
                  onChange={(event) => setOpacity(Number(event.target.value))}
                />
              </label>
            ) : (
              <label>
                Swipe boundary {Math.round(swipePosition * 100)}%
                <input
                  aria-label="Swipe boundary"
                  type="range"
                  min="0"
                  max="1"
                  step="0.01"
                  value={swipePosition}
                  onChange={(event) => setSwipePosition(Number(event.target.value))}
                />
              </label>
            )}
          </section>
        </>
      )}

      <section className="reviewed-limitations">
        <div>
          <p className="eyebrow">Display boundaries</p>
          <h2>Native DICOM remains authoritative</h2>
          <p>
            This surface offers only opacity and swipe of reviewed derivatives. It does not
            provide subtraction, checkerboard or edge QA, native-moving pixels, measurements,
            export, or medical conclusions.
          </p>
        </div>
        <ul>
          {context.limitations.map((limitation) => (
            <li key={limitation}>{limitation}</li>
          ))}
        </ul>
      </section>
    </main>
  );
};
