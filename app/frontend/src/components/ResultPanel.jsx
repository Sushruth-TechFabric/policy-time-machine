import { POLICY_ID_PATTERN } from '../lib/policyId.js';
import { autoChartColumns } from '../lib/chartRules.js';
import { formatNumber } from '../lib/format.js';
import BarChart from './BarChart.jsx';
import EvidenceDrawer from './EvidenceDrawer.jsx';
import AgentWorking from './AgentWorking.jsx';
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
              <th key={c.name}>{c.name.replaceAll('_', ' ')}</th>
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

function distinctPolicyCount(columns, rows) {
  const col = columns.find((c) => /policy_id/i.test(c.name));
  if (!col) return null;
  return new Set(rows.map((r) => r[col.name])).size;
}

function AnswerMeta({ node, rowCount, policyCount }) {
  return (
    <div className="answer-meta">
      <span className="meta-pill result-row-count">{rowCount} row{rowCount === 1 ? '' : 's'}</span>
      {policyCount != null && (
        <span className="meta-pill">{policyCount} polic{policyCount === 1 ? 'y' : 'ies'}</span>
      )}
      {node.genie.generated_sql && <span className="meta-pill meta-pill--agent">SQL generated</span>}
      {node.elapsedMs != null && (
        <span className="meta-pill meta-pill--mono">{(node.elapsedMs / 1000).toFixed(1)}s</span>
      )}
    </div>
  );
}

function QuestionHeader({ question }) {
  return (
    <div className="answer-question">
      <span className="answer-question-label">You asked</span>
      <p className="answer-question-text">{question}</p>
    </div>
  );
}

/**
 * Region 3 — the answer card. One rail, top to bottom: the question, Genie's
 * reading of it, the visual, the rows, and the generated SQL. Generic
 * rendering only — no bespoke renderer per result shape (ADR-0007). Genie
 * failures are stated plainly in this same panel, never an error screen.
 */
export default function ResultPanel({ node, loading, pendingQuestion, onPolicyClick }) {
  if (loading) {
    return (
      <div className="result-panel">
        <AgentWorking question={pendingQuestion ?? 'Working on your question'} />
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
        <div className="answer-card">
          <QuestionHeader question={question} />
          <div className="result-message result-message--error">
            <p className="result-message-title">Genie could not answer this one.</p>
            <p>{genie.error || 'The request failed.'}</p>
            <p className="result-message-hint">Rephrase the question or start from one of the suggestions below.</p>
          </div>
        </div>
      </div>
    );
  }

  if (genie.status === 'clarification') {
    return (
      <div className="result-panel">
        <div className="answer-card">
          <QuestionHeader question={question} />
          <div className="result-message result-message--clarification">
            <p className="result-message-title">Genie needs one more detail.</p>
            <p>{genie.description}</p>
            <p className="result-message-hint">Answer in the ask bar — the conversation keeps its context.</p>
          </div>
        </div>
      </div>
    );
  }

  if (genie.status === 'empty' || !genie.rows || genie.rows.length === 0) {
    return (
      <div className="result-panel">
        <div className="answer-card">
          <QuestionHeader question={question} />
          <div className="result-message">
            <p className="result-message-title">No matching rows.</p>
            <p>The query ran, but nothing in the data fits. Widen the window or drop a condition.</p>
          </div>
          {genie.generated_sql && (
            <EvidenceDrawer rowCount={0} sql={genie.generated_sql} description={genie.description} />
          )}
        </div>
      </div>
    );
  }

  const chart = autoChartColumns(genie.columns, genie.rows);
  const rowCount = genie.rows.length;
  const policyCount = distinctPolicyCount(genie.columns, genie.rows);

  return (
    <div className="result-panel">
      <div className="answer-card">
        <QuestionHeader question={question} />
        {genie.description && (
          <div className="answer-interpretation">
            <span className="interpretation-label">How Genie read it</span>
            <p className="interpretation-text">{genie.description}</p>
          </div>
        )}
        <AnswerMeta node={node} rowCount={rowCount} policyCount={policyCount} />
        {chart && <BarChart rows={genie.rows} textColumn={chart.textColumn} numericColumn={chart.numericColumn} />}
        <ResultTable columns={genie.columns} rows={genie.rows} onPolicyClick={onPolicyClick} />
        {/* description is omitted here — it already renders above as "How Genie read it" */}
        <EvidenceDrawer rowCount={rowCount} sql={genie.generated_sql} description={null} />
      </div>
    </div>
  );
}
