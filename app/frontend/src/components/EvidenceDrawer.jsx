import { useState } from 'react';
import './EvidenceDrawer.css';

/**
 * Collapsed by default: "N rows · view query". Expanded: generated SQL, row
 * count, Genie's description (docs/specs/06-ux-specification.md §1). Every
 * trail node carries its own SQL/row-count/description (ADR-0011), so this
 * always reflects the currently displayed node, not a running total.
 */
export default function EvidenceDrawer({ rowCount, sql, description }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="evidence-drawer">
      <button type="button" className="evidence-toggle" onClick={() => setExpanded((v) => !v)} aria-expanded={expanded}>
        <span className="evidence-chevron">{expanded ? '▾' : '▸'}</span>
        Evidence: {rowCount} row{rowCount === 1 ? '' : 's'} · view query
      </button>
      {expanded && (
        <div className="evidence-body">
          {description && <p className="evidence-description">{description}</p>}
          <p className="evidence-row-count">{rowCount} row{rowCount === 1 ? '' : 's'} returned.</p>
          {sql ? (
            <pre className="evidence-sql">
              <code>{sql}</code>
            </pre>
          ) : (
            <p className="evidence-sql-missing">No generated SQL for this turn.</p>
          )}
        </div>
      )}
    </div>
  );
}
