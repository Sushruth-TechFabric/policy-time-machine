import { formatCurrency, formatEventDate } from '../../lib/format.js';
import './review.css';

const STATE_LABEL = { queued: 'Brief not yet built', in_progress: 'Run in progress', brief_ready: 'Brief ready', failed: 'Last Run failed' };
const OUTCOME_LABEL = { closer_look: 'Warrants a closer look', nothing_noteworthy: 'Nothing noteworthy', more_information: 'Needs more information' };

export default function QueueList({ rows, selectedId, onSelect }) {
  if (!rows) return <div className="queue-empty">Loading the queue…</div>;
  if (rows.length === 0) return <div className="queue-empty">No routed claims yet. The nightly Workflow routes claims; "Prepare a Brief" on a timeline routes one now.</div>;
  return (
    <ul className="queue-list">
      {rows.map((r) => (
        <li key={r.claim_id}>
          <button type="button" className={`queue-row${r.claim_id === selectedId ? ' queue-row--active' : ''}`} onClick={() => onSelect(r.claim_id)}>
            <div className="queue-row-head">
              <span className="queue-claim">{r.claim_id}</span>
              <span className="queue-policy">{r.policy_id}</span>
              <span className="queue-amount">{formatCurrency(Number(r.settled_amount))}</span>
            </div>
            <div className="queue-row-meta">
              <span className="tl-severity-badge" data-band={r.severity_band}>{r.severity_band}</span>
              <span>{r.coverage_line} · reported {formatEventDate(r.report_date)}</span>
            </div>
            <div className="queue-row-rule">{r.routed_by === 'rule' ? r.routing_rule : 'Requested from the timeline'}</div>
            <div className="queue-row-state">
              {r.disposition ? OUTCOME_LABEL[r.disposition.outcome] : STATE_LABEL[r.run_state] ?? r.run_state}
            </div>
          </button>
        </li>
      ))}
    </ul>
  );
}
