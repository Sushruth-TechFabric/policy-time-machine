// Real backend calls, or VITE_MOCK=1 fixtures. Both paths return identical
// shapes so the rest of the app never checks the mode. Real calls go through
// the Vite dev proxy (/api -> http://localhost:8000, see vite.config.js).

import {
  mockCreateInvestigation,
  mockSendMessage,
  mockGetTimeline,
  mockGetSimilar,
  mockGetPatterns,
  mockGetChips,
} from './mockData.js';

export const MOCK_MODE = import.meta.env.VITE_MOCK === '1';

// Small, deliberate artificial latency so mock mode exercises the same
// loading states a real deployment would: timeline resolves fast, Genie
// resolves slower — never a spinner tied to Genie on the timeline side
// (docs/specs/06-ux-specification.md §3).
function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function jsonOrThrow(res) {
  if (!res.ok) {
    const body = await res.text().catch(() => '');
    throw new Error(`Request failed (${res.status}): ${body || res.statusText}`);
  }
  return res.json();
}

export async function createInvestigation() {
  if (MOCK_MODE) {
    await delay(80);
    return mockCreateInvestigation();
  }
  const res = await fetch('/api/investigations', { method: 'POST' });
  return jsonOrThrow(res);
}

export async function sendMessage(investigationId, question, mockContext) {
  if (MOCK_MODE) {
    await delay(650 + Math.random() * 400);
    return mockSendMessage(investigationId, question, mockContext);
  }
  const res = await fetch(`/api/investigations/${investigationId}/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
  });
  return jsonOrThrow(res);
}

export async function getTimeline(policyId) {
  if (MOCK_MODE) {
    await delay(90 + Math.random() * 80);
    return mockGetTimeline(policyId);
  }
  const res = await fetch(`/api/policies/${policyId}/timeline`);
  return jsonOrThrow(res);
}

export async function getSimilar(policyId) {
  if (MOCK_MODE) {
    await delay(120);
    return mockGetSimilar(policyId);
  }
  const res = await fetch(`/api/policies/${policyId}/similar`);
  return jsonOrThrow(res);
}

export async function getPatterns(policyId) {
  if (MOCK_MODE) {
    await delay(90);
    return mockGetPatterns(policyId);
  }
  const res = await fetch(`/api/policies/${policyId}/patterns`);
  return jsonOrThrow(res);
}

export async function getChips(context, activePolicyId) {
  if (MOCK_MODE) {
    await delay(60);
    return mockGetChips(context, activePolicyId);
  }
  const res = await fetch(`/api/chips?context=${encodeURIComponent(context)}`);
  return jsonOrThrow(res);
}
