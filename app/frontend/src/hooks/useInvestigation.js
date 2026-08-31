import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createInvestigation, sendMessage, getTimeline, getPatterns, getSimilar, getChips } from '../api/client.js';
import { detectPolicyIds, timelineIdFor } from '../lib/policyId.js';
import { trailLabelFor } from '../lib/trailLabel.js';
import { normalizeGenieResult } from '../lib/normalize.js';

let nodeCounter = 0;
// Timestamp component keeps ids unique against nodes restored from an
// earlier session, whose counters restarted from zero.
function nextNodeId() {
  nodeCounter += 1;
  return `node-${Date.now().toString(36)}-${nodeCounter}`;
}

function loadStoredInvestigation(storageKey) {
  if (!storageKey) return null;
  try {
    const parsed = JSON.parse(window.localStorage.getItem(storageKey));
    return Array.isArray(parsed?.trail) ? parsed : null;
  } catch {
    return null;
  }
}

const RESET_STATUSES = new Set(['error', 'empty', 'clarification']);

function computeChipContext(activeNode, displayedTimelineId) {
  if (!activeNode) return 'investigation_start';
  const { genie } = activeNode;
  if (genie?.status === 'ok' && genie.rows?.length) {
    const looksLikeSimilarity = genie.columns?.some((c) => c.name === 'similar_policy_id');
    return looksLikeSimilarity ? 'similarity_view' : 'cohort_on_screen';
  }
  if (displayedTimelineId) return 'timeline_open';
  return 'investigation_start';
}

/**
 * Owns the whole investigation: the Genie-conversation-shaped trail, the
 * left-panel timeline that never blocks on Genie (ADR-0007), and the
 * breadcrumb's cached-view restore (ADR-0011 — clicking a node never
 * re-fetches and never sends a new thread message).
 */
