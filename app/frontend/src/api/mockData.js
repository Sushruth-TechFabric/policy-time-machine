// Mock fixtures for VITE_MOCK=1. Fully replicates the backend API contract
// (see app/frontend/README.md and docs/specs/06-ux-specification.md) with
// canned, deterministic responses so the UI is demoable with no backend.
//
// The scripted questions below are lifted verbatim from
// docs/specs/07-demo-specification.md so mock mode plays the same beats as
// the real demo. All copy obeys the approved vocabulary in
// docs/specs/03-genie-knowledge.md §7 — never fraud/suspicious/red flag/etc.

import { detectPolicyIds, timelineIdFor } from '../lib/policyId.js';

// ---------------------------------------------------------------------------
// Deterministic small PRNG so "random-looking" padding rows are stable across
// renders and test runs (no dependency on Math.random / wall clock seeding).
// ---------------------------------------------------------------------------
function hashSeed(str) {
  let h = 1779033703 ^ str.length;
  for (let i = 0; i < str.length; i++) {
    h = Math.imul(h ^ str.charCodeAt(i), 3432918353);
    h = (h << 13) | (h >>> 19);
  }
  return h >>> 0;
}

function mulberry32(seed) {
  let a = seed;
  return function rand() {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function rngFor(seedStr) {
  return mulberry32(hashSeed(seedStr));
}

function daysAgoISO(n) {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
}

function syntheticPolicyId(rng) {
  const n = 10000 + Math.floor(rng() * 90000);
  return `P-${String(n).slice(0, 5)}`;
}

// ---------------------------------------------------------------------------
// Authored policies — hand-built so the demo's named beats look intentional.
// ---------------------------------------------------------------------------

const P_18492_TIMELINE = {
  found: true,
  events: [
    {
      event_date: daysAgoISO(410),
      event_type: 'policy_created',
      event_category: null,
      endorsement_id: null,
      coverage_line: null,
      old_value: null,
      new_value: null,
      display_label: 'Policy issued',
      amount: null,
      is_material: false,
      source_id: 'P-18492',
    },
    {
      event_date: daysAgoISO(28),
      event_type: 'policy_change',
      event_category: 'address',
      endorsement_id: 'END-7731',
      coverage_line: null,
      old_value: 'Phoenix, AZ 85001',
      new_value: 'Scottsdale, AZ 85251',
      display_label: 'Address changed',
      amount: null,
      is_material: true,
      source_id: 'CHG-40391',
    },
    {
      event_date: daysAgoISO(28),
      event_type: 'policy_change',
      event_category: 'coverage',
      endorsement_id: 'END-7731',
      coverage_line: 'COLL',
      old_value: '100,000',
      new_value: '300,000',
      display_label: 'Collision limit increased',
      amount: null,
      is_material: true,
      source_id: 'CHG-40392',
    },
    {
      event_date: daysAgoISO(20),
      event_type: 'policy_change',
      event_category: 'vehicle',
      endorsement_id: 'END-7745',
      coverage_line: null,
      old_value: '2019 Honda Accord',
      new_value: '2023 Honda Accord',
      display_label: 'Vehicle changed',
      amount: null,
      is_material: true,
      source_id: 'CHG-40410',
    },
    {
      event_date: daysAgoISO(14),
      event_type: 'claim_filed',
      event_category: null,
      endorsement_id: null,
      coverage_line: 'COLL',
      old_value: null,
      new_value: null,
      display_label: '97% of the COLL limit at the time of loss',
      amount: 24700,
      is_material: false,
      source_id: 'CLM-90142',
    },
  ],
};

const P_18492_PATTERNS = [
  {
    pattern_code: 'coverage_raised_then_claimed_same_line',
    pattern_name: 'Coverage raised, then claimed on the same line',
    matched_on_date: daysAgoISO(28),
    evidence_summary:
      'COLL limit raised from $100,000 to $300,000, then a claim on the same line 14 days later.',
  },
];

const P_20114_TIMELINE = {
  found: true,
  events: [
    {
      event_date: daysAgoISO(14),
      event_type: 'policy_change',
      event_category: 'coverage',
      endorsement_id: 'END-8802',
      coverage_line: 'BI',
      old_value: '250,000',
      new_value: '500,000',
      display_label: 'Bodily injury liability limit increased',
      amount: null,
      is_material: true,
      source_id: 'CHG-51120',
    },
    {
      event_date: daysAgoISO(5),
      event_type: 'claim_filed',
      event_category: null,
      endorsement_id: null,
      coverage_line: 'BI',
      old_value: null,
      new_value: null,
      display_label: 'Claim filed on the recently raised BI line',
      amount: 61200,
      is_material: false,
      source_id: 'CLM-91887',
    },
  ],
};

const P_20114_PATTERNS = [
  {
    pattern_code: 'coverage_raised_then_claimed_same_line',
    pattern_name: 'Coverage raised, then claimed on the same line',
    matched_on_date: daysAgoISO(14),
    evidence_summary: 'BI limit raised from $250,000 to $500,000, then a claim on the same line 9 days later.',
  },
];

const P_11907_TIMELINE = {
  found: true,
  events: [
    {
      event_date: daysAgoISO(32),
      event_type: 'policy_change',
      event_category: 'deductible',
      endorsement_id: 'END-6640',
      coverage_line: 'COLL',
      old_value: '1,000',
      new_value: '500',
      display_label: 'Collision deductible decreased',
      amount: null,
      is_material: true,
      source_id: 'CHG-33280',
    },
    {
      event_date: daysAgoISO(10),
      event_type: 'claim_filed',
      event_category: null,
      endorsement_id: null,
      coverage_line: 'COLL',
      old_value: null,
      new_value: null,
      display_label: 'Claim filed',
      amount: 8400,
      is_material: false,
      source_id: 'CLM-88213',
    },
  ],
};

const P_11907_PATTERNS = [];

// The one id reserved to demonstrate the explicit not-found state (Journey 5
// / docs/specs/12-user-journeys.md — "she types P-18499, which does not
// exist"). Never auto-generated, and never appears in any cohort/similarity
// row, so it only surfaces when a user types it deliberately.
const NOT_FOUND_ID = 'P-18499';

const AUTHORED_POLICIES = {
  'P-18492': { timeline: P_18492_TIMELINE, patterns: P_18492_PATTERNS },
  'P-20114': { timeline: P_20114_TIMELINE, patterns: P_20114_PATTERNS },
  'P-11907': { timeline: P_11907_TIMELINE, patterns: P_11907_PATTERNS },
};

const CHANGE_CATEGORIES = ['address', 'coverage', 'vehicle', 'deductible', 'status'];
const CATEGORY_LABELS = {
  address: 'Address changed',
  coverage: 'Coverage limit changed',
  vehicle: 'Vehicle changed',
  deductible: 'Deductible changed',
  status: 'Status changed',
};

function generateSyntheticTimeline(policyId) {
  const rng = rngFor(policyId);
  const category = CHANGE_CATEGORIES[Math.floor(rng() * CHANGE_CATEGORIES.length)];
  const changeDaysAgo = 10 + Math.floor(rng() * 60);
  const claimDaysAgo = Math.max(1, changeDaysAgo - (3 + Math.floor(rng() * 25)));
  const amount = Math.round(1500 + rng() * 70000);
  return {
    found: true,
    events: [
      {
        event_date: daysAgoISO(changeDaysAgo),
        event_type: 'policy_change',
        event_category: category,
        endorsement_id: `END-${Math.floor(rng() * 9000 + 1000)}`,
        coverage_line: category === 'coverage' || category === 'deductible' ? 'COLL' : null,
        old_value: null,
        new_value: null,
        display_label: CATEGORY_LABELS[category],
        amount: null,
        is_material: true,
        source_id: `CHG-${Math.floor(rng() * 90000 + 10000)}`,
      },
      {
        event_date: daysAgoISO(claimDaysAgo),
        event_type: 'claim_filed',
        event_category: null,
        endorsement_id: null,
        coverage_line: category === 'coverage' || category === 'deductible' ? 'COLL' : null,
        old_value: null,
        new_value: null,
        display_label: 'Claim filed',
        amount,
        is_material: false,
        source_id: `CLM-${Math.floor(rng() * 90000 + 10000)}`,
      },
    ],
  };
}

// ---------------------------------------------------------------------------
// Similarity — planted so the demo's third neighbour is P-20114, matching
// docs/specs/12-user-journeys.md Journey 4 ("she clicks the third...
// P-18492 › similar policies › P-20114").
// ---------------------------------------------------------------------------

const REASON_POOL = [
  'comparable change velocity',
  'coverage increase preceding a same-line claim',
  'both in the top decile for material changes per year',
  'similar category mix of material changes',
  'matched noteworthy pattern: coverage raised then claimed same line',
  'similar claim severity profile',
  'similar limit utilisation at time of loss',
];

function buildNeighbours(originId, plantedRanked) {
  const neighbours = [...plantedRanked];
  const rng = rngFor(`similar:${originId}`);
  while (neighbours.length < 20) {
    const rank = neighbours.length + 1;
    const reasons = [REASON_POOL[Math.floor(rng() * REASON_POOL.length)], REASON_POOL[Math.floor(rng() * REASON_POOL.length)]];
    neighbours.push({
      similar_policy_id: syntheticPolicyId(rng),
      rank,
      similarity_score: Number((0.55 - rank * 0.015 + rng() * 0.02).toFixed(3)),
      top_reasons: Array.from(new Set(reasons)).join('; '),
    });
  }
  return neighbours;
}

const SIMILARITY = {
  'P-18492': buildNeighbours('P-18492', [
    {
      similar_policy_id: 'P-31006',
      rank: 1,
      similarity_score: 0.912,
      top_reasons: 'comparable change velocity; both in the top decile for material changes per year',
    },
    {
      similar_policy_id: 'P-40221',
      rank: 2,
      similarity_score: 0.887,
      top_reasons: 'coverage increase preceding a same-line claim; similar claim severity profile',
    },
    {
      similar_policy_id: 'P-20114',
      rank: 3,
      similarity_score: 0.864,
      top_reasons:
        'comparable change velocity; coverage increase preceding a same-line claim; both in the top decile for material changes per year',
    },
  ]),
};

// ---------------------------------------------------------------------------
// Chip banks — the four contexts the backend serves, per app/frontend README.
// Each chip is a complete, context-free question with entities interpolated
// (ADR-0011); none rely on carried conversation state.
// ---------------------------------------------------------------------------

function chipBank(context, activePolicyId) {
  const pid = activePolicyId ?? 'P-18492';
  switch (context) {
    case 'investigation_start':
      return [
        'Show policies where coverage increased within 30 days before a claim.',
        'Which material changes happen most frequently before high-severity claims?',
        'Show unusual historical patterns worth investigating.',
      ];
    case 'timeline_open':
      return [
        `What changed on ${pid} in the 90 days before its latest claim?`,
        `Find policies with histories similar to ${pid}.`,
        'Show unusual historical patterns worth investigating.',
      ];
    case 'similarity_view':
      return [
        'Show unusual historical patterns worth investigating.',
        'Compare policies with recent material changes against those without.',
        `What changed on ${pid} in the 90 days before its latest claim?`,
      ];
    case 'cohort_on_screen':
      return [
        'Of policies where coverage increased within 30 days before a claim, which had a claim near the new limit?',
        'Compare policies with recent material changes against those without.',
        'Which material changes happen most frequently before claims above $25,000?',
      ];
    default:
      return [];
  }
}

// ---------------------------------------------------------------------------
// The 47-row cohort (docs/specs/06-ux-specification.md §1's RESULT table).
// First three rows are authored verbatim from the ASCII mock; the remaining
// 44 are deterministically generated padding so "47 rows" is literally true.
// ---------------------------------------------------------------------------

function buildCohort47() {
  const rows = [
    { policy_id: 'P-18492', days_to_next_claim_loss: 14, claim_amount: 24700 },
    { policy_id: 'P-20114', days_to_next_claim_loss: 9, claim_amount: 61200 },
    { policy_id: 'P-11907', days_to_next_claim_loss: 22, claim_amount: 8400 },
  ];
  const rng = rngFor('cohort-47');
  while (rows.length < 47) {
    rows.push({
      policy_id: syntheticPolicyId(rng),
      days_to_next_claim_loss: 1 + Math.floor(rng() * 30),
      claim_amount: Math.round(800 + rng() * 90000),
    });
  }
  return rows;
}

const COHORT_47_ROWS = buildCohort47();

function buildNarrowedNine() {
  const rows = [{ policy_id: 'P-18492', days_to_next_claim_loss: 14, claim_amount: 24700, limit_utilization_pct: 97 }];
  const rng = rngFor('cohort-9-near-limit');
  // Sample distinct policies (no replacement) so the subset never repeats a
  // policy_id — this is a subset of a policy-grain cohort, not a
  // change-grain one, so distinct ids are the correct shape here.
  const pool = [...COHORT_47_ROWS.slice(1)];
  for (let i = 0; i < 8 && pool.length > 0; i++) {
    const index = Math.floor(rng() * pool.length);
    const [source] = pool.splice(index, 1);
    rows.push({
      policy_id: source.policy_id,
      days_to_next_claim_loss: source.days_to_next_claim_loss,
      claim_amount: source.claim_amount,
      limit_utilization_pct: 90 + Math.round(rng() * 9),
    });
  }
  return rows;
}

const RANKING_ROWS = [
  { change_category: 'coverage', change_count: 132 },
  { change_category: 'deductible', change_count: 98 },
  { change_category: 'vehicle', change_count: 61 },
  { change_category: 'status', change_count: 54 },
  { change_category: 'address', change_count: 39 },
];

const COMPARISON_ROWS = [
  { comparison_group: 'recent material change', rate_pct: 8.5, n: 1240 },
  { comparison_group: 'no recent material change', rate_pct: 5.8, n: 6180 },
];

const PATTERN_ROWS = [
  { pattern_name: 'Coverage raised, then claimed on the same line', policies: 40 },
  { pattern_name: 'Deductible lowered before a claim', policies: 30 },
  { pattern_name: 'Change made in the loss-to-report gap', policies: 22 },
  { pattern_name: 'Rapid change cluster', policies: 18 },
  { pattern_name: 'Vehicle and address changed within 60 days', policies: 35 },
  { pattern_name: 'Claim near a recently raised limit', policies: 15 },
];

// ---------------------------------------------------------------------------
// The mock Genie engine. Matches canned demo-script questions (see
// docs/specs/07-demo-specification.md) first; falls back to a per-policy
// echo when a single known id is present; otherwise reports an honest empty
// result rather than fabricating something plausible-looking. `contains`
// checks are case-insensitive substring matches on the raw question text.
// ---------------------------------------------------------------------------

function contains(text, phrase) {
  return text.toLowerCase().includes(phrase.toLowerCase());
}

function genieOk({ columns, rows, sql, description }) {
  return { status: 'ok', columns, rows, generated_sql: sql, description, error: null };
}

function genieEmpty(description) {
  return { status: 'empty', columns: [], rows: [], generated_sql: null, description, error: null };
}

function genieError(message) {
  return {
    status: 'error',
    columns: [],
    rows: [],
    generated_sql: null,
    description: null,
    error: message,
  };
}

function genieClarification(question) {
  return {
    status: 'clarification',
    columns: [],
    rows: [],
    generated_sql: null,
    description: question,
    error: null,
  };
}

function answerFor(question, { lastOpenPolicyId } = {}) {
  const q = question.trim();

  // Manual demo hooks for the two failure states that have no natural
  // trigger in a canned-answer mock (see this module's header comment).
  if (contains(q, 'timeout') || contains(q, 'genie error')) {
    return genieError('Genie could not complete this request. The connection to the SQL warehouse timed out.');
  }
  if (contains(q, 'clarify')) {
    return genieClarification('Do you mean claims filed in the last 90 days, or claims with a loss date in the last 90 days?');
  }

  if (contains(q, 'coverage increased') && contains(q, '30 days') && !contains(q, 'near the') && !contains(q, 'which of these')) {
    return genieOk({
      columns: [{ name: 'policy_id' }, { name: 'days_to_next_claim_loss' }, { name: 'claim_amount' }],
      rows: COHORT_47_ROWS,
      sql:
        "SELECT policy_id, days_to_next_claim_loss, claim_amount\nFROM policy_change_event\nWHERE change_category = 'coverage'\n  AND change_direction = 'increase'\n  AND change_timing = 'before_loss'\n  AND days_to_next_claim_loss <= 30\nORDER BY days_to_next_claim_loss",
      description: '47 policies had a coverage increase in the 30 days before a claim, ordered by days between the change and the loss.',
    });
  }

  if (contains(q, 'which of these') || (contains(q, 'near the new limit') && contains(q, 'claim'))) {
    return genieOk({
      columns: [
        { name: 'policy_id' },
        { name: 'days_to_next_claim_loss' },
        { name: 'claim_amount' },
        { name: 'limit_utilization_pct' },
      ],
      rows: buildNarrowedNine(),
      sql:
        "SELECT policy_id, days_to_next_claim_loss, claim_amount, limit_utilization_pct\nFROM claim_event\nWHERE at_or_near_limit = true\n  AND policy_id IN (/* previous turn's cohort */)\nORDER BY limit_utilization_pct DESC",
      description: 'Of the 47 policies, 9 also had a claim at or near the newly raised limit (utilisation of 90% or more).',
    });
  }

  if (contains(q, 'compare') && contains(q, 'material change')) {
    return genieOk({
      columns: [{ name: 'comparison_group' }, { name: 'rate_pct' }, { name: 'n' }],
      rows: COMPARISON_ROWS,
      sql:
        "SELECT CASE WHEN last_material_change_date >= CURRENT_DATE - INTERVAL 90 DAY\n            THEN 'recent material change' ELSE 'no recent material change' END AS comparison_group,\n       AVG(CASE WHEN claim_count > 0 THEN 1.0 ELSE 0.0 END) * 100 AS rate_pct,\n       COUNT(*) AS n\nFROM policy_profile\nGROUP BY 1",
      description: 'Claim rate for policies with a recent material change versus policies without, each with its group size.',
    });
  }

  if (contains(q, 'material changes') && (contains(q, 'frequently') || contains(q, 'most often'))) {
    return genieOk({
      columns: [{ name: 'change_category' }, { name: 'change_count' }],
      rows: RANKING_ROWS,
      sql:
        "SELECT change_category, COUNT(*) AS change_count\nFROM policy_change_event\nWHERE is_material = true\n  AND change_timing = 'before_loss'\n  AND days_to_next_claim_loss <= 60\n  AND next_claim_severity IN ('severe','catastrophic')\nGROUP BY change_category\nORDER BY change_count DESC",
      description: 'Material change categories ranked by how often they precede a high-severity claim.',
    });
  }

  if (contains(q, 'unusual historical patterns') || contains(q, 'patterns worth investigating') || contains(q, 'raised-then-claimed pattern')) {
    return genieOk({
      columns: [{ name: 'pattern_name' }, { name: 'policies' }],
      rows: PATTERN_ROWS,
      sql: 'SELECT pattern_name, COUNT(DISTINCT policy_id) AS policies\nFROM policy_pattern_match\nGROUP BY pattern_name\nORDER BY policies DESC',
      description: 'Every defined noteworthy pattern and the count of investigation candidates matching it.',
    });
  }

  if (contains(q, 'similar') || contains(q, 'looks like') || contains(q, 'histories like')) {
    const detected = detectPolicyIds(q);
    const originId = timelineIdFor(detected) ?? lastOpenPolicyId ?? 'P-18492';
    const neighbours = SIMILARITY[originId] ?? buildNeighbours(originId, []);
    return genieOk({
      columns: [{ name: 'rank' }, { name: 'similar_policy_id' }, { name: 'similarity_score' }, { name: 'top_reasons' }],
      rows: neighbours.map((n) => ({
        rank: n.rank,
        similar_policy_id: n.similar_policy_id,
        similarity_score: n.similarity_score,
        top_reasons: n.top_reasons,
      })),
      sql: `SELECT s.rank, s.similar_policy_id, s.similarity_score, s.top_reasons\nFROM policy_similarity s\nWHERE s.policy_id = '${originId}'\nORDER BY s.rank`,
      description: `Top ${neighbours.length} policies with histories closest to ${originId}, most similar first. Similarity is directional and capped at 20.`,
    });
  }

  const detected = detectPolicyIds(q);
  if (detected.length === 1) {
    const pid = detected[0];
    const authored = AUTHORED_POLICIES[pid];
    if (authored) {
      const events = authored.timeline.events;
      return genieOk({
        columns: [{ name: 'event_date' }, { name: 'event_type' }, { name: 'display_label' }, { name: 'amount' }],
        rows: events.map((e) => ({
          event_date: e.event_date,
          event_type: e.event_type,
          display_label: e.display_label,
          amount: e.amount,
        })),
        sql: `SELECT event_date, event_type, display_label, amount\nFROM policy_timeline_event\nWHERE policy_id = '${pid}'\nORDER BY event_date`,
        description: `Every recorded event on ${pid}, in order.`,
      });
    }
    if (pid === NOT_FOUND_ID) {
      return genieEmpty(`No matching rows for ${pid}.`);
    }
    // Any other single id: fall through to a synthetic-but-plausible echo so
    // clicking generated cohort/similarity rows never dead-ends.
    const synthetic = generateSyntheticTimeline(pid);
    return genieOk({
      columns: [{ name: 'event_date' }, { name: 'event_type' }, { name: 'display_label' }, { name: 'amount' }],
      rows: synthetic.events.map((e) => ({
        event_date: e.event_date,
        event_type: e.event_type,
        display_label: e.display_label,
        amount: e.amount,
      })),
      sql: `SELECT event_date, event_type, display_label, amount\nFROM policy_timeline_event\nWHERE policy_id = '${pid}'\nORDER BY event_date`,
      description: `Every recorded event on ${pid}, in order.`,
    });
  }

  return genieEmpty(`No matching rows for "${q}".`);
}

// ---------------------------------------------------------------------------
// Public mock API surface — mirrors app/backend's contract exactly.
// ---------------------------------------------------------------------------

let mockInvestigationCounter = 0;

export function mockCreateInvestigation() {
  mockInvestigationCounter += 1;
  return Promise.resolve({ investigation_id: `mock-inv-${mockInvestigationCounter}` });
}

export function mockSendMessage(_investigationId, question, context = {}) {
  const detected_policy_ids = detectPolicyIds(question);
  const timeline_policy_id = timelineIdFor(detected_policy_ids);
  const genie = answerFor(question, context);
  return Promise.resolve({ detected_policy_ids, timeline_policy_id, genie });
}

export function mockGetTimeline(policyId) {
  const authored = AUTHORED_POLICIES[policyId];
  if (authored) return Promise.resolve(authored.timeline);
  if (policyId === NOT_FOUND_ID) return Promise.resolve({ found: false, events: [] });
  return Promise.resolve(generateSyntheticTimeline(policyId));
}

export function mockGetSimilar(policyId) {
  const neighbours = SIMILARITY[policyId] ?? buildNeighbours(policyId, []);
  return Promise.resolve({ neighbours });
}

export function mockGetPatterns(policyId) {
  const authored = AUTHORED_POLICIES[policyId];
  if (authored) return Promise.resolve({ patterns: authored.patterns });
  return Promise.resolve({ patterns: [] });
}

export function mockGetChips(context, activePolicyId) {
  return Promise.resolve({ chips: chipBank(context, activePolicyId) });
}

export { NOT_FOUND_ID };
