import TabBar from './TabBar.jsx';
import './AppHeader.css';

/** The brand line and the investigation tab strip — rendered once, above
 *  whichever workspace is active. */
export default function AppHeader({ tabs, activeId, onSelect, onClose, onNew }) {
  return (
    <div className="app-header">
      <div className="brand-row">
        <div className="brand">
          <svg className="brand-mark" viewBox="0 0 24 24" aria-hidden="true">
            <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeWidth="2" />
            <path d="M12 7v5l3.2 2.4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          </svg>
          <span className="brand-name">Policy Time Machine</span>
          <span className="brand-sub">Genie-powered policy history investigation</span>
        </div>
      </div>
      <TabBar tabs={tabs} activeId={activeId} onSelect={onSelect} onClose={onClose} onNew={onNew} />
    </div>
  );
}
