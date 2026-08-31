import { groupTimelineEvents } from '../lib/timelineGrouping.js';
import { severityBand } from '../lib/severity.js';
import { formatCurrency, formatEventDate, formatFullDate } from '../lib/format.js';
import './Timeline.css';

function patternsForCard(card, patterns) {
  if (!patterns || patterns.length === 0) return [];
  const dates = new Set(card.deltas.map((d) => d.event_date));
  return patterns.filter((p) => dates.has(p.matched_on_date));
}

function DeltaLine({ event }) {
  return (
    <div className="delta">
      <div className="delta-label">
        {event.display_label}
        {event.coverage_line ? <span className="delta-line"> · {event.coverage_line}</span> : null}
      </div>
      {(event.old_value != null || event.new_value != null) && (
        <div className="delta-values">
          <span>{event.old_value ?? '—'}</span>
          <span className="delta-arrow">→</span>
          <span>{event.new_value ?? '—'}</span>
        </div>
      )}
    </div>
  );
}

function ClaimCard({ card, patterns }) {
  const event = card.deltas[0];
  const band = severityBand(event.amount);
  const matched = patternsForCard(card, patterns);
  return (
    <li className="tl-row tl-row--claim">
      <span className="tl-marker tl-marker--claim" aria-hidden="true" />
      <div className="tl-card tl-card--claim">
        <div className="tl-card-head">
          <span className="tl-date" title={formatFullDate(card.date)}>{formatEventDate(card.date)}</span>
          <span className="tl-claim-tag">Claim</span>
          {matched.map((p) => (
            <span key={p.pattern_code} className="tl-pattern-marker" title={`${p.pattern_name} — ${p.evidence_summary}`}>
              ●
            </span>
          ))}
        </div>
        <div className="tl-claim-amount">{formatCurrency(event.amount)}</div>
        {band && <div className="tl-severity-badge" data-band={band}>{band}</div>}
        {event.coverage_line && <div className="delta-line">{event.coverage_line} line</div>}
        {event.display_label && <div className="tl-claim-note">{event.display_label}</div>}
      </div>
    </li>
  );
}

function InfoCard({ card }) {
  const event = card.deltas[0];
  return (
    <li className="tl-row tl-row--info">
      <span className="tl-marker tl-marker--info" aria-hidden="true" />
      <div className="tl-card tl-card--info">
        <span className="tl-date" title={formatFullDate(card.date)}>{formatEventDate(card.date)}</span>
        <span className="tl-info-label">{event.display_label}</span>
      </div>
    </li>
  );
}

function ChangeCard({ card, patterns }) {
  const matched = patternsForCard(card, patterns);
  return (
    <li className="tl-row">
      <span className="tl-marker" aria-hidden="true" />
      <div className="tl-card">
        <div className="tl-card-head">
          <span className="tl-date" title={formatFullDate(card.date)}>{formatEventDate(card.date)}</span>
          {card.deltas.length > 1 && <span className="tl-endorsement-tag">{card.deltas.length} changes · one endorsement</span>}
          {matched.map((p) => (
            <span key={p.pattern_code} className="tl-pattern-marker" title={`${p.pattern_name} — ${p.evidence_summary}`}>
              ●
            </span>
          ))}
        </div>
        {card.deltas.map((event, i) => (
          <DeltaLine key={event.timeline_event_id ?? `${card.id}-${i}`} event={event} />
        ))}
      </div>
    </li>
  );
}

function TimelineCard({ card, patterns }) {
  if (card.kind === 'claim') return <ClaimCard card={card} patterns={patterns} />;
  if (card.kind === 'renewal' || card.kind === 'policy_created') return <InfoCard card={card} />;
  return <ChangeCard card={card} patterns={patterns} />;
}

/**
 * Region 2 — the signature visual. Vertical spine, dated cards, changes
 * sharing an endorsement collapsed to one card with N deltas, claims
 * carrying the screen's only strong accent, pattern-matched cards carrying
 * a named-tooltip marker. Renders from its own fetch and never shows a
 * spinner tied to Genie (docs/specs/06-ux-specification.md §2, §3).
 */
export default function Timeline({ policyId, data, onFindSimilar, findSimilarBusy }) {
  if (!policyId) return null;

  return (
    <div className="timeline-panel">
      <div className="timeline-header">
        <span className="timeline-title">Timeline</span>
        <span className="timeline-policy-id">{policyId}</span>
      </div>

      {!data && <div className="timeline-loading">Loading {policyId}'s history…</div>}

      {data && data.found === false && (
        <div className="timeline-not-found">
          No policy {policyId} found.
          <div className="timeline-not-found-sub">Check the identifier and try again — an id is five digits after "P-".</div>
        </div>
      )}

      {data && data.found === true && data.events.length === 0 && (
        <div className="timeline-not-found">No recorded events for {policyId}.</div>
      )}

      {data && data.found === true && data.events.length > 0 && (
        <>
          <ul className="tl-spine">
            {groupTimelineEvents(data.events).map((card) => (
              <TimelineCard key={card.id} card={card} patterns={data.patterns} />
            ))}
          </ul>
          <button
            type="button"
            className="find-similar-btn"
            onClick={() => onFindSimilar(policyId)}
            disabled={findSimilarBusy}
            title={`Read from the precomputed similarity table for ${policyId}`}
          >
            Find similar policies →
          </button>
        </>
      )}
    </div>
  );
}
