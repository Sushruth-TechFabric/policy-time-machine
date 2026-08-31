import { formatNumber } from '../lib/format.js';
import './BarChart.css';

/**
 * Hand-rolled horizontal bar list — plain divs, no chart library. Only
 * rendered when the result is exactly one text column and one numeric
 * column (lib/chartRules.js). Single series, single hue (the agent indigo);
 * labels and values stay in ink, never the series color.
 */
export default function BarChart({ rows, textColumn, numericColumn }) {
  const max = Math.max(...rows.map((r) => Number(r[numericColumn]) || 0), 1);
  return (
    <div className="bar-chart" role="img" aria-label={`Bar chart of ${numericColumn} by ${textColumn}`}>
      <div className="bar-chart-title">
        {numericColumn.replaceAll('_', ' ')} by {textColumn.replaceAll('_', ' ')}
      </div>
      {rows.slice(0, 20).map((row, i) => {
        const value = Number(row[numericColumn]) || 0;
        const pct = Math.max((value / max) * 100, 0.75);
        return (
          <div
            className="bar-row"
            key={row[textColumn] ?? i}
            title={`${row[textColumn]}: ${formatNumber(value)}`}
          >
            <span className="bar-label">{row[textColumn]}</span>
            <div className="bar-track">
              <div className="bar-fill" style={{ width: `${pct}%` }} />
            </div>
            <span className="bar-value">{formatNumber(value)}</span>
          </div>
        );
      })}
      {rows.length > 20 && <div className="bar-chart-more">Top 20 of {rows.length} shown — the full set is in the table.</div>}
    </div>
  );
}
