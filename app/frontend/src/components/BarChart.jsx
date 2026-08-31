import { formatNumber } from '../lib/format.js';
import './BarChart.css';

/**
 * Hand-rolled horizontal bar chart — plain divs, no chart library. Only
 * rendered when the result is exactly one text column and one numeric
 * column (lib/chartRules.js). Inherits the app's palette: no rainbow
 * per-category colours (docs/specs/06-ux-specification.md §4).
 */
export default function BarChart({ rows, textColumn, numericColumn }) {
  const max = Math.max(...rows.map((r) => Number(r[numericColumn]) || 0), 1);
  return (
    <div className="bar-chart" role="img" aria-label={`Bar chart of ${numericColumn} by ${textColumn}`}>
      {rows.map((row, i) => {
        const value = Number(row[numericColumn]) || 0;
        const pct = (value / max) * 100;
        return (
          <div className="bar-row" key={row[textColumn] ?? i}>
            <span className="bar-label">{row[textColumn]}</span>
            <div className="bar-track">
              <div className="bar-fill" style={{ width: `${pct}%` }} />
            </div>
            <span className="bar-value">{formatNumber(value)}</span>
          </div>
        );
      })}
    </div>
  );
}
