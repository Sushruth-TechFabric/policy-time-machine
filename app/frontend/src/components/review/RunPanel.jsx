import { useEffect, useState } from 'react';
import { getRun } from '../../api/client.js';
import './review.css';

const STEP_COPY = [
  ['branch_created', 'Working Branch created'],
  ['sequence', 'Section 1: the sequence'],
  ['relevant_changes', 'Section 2: the relevant changes'],
  ['question_chosen', 'Model chose the frequency question'],
  ['genie_answered', 'Genie answered'],
  ['genie_follow_up', 'Genie follow-up'],
  ['similar', 'Section 4: similar histories'],
  ['sentence_', 'Sentences validated against the vocabulary'],
  ['promoted', 'Brief promoted to the review record'],
  ['demo_hold', 'Holding the branch for inspection'],
  ['branch_deleted', 'Working Branch deleted by the harness'],
];

// Consecutive failed polls (2s apart) before the panel stops asking.
const MAX_POLL_MISSES = 15;

function stepIndex(step) {
  if (!step) return -1;
  return STEP_COPY.findIndex(([key]) => step.startsWith(key));
}

/** Polls one Run and narrates the harness's fixed plan. The model never
 *  appears as the actor of a lifecycle step — the harness does.
 *
 *  A completed Run hands back to the view, which reloads the detail and
 *  renders the Brief. A failed one stays on screen with its failure and a
 *  retry, because nothing downstream would otherwise show it. */
export default function RunPanel({ runId, onFinished, onRetry }) {
  const [run, setRun] = useState(null);
  const [lost, setLost] = useState(false);

  useEffect(() => {
    if (!runId) return undefined;
    let cancelled = false;
    let misses = 0;
    setRun(null);
    setLost(false);
    const poll = async () => {
      try {
        const next = await getRun(runId);
        if (cancelled) return;
        misses = 0;
        setRun(next);
        if (next.status === 'running') setTimeout(poll, 1000);
        else if (next.status === 'completed') onFinished?.(next);
      } catch {
        if (cancelled) return;
        misses += 1;
        // A restart can leave a claim in_progress with a run_id the registry
        // minted but never persisted; /runs/{id} then 404s for ever. Give up
        // after ~30s rather than narrating work nobody is doing.
        if (misses >= MAX_POLL_MISSES) { setLost(true); onFinished?.(null); return; }
        setTimeout(poll, 2000);
      }
    };
    poll();
    return () => { cancelled = true; };
  }, [runId, onFinished]);

  if (lost) {
    return (
      <div className="run-panel">
        <div className="run-head"><span className="run-title">No Run record found</span></div>
        <p className="run-failure">
          No Run record was found for this request. Another Run may already be in progress for this claim;
          the queue will update when it finishes.
        </p>
      </div>
    );
  }

  const active = stepIndex(run?.current_step);
  return (
    <div className="run-panel" aria-busy={run?.status === 'running'}>
      <div className="run-head">
        <span className="run-title">{run?.status === 'failed' ? 'Run failed' : run?.status === 'completed' ? 'Run complete' : 'The harness is working'}</span>
        {run?.branch_name && <span className="run-branch">{run.branch_name}</span>}
      </div>
      <ol className="aw-stages">
        {STEP_COPY.map(([key, label], i) => {
          const state = i < active ? 'done' : i === active ? 'active' : 'todo';
          const text = key === 'branch_created' && run?.branch_name ? `${label}: ${run.branch_name.split('/').pop()}` : label;
          return <li key={key} className={`aw-stage aw-stage--${state}`}><span className="aw-dot" aria-hidden="true" /><span className="aw-stage-label">{text}</span></li>;
        })}
      </ol>
      {run?.failure && <div className="run-failure">{run.failure}</div>}
      {run?.status === 'failed' && onRetry && (
        <button type="button" className="ask-submit run-retry" onClick={onRetry}>Try again</button>
      )}
      {run?.trace_id && <div className="run-trace">MLflow trace {run.trace_id}</div>}
    </div>
  );
}
