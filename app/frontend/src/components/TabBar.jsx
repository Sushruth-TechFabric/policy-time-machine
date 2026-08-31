import './TabBar.css';

/**
 * One tab per open investigation. Each tab is a live, independent Genie
 * conversation — switching never resets anything, closing discards that
 * conversation only. The last tab can't be closed; a fresh one is always
 * one click away.
 */
export default function TabBar({ tabs, activeId, onSelect, onClose, onNew }) {
  return (
    <div className="tab-bar" role="tablist" aria-label="Open investigations">
      {tabs.map((tab, i) => (
        <div
          key={tab.id}
          className={`tab${tab.id === activeId ? ' tab--active' : ''}`}
          role="tab"
          aria-selected={tab.id === activeId}
        >
          <button type="button" className="tab-label" onClick={() => onSelect(tab.id)} title={tab.label ?? undefined}>
            {tab.label ?? `Investigation ${i + 1}`}
          </button>
          {tabs.length > 1 && (
            <button
              type="button"
              className="tab-close"
              onClick={() => onClose(tab.id)}
              aria-label={`Close ${tab.label ?? `Investigation ${i + 1}`}`}
            >
              ×
            </button>
          )}
        </div>
      ))}
      <button type="button" className="tab-new" onClick={onNew} aria-label="Open a new investigation tab">
        +
      </button>
    </div>
  );
}