export function useInvestigation(storageKey) {
  const [trail, setTrail] = useState(() => loadStoredInvestigation(storageKey)?.trail ?? []);
  const [activeIndex, setActiveIndex] = useState(() => {
    const stored = loadStoredInvestigation(storageKey);
    return stored ? Math.min(stored.activeIndex ?? stored.trail.length - 1, stored.trail.length - 1) : -1;
  });
  const [manualTimelineId, setManualTimelineId] = useState(null);
  const [liveTimelineId, setLiveTimelineId] = useState(null);
  const [genieLoading, setGenieLoading] = useState(false);
  const [pendingQuestion, setPendingQuestion] = useState(null);
  const [bootError, setBootError] = useState(null);
  const [highlightReset, setHighlightReset] = useState(false);
  const [chips, setChips] = useState([]);
  // Resolved timelines, keyed by policy id. This is the one thing every
  // consumer of the hook reads during render (via `displayedTimeline`
  // below), so it lives in state rather than a ref — refs must never be
  // read during render.
  const [resolvedTimelines, setResolvedTimelines] = useState({});

  const investigationIdRef = useRef(null);
  // Bookkeeping only: the single fetch-or-cache-hit gate per policy id, so
  // two near-simultaneous callers (e.g. a chip click racing a row click)
  // share one network call. Never read during render — `resolvedTimelines`
  // state is the render-time source of truth.
  const fetchCacheRef = useRef(new Map()); // policyId -> Promise<snapshot>

  const fetchTimelineSnapshot = useCallback((policyId) => {
    const cache = fetchCacheRef.current;
    if (cache.has(policyId)) return cache.get(policyId);
    const promise = (async () => {
      const timeline = await getTimeline(policyId);
      const result = !timeline.found
        ? { found: false, events: [], patterns: [] }
        : { found: true, events: timeline.events, patterns: (await getPatterns(policyId)).patterns ?? [] };
      setResolvedTimelines((prev) => ({ ...prev, [policyId]: result }));
      return result;
    })();
    cache.set(policyId, promise);
    return promise;
  }, []);

  const ensureInvestigation = useCallback(async () => {
    if (investigationIdRef.current) return investigationIdRef.current;
    const { investigation_id } = await createInvestigation();
    investigationIdRef.current = investigation_id;
    return investigation_id;
  }, []);

  const activeNode = activeIndex >= 0 ? trail[activeIndex] ?? null : null;
  const displayedTimelineId = manualTimelineId ?? (genieLoading ? liveTimelineId : activeNode?.timelinePolicyId ?? null);
  const displayedTimeline = displayedTimelineId ? resolvedTimelines[displayedTimelineId] ?? null : null;

  // The trail survives a page refresh (persisted below), but resolved
  // timelines don't — refetch whichever one the restored view is showing.
  useEffect(() => {
    if (displayedTimelineId && !resolvedTimelines[displayedTimelineId]) {
      fetchTimelineSnapshot(displayedTimelineId).catch(() => {});
    }
  }, [displayedTimelineId, resolvedTimelines, fetchTimelineSnapshot]);

  // Persist the conversation so a refresh (or tab switch tomorrow) keeps the
  // work. The Genie conversation id itself is deliberately not persisted —
  // after a reload, the next question starts a fresh Genie thread while the
  // visible trail stays intact.
  useEffect(() => {
    if (!storageKey) return;
    try {
      if (trail.length === 0) window.localStorage.removeItem(storageKey);
      else window.localStorage.setItem(storageKey, JSON.stringify({ trail, activeIndex }));
    } catch {
      /* storage full or unavailable — the app keeps working in-memory */
    }
  }, [storageKey, trail, activeIndex]);

  const submitQuestion = useCallback(
    async (rawQuestion) => {
      const question = rawQuestion.trim();
      if (!question || genieLoading) return;

      setManualTimelineId(null);
      setHighlightReset(false);
      setBootError(null);

      const detected = detectPolicyIds(question);
      const predictedId = timelineIdFor(detected);
      setLiveTimelineId(predictedId);
      setGenieLoading(true);
      setPendingQuestion(question);
      const startedAt = Date.now();

      const timelinePromise = predictedId ? fetchTimelineSnapshot(predictedId) : Promise.resolve(null);

      try {
        const invId = await ensureInvestigation();
        const [result] = await Promise.all([
          sendMessage(invId, question, { lastOpenPolicyId: displayedTimelineId }),
          timelinePromise,
        ]);
        const node = {
          id: nextNodeId(),
          question,
          detectedPolicyIds: detected,
          timelinePolicyId: predictedId,
          genie: normalizeGenieResult(result.genie),
          elapsedMs: Date.now() - startedAt,
          label: trailLabelFor(question),
        };
        setTrail((t) => {
          const next = [...t, node];
          setActiveIndex(next.length - 1);
          return next;
        });
        if (RESET_STATUSES.has(result.genie.status)) setHighlightReset(true);
      } catch (err) {
        setBootError(err?.message || 'Something went wrong reaching the investigation service.');
        setHighlightReset(true);
      } finally {
        setGenieLoading(false);
        setPendingQuestion(null);
        setLiveTimelineId(null);
      }
    },
    [ensureInvestigation, fetchTimelineSnapshot, genieLoading, displayedTimelineId],
  );

  // Policy row clicked in a result table: that policy's timeline loads on
  // the left. Never sends a message and never grows the trail
  // (docs/specs/06-ux-specification.md §2).
  const openPolicyTimeline = useCallback(
    (policyId) => {
      setManualTimelineId(policyId);
      fetchTimelineSnapshot(policyId).catch(() => {});
    },
    [fetchTimelineSnapshot],
  );

  // The timeline's "find similar policies" affordance (ADR-0010): reads
  // policy_similarity directly rather than round-tripping through Genie, so
  // it is fast and always available — the same table a typed "similar"
  // question or chip resolves against, just reached by a faster path. Still
  // adds a trail node, because it is a real turn in the investigation.
  const findSimilar = useCallback(
    async (policyId) => {
      if (genieLoading) return;
      setManualTimelineId(null);
      setHighlightReset(false);
      setBootError(null);
      setGenieLoading(true);
      setPendingQuestion(`Find policies with histories similar to ${policyId}.`);
      setLiveTimelineId(policyId);
      const startedAt = Date.now();
      try {
        await ensureInvestigation();
        const { neighbours } = await getSimilar(policyId);
        const genie = {
          status: 'ok',
          columns: [{ name: 'rank' }, { name: 'similar_policy_id' }, { name: 'similarity_score' }, { name: 'top_reasons' }],
          rows: neighbours.map((n) => ({
            rank: n.rank,
            similar_policy_id: n.similar_policy_id,
            similarity_score: n.similarity_score,
            top_reasons: n.top_reasons,
          })),
          generated_sql: `SELECT s.rank, s.similar_policy_id, s.similarity_score, s.top_reasons\nFROM policy_similarity s\nWHERE s.policy_id = '${policyId}'\nORDER BY s.rank`,
          description: `Top ${neighbours.length} polic${neighbours.length === 1 ? 'y' : 'ies'} with histories closest to ${policyId}, read directly from the precomputed similarity table (not a Genie query). Similarity is directional and capped at 20.`,
          error: null,
        };
        const node = {
          id: nextNodeId(),
          question: `Find policies with histories similar to ${policyId}.`,
          detectedPolicyIds: [policyId],
          timelinePolicyId: policyId,
          genie,
          elapsedMs: Date.now() - startedAt,
          label: 'Similar',
        };
        setTrail((t) => {
          const next = [...t, node];
          setActiveIndex(next.length - 1);
          return next;
        });
      } catch (err) {
        setBootError(err?.message || 'Something went wrong reaching the investigation service.');
        setHighlightReset(true);
      } finally {
        setGenieLoading(false);
        setPendingQuestion(null);
        setLiveTimelineId(null);
      }
    },
    [ensureInvestigation, genieLoading],
  );

  // Breadcrumb click: restore a cached view. No re-fetch, no new message
  // (ADR-0011). The timeline for that node is already in resolvedTimelines
  // because it was fetched before the node was ever created.
  const goToNode = useCallback((index) => {
    setManualTimelineId(null);
    setActiveIndex(index);
  }, []);

  const startNewInvestigation = useCallback(() => {
    investigationIdRef.current = null;
    fetchCacheRef.current = new Map();
    setResolvedTimelines({});
    setTrail([]);
    setActiveIndex(-1);
    setManualTimelineId(null);
    setLiveTimelineId(null);
    setGenieLoading(false);
    setPendingQuestion(null);
    setBootError(null);
    setHighlightReset(false);
  }, []);

  const chipContext = useMemo(() => computeChipContext(activeNode, displayedTimelineId), [activeNode, displayedTimelineId]);

  useEffect(() => {
    let cancelled = false;
    getChips(chipContext, displayedTimelineId ?? undefined).then((res) => {
      if (!cancelled) setChips(res.chips ?? []);
    });
    return () => {
      cancelled = true;
    };
  }, [chipContext, displayedTimelineId]);

  return {
    trail,
    activeIndex,
    activeNode,
    displayedTimelineId,
    displayedTimeline,
    genieLoading,
    pendingQuestion,
    bootError,
    highlightReset,
    chips,
    submitQuestion,
    openPolicyTimeline,
    findSimilar,
    goToNode,
    startNewInvestigation,
  };
}
