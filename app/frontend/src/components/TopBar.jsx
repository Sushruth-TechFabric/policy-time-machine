import { useState } from 'react';
import './TopBar.css';

/**
 * Region 1's input line: the investigation bar plus the always-visible
 * New investigation control (docs/specs/06-ux-specification.md §1).
 * Near-stock effort per the component inventory (§7).
 */
export default function TopBar({ onSubmit, onNewInvestigation, disabled, highlightReset }) {
  const [value, setValue] = useState('');

  function handleSubmit(e) {
    e.preventDefault();
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSubmit(trimmed);
    setValue('');
  }

  return (
    <div className="top-bar">
      <form className="top-bar-form" onSubmit={handleSubmit}>
        <input
          className="top-bar-input"
          type="text"
          placeholder="Ask about policy history..."
          value={value}
          onChange={(e) => setValue(e.target.value)}
          disabled={disabled}
          aria-label="Ask about policy history"
        />
      </form>
      <button
        type="button"
        className={`new-investigation-btn${highlightReset ? ' highlight' : ''}`}
        onClick={onNewInvestigation}
      >
        New investigation
      </button>
    </div>
  );
}
