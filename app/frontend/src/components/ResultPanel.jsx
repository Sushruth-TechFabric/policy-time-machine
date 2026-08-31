import { POLICY_ID_PATTERN } from '../lib/policyId.js';
import { autoChartColumns } from '../lib/chartRules.js';
import { formatNumber } from '../lib/format.js';
import BarChart from './BarChart.jsx';
import EvidenceDrawer from './EvidenceDrawer.jsx';
import './ResultPanel.css';

function isPolicyIdValue(value) {
  return typeof value === 'string' && new RegExp(POLICY_ID_PATTERN.source, 'i').test(value) && value.length <= 8;
}

function Cell({ value, onPolicyClick }) {
  if (isPolicyIdValue(value)) {
    return (
      <button type="button" className="cell-policy-link" onClick={() => onPolicyClick(value)} title={`Open ${value}'s timeline`}>
        {value}
      </button>
    );
  }
  if (typeof value === 'number') return <span className="cell-numeric">{formatNumber(value)}</span>;
  return <span>{value ?? ''}</span>;
}

function ResultTable({ columns, rows, onPolicyClick }) {
  return (
    <div className="result-table-wrap">
      <table className="result-table">
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.name}>{c.name}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            // eslint-disable-next-line react/no-array-index-key
            <tr key={i}>
              {columns.map((c) => (
                <td key={c.name}>
                  <Cell value={row[c.name]} onPolicyClick={onPolicyClick} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Skeleton() {
  return (
    <div className="result-skeleton" aria-busy="true" aria-label="Loading result">
      <div className="skel-line skel-line--title" />
      <div className="skel-line" />
      <div className="skel-line" />
      <div className="skel-line" style={{ width: '60%' }} />
    </div>
  );
}

/**
 * Region 3 — table plus auto-chart, then the evidence drawer
 * (docs/specs/06-ux-specification.md §1). Generic rendering only: no
 * bespoke renderer per result shape (ADR-0007). Never an error-shaped
 * layout for genie failures — those are stated plainly, in this same panel.
 */
export default function ResultPanel({ node, loading, onPolicyClick }) {
  if (loading) {
    return (
      <div className="result-panel">
        <Skeleton />
      </div>
    );
  }

  if (!node) {
    return <div className="result-panel result-panel--empty" />;
  }

  const { genie, question } = node;

  if (genie.status === 'error') {
    return (
      <div className="result-panel">
        <div className="result-message result-message--error">
          <p className="result-message-title">Genie could not answer this one.</p>
          <p>{genie.error || 'The request failed.'}</p>
        </div>
      </div>
    );
  }

  if (genie.status === 'clarification') {
    return (
      <div className="result-panel">
        <div className="result-message result-message--clarification">
          <p className="result-message-title">Genie needs one more detail.</p>
          <p>{genie.description}</p>
        </div>
      </div>
    );
  }

  if (genie.status === 'empty' || !genie.rows || genie.rows.length === 0) {
    return (
      <div className="result-panel">
        <div className="result-message">
          <p className="result-message-title">Asked: "{question}"</p>
          <p>No matching rows.</p>
        </div>
      </div>
    );
  }

  const chart = autoChartColumns(genie.columns, genie.rows);
  const rowCount = genie.rows.length;

  return (
    <div className="result-panel">
      <div className="result-header">
        <span className="result-row-count">{rowCount} row{rowCount === 1 ? '' : 's'}</span>
      </div>
      {chart && <BarChart rows={genie.rows} textColumn={chart.textColumn} numericColumn={chart.numericColumn} />}
      <ResultTable columns={genie.columns} rows={genie.rows} onPolicyClick={onPolicyClick} />
      <EvidenceDrawer rowCount={rowCount} sql={genie.generated_sql} description={genie.description} />
    </div>
  );
}
