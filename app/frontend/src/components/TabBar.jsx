import { useEffect, useRef, useState } from 'react';
import './TabBar.css';

function RenameInput({ initial, onCommit, onCancel }) {
  const [value, setValue] = useState(initial);
  const inputRef = useRef(null);

  useEffect(() => {
    inputRef.current?.select();
  }, []);

  return (
    <input
      ref={inputRef}
      className="tab-rename-input"
      value={value}
      aria-label="Rename investigation"
      onChange={(e) => setValue(e.target.value)}
      onBlur={() => onCommit(value)}
      onKeyDown={(e) => {
        if (e.key === 'Enter') onCommit(value);
        if (e.key === 'Escape') onCancel();
      }}
    />
  );
}

/**
 * One tab per open investigation. Each tab is a live, independent Genie
 * conversation — switching never resets anything, closing discards that
 * conversation only. Double-click a tab to name it yourself; a typed name
 * sticks and is never overwritten by the auto-name. The last tab can't be
 * closed; a fresh one is always one click away.
 */
export default function TabBar({ tabs, activeId, onSelect, onClose, onNew, onRename }) {
  const [editingId, setEditingId] = useState(null);

  return (
    <div className="tab-bar" role="tablist" aria-label="Open investigations">
      {tabs.map((tab, i) => {
        const displayLabel = tab.label ?? `Investigation ${i + 1}`;
        return (
          <div
            key={tab.id}
            className={`tab${tab.id === activeId ? ' tab--active' : ''}`}
            role="tab"
            aria-selected={tab.id === activeId}
          >
            {editingId === tab.id ? (
              <RenameInput
                initial={displayLabel}
                onCommit={(value) => {
                  // An untouched commit (double-click, then click away) must
                  // not turn the rendered fallback into a sticky custom label.
                  if (value !== displayLabel) onRename(tab.id, value);
                  setEditingId(null);
                }}
                onCancel={() => setEditingId(null)}
              />
            ) : (
              <button
                type="button"
                className="tab-label"
                onClick={() => onSelect(tab.id)}
                onDoubleClick={() => setEditingId(tab.id)}
                title={`${displayLabel} — double-click to rename`}
              >
                {displayLabel}
              </button>
            )}
            {tabs.length > 1 && editingId !== tab.id && (
              <button
                type="button"
                className="tab-close"
                onClick={() => onClose(tab.id)}
                aria-label={`Close ${displayLabel}`}
              >
                ×
              </button>
            )}
          </div>
        );
      })}
      <button type="button" className="tab-new" onClick={onNew} aria-label="Open a new investigation tab">
        +
      </button>
    </div>
  );
}
