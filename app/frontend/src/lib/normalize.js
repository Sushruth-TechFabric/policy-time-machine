// The backend returns Genie rows exactly as the warehouse hands them over:
// positional arrays of strings (`data_array`). The renderer, the chart rules
// and the policy-id link detection all work on objects keyed by column name
// with real numbers where the column is numeric. This is the single place
// that conversion happens — everything downstream can assume object rows.

const NUMERIC_PATTERN = /^-?\d+(\.\d+)?$/;

function columnLooksNumeric(rows, index) {
  let sawValue = false;
  for (const row of rows) {
    const v = row[index];
    if (v == null || v === '') continue;
    if (typeof v === 'number') {
      sawValue = true;
      continue;
    }
    if (typeof v !== 'string' || !NUMERIC_PATTERN.test(v)) return false;
    sawValue = true;
  }
  return sawValue;
}

/**
 * Returns a copy of a Genie result whose rows are objects keyed by column
 * name, with numeric-looking columns coerced to numbers. Idempotent: rows
 * that are already objects (mock mode, the similarity fast path) pass
 * through untouched apart from numeric coercion.
 */
export function normalizeGenieResult(genie) {
  if (!genie || !Array.isArray(genie.rows) || genie.rows.length === 0) return genie;
  const columns = genie.columns ?? [];
  const names = columns.map((c) => c.name);

  const arrayRows = genie.rows.map((row) => (Array.isArray(row) ? row : names.map((n) => row[n])));

  const numericByIndex = names.map((_, i) => columnLooksNumeric(arrayRows, i));

  const rows = arrayRows.map((row) => {
    const obj = {};
    names.forEach((name, i) => {
      const v = row[i];
      obj[name] = numericByIndex[i] && typeof v === 'string' && v !== '' ? Number(v) : v;
    });
    return obj;
  });

  return { ...genie, rows };
}
