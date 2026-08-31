import { describe, expect, it, vi, beforeEach } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';

vi.mock('../api/client.js', async () => {
  const mockData = await import('../api/mockData.js');
  return {
    MOCK_MODE: true,
    createInvestigation: vi.fn(mockData.mockCreateInvestigation),
    sendMessage: vi.fn(mockData.mockSendMessage),
    getTimeline: vi.fn(mockData.mockGetTimeline),
    getSimilar: vi.fn(mockData.mockGetSimilar),
    getPatterns: vi.fn(mockData.mockGetPatterns),
    getChips: vi.fn(mockData.mockGetChips),
  };
});

// Imported after the mock so the hook picks up the mocked client.
const { useInvestigation } = await import('./useInvestigation.js');
const client = await import('../api/client.js');

beforeEach(() => {
  client.createInvestigation.mockClear();
  client.sendMessage.mockClear();
  client.getTimeline.mockClear();
  client.getPatterns.mockClear();
  client.getSimilar.mockClear();
  client.getChips.mockClear();
});

describe('useInvestigation — breadcrumb cached-view restore (ADR-0011)', () => {
  it('never re-fetches a policy timeline that is already cached when a breadcrumb node is restored', async () => {
    const { result } = renderHook(() => useInvestigation());

    await act(async () => {
      await result.current.submitQuestion('What changed on P-18492 in the last year?');
    });
    await waitFor(() => expect(result.current.displayedTimelineId).toBe('P-18492'));
    expect(client.getTimeline).toHaveBeenCalledTimes(1);
    expect(client.getTimeline).toHaveBeenCalledWith('P-18492');

    await act(async () => {
      await result.current.submitQuestion('What changed on P-20114 in the last year?');
    });
    await waitFor(() => expect(result.current.displayedTimelineId).toBe('P-20114'));
    expect(client.getTimeline).toHaveBeenCalledTimes(2);

    // Restore the first trail node. This must not re-fetch P-18492's
    // timeline, and must not send a new message.
    const sendMessageCallsBeforeRestore = client.sendMessage.mock.calls.length;
    act(() => {
      result.current.goToNode(0);
    });

    expect(result.current.displayedTimelineId).toBe('P-18492');
    expect(result.current.activeNode.question).toBe('What changed on P-18492 in the last year?');
    expect(client.getTimeline).toHaveBeenCalledTimes(2); // unchanged — no re-fetch
    expect(client.sendMessage).toHaveBeenCalledTimes(sendMessageCallsBeforeRestore); // unchanged — no new message
  });

  it('restoring a node shows that node\'s own trail label without touching trail length', async () => {
    const { result } = renderHook(() => useInvestigation());

    await act(async () => {
      await result.current.submitQuestion('Show policies where coverage increased within 30 days before a claim.');
    });
    await act(async () => {
      await result.current.submitQuestion('What changed on P-18492 in the last year?');
    });

    expect(result.current.trail).toHaveLength(2);

    act(() => {
      result.current.goToNode(0);
    });

    expect(result.current.trail).toHaveLength(2); // restoring never grows the trail
    expect(result.current.activeIndex).toBe(0);
    expect(result.current.displayedTimelineId).toBeNull(); // that node's own question had no policy id
  });
});

describe('useInvestigation — New investigation reset', () => {
  it('clears the trail, active timeline and highlight so the next question starts a fresh investigation', async () => {
    const { result } = renderHook(() => useInvestigation());

    await act(async () => {
      await result.current.submitQuestion('What changed on P-18492 in the last year?');
    });
    await act(async () => {
      await result.current.submitQuestion('What changed on P-18499?'); // unknown id -> highlightReset
    });
    expect(result.current.trail).toHaveLength(2);
    expect(result.current.highlightReset).toBe(true);

    act(() => {
      result.current.startNewInvestigation();
    });

    expect(result.current.trail).toEqual([]);
    expect(result.current.activeIndex).toBe(-1);
    expect(result.current.activeNode).toBeNull();
    expect(result.current.displayedTimelineId).toBeNull();
    expect(result.current.highlightReset).toBe(false);

    // A fresh question after reset produces exactly one node, not three.
    await act(async () => {
      await result.current.submitQuestion('What changed on P-11907 in the last year?');
    });
    expect(result.current.trail).toHaveLength(1);
    expect(result.current.displayedTimelineId).toBe('P-11907');
  });
});

describe('useInvestigation — panel-behaviour routing (docs/specs/06-ux-specification.md §2)', () => {
  it('opens no timeline when zero policy ids are detected', async () => {
    const { result } = renderHook(() => useInvestigation());
    await act(async () => {
      await result.current.submitQuestion('Which material changes happen most frequently before claims?');
    });
    expect(result.current.displayedTimelineId).toBeNull();
  });

  it('opens no timeline when several policy ids are detected', async () => {
    const { result } = renderHook(() => useInvestigation());
    await act(async () => {
      await result.current.submitQuestion('Compare P-18492 and P-20114.');
    });
    expect(result.current.displayedTimelineId).toBeNull();
  });

  it('shows an explicit not-found state for a single unknown policy id, never an empty timeline', async () => {
    const { result } = renderHook(() => useInvestigation());
    await act(async () => {
      await result.current.submitQuestion('What changed on P-18499?');
    });
    await waitFor(() => expect(result.current.displayedTimeline).not.toBeNull());
    expect(result.current.displayedTimelineId).toBe('P-18499');
    expect(result.current.displayedTimeline.found).toBe(false);
  });

  it('a policy row click opens that timeline without growing the trail', async () => {
    const { result } = renderHook(() => useInvestigation());
    await act(async () => {
      await result.current.submitQuestion('Show policies where coverage increased within 30 days before a claim.');
    });
    const trailLengthBefore = result.current.trail.length;

    act(() => {
      result.current.openPolicyTimeline('P-11907');
    });
    await waitFor(() => expect(result.current.displayedTimelineId).toBe('P-11907'));

    expect(result.current.trail).toHaveLength(trailLengthBefore);
  });
});
