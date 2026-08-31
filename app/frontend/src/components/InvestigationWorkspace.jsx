import { useCallback, useEffect, useRef } from 'react';
import TopBar from './TopBar.jsx';
import Trail from './Trail.jsx';
import Timeline from './Timeline.jsx';
import ResultPanel from './ResultPanel.jsx';
import AgentWorking from './AgentWorking.jsx';
import ChipRow from './ChipRow.jsx';
import EmptyState from './EmptyState.jsx';
import { useInvestigation } from '../hooks/useInvestigation.js';

/**
 * One investigation — one Genie conversation, one trail, one timeline
 * (docs/specs/06-ux-specification.md §1). Turns render as a running
 * conversation: every earlier answer stays on screen and a new question
 * appends below it. The app mounts one workspace per tab and hides the
 * inactive ones, so every tab keeps its full state across switches — and
 * the trail itself is persisted, so it survives a page refresh too.
 */
export default function InvestigationWorkspace({ storageKey, onLabel, onNewInvestigation }) {
  const {
    trail,
    activeIndex,
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
  } = useInvestigation(storageKey);

  // The tab names itself after the opening question.
  const firstLabel = trail.length > 0 ? trail[0].label : null;
  useEffect(() => {
    onLabel?.(firstLabel);
  }, [firstLabel, onLabel]);

  // Follow the conversation: a new turn (or the working card) scrolls into
  // view as it appears.
  const conversationEndRef = useRef(null);
  const lastTrailLength = useRef(trail.length);
  useEffect(() => {
    const grew = trail.length > lastTrailLength.current;
    lastTrailLength.current = trail.length;
    if (grew || genieLoading) {
      conversationEndRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'end' });
    }
  }, [trail.length, genieLoading]);

  const conversationRef = useRef(null);
  const selectTurn = useCallback(
    (index) => {
      goToNode(index);
      conversationRef.current
        ?.querySelector(`[data-turn="${index}"]`)
        ?.scrollIntoView?.({ behavior: 'smooth', block: 'start' });
    },
    [goToNode],
  );

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
      <Trail trail={trail} activeIndex={activeIndex} onSelect={selectTurn} />
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
            <div className="conversation" ref={conversationRef}>
              {trail.map((node, i) => (
                <div
                  key={node.id}
                  data-turn={i}
                  className={`conversation-turn${i === activeIndex ? ' conversation-turn--active' : ''}`}
                >
                  <ResultPanel node={node} loading={false} onPolicyClick={openPolicyTimeline} />
                </div>
              ))}
              {genieLoading && (
                <div className="conversation-turn">
                  <div className="result-panel">
                    <AgentWorking question={pendingQuestion ?? 'Working on your question'} />
                  </div>
                </div>
              )}
              <div ref={conversationEndRef} aria-hidden="true" />
            </div>
          )}
          <ChipRow chips={chips} onSelect={submitQuestion} disabled={genieLoading} />
        </div>
      </div>
    </div>
  );
}
