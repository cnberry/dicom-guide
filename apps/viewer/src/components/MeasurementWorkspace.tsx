import { useEffect, useMemo, useState } from 'react';
import type { Compatibility, DicomSeries } from '../dicom';
import {
  buildMeasurementComparisonDraft,
  downloadMeasurementComparisonDraft,
  assessMeasurementPairingContext,
  type MeasurementComparisonDraft,
} from '../measurementComparison';
import type { MeasurementEvidence } from '../measurements';

type Props = {
  measurements: MeasurementEvidence[];
  baseline?: DicomSeries;
  followup?: DicomSeries;
  compatibilityLevel: Compatibility['level'];
  onDeleteMeasurement: (trackingId: string) => boolean;
};

const formatMeasurementResult = (measurement: MeasurementEvidence): string => {
  if (measurement.type === 'length') {
    return measurement.result.value === undefined
      ? 'Physical units unavailable'
      : `${measurement.result.value.toFixed(1)} mm`;
  }
  if (measurement.type === 'elliptical_roi') {
    if (
      measurement.result.major_axis === undefined ||
      measurement.result.minor_axis === undefined ||
      measurement.result.area === undefined
    ) {
      return 'Physical units unavailable';
    }
    return `${measurement.result.major_axis.toFixed(1)} × ${measurement.result.minor_axis.toFixed(1)} mm · ${measurement.result.area.toFixed(1)} mm²`;
  }
  if (
    measurement.result.long_axis === undefined ||
    measurement.result.short_axis === undefined ||
    measurement.result.product === undefined
  ) {
    return 'Physical units unavailable';
  }
  return `${measurement.result.long_axis.toFixed(1)} × ${measurement.result.short_axis.toFixed(1)} mm · ${measurement.result.product.toFixed(1)} mm²`;
};

const formatOpaqueSource = (value: string, kind: 'series' | 'instance'): string =>
  value.startsWith(`${kind}_`)
    ? `${kind}_${value.slice(kind.length + 1, kind.length + 9)}…`
    : `${kind} ${value.slice(0, 8)}…`;

const measurementTypeLabel = (measurement: MeasurementEvidence): string =>
  measurement.type === 'bidirectional'
    ? 'Bidirectional'
    : measurement.type === 'elliptical_roi'
      ? 'Ellipse ROI'
      : 'Length';

const metricLabel = (metric: string): string => metric.replaceAll('_', ' ');

