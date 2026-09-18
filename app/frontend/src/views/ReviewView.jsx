import { useCallback, useEffect, useState } from 'react';
import { getReviewQueue, getReviewClaim, prepareBrief, getTimeline, getPatterns } from '../api/client.js';
import Timeline from '../components/Timeline.jsx';
import QueueList from '../components/review/QueueList.jsx';
import BriefPanel from '../components/review/BriefPanel.jsx';
import RunPanel from '../components/review/RunPanel.jsx';
import DispositionForm from '../components/review/DispositionForm.jsx';
import './ReviewView.css';

/**
 * The review record: queue on the left, timeline + Brief on the right.
 * Separate from the investigation workbench by design (grill session
 * 2026-09-17, question 7). Access mirrors the on-behalf-of timeline read:
 * if the timeline reports no_access, so does the Brief (ADR-0019).
 *
 * Selection is kept locally (initialised from, and re-synced with, the
 * `selectedClaimId` prop) rather than driven solely by the prop: the parent
 * may pass a no-op `onSelectClaim`, and a row click must still open the
 * Brief immediately.
 */
export default function ReviewView({ selectedClaimId, onSelectClaim, onOpenAsInvestigation }) {
  const [selected, setSelected] = useState(selectedClaimId ?? null);
  const [queue, setQueue] = useState(null);
  const [detail, setDetail] = useState(null);
  const [timeline, setTimeline] = useState(null);
  const [runId, setRunId] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => { setSelected(selectedClaimId ?? null); }, [selectedClaimId]);

  const handleSelect = useCallback((claimId) => {
    setSelected(claimId);
    onSelectClaim(claimId);
  }, [onSelectClaim]);

  const loadQueue = useCallback(async () => {
    try { setQueue((await getReviewQueue()).queue); } catch (err) { setError(err?.message || 'Could not load the queue.'); }
  }, []);

  const loadDetail = useCallback(async (claimId) => {
    if (!claimId) { setDetail(null); setTimeline(null); return; }
    try {
      const next = await getReviewClaim(claimId);
      setDetail(next);
      if (next.active_run?.status === 'running') setRunId(next.active_run.run_id);
      const t = await getTimeline(next.policy_id);
      setTimeline(t.no_access ? { found: false, events: [], patterns: [], noAccess: true }
        : !t.found ? { found: false, events: [], patterns: [] }
          : { found: true, events: t.events, patterns: (await getPatterns(next.policy_id)).patterns ?? [] });
    } catch (err) {
      setError(err?.message || 'Could not load the claim.');
    }
  }, []);

  useEffect(() => { loadQueue(); }, [loadQueue]);
  useEffect(() => { loadDetail(selected); }, [selected, loadDetail]);

  const onFinished = useCallback(() => { setRunId(null); loadDetail(selected); loadQueue(); }, [loadDetail, loadQueue, selected]);

  async function startRun() {
    try {
      const res = await prepareBrief(selected);
      if (res.no_access) { setTimeline({ found: false, events: [], patterns: [], noAccess: true }); return; }
      setRunId(res.run_id);
    } catch (err) {
      setError(err?.message || 'Could not start a Run.');
    }
  }

  const noAccess = Boolean(timeline?.noAccess);
  return (
    <div className="review-view">
      <aside className="review-queue">
        <div className="review-queue-head">Routed claims</div>
        <QueueList rows={queue} selectedId={selected} onSelect={handleSelect} />
      </aside>
      <div className="review-detail">
        {error && <div className="app-boot-error">{error}</div>}
        {!detail && <div className="review-placeholder">Select a routed claim.</div>}
        {detail && (
          <div className="review-split">
            <div className="timeline-region">
              <Timeline policyId={detail.policy_id} data={timeline} onFindSimilar={() => {}} findSimilarBusy />
            </div>
            <div className="review-brief-region">
              {runId && <RunPanel runId={runId} onFinished={onFinished} />}
              {!runId && !detail.brief && !noAccess && (
                <div className="review-no-brief">
                  <p>No Brief yet for {detail.claim_id}.</p>
                  <button type="button" className="ask-submit" onClick={startRun}>Prepare a Brief</button>
                </div>
              )}
              {(detail.brief || noAccess) && !runId && (
                <>
                  <BriefPanel key={detail.claim_id} brief={detail.brief} noAccess={noAccess} onOpenAsInvestigation={onOpenAsInvestigation} />
                  {!noAccess && <DispositionForm key={detail.claim_id} claimId={detail.claim_id} disposition={detail.disposition}
                    onRecorded={(d) => { setDetail({ ...detail, disposition: d }); loadQueue(); }} />}
                </>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
