import type {
  LoadedSourceSegmentation,
  ResolvedSourceSegmentation,
  ResolvedSourceSegmentationCatalog,
  SourceSegment,
} from '../sourceSegmentations';

const MAX_VISIBLE_SEGMENTATIONS = 64;
const MAX_VISIBLE_SEGMENTS = 32;

type Props = {
  catalog?: ResolvedSourceSegmentationCatalog;
  message: string;
  loading: boolean;
  opening: boolean;
  active?: LoadedSourceSegmentation;
  disabled?: boolean;
  onOpen: (
    segmentation: ResolvedSourceSegmentation,
    segment: SourceSegment,
  ) => void;
  onClear: () => void;
};

export function SourceSegmentationPanel({
  catalog,
  message,
  loading,
  opening,
  active,
  disabled = false,
  onOpen,
  onClear,
}: Props) {
  const visible = catalog?.segmentations.slice(0, MAX_VISIBLE_SEGMENTATIONS) ?? [];
  const hidden = Math.max(0, (catalog?.segmentations.length ?? 0) - visible.length);
  return (
    <section className="source-segmentation-panel" aria-labelledby="source-segmentation-heading">
      <div className="source-segmentation-heading">
        <div>
          <span className="eyebrow">Source-carried DICOM masks · SEG · local read-only</span>
          <h2 id="source-segmentation-heading">Source-carried DICOM segmentations</h2>
          <p>
            Open one source segment that passed DICOM Guide&apos;s narrow technical import profile on its
            exact native MR/CT grid. Full DICOM conformance is not certified. Labels, coded
            properties, algorithms, and boundaries come from the object; DICOM Guide does not
            authenticate or clinically interpret them.
          </p>
        </div>
        <span className="unreviewed-badge">
          {catalog
            ? `${catalog.catalog.supported_segmentation_count} supported · ${catalog.catalog.unsupported_segmentation_count} locked`
            : loading
              ? 'Checking locally…'
              : 'Unavailable'}
        </span>
      </div>

      {active && (
        <div className="source-segmentation-active">
          <strong>
            {opening ? 'Preparing read-only source DICOM SEG…' : 'Read-only source DICOM SEG open'}
          </strong>
          <span>
            Segment {active.segment.segment_number} · {active.segment.segment_label} · source
            meaning not assessed
          </span>
          <button type="button" onClick={onClear}>Close read-only MPR</button>
        </div>
      )}

      {visible.length > 0 && (
        <ol className="source-segmentation-items">
          {visible.map((resolved, segmentationIndex) => {
            const visibleSegments = resolved.state.segments.slice(0, MAX_VISIBLE_SEGMENTS);
            return (
              <li key={resolved.state.segmentation_id}>
                <div className="source-segmentation-copy">
                  <span className="source-segmentation-source-label">
                    DICOM SEG object {segmentationIndex + 1} · creator not authenticated
                  </span>
                  <strong>
                    {resolved.state.referenced_series.modality} native grid ·{' '}
                    {resolved.state.referenced_series.ordered_instance_ids.length} source slices
                  </strong>
                  <span>
                    {resolved.state.segment_count} {resolved.state.segment_count === 1 ? 'segment' : 'segments'} ·{' '}
                    {resolved.state.frame_count} source-mapped {resolved.state.frame_count === 1 ? 'frame' : 'frames'}
                  </span>
                </div>
                <div className="source-segmentation-segments">
                  {visibleSegments.map((segment) => {
                    const isActive = active?.state.segmentation_id === resolved.state.segmentation_id &&
                      active.segment.segment_number === segment.segment_number;
                    return (
                      <article key={segment.segment_number}>
                        <div>
                          <strong>
                            Segment {segment.segment_number} · {segment.segment_label}
                          </strong>
                          <span>
                            {segment.property_type.meaning} ({segment.property_type.scheme}{' '}
                            {segment.property_type.value}) · {segment.algorithm_type.toLowerCase()}
                            {segment.algorithm_name ? ` · ${segment.algorithm_name}` : ''}
                          </span>
                          <span>
                            {segment.marked_voxel_count.toLocaleString()} marked voxels ·{' '}
                            {segment.computed_volume_ml.toFixed(3)} mL technical native-grid volume ·
                            unreviewed
                          </span>
                        </div>
                        <button
                          type="button"
                          disabled={disabled || opening || isActive}
                          onClick={() => onOpen(resolved, segment)}
                        >
                          {isActive
                            ? 'Open read-only'
                            : opening
                              ? 'Validating mask…'
                              : 'Open read-only MPR'}
                        </button>
                      </article>
                    );
                  })}
                  {resolved.state.segment_count > visibleSegments.length && (
                    <small>
                      {resolved.state.segment_count - visibleSegments.length} additional segments
                      are withheld from this bounded control list.
                    </small>
                  )}
                </div>
              </li>
            );
          })}
        </ol>
      )}

      {hidden > 0 && (
        <p className="source-segmentation-message">
          {hidden.toLocaleString()} additional supported SEG objects are withheld from this
          bounded control list.
        </p>
      )}
      <p
        className="source-segmentation-message"
        role={message.includes('changed') || message.includes('failed') ? 'alert' : 'status'}
        aria-live="polite"
      >
        {message}
      </p>
      <p className="source-segmentation-safety">
        Segment labels and coded meanings may contain identifiers or clinical language. The
        displayed mask is a locally decoded, source-byte-anchored dense reconstruction on the exact
        source grid. Technical volume is marked-voxel arithmetic—not validation of the boundary,
        represented tissue, lesion identity, diagnosis, response, or treatment effect. Confirm the
        object and its meaning in the clinical imaging system.
      </p>
    </section>
  );
}
