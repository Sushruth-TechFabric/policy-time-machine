// ADR-0007's generic renderer: a table always, and an auto-chart only when
// the result shape is exactly one text column and one numeric column
// (docs/specs/06-ux-specification.md §1). Anything else — including the
// three-column cohort table and the label/rate/n comparison shape — stays
// table-only, which is also how the comparison contract (ADR-0014) reads:
// a chart would flatten the paired rate+n into one axis and lose the point.

function columnIsNumeric(rows, name) {
  return rows.length > 0 && rows.every((row) => row[name] == null || typeof row[name] === 'number');
}

/**
 * Returns { textColumn, numericColumn } when the result qualifies for the
 * auto bar chart, otherwise null.
 */
export function autoChartColumns(columns, rows) {
  if (!columns || columns.length !== 2 || !rows || rows.length === 0) return null;
  const [a, b] = columns.map((c) => c.name);
  const aNumeric = columnIsNumeric(rows, a);
  const bNumeric = columnIsNumeric(rows, b);
  if (aNumeric && !bNumeric) return { textColumn: b, numericColumn: a };
  if (bNumeric && !aNumeric) return { textColumn: a, numericColumn: b };
  return null;
}
