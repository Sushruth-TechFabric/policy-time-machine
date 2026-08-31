import { useEffect, useState } from 'react';
import './AgentWorking.css';

// The real Genie pipeline stages, in order. Genie's API is a single blocking
// call, so stage transitions on screen are paced estimates — the elapsed
// clock is real, and the finished answer replaces this card with the actual
// evidence (interpretation, SQL, rows).
const STAGES = [
  { at: 0, label: 'Sending your question to the Genie space' },
  { at: 1.5, label: 'Genie reads the semantic model & instructions' },
  { at: 4, label: 'Writing SQL against the gold tables' },
  { at: 8, label: 'Running the query on the SQL warehouse' },
  { at: 14, label: 'Assembling the answer' },
];

export default function AgentWorking({ question }) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const started = Date.now();
    const id = setInterval(() => setElapsed((Date.now() - started) / 1000), 250);
    return () => clearInterval(id);
  }, []);

  const activeIndex = STAGES.reduce((acc, s, i) => (elapsed >= s.at ? i : acc), 0);

  return (
    <div className="agent-working" aria-busy="true" aria-label="Genie is answering">
      <div className="aw-question">
        <span className="aw-question-label">You asked</span>
        <p className="aw-question-text">{question}</p>
      </div>

      <div className="aw-head">
        <span className="aw-title">Genie is working</span>
        <span className="aw-clock">{elapsed.toFixed(1)}s</span>
      </div>

      <ol className="aw-stages">
        {STAGES.map((stage, i) => {
          const state = i < activeIndex ? 'done' : i === activeIndex ? 'active' : 'todo';
          return (
            <li key={stage.label} className={`aw-stage aw-stage--${state}`}>
              <span className="aw-dot" aria-hidden="true">
                {state === 'done' ? (
                  <svg viewBox="0 0 10 10">
                    <path d="M2 5.2L4.2 7.4 8 3" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                ) : null}
              </span>
              <span className="aw-stage-label">{stage.label}</span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
