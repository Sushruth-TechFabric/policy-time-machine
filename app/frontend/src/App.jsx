import './App.css';
import TopBar from './components/TopBar.jsx';
import Trail from './components/Trail.jsx';
import Timeline from './components/Timeline.jsx';
import ResultPanel from './components/ResultPanel.jsx';
import ChipRow from './components/ChipRow.jsx';
import EmptyState from './components/EmptyState.jsx';
import { useInvestigation } from './hooks/useInvestigation.js';

/**
 * One screen, three regions, nothing else (docs/specs/06-ux-specification.md
 * §1). The fixed ~40/60 split exists only when a timeline is showing —
 * otherwise the result panel takes the full width (§2). Before the first
 * turn, the result region carries the capability showcase instead.
 */
function App() {
  const {
    trail,
    activeIndex,
    activeNode,
    displayedTimelineId,
    displayedTimeline,
    genieLoading,
    pendingQuestion,
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
  const showShowcase = trail.length === 0 && !genieLoading && !displayedTimelineId;

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
          {showShowcase ? (
            <EmptyState />
          ) : (
            <ResultPanel
              node={activeNode}
              loading={genieLoading}
              pendingQuestion={pendingQuestion}
              onPolicyClick={openPolicyTimeline}
            />
          )}
          <ChipRow chips={chips} onSelect={submitQuestion} disabled={genieLoading} />
        </div>
      </div>
    </div>
  );
}

export default App;
