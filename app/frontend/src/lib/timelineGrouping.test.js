import { describe, expect, it } from 'vitest';
import { groupTimelineEvents } from './timelineGrouping.js';

function event(overrides) {
  return {
    timeline_event_id: 'evt',
    event_date: '2026-01-01',
    event_type: 'policy_change',
    event_category: 'coverage',
    endorsement_id: null,
    coverage_line: null,
    old_value: null,
    new_value: null,
    display_label: 'Changed',
    amount: null,
    is_material: true,
    source_id: 'src',
    ...overrides,
  };
}

describe('groupTimelineEvents', () => {
  it('collapses changes sharing an endorsement_id into one card with N deltas', () => {
    const events = [
      event({ timeline_event_id: 'e1', event_date: '2026-01-04', event_category: 'address', endorsement_id: 'END-1', display_label: 'Address changed' }),
      event({ timeline_event_id: 'e2', event_date: '2026-01-04', event_category: 'coverage', endorsement_id: 'END-1', display_label: 'Collision limit increased' }),
    ];

    const cards = groupTimelineEvents(events);

    expect(cards).toHaveLength(1);
    expect(cards[0].kind).toBe('change');
    expect(cards[0].deltas).toHaveLength(2);
    expect(cards[0].deltas.map((d) => d.event_category)).toEqual(['address', 'coverage']);
  });

  it('keeps changes without a shared endorsement_id as separate cards', () => {
    const events = [
      event({ timeline_event_id: 'e1', event_date: '2026-01-04', endorsement_id: 'END-1' }),
      event({ timeline_event_id: 'e2', event_date: '2026-01-20', endorsement_id: 'END-2' }),
    ];

    const cards = groupTimelineEvents(events);

    expect(cards).toHaveLength(2);
  });

  it('never groups a claim into a change card, even if it shared an endorsement_id', () => {
    const events = [
      event({ timeline_event_id: 'e1', event_date: '2026-01-04', endorsement_id: 'SHARED' }),
      event({
        timeline_event_id: 'e2',
        event_date: '2026-01-04',
        event_type: 'claim_filed',
        event_category: null,
        endorsement_id: 'SHARED',
        amount: 24700,
        display_label: 'Claim filed',
      }),
    ];

    const cards = groupTimelineEvents(events);

    expect(cards).toHaveLength(2);
    expect(cards.map((c) => c.kind).sort()).toEqual(['change', 'claim']);
  });

  it('orders cards chronologically by the earliest date in the group', () => {
    const events = [
      event({ timeline_event_id: 'e3', event_date: '2026-02-02', event_type: 'claim_filed', event_category: null, amount: 24700 }),
      event({ timeline_event_id: 'e1', event_date: '2026-01-04', endorsement_id: 'END-1' }),
      event({ timeline_event_id: 'e2', event_date: '2026-01-27', event_category: 'vehicle' }),
    ];

    const cards = groupTimelineEvents(events);

    expect(cards.map((c) => c.date)).toEqual(['2026-01-04', '2026-01-27', '2026-02-02']);
  });

  it('matches the P-18492 fixture shape: 3 cards for 4 change/claim events grouped by endorsement', () => {
    const events = [
      event({ timeline_event_id: 'e1', event_date: '2026-01-04', event_category: 'address', endorsement_id: 'END-7731', display_label: 'Address changed' }),
      event({ timeline_event_id: 'e2', event_date: '2026-01-04', event_category: 'coverage', endorsement_id: 'END-7731', coverage_line: 'COLL', old_value: '100,000', new_value: '300,000', display_label: 'Collision limit increased' }),
      event({ timeline_event_id: 'e3', event_date: '2026-01-27', event_category: 'vehicle', endorsement_id: 'END-7745', display_label: 'Vehicle changed' }),
      event({ timeline_event_id: 'e4', event_date: '2026-02-02', event_type: 'claim_filed', event_category: null, endorsement_id: null, coverage_line: 'COLL', amount: 24700, display_label: 'Claim filed' }),
    ];

    const cards = groupTimelineEvents(events);

    expect(cards).toHaveLength(3);
    expect(cards[0].deltas).toHaveLength(2); // address + COLL increase, one endorsement
    expect(cards[1].deltas).toHaveLength(1); // vehicle change
    expect(cards[2].kind).toBe('claim');
    expect(cards[2].deltas[0].amount).toBe(24700);
  });
});
