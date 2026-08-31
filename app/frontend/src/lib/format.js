export function formatCurrency(amount) {
  if (amount == null || Number.isNaN(amount)) return '';
  return `$${Math.round(amount).toLocaleString('en-US')}`;
}

export function formatNumber(value) {
  if (value == null || Number.isNaN(value)) return '';
  return Number(value).toLocaleString('en-US');
}

// Absolute calendar-date rendering, e.g. "Jan 04". The demo *script* is
// written in relative language (ADR-0006's moving anchor), but the on-screen
// dates themselves are ordinary calendar dates — the ASCII mock in
// docs/specs/06-ux-specification.md §1 renders them this way.
export function formatEventDate(isoDate) {
  if (!isoDate) return '';
  const d = new Date(`${isoDate}T00:00:00`);
  if (Number.isNaN(d.getTime())) return isoDate;
  return d.toLocaleDateString('en-US', { month: 'short', day: '2-digit' });
}

export function formatFullDate(isoDate) {
  if (!isoDate) return '';
  const d = new Date(`${isoDate}T00:00:00`);
  if (Number.isNaN(d.getTime())) return isoDate;
  return d.toLocaleDateString('en-US', { month: 'short', day: '2-digit', year: 'numeric' });
}

/** True when a Genie result column is a numeric-looking column. */
export function isNumericColumn(rows, columnName) {
  if (!rows || rows.length === 0) return false;
  return rows.every((row) => {
    const v = row[columnName];
    return v == null || typeof v === 'number';
  });
}
