import { useState } from 'react';
import './TopBar.css';

/**
 * Region 1 — the brand line and the ask bar. The ask bar is the app's one
 * command surface: typed questions and chip clicks both land here
 * (docs/specs/06-ux-specification.md §1).
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
    <header className="top-bar">
      <div className="brand-row">
        <div className="brand">
          <svg className="brand-mark" viewBox="0 0 24 24" aria-hidden="true">
            <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeWidth="2" />
            <path d="M12 7v5l3.2 2.4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          </svg>
          <span className="brand-name">Policy Time Machine</span>
          <span className="brand-sub">Genie-powered policy history investigation</span>
        </div>
        <button
          type="button"
          className={`new-investigation-btn${highlightReset ? ' highlight' : ''}`}
          onClick={onNewInvestigation}
        >
          New investigation
        </button>
      </div>

      <form className="ask-bar" onSubmit={handleSubmit}>
        <svg className="ask-icon" viewBox="0 0 20 20" aria-hidden="true">
          <circle cx="9" cy="9" r="6" fill="none" stroke="currentColor" strokeWidth="1.8" />
          <path d="M13.5 13.5L17 17" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
        </svg>
        <input
          className="ask-input"
          type="text"
          placeholder="Ask about policy history — coverage changes, claims, patterns, similar policies…"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          disabled={disabled}
          aria-label="Ask about policy history"
        />
        <button type="submit" className="ask-submit" disabled={disabled || !value.trim()}>
          {disabled ? 'Genie is working…' : 'Ask Genie'}
        </button>
      </form>
    </header>
  );
}
