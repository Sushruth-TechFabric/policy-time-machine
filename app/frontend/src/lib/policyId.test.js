import { describe, expect, it } from 'vitest';
import { detectPolicyIds, timelineIdFor } from './policyId.js';

describe('detectPolicyIds', () => {
  it('matches P- plus five digits, case-insensitively', () => {
    expect(detectPolicyIds('What changed on p-18492 last year?')).toEqual(['P-18492']);
  });

  it('returns distinct ids in first-seen order', () => {
    expect(detectPolicyIds('Compare P-18492 and P-20114, then P-18492 again')).toEqual(['P-18492', 'P-20114']);
  });

  it('does not match a policy id embedded in a longer token', () => {
    expect(detectPolicyIds('CLAIM-P-184920 is unrelated')).toEqual([]);
  });

  it('returns an empty array when no id is present', () => {
    expect(detectPolicyIds('Which material changes happen most frequently?')).toEqual([]);
  });
});

describe('timelineIdFor', () => {
  it('routes on exactly one id', () => {
    expect(timelineIdFor(['P-18492'])).toBe('P-18492');
  });

  it('opens nothing for zero ids', () => {
    expect(timelineIdFor([])).toBeNull();
  });

  it('opens nothing for several ids (ADR-0007: several ids suppress the timeline)', () => {
    expect(timelineIdFor(['P-18492', 'P-20114'])).toBeNull();
  });
});
