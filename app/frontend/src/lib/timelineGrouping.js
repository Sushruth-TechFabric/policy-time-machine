// The Timeline's one piece of real logic: changes committed in the same
// endorsement render as a single card carrying N deltas (docs/specs/06 §1,
// ADR-0003's payoff for carrying `endorsement_id`). Claims are never grouped
// — they are always their own card, visually distinct, carrying the
// screen's one strong accent.

const CLAIM_EVENT_TYPES = new Set(['claim_filed', 'claim_payment']);

function cardKind(eventType) {
  if (CLAIM_EVENT_TYPES.has(eventType)) return 'claim';
  if (eventType === 'renewal') return 'renewal';
  if (eventType === 'status_change') return 'status_change';
  if (eventType === 'policy_created') return 'policy_created';
  return 'change';
}

/**
 * Groups a policy's timeline_event rows into display cards.
 *
 * - Events sharing a non-empty `endorsement_id` collapse into one card with
 *   `deltas` = each event as one line-item delta.
 * - Claims (`claim_filed`, `claim_payment`) are never grouped, regardless of
 *   endorsement_id, and always form their own card.
 * - Card order follows the earliest `event_date` in the group; ties keep
 *   the input order (the API is expected to return date-ordered rows).
 */
export function groupTimelineEvents(events) {
  if (!events || events.length === 0) return [];

  const cards = [];
  const groupIndexByEndorsement = new Map();

  events.forEach((event, i) => {
    const kind = cardKind(event.event_type);
    const endorsementId = event.endorsement_id;
    const groupable = kind === 'change' || kind === 'status_change';

    if (groupable && endorsementId && groupIndexByEndorsement.has(endorsementId)) {
      const card = cards[groupIndexByEndorsement.get(endorsementId)];
      card.deltas.push(event);
      if (event.event_date < card.date) card.date = event.event_date;
      return;
    }

    const card = {
      id: endorsementId && groupable ? `endorsement:${endorsementId}` : `event:${event.timeline_event_id ?? i}`,
      kind,
      date: event.event_date,
      endorsementId: groupable ? endorsementId ?? null : null,
      deltas: [event],
    };
    if (groupable && endorsementId) {
      groupIndexByEndorsement.set(endorsementId, cards.length);
    }
    cards.push(card);
  });

  cards.sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));
  return cards;
}
