// ADR-0007: the app's only NL "understanding" is a regex over the question
// text. Policy ids are `P-` followed by five digits, matched case-insensitively
// on word boundaries. This file is the single source of truth for that regex
// so detection stays identical wherever it is used (input bar, chip text,
// table cells).

export const POLICY_ID_PATTERN = /\bP-\d{5}\b/gi;

/**
 * Returns the distinct set of policy ids mentioned in `text`, uppercased and
 * in first-seen order. Empty array when none are present.
 */
export function detectPolicyIds(text) {
  if (!text) return [];
  const matches = text.match(POLICY_ID_PATTERN) ?? [];
  const seen = new Set();
  const ids = [];
  for (const raw of matches) {
    const id = raw.toUpperCase();
    if (!seen.has(id)) {
      seen.add(id);
      ids.push(id);
    }
  }
  return ids;
}

/**
 * ADR-0007's panel-routing rule applied to a question's detected ids:
 * zero or several ids -> no single timeline to open; exactly one -> that id.
 * Returns null when there is no single id to route on.
 */
export function timelineIdFor(detectedIds) {
  return detectedIds.length === 1 ? detectedIds[0] : null;
}
