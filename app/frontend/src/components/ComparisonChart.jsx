import { formatNumber } from '../lib/format.js';
import './ComparisonChart.css';

function humanize(name) {
  return name.replaceAll('_', ' ');
}

function MeasurePanel({ title, rows, textColumn, valueColumn, tone }) {
  const max = Math.max(...rows.map((r) => Number(r[valueColumn]) || 0), Number.EPSILON);
  return (
    <div className="cmp-panel">
      <div className="cmp-panel-title">{title}</div>
      {rows.map((row, i) => {
        const value = Number(row[valueColumn]) || 0;
        const pct = Math.max((value / max) * 100, 0.75);
        return (
          <div className="cmp-row" key={row[textColumn] ?? i} title={`${row[textColumn]}: ${formatNumber(value)}`}>
            <span className="cmp-label">{row[textColumn]}</span>
            <div className="cmp-track">
              <div className={`cmp-fill cmp-fill--${tone}`} style={{ width: `${pct}%` }} />
            </div>
            <span className="cmp-value">{formatNumber(value)}</span>
          </div>
        );
      })}
    </div>
  );
}

/**
 * The comparison contract's paired small multiples (ADR-0014): both groups,
 * shown twice — once for the measure under investigation, once for the
 * sample size behind it. Each panel has its own axis; the two are never
 * merged onto one scale. The measure carries the agent hue, n stays
 * neutral — it is context, not the finding.
 */
export default function ComparisonChart({ rows, textColumn, measureColumn, nColumn }) {
  return (
    <div
      className="comparison-chart"
      role="img"
      aria-label={`Comparison of ${measureColumn} between groups, with sample sizes`}
    >
      <MeasurePanel title={humanize(measureColumn)} rows={rows} textColumn={textColumn} valueColumn={measureColumn} tone="measure" />
      <MeasurePanel title={`${humanize(nColumn)} — group size`} rows={rows} textColumn={textColumn} valueColumn={nColumn} tone="context" />
      <p className="cmp-footnote">Independent scales — a rate is only as strong as the group size beside it.</p>
    </div>
  );
}
