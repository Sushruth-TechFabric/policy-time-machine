import './App.css';
import TopBar from './components/TopBar.jsx';
import Trail from './components/Trail.jsx';
import Timeline from './components/Timeline.jsx';
import ResultPanel from './components/ResultPanel.jsx';
import ChipRow from './components/ChipRow.jsx';
import { useInvestigation } from './hooks/useInvestigation.js';

/**
 * One screen, three regions, nothing else (docs/specs/06-ux-specification.md
 * §1). The fixed ~40/60 split exists only when a timeline is showing —
 * otherwise the result panel takes the full width (§2).
 */
function App() {
  const {
    trail,
    activeIndex,
    activeNode,
    displayedTimelineId,
    displayedTimeline,
    genieLoading,
    bootError,
    highlightReset,
    chips,
    submitQuestion,
    openPolicyTimeline,
    findSimilar,
    goToNode,
    startNewInvestigation,
  } = useInvestigation();

  const split = Boolean(displayedTimelineId);

  return (
    <div className="app">
      <TopBar
        onSubmit={submitQuestion}
        onNewInvestigation={startNewInvestigation}
        disabled={genieLoading}
        highlightReset={highlightReset}
      />
      <Trail trail={trail} activeIndex={activeIndex} onSelect={goToNode} />
      {bootError && <div className="app-boot-error">{bootError}</div>}

      <div className={`app-body ${split ? 'split' : 'full'}`}>
        <div className="timeline-region">
          <Timeline
            policyId={displayedTimelineId}
            data={displayedTimeline}
            onFindSimilar={findSimilar}
            findSimilarBusy={genieLoading}
          />
        </div>
        <div className="result-region">
          <ResultPanel node={activeNode} loading={genieLoading} onPolicyClick={openPolicyTimeline} />
          <ChipRow chips={chips} onSelect={submitQuestion} disabled={genieLoading} />
        </div>
      </div>
    </div>
  );
}

export default App;
