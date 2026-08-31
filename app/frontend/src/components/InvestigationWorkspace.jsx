import { useEffect } from 'react';
import TopBar from './TopBar.jsx';
import Trail from './Trail.jsx';
import Timeline from './Timeline.jsx';
import ResultPanel from './ResultPanel.jsx';
import ChipRow from './ChipRow.jsx';
import EmptyState from './EmptyState.jsx';
import { useInvestigation } from '../hooks/useInvestigation.js';

/**
 * One investigation — one Genie conversation, one trail, one timeline
 * (docs/specs/06-ux-specification.md §1). The app mounts one workspace per
 * tab and hides the inactive ones, so every tab keeps its full state:
 * switching tabs never re-fetches and never touches another tab's
 * conversation (ADR-0011 per tab).
 */
export default function InvestigationWorkspace({ onLabel, onNewInvestigation }) {
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
  } = useInvestigation();

  // The tab names itself after the opening question.
  const firstLabel = trail.length > 0 ? trail[0].label : null;
  useEffect(() => {
    onLabel?.(firstLabel);
  }, [firstLabel, onLabel]);

  const split = Boolean(displayedTimelineId);
  const showShowcase = trail.length === 0 && !genieLoading && !displayedTimelineId;

  return (
    <div className="workspace">
      <TopBar
        onSubmit={submitQuestion}
        onNewInvestigation={onNewInvestigation}
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