export function MeasurementWorkspace({
  measurements,
  baseline,
  followup,
  compatibilityLevel,
  onDeleteMeasurement,
}: Props) {
  const [baselineMeasurementId, setBaselineMeasurementId] = useState('');
  const [followupMeasurementId, setFollowupMeasurementId] = useState('');
  const [lesionLabel, setLesionLabel] = useState('');
  const [comparisonDraft, setComparisonDraft] = useState<MeasurementComparisonDraft>();
  const [message, setMessage] = useState(
    'Labels and pair selections are working notes; they do not establish lesion identity.',
  );
  const baselineMeasurements = useMemo(
    () => measurements.filter((item) => item.source.series_id === baseline?.id),
    [baseline?.id, measurements],
  );
  const followupMeasurements = useMemo(
    () => measurements.filter((item) => item.source.series_id === followup?.id),
    [followup?.id, measurements],
  );
  const pairingContext = useMemo(
    () => assessMeasurementPairingContext(baseline, followup, compatibilityLevel),
    [baseline, compatibilityLevel, followup],
  );
  const longitudinalContextReady = pairingContext.ready;

  useEffect(() => {
    if (!baselineMeasurements.some((item) => item.tracking_id === baselineMeasurementId)) {
      setBaselineMeasurementId('');
    }
    if (!followupMeasurements.some((item) => item.tracking_id === followupMeasurementId)) {
      setFollowupMeasurementId('');
    }
    setComparisonDraft(undefined);
  }, [baselineMeasurements, followupMeasurements]);

  const previewComparison = () => {
    if (!longitudinalContextReady) {
      setMessage(pairingContext.reason);
      return;
    }
    const baselineMeasurement = baselineMeasurements.find(
      (item) => item.tracking_id === baselineMeasurementId,
    );
    const followupMeasurement = followupMeasurements.find(
      (item) => item.tracking_id === followupMeasurementId,
    );
    if (!baselineMeasurement || !followupMeasurement) {
      setMessage('Select one source-linked measurement from each timepoint.');
      return;
    }
    try {
      const draft = buildMeasurementComparisonDraft(
        baselineMeasurement,
        followupMeasurement,
        lesionLabel,
      );
      setComparisonDraft(draft);
      setMessage('Numeric draft built locally. Same-lesion identity and clinical meaning remain unreviewed.');
    } catch (error) {
      setComparisonDraft(undefined);
      setMessage(error instanceof Error ? error.message : 'Unable to pair these measurements.');
    }
  };

  const deleteMeasurement = (trackingId: string) => {
    if (onDeleteMeasurement(trackingId)) {
      setMessage('Annotation removed from this in-memory session; original DICOM is unchanged.');
    } else {
      setMessage('Display the source series before deleting an imported annotation.');
    }
  };

  return (
    <section className="measurement-panel" aria-label="Measurement evidence">
      <div className="measurement-heading">
        <div>
          <span className="eyebrow">Source-linked evidence · never a response verdict</span>
          <h2>Manual measurements</h2>
        </div>
        <span className="unreviewed-badge">{measurements.length} unreviewed</span>
      </div>
      <div className="measurement-table-wrap">
        <table>
          <thead>
            <tr>
              <th>Type</th>
              <th>Result</th>
              <th>Opaque source</th>
              <th>Tracking ID</th>
              <th>Session</th>
            </tr>
          </thead>
          <tbody>
            {measurements.length ? (
              measurements.map((measurement) => (
                <tr key={measurement.tracking_id}>
                  <td>{measurementTypeLabel(measurement)}</td>
                  <td>{formatMeasurementResult(measurement)}</td>
                  <td>
                    {formatOpaqueSource(measurement.source.series_id, 'series')} ·{' '}
                    {formatOpaqueSource(measurement.source.instance_id, 'instance')}
                  </td>
                  <td><code>{measurement.tracking_id}</code></td>
                  <td>
                    <button
                      className="table-action"
                      onClick={() => deleteMeasurement(measurement.tracking_id)}
                    >
                      Delete annotation
                    </button>
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={5}>No manual measurements. Draw on a selected native source image.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="pairing-editor" aria-label="Explicit lesion measurement pairing">
        <div className="pairing-heading">
          <div>
            <span className="eyebrow">Human-selected linkage · local numeric draft</span>
            <h3>Pair one lesion measurement across time</h3>
          </div>
          <span className="unreviewed-badge">No response category</span>
        </div>
        <div className="pairing-fields">
          <label>
            <span>Working lesion label</span>
            <input
              value={lesionLabel}
              maxLength={80}
              placeholder="Example: target lesion A"
              onChange={(event) => {
                setLesionLabel(event.target.value);
                setComparisonDraft(undefined);
              }}
            />
          </label>
          <label>
            <span>Baseline measurement</span>
            <select
              value={baselineMeasurementId}
              disabled={!longitudinalContextReady || baselineMeasurements.length === 0}
              onChange={(event) => {
                setBaselineMeasurementId(event.target.value);
                setComparisonDraft(undefined);
              }}
            >
              <option value="">Choose baseline evidence</option>
              {baselineMeasurements.map((measurement) => (
                <option key={measurement.tracking_id} value={measurement.tracking_id}>
                  {measurementTypeLabel(measurement)} · {formatMeasurementResult(measurement)}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Follow-up measurement</span>
            <select
              value={followupMeasurementId}
              disabled={!longitudinalContextReady || followupMeasurements.length === 0}
              onChange={(event) => {
                setFollowupMeasurementId(event.target.value);
                setComparisonDraft(undefined);
              }}
            >
              <option value="">Choose follow-up evidence</option>
              {followupMeasurements.map((measurement) => (
                <option key={measurement.tracking_id} value={measurement.tracking_id}>
                  {measurementTypeLabel(measurement)} · {formatMeasurementResult(measurement)}
                </option>
              ))}
            </select>
          </label>
          <button className="primary-action" onClick={previewComparison}>
            Build numeric preview
          </button>
        </div>
        <p className="pairing-message" aria-live="polite">{message}</p>
        {comparisonDraft && (
          <div className="comparison-preview">
            <div>
              <strong>{comparisonDraft.pairing.lesion_label}</strong>
              <span>Unreviewed explicit pair</span>
            </div>
            <table>
              <thead>
                <tr>
                  <th>Metric</th>
                  <th>Baseline</th>
                  <th>Follow-up</th>
                  <th>Absolute change</th>
                  <th>Percent change</th>
                </tr>
              </thead>
              <tbody>
                {comparisonDraft.computed_results.map((result) => (
                  <tr key={result.metric}>
                    <td>{metricLabel(result.metric)}</td>
                    <td>{result.baseline.toFixed(1)} {result.unit}</td>
                    <td>{result.followup.toFixed(1)} {result.unit}</td>
                    <td>{result.absolute_change.toFixed(1)} {result.unit}</td>
                    <td>
                      {result.percent_change === undefined
                        ? 'Undefined'
                        : `${result.percent_change.toFixed(1)}%`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p>
              This is arithmetic over two explicitly selected manual measurements—not a claim of
              tumor response, progression, treatment effect, or same-lesion identity.
            </p>
            <button onClick={() => downloadMeasurementComparisonDraft(comparisonDraft)}>
              Export unreviewed comparison JSON
            </button>
          </div>
        )}
      </div>
    </section>
  );
}
