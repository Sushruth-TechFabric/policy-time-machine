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

function stepIndex(step) {
  if (!step) return -1;
  return STEP_COPY.findIndex(([key]) => step.startsWith(key));
}

/** Polls one Run and narrates the harness's fixed plan. The model never
 *  appears as the actor of a lifecycle step — the harness does. */
export default function RunPanel({ runId, onFinished }) {
  const [run, setRun] = useState(null);

  useEffect(() => {
    if (!runId) return undefined;
    let cancelled = false;
    const poll = async () => {
      try {
        const next = await getRun(runId);
        if (cancelled) return;
        setRun(next);
        if (next.status === 'running') setTimeout(poll, 1000);
        else onFinished?.(next);
      } catch {
        if (!cancelled) setTimeout(poll, 2000);
      }
    };
    poll();
    return () => { cancelled = true; };
  }, [runId, onFinished]);

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
      {run?.trace_id && <div className="run-trace">MLflow trace {run.trace_id}</div>}
    </div>
  );
}
