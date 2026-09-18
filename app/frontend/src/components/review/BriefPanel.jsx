import EvidenceDrawer from '../EvidenceDrawer.jsx';
import './review.css';

// The harness owns the order and records it on the Brief (ADR-0018); this
// is only the fallback for a Brief built before the field existed.
const ORDER = ['sequence', 'relevant_changes', 'frequency', 'similar'];

function rowsToObjects(section) {
  if (section.columns && section.rows.length && Array.isArray(section.rows[0])) {
    return section.rows.map((r) => Object.fromEntries(section.columns.map((c, i) => [c, r[i]])));
  }
  return section.rows;
}

function SectionTable({ rows }) {
  if (!rows.length) return <div className="brief-empty">No rows.</div>;
  const cols = Object.keys(rows[0]);
  return (
    <div className="brief-table-wrap">
      <table className="brief-table">
        <thead><tr>{cols.map((c) => <th key={c}>{c}</th>)}</tr></thead>
        <tbody>{rows.map((r, i) => <tr key={i}>{cols.map((c) => <td key={c}>{r[c] == null ? '' : String(r[c])}</td>)}</tr>)}</tbody>
      </table>
    </div>
  );
}

function questionFor(key, section, brief) {
  if (key === 'frequency') return section.question;
  if (key === 'similar') return `Find policies with histories similar to ${brief.policy_id}.`;
  if (key === 'relevant_changes') return `What changed before the latest claim on ${brief.policy_id}?`;
  return `What changed on policy ${brief.policy_id} during the last year?`;
}

/** Four sections, each with its sentence, its rows and its evidence.
 *  There is deliberately no summary: the weighing is the Disposition. */
export default function BriefPanel({ brief, noAccess, onOpenAsInvestigation }) {
  if (noAccess) {
    return <div className="brief-no-access">You don't have access to the policy data behind this Brief. Unity Catalog governs the source; the Brief mirrors its answer.</div>;
  }
  if (!brief) return null;
  return (
    <div className="brief-panel">
      <div className="brief-head">
        <span className="brief-title">Brief for {brief.claim_id}</span>
        <span className="brief-meta">built against the dataset as of {brief.anchor_date}</span>
      </div>
      {(brief.section_order ?? ORDER).map((key) => {
        const s = brief.sections[key];
        if (!s) return null;
        const rows = rowsToObjects(s);
        return (
          <section key={key} className="brief-section">
            <div className="brief-section-head">
              <h3 className="brief-section-title">{s.title}</h3>
              <button type="button" className="brief-open" onClick={() => onOpenAsInvestigation(questionFor(key, s, brief))}>Open as investigation</button>
            </div>
            {key === 'frequency' && (
              <div className="brief-question">
                <span className="brief-question-label">{s.question_source === 'model' ? 'Question the model chose' : 'Canonical question (model proposal rejected)'}</span>
                <p>{s.question}</p>
                {s.follow_up && <p className="brief-follow-up">Follow-up: {s.follow_up}</p>}
              </div>
            )}
            {key === 'relevant_changes' && s.patterns?.length > 0 && (
              <ul className="brief-patterns">{s.patterns.map((p) => <li key={p.pattern_code}>{p.pattern_name}</li>)}</ul>
            )}
            {s.sentence ? <p className="brief-sentence">{s.sentence}</p>
              : <p className="brief-sentence brief-sentence--withheld">Sentence withheld: {s.sentence_dropped_reason ?? 'vocabulary check'}</p>}
            <SectionTable rows={rows} />
            <EvidenceDrawer rowCount={s.row_count} sql={s.sql} description={s.description ?? null} />
          </section>
        );
      })}
    </div>
  );
}
