// ADR-0007's generic renderer: a table always, and an auto-chart only when
// the result shape is exactly one text column and one numeric column
// (docs/specs/06-ux-specification.md §1). Anything else — including the
// three-column cohort table and the label/rate/n comparison shape — stays
// table-only, which is also how the comparison contract (ADR-0014) reads:
// a chart would flatten the paired rate+n into one axis and lose the point.
//
// Within that two-column shape, the text column's content picks the form:
// dates make it a trend (line), anything else a ranking (bar).

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

/**
 * Returns { type: 'bar' | 'line', textColumn, numericColumn } when the
 * result qualifies for an auto chart, otherwise null.
 */
export function autoChart(columns, rows) {
  if (!columns || columns.length !== 2 || !rows || rows.length === 0) return null;
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
