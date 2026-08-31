import './EmptyState.css';

const CAPABILITIES = [
  {
    title: 'Ask in plain English',
    body: 'Genie turns your question into SQL against the gold policy-history tables — no query writing needed.',
  },
  {
    title: 'Follow up naturally',
    body: 'Each investigation is one Genie conversation. "Now only the severe ones" refines the previous answer.',
  },
  {
    title: 'Every answer shows its evidence',
    body: 'The exact SQL Genie generated, its reading of your question, and the row count ship with every result.',
  },
  {
    title: 'Timelines, patterns & similar policies',
    body: 'Mention a policy id and its full change-and-claim timeline opens alongside, with noteworthy patterns marked.',
  },
  {
    title: 'Ambiguity gets a question back',
    body: 'When a question can be read two ways, Genie asks for the missing detail instead of guessing.',
  },
];

const FLOW = ['Your question', 'Genie space', 'Generated SQL', 'SQL warehouse', 'Answer + evidence'];

function FlowDiagram() {
  return (
    <div className="flow-diagram" role="img" aria-label="How an answer is produced: your question goes to the Genie space, which generates SQL, runs it on the SQL warehouse, and returns the answer with evidence">
      {FLOW.map((step, i) => (
        <span key={step} className="flow-step-wrap">
          {i > 0 && (
            <svg className="flow-arrow" viewBox="0 0 24 10" aria-hidden="true">
              <path d="M0 5h20m0 0l-4-4m4 4l-4 4" fill="none" stroke="currentColor" strokeWidth="1.5" />
            </svg>
          )}
          <span className={`flow-step${i === 1 ? ' flow-step--agent' : ''}`}>{step}</span>
        </span>
      ))}
    </div>
  );
}

/**
 * The opening screen: what this app is, what the Genie agent can do here,
 * and how an answer is produced. The starter chips below it are the
 * invitation to act.
 */
export default function EmptyState() {
  return (
    <div className="empty-state">
      <p className="es-eyebrow">Databricks AI/BI Genie · auto policy history</p>
      <h1 className="es-title">Ask your policy data anything.</h1>
      <p className="es-lede">
        Policy Time Machine investigates how policies changed over time and how those changes relate to
        claims — every answer backed by the SQL that produced it.
      </p>

      <FlowDiagram />

      <div className="es-grid">
        {CAPABILITIES.map((c) => (
          <div className="es-card" key={c.title}>
            <h2 className="es-card-title">{c.title}</h2>
            <p className="es-card-body">{c.body}</p>
          </div>
        ))}
      </div>

      <p className="es-hint">Start with a question below, or type your own.</p>
    </div>
  );
}
