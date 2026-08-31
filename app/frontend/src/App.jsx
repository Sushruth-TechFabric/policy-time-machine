import { useCallback, useRef, useState } from 'react';
import './App.css';
import AppHeader from './components/AppHeader.jsx';
import InvestigationWorkspace from './components/InvestigationWorkspace.jsx';

/**
 * The app is a strip of investigation tabs over independent workspaces.
 * Every workspace stays mounted — hidden, not unmounted — so each tab keeps
 * its Genie conversation, trail, and timelines intact while the user works
 * across several lines of enquiry in parallel.
 */
function App() {
  const [tabs, setTabs] = useState([{ id: 1, label: null }]);
  const [activeId, setActiveId] = useState(1);
  const nextIdRef = useRef(2);

  const addTab = useCallback(() => {
    const id = nextIdRef.current;
    nextIdRef.current += 1;
    setTabs((t) => [...t, { id, label: null }]);
    setActiveId(id);
  }, []);

  const closeTab = useCallback(
    (id) => {
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

  const setLabel = useCallback((id, label) => {
    setTabs((t) => (t.some((tab) => tab.id === id && tab.label !== label)
      ? t.map((tab) => (tab.id === id ? { ...tab, label } : tab))
      : t));
  }, []);

  return (
    <div className="app">
      <AppHeader tabs={tabs} activeId={activeId} onSelect={setActiveId} onClose={closeTab} onNew={addTab} />
      {tabs.map((tab) => (
        <div key={tab.id} className="tab-panel" hidden={tab.id !== activeId}>
          <InvestigationWorkspace
            onLabel={(label) => setLabel(tab.id, label)}
            onNewInvestigation={addTab}
          />
        </div>
      ))}
    </div>
  );
}

export default App;
