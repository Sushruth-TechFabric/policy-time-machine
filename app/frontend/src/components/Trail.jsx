import './Trail.css';

/**
 * The investigation trail — one numbered node per Genie turn, in the order
 * they were asked (the numbering is the sequence of the enquiry). Clicking a
 * node restores that turn's cached view: no re-fetch, no new thread message
 * (ADR-0011). Rendered only once the investigation has a first turn.
 */
export default function Trail({ trail, activeIndex, onSelect }) {
  if (trail.length === 0) return null;

  return (
    <nav className="trail" aria-label="Investigation trail">
      <span className="trail-caption">Investigation</span>
      {trail.map((node, i) => (
        <span className="trail-item" key={node.id}>
          {i > 0 && <span className="trail-sep" aria-hidden="true" />}
          <button
            type="button"
            className={`trail-node${i === activeIndex ? ' active' : ''}`}
            onClick={() => onSelect(i)}
            title={node.question}
          >
            <span className="trail-num">{i + 1}</span>
            {node.label}
          </button>
        </span>
      ))}
    </nav>
  );
}
