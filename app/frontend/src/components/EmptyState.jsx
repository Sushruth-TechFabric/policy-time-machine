import './EmptyState.css';

const CAPABILITIES = [
  {
    title: 'Spot changes before claims',
    body: 'Find policies whose coverage rose or deductible fell in the days before a loss — with the timing laid out.',
  },
  {
    title: "Follow a policy's story",
    body: 'Mention a policy id and its full history opens alongside: every change, renewal, and claim on one dated timeline.',
  },
  {
    title: 'Compare cohorts fairly',
    body: 'Rates always arrive with both groups and their sizes, so a difference is never shown without its context.',
  },
  {
    title: 'Find similar histories',
    body: 'Surface policies whose change-and-claim behaviour looks alike, ranked, with the reasons they match.',
  },
  {
    title: 'Verify every answer',
    body: 'Each result carries the exact SQL that produced it and how your question was read — inspect it, copy it, rerun it.',
  },
];

const FLOW = ['Your question', 'AI analyst (Genie)', 'SQL', 'Your policy data', 'Answer + evidence'];

function FlowDiagram() {
  return (
    <div className="flow-diagram" role="img" aria-label="How an answer is produced: your question goes to the AI analyst (Databricks Genie), which writes SQL, runs it against your policy data, and returns the answer with evidence">
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
      <p className="es-eyebrow">Auto policy investigation workbench</p>
      <h1 className="es-title">Understand how policies change — and what follows.</h1>
      <p className="es-lede">
        Ask about coverage changes, claims, and policyholder history in plain English. Answers come back
        as data you can inspect, chart, and verify — every one backed by the SQL that produced it.
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
