// The breadcrumb trail shows short paraphrases, not full question text
// (docs/specs/06-ux-specification.md §1's mock: "Coverage up before claims
// > P-18492 > Similar"). The API doesn't supply a label, so the frontend
// derives one: a small curated map for the demo-script questions this app
// authors as chips/affordances, falling back to truncation for anything
// typed freehand.

const CURATED = [
  // Order matters: the narrowed-cohort question deliberately repeats
  // "coverage increased...30 days" while restating the first turn's
  // criteria (chips must be context-free — ADR-0011), so its own,
  // more specific test must be checked first or it would collide with
  // the label below.
  { test: (q) => /which of these/i.test(q) || /which had a claim near the new limit/i.test(q), label: 'Near new limit' },
  { test: (q) => /coverage increased/i.test(q) && /30 days/i.test(q), label: 'Coverage up before claims' },
  { test: (q) => /^find policies with histories similar to/i.test(q), label: 'Similar' },
  { test: (q) => /compare/i.test(q) && /material change/i.test(q), label: 'Recent vs. not' },
  { test: (q) => /material changes/i.test(q) && /(frequently|most often)/i.test(q), label: 'Top change categories' },
  { test: (q) => /unusual historical patterns/i.test(q) || /patterns worth investigating/i.test(q), label: 'Patterns' },
  { test: (q) => /^what changed on/i.test(q), label: "What changed" },
];

const MAX_LEN = 28;

export function trailLabelFor(question) {
  const curated = CURATED.find((c) => c.test(question));
  if (curated) return curated.label;
  const trimmed = question.trim().replace(/[?.!]+$/, '');
  if (trimmed.length <= MAX_LEN) return trimmed;
  return `${trimmed.slice(0, MAX_LEN - 1)}…`;
}
