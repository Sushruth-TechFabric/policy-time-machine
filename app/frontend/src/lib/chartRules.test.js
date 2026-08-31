import { describe, expect, it } from 'vitest';
import { autoChart } from './chartRules.js';

const cols = (...names) => names.map((name) => ({ name }));

describe('autoChart', () => {
  it('picks a bar chart for one text + one numeric column', () => {
    const rows = [
      { change_category: 'coverage', n: 132 },
      { change_category: 'deductible', n: 98 },
    ];
    expect(autoChart(cols('change_category', 'n'), rows)).toEqual({
      type: 'bar',
      textColumn: 'change_category',
      numericColumn: 'n',
    });
  });

  it('picks a line chart when the text column holds dates', () => {
    const rows = [
      { month: '2026-05', n: 4 },
      { month: '2026-06', n: 9 },
      { month: '2026-07', n: 6 },
    ];
    expect(autoChart(cols('month', 'n'), rows)).toEqual({
      type: 'line',
      textColumn: 'month',
      numericColumn: 'n',
    });
  });

  it('needs at least three points before calling something a trend', () => {
    const rows = [
      { month: '2026-05', n: 4 },
      { month: '2026-06', n: 9 },
    ];
    expect(autoChart(cols('month', 'n'), rows)?.type).toBe('bar');
  });

  it('recognises the label/rate/n comparison shape as paired small multiples', () => {
    const rows = [
      { comparison_group: 'recent material change', rate_pct: 8.5, n: 1240 },
      { comparison_group: 'no recent material change', rate_pct: 5.8, n: 6180 },
    ];
    expect(autoChart(cols('comparison_group', 'rate_pct', 'n'), rows)).toEqual({
      type: 'comparison',
      textColumn: 'comparison_group',
      measureColumn: 'rate_pct',
      nColumn: 'n',
    });
  });

  it('finds the sample-size column by name, not by position', () => {
    const rows = [
      { group: 'a', policy_count: 120, avg_claims: 1.4 },
      { group: 'b', policy_count: 300, avg_claims: 0.9 },
    ];
    const chart = autoChart(cols('group', 'policy_count', 'avg_claims'), rows);
    expect(chart.nColumn).toBe('policy_count');
    expect(chart.measureColumn).toBe('avg_claims');
  });

  it('a lone group (one row) or a wide cohort stays table-only', () => {
    expect(autoChart(cols('label', 'rate', 'n'), [{ label: 'with changes', rate: 0.4, n: 120 }])).toBeNull();
    const wide = Array.from({ length: 8 }, (_, i) => ({ label: `g${i}`, rate: i, n: i }));
    expect(autoChart(cols('label', 'rate', 'n'), wide)).toBeNull();
    expect(autoChart(cols('a', 'b', 'c', 'd'), [{ a: 1, b: 2, c: 3, d: 4 }])).toBeNull();
  });
});
