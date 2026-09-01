import { useCallback, useEffect, useRef, useState } from 'react';
import './App.css';
import AppHeader from './components/AppHeader.jsx';
import InvestigationWorkspace from './components/InvestigationWorkspace.jsx';

const TABS_KEY = 'ptm.tabs.v1';
const investigationKey = (tabId) => `ptm.inv.${tabId}.v1`;

function loadStoredTabs() {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(TABS_KEY));
    if (!Array.isArray(parsed?.tabs) || parsed.tabs.length === 0) return null;
    const tabs = parsed.tabs.filter((t) => typeof t.id === 'number');
    if (tabs.length === 0) return null;
    const activeId = tabs.some((t) => t.id === parsed.activeId) ? parsed.activeId : tabs[0].id;
    return { tabs, activeId };
  } catch {
    return null;
  }
}

/**
 * The app is a strip of investigation tabs over independent workspaces.
 * Every workspace stays mounted — hidden, not unmounted — so each tab keeps
 * its Genie conversation, trail, and timelines intact while the user works
 * across several lines of enquiry in parallel.
 */
function App() {
  const [initial] = useState(() => loadStoredTabs() ?? { tabs: [{ id: 1, label: null }], activeId: 1 });
  const [tabs, setTabs] = useState(initial.tabs);
  const [activeId, setActiveId] = useState(initial.activeId);
  const nextIdRef = useRef(initial.tabs.reduce((m, t) => Math.max(m, t.id), 1) + 1);

  useEffect(() => {
    try {
      window.localStorage.setItem(TABS_KEY, JSON.stringify({ tabs, activeId }));
    } catch {
      /* storage unavailable — tabs stay in-memory only */
    }
  }, [tabs, activeId]);

  const addTab = useCallback(() => {
    const id = nextIdRef.current;
    nextIdRef.current += 1;
    setTabs((t) => [...t, { id, label: null }]);
    setActiveId(id);
  }, []);

  const closeTab = useCallback(
    (id) => {
      try {
        window.localStorage.removeItem(investigationKey(id));
      } catch {
        /* nothing to clean up */
      }
      setTabs((t) => {
        if (t.length <= 1) return t;
        const index = t.findIndex((tab) => tab.id === id);
        const next = t.filter((tab) => tab.id !== id);
        setActiveId((current) => {
          if (current !== id) return current;
          const neighbour = next[Math.min(index, next.length - 1)];
          return neighbour.id;
        });
        return next;
      });
    },
    [],
  );

  // Auto-naming from the opening question; never overwrites a name the
  // user typed themselves.
  const setLabel = useCallback((id, label) => {
    setTabs((t) => (t.some((tab) => tab.id === id && !tab.custom && tab.label !== label)
      ? t.map((tab) => (tab.id === id && !tab.custom ? { ...tab, label } : tab))
      : t));
  }, []);

  const renameTab = useCallback((id, label) => {
    const trimmed = label.trim();
    setTabs((t) => t.map((tab) => (tab.id === id
      ? trimmed
        ? { ...tab, label: trimmed, custom: true }
        // Clearing the name reverts to the auto-name path immediately: the
        // label must go too, or the stale custom text keeps rendering.
        : { ...tab, label: null, custom: false }
      : tab)));
  }, []);

  return (
    <div className="app">
      <AppHeader
        tabs={tabs}
        activeId={activeId}
        onSelect={setActiveId}
        onClose={closeTab}
        onNew={addTab}
        onRename={renameTab}
      />
      {tabs.map((tab) => (
        <div key={tab.id} className="tab-panel" hidden={tab.id !== activeId}>
          <InvestigationWorkspace
            storageKey={investigationKey(tab.id)}
            onLabel={(label) => setLabel(tab.id, label)}
            onNewInvestigation={addTab}
          />
        </div>
      ))}
    </div>
  );
}

export default App;
