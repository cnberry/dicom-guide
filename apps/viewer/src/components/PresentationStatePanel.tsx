import type {
  AppliedPresentationState,
  PresentationStateTarget,
  ResolvedPresentationState,
  ResolvedPresentationStateCatalog,
} from '../presentationStates';

const MAX_VISIBLE_STATES = 64;
const MAX_VISIBLE_TARGETS = 12;

type Props = {
  catalog?: ResolvedPresentationStateCatalog;
  message: string;
  loading: boolean;
  disabled?: boolean;
  imageA?: AppliedPresentationState;
  imageB?: AppliedPresentationState;
  onOpen: (
    state: ResolvedPresentationState,
    target: PresentationStateTarget,
    slot: 'image_a' | 'image_b',
  ) => void;
  onClear: (slot: 'image_a' | 'image_b') => void;
};

const countLabel = (count: number, singular: string, plural = `${singular}s`) =>
  `${count} ${count === 1 ? singular : plural}`;

export function PresentationStatePanel({
  catalog,
  message,
  loading,
  disabled = false,
  imageA,
  imageB,
  onOpen,
  onClear,
}: Props) {
  const visibleStates = catalog?.states.slice(0, MAX_VISIBLE_STATES) ?? [];
  const hiddenStateCount = Math.max(0, (catalog?.states.length ?? 0) - visibleStates.length);
  return (
    <section
      className="presentation-state-panel"
      aria-labelledby="presentation-state-heading"
    >
      <div className="presentation-state-heading">
        <div>
          <span className="eyebrow">Source-carried DICOM display instructions · GSPS</span>
          <h2 id="presentation-state-heading">
            Source-carried DICOM presentation states (GSPS)
          </h2>
          <p>
            Open a supported state deliberately to navigate to an exact referenced image, apply
            its supported linear window, and render supported source coordinates and text.
            DICOM Guide does not authenticate the creator or infer clinical meaning.
          </p>
        </div>
        <span className="unreviewed-badge">
          {catalog
            ? `${catalog.catalog.supported_state_count} supported · ${catalog.catalog.unsupported_state_count} locked`
            : loading
              ? 'Checking locally…'
              : 'Unavailable'}
        </span>
      </div>

      {(imageA || imageB) && (
        <div className="presentation-state-active" aria-label="Applied source-carried GSPS states">
          <strong>Strict source-carried GSPS display active</strong>
          {imageA && (
            <span>
              Image A · GSPS state{' '}
              {catalog
                ? catalog.states.findIndex(
                    (item) =>
                      item.state.presentation_state_id === imageA.state.presentation_state_id,
                  ) + 1
                : '—'}
              <button type="button" onClick={() => onClear('image_a')}>Clear</button>
            </span>
          )}
          {imageB && (
            <span>
              Image B · GSPS state{' '}
              {catalog
                ? catalog.states.findIndex(
                    (item) =>
                      item.state.presentation_state_id === imageB.state.presentation_state_id,
                  ) + 1
                : '—'}
              <button type="button" onClick={() => onClear('image_b')}>Clear</button>
            </span>
          )}
        </div>
      )}

      {visibleStates.length > 0 ? (
        <ol className="presentation-state-items">
          {visibleStates.map((resolved, stateIndex) => {
            const { state } = resolved;
            const visibleTargets = resolved.targets.slice(0, MAX_VISIBLE_TARGETS);
            const hiddenTargets = resolved.targets.length - visibleTargets.length;
            return (
              <li key={state.presentation_state_id}>
                <div className="presentation-state-copy">
                  <span className="presentation-state-source-label">
                    GSPS state {stateIndex + 1} · creator not authenticated · source object read-only
                  </span>
                  <strong>
                    WC {state.presentation.window_center.toLocaleString()} · WW{' '}
                    {state.presentation.window_width.toLocaleString()}
                  </strong>
                  <span>
                    {countLabel(state.referenced_instance_count, 'referenced image')} ·{' '}
                    {countLabel(state.annotation_count, 'annotation')} ·{' '}
                    {countLabel(state.graphic_count, 'polyline')} ·{' '}
                    {countLabel(state.text_count, 'source text object')}
                  </span>
                  {resolved.targets[0]?.basis === 'first_referenced_image' && (
                    <small>
                      No explicit annotation target; the control opens the first image in the
                      source reference list and does not imply clinical relevance.
                    </small>
                  )}
                  {hiddenTargets > 0 && (
                    <small>
                      {hiddenTargets.toLocaleString()} additional source targets are withheld from
                      this bounded control list.
                    </small>
                  )}
                </div>
                <div className="presentation-state-targets">
                  {visibleTargets.map((target, targetIndex) => (
                    <div key={target.instanceId}>
                      <span>
                        {target.basis === 'source_annotation'
                          ? `Annotated target ${targetIndex + 1}`
                          : 'First referenced image'}{' '}
                        · {target.modality} · slice {target.stackPosition} / {target.stackCount}
                      </span>
                      <div>
                        <button
                          type="button"
                          disabled={disabled}
                          onClick={() => onOpen(resolved, target, 'image_a')}
                        >
                          Open in Image A
                        </button>
                        <button
                          type="button"
                          disabled={disabled}
                          onClick={() => onOpen(resolved, target, 'image_b')}
                        >
                          Open in Image B
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </li>
            );
          })}
        </ol>
      ) : null}

      {hiddenStateCount > 0 && (
        <p className="presentation-state-message">
          {hiddenStateCount.toLocaleString()} additional supported states are withheld from this
          bounded control list.
        </p>
      )}
      <p
        className="presentation-state-message"
        role={
          message.includes('changed after startup') ||
          message.includes('invalid') ||
          message.includes('does not match')
            ? 'alert'
            : 'status'
        }
        aria-live="polite"
      >
        {message}
      </p>
      <p className="presentation-state-safety">
        Source text may contain identifiers or clinical language. DICOM Guide does not verify the
        creator, credentials, signature, review status, accuracy, or meaning. Orange is a
        high-contrast rendering of supported source coordinates; source color, style, layer
        behavior, and full GSPS fidelity are not claimed. The graphic is not a DICOM Guide ROI or
        measurement. While a state is active, viewport manipulation, measurement drafts, agent
        state, MPR, and evidence exports are locked. The original image and GSPS object remain
        authoritative.
      </p>
    </section>
  );
}
