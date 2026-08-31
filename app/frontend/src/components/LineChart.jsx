import { formatNumber } from '../lib/format.js';
import './LineChart.css';

const W = 640;
const H = 200;
const PAD = { top: 14, right: 16, bottom: 26, left: 48 };

/**
 * Hand-rolled SVG trend line for date + numeric result shapes. Single
 * series, single hue; every point carries a native tooltip. Points are
 * plotted in date order regardless of how the query sorted them.
 */
export default function LineChart({ rows, textColumn, numericColumn }) {
  const points = rows
    .map((r) => ({ label: r[textColumn], value: Number(r[numericColumn]) || 0 }))
    .sort((a, b) => (a.label < b.label ? -1 : a.label > b.label ? 1 : 0));

  const max = Math.max(...points.map((p) => p.value), 1);
  const innerW = W - PAD.left - PAD.right;
  const innerH = H - PAD.top - PAD.bottom;
  const x = (i) => PAD.left + (points.length === 1 ? innerW / 2 : (i / (points.length - 1)) * innerW);
  const y = (v) => PAD.top + innerH - (v / max) * innerH;

  const path = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${x(i).toFixed(1)},${y(p.value).toFixed(1)}`).join(' ');
  const area = `${path} L${x(points.length - 1).toFixed(1)},${(PAD.top + innerH).toFixed(1)} L${x(0).toFixed(1)},${(PAD.top + innerH).toFixed(1)} Z`;

  const mid = Math.round(points.length / 2) - 1;
  const xTicks = points.length > 2 ? [0, mid, points.length - 1] : points.map((_, i) => i);

  return (
    <div className="line-chart" role="img" aria-label={`Trend of ${numericColumn} by ${textColumn}`}>
      <div className="line-chart-title">
        {numericColumn.replaceAll('_', ' ')} over {textColumn.replaceAll('_', ' ')}
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="line-chart-svg" preserveAspectRatio="none">
        {[0, 0.5, 1].map((t) => (
          <g key={t}>
            <line
              x1={PAD.left}
              x2={W - PAD.right}
              y1={y(max * t)}
              y2={y(max * t)}
              className="lc-grid"
            />
            <text x={PAD.left - 8} y={y(max * t) + 3.5} className="lc-axis-label" textAnchor="end">
              {formatNumber(Math.round(max * t))}
            </text>
          </g>
        ))}
        <path d={area} className="lc-area" />
        <path d={path} className="lc-line" />
        {points.map((p, i) => (
          <circle key={p.label ?? i} cx={x(i)} cy={y(p.value)} r="4" className="lc-dot">
            <title>{`${p.label}: ${formatNumber(p.value)}`}</title>
          </circle>
        ))}
        {xTicks.map((i) => (
          <text key={i} x={x(i)} y={H - 8} className="lc-axis-label" textAnchor="middle">
            {points[i].label}
          </text>
        ))}
      </svg>
    </div>
  );
}
