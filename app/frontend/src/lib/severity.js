// ADR-0008: severity is a fixed, documented dollar-band cut — a generator
// contract, not a computed statistic. The bands are constants, so deriving
// the band client-side from a settled `amount` is exactly the same
// classification the pipeline would have made; nothing here reads as an
// improvised threshold. "High-severity" means severe or catastrophic.

export const SEVERITY_BANDS = [
  { code: 'minor', label: 'minor', min: 0, max: 2500 },
  { code: 'moderate', label: 'moderate', min: 2500, max: 10000 },
  { code: 'severe', label: 'severe', min: 10000, max: 50000 },
  { code: 'catastrophic', label: 'catastrophic', min: 50000, max: Infinity },
];

export function severityBand(amount) {
  if (amount == null || Number.isNaN(amount)) return null;
  const band = SEVERITY_BANDS.find((b) => amount >= b.min && amount < b.max);
  return band ? band.code : 'catastrophic';
}

export function isHighSeverity(amount) {
  const band = severityBand(amount);
  return band === 'severe' || band === 'catastrophic';
}
