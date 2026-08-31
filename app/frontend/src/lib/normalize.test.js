import { describe, expect, it } from 'vitest';
import { normalizeGenieResult } from './normalize.js';

const columns = [{ name: 'policy_id' }, { name: 'change_count' }, { name: 'change_date' }];

describe('normalizeGenieResult', () => {
  it('converts positional array rows (the backend contract) into objects keyed by column name', () => {
    const genie = {
      status: 'ok',
      columns,
      rows: [['P-10155', '4', '2025-06-01']],
    };
    const out = normalizeGenieResult(genie);
    expect(out.rows[0].policy_id).toBe('P-10155');
    expect(out.rows[0].change_date).toBe('2025-06-01');
  });

  it('coerces columns whose every value is numeric-looking to real numbers', () => {
    const genie = {
      status: 'ok',
      columns,
      rows: [
        ['P-10155', '4', '2025-06-01'],
        ['P-20988', '12.5', '2025-07-09'],
      ],
    };
    const out = normalizeGenieResult(genie);
    expect(out.rows.map((r) => r.change_count)).toEqual([4, 12.5]);
  });

  it('never coerces ids or dates', () => {
    const genie = { status: 'ok', columns, rows: [['P-10155', '4', '2025-06-01']] };
    const out = normalizeGenieResult(genie);
    expect(typeof out.rows[0].policy_id).toBe('string');
    expect(typeof out.rows[0].change_date).toBe('string');
  });

  it('passes object rows through untouched apart from numeric coercion (idempotent)', () => {
    const genie = {
      status: 'ok',
      columns,
      rows: [{ policy_id: 'P-10155', change_count: 4, change_date: '2025-06-01' }],
    };
    const out = normalizeGenieResult(genie);
    expect(out.rows[0]).toEqual({ policy_id: 'P-10155', change_count: 4, change_date: '2025-06-01' });
  });

  it('leaves empty and errored results alone', () => {
    const empty = { status: 'empty', columns: [], rows: [] };
    expect(normalizeGenieResult(empty)).toBe(empty);
    expect(normalizeGenieResult(null)).toBe(null);
  });
});
