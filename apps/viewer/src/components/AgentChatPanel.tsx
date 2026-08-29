import type { AgentChatContext } from '../agentChatContext';
import { formatDicomDate } from '../dicom';
import { formatMprPatientPoint } from '../mpr';

export function AgentChatPanel({
  context,
  seriesDescription,
}: {
  context?: AgentChatContext;
  seriesDescription?: string;
}) {
  return (
    <aside className="agent-chat" aria-label="OpenAI agent chat">
      <header className="agent-chat-heading">
        <div>
          <span className="eyebrow">Local image context</span>
          <h2>Agent chat</h2>
        </div>
        <span className="agent-chat-status">Connector next</span>
      </header>

      <div className="agent-chat-context" aria-label="Image context for agent chat">
        {context ? (
          <>
            <strong>{seriesDescription || 'Selected series'}</strong>
            <dl>
              <div>
                <dt>View</dt>
                <dd>{context.view_mode === 'mpr' ? '3-plane MPR' : 'Single image'}</dd>
              </div>
              <div>
                <dt>Source</dt>
                <dd>
                  {context.modality} · {formatDicomDate(context.acquisition_date)}
                </dd>
              </div>
              <div>
                <dt>Image</dt>
                <dd>
                  {context.stack_position} / {context.stack_count}
                </dd>
              </div>
              <div>
                <dt>Pointer</dt>
                <dd>
                  {context.patient_point_lps_mm
                    ? `${formatMprPatientPoint(context.patient_point_lps_mm)} LPS`
                    : context.view_mode === 'mpr'
                      ? 'Building crosshairs…'
                      : 'Move over the image'}
                </dd>
              </div>
            </dl>
          </>
        ) : (
          <span>Open a series to prepare exact local context.</span>
        )}
      </div>

      <div className="agent-chat-transcript" aria-live="polite">
        <article className="agent-message assistant">
          <span>OpenAI agent</span>
          <p>
            This panel will attach the exact local series, source image, view, and pointer to
            each message. The local agent connector is the next implementation step.
          </p>
        </article>
        <p className="agent-chat-privacy">
          No pixels or DICOM files are sent by this panel. Source inspection remains local.
        </p>
      </div>

      <form className="agent-chat-composer" aria-label="Agent message composer">
        <label htmlFor="agent-chat-message">Message</label>
        <textarea
          id="agent-chat-message"
          rows={3}
          disabled
          placeholder="Available when the local OpenAI agent connector is running"
        />
        <button type="submit" disabled>
          Send
        </button>
      </form>
    </aside>
  );
}
