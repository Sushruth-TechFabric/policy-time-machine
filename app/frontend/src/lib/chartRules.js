// ADR-0007's generic renderer: a table always, plus an auto-chart for two
// recognised shapes (docs/specs/06-ux-specification.md §1):
//
// - one text + one numeric column: a ranking (bar), or a trend (line) when
//   the text column holds dates;
// - the label/rate/n comparison shape (ADR-0014: both groups, each with its
//   rate and sample size): paired small multiples, one mini-chart per
//   measure with its own axis — never one combined axis, which would
//   flatten the paired rate+n and lose the point.
//
// Anything else stays table-only.

const DATE_PATTERN = /^\d{4}-\d{2}(-\d{2})?([T ].*)?$/;

function columnIsNumeric(rows, name) {
  return rows.length > 0 && rows.every((row) => row[name] == null || typeof row[name] === 'number');
}

function columnIsDate(rows, name) {
  return (
    rows.length >= 3 &&
    rows.every((row) => typeof row[name] === 'string' && DATE_PATTERN.test(row[name]))
  );
}

// Column names that mean "sample size" in the comparison contract's
// label/rate/n shape. The measure is whichever numeric column isn't this.
const N_COLUMN_PATTERN = /^n$|(^|_)(n|count|size|policies)($|_)/i;

function detectComparison(columns, rows) {
  if (columns.length !== 3 || rows.length < 2 || rows.length > 4) return null;
  const names = columns.map((c) => c.name);
  const numeric = names.filter((name) => columnIsNumeric(rows, name));
  const text = names.filter((name) => !numeric.includes(name));
  if (numeric.length !== 2 || text.length !== 1) return null;
  // Measure names commonly end in _count/_size too (claim_count), so prefer
  // an exact whole-name match, then a unique token match; when both numerics
  // match ambiguously, fall back to position — Genie's SELECT puts n last.
  const exact = numeric.find((name) => /^(n|count|size|policies|sample_size)$/i.test(name));
  const tokenMatches = numeric.filter((name) => N_COLUMN_PATTERN.test(name));
  const nColumn = exact ?? (tokenMatches.length === 1 ? tokenMatches[0] : numeric[1]);
  const measureColumn = numeric.find((name) => name !== nColumn);
  return { type: 'comparison', textColumn: text[0], measureColumn, nColumn };
}

/**
 * Returns the qualifying auto-chart spec, otherwise null:
 * - { type: 'bar' | 'line', textColumn, numericColumn }
 * - { type: 'comparison', textColumn, measureColumn, nColumn }
 */
export function autoChart(columns, rows) {
  if (!columns || !rows || rows.length === 0) return null;
  if (columns.length === 3) return detectComparison(columns, rows);
  if (columns.length !== 2) return null;
  const [a, b] = columns.map((c) => c.name);
  const aNumeric = columnIsNumeric(rows, a);
  const bNumeric = columnIsNumeric(rows, b);
  let textColumn;
  let numericColumn;
  if (aNumeric && !bNumeric) {
    textColumn = b;
    numericColumn = a;
  } else if (bNumeric && !aNumeric) {
    textColumn = a;
    numericColumn = b;
  } else {
    return null;
  }
  const type = columnIsDate(rows, textColumn) ? 'line' : 'bar';
  return { type, textColumn, numericColumn };
}

/** Back-compat name used by earlier callers/tests: bar-qualifying shapes only. */
export function autoChartColumns(columns, rows) {
  const chart = autoChart(columns, rows);
  return chart && chart.type === 'bar' ? { textColumn: chart.textColumn, numericColumn: chart.numericColumn } : null;
}
