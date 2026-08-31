import './Trail.css';

/**
 * The breadcrumb trail — the navigation (docs/specs/06-ux-specification.md
 * §1). Clicking a node restores a cached view: no re-fetch, no new thread
 * message (ADR-0011). Rendered only once the investigation has a first
 * turn; an empty trail before that would just be noise on an already-quiet
 * opening screen.
 */
export default function Trail({ trail, activeIndex, onSelect }) {
  if (trail.length === 0) return null;

  return (
    <nav className="trail" aria-label="Investigation trail">
      {trail.map((node, i) => (
        <span className="trail-item" key={node.id}>
          {i > 0 && <span className="trail-sep">›</span>}
          <button
            type="button"
            className={`trail-node${i === activeIndex ? ' active' : ''}`}
            onClick={() => onSelect(i)}
            title={node.question}
          >
            {node.label}
          </button>
        </span>
      ))}
    </nav>
  );
}
