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

  it('stays table-only for three or more columns (the comparison contract)', () => {
    const rows = [{ label: 'with changes', rate: 0.4, n: 120 }];
    expect(autoChart(cols('label', 'rate', 'n'), rows)).toBeNull();
  });
});
