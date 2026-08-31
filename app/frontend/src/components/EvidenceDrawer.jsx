import { useState } from 'react';
import { tokenizeSql } from '../lib/sqlHighlight.js';
import './EvidenceDrawer.css';

function HighlightedSql({ sql }) {
  return (
    <pre className="evidence-sql">
      <code>
        {tokenizeSql(sql).map((t, i) => (
          // eslint-disable-next-line react/no-array-index-key
          <span key={i} className={t.type === 'plain' ? undefined : `sql-${t.type}`}>
            {t.text}
          </span>
        ))}
      </code>
    </pre>
  );
}

/**
 * The evidence panel — collapsed to one line, expands to the exact SQL Genie
 * generated for this turn. Every trail node carries its own SQL/row-count/
 * description (ADR-0011), so this always reflects the displayed node.
 */
export default function EvidenceDrawer({ rowCount, sql, description }) {
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);

  async function copySql() {
    try {
      await navigator.clipboard.writeText(sql);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      /* clipboard unavailable — the SQL is still selectable */
    }
  }

  return (
    <div className="evidence-drawer">
      <button type="button" className="evidence-toggle" onClick={() => setExpanded((v) => !v)} aria-expanded={expanded}>
        <span className="evidence-chevron" aria-hidden="true">{expanded ? '▾' : '▸'}</span>
        Evidence: {rowCount} row{rowCount === 1 ? '' : 's'} · view query
      </button>
      {expanded && (
        <div className="evidence-body">
          {description && <p className="evidence-description">{description}</p>}
          <div className="evidence-sql-head">
            <span className="evidence-sql-title">Generated SQL — written by Genie, run on the SQL warehouse</span>
            {sql && (
              <button type="button" className="evidence-copy" onClick={copySql}>
                {copied ? 'Copied' : 'Copy SQL'}
              </button>
            )}
          </div>
          {sql ? (
            <HighlightedSql sql={sql} />
          ) : (
            <p className="evidence-sql-missing">No generated SQL for this turn.</p>
          )}
          <p className="evidence-row-count">{rowCount} row{rowCount === 1 ? '' : 's'} returned.</p>
        </div>
      )}
    </div>
  );
}
