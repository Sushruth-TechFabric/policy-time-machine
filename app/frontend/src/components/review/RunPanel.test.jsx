import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, render, screen } from '@testing-library/react';

const getRun = vi.fn();
vi.mock('../../api/client.js', () => ({ getRun: (...args) => getRun(...args) }));

const { default: RunPanel } = await import('./RunPanel.jsx');

/** Drain the poll loop: each tick resolves a pending getRun, then schedules
 *  the next timer. */
async function advance(ms) {
  await act(async () => { await vi.advanceTimersByTimeAsync(ms); });
}

describe('RunPanel', () => {
  beforeEach(() => { vi.useFakeTimers(); getRun.mockReset(); });
  afterEach(() => { vi.useRealTimers(); });

  it('stops polling a Run the record never held and says so', async () => {
    getRun.mockRejectedValue(new Error('Request failed (404)'));
    const onFinished = vi.fn();
    render(<RunPanel runId="run-ghost" onFinished={onFinished} onRetry={() => {}} />);

    // 15 consecutive misses, 2s apart, plus slack for the first immediate poll.
    await advance(40000);

    expect(screen.getByText(/No Run record was found for this request/)).toBeInTheDocument();
    expect(screen.queryByText('The harness is working')).not.toBeInTheDocument();
    expect(onFinished).toHaveBeenCalled();
    expect(getRun.mock.calls.length).toBe(15);
  });

  it('stays on screen for a failed Run and offers a retry instead of unmounting', async () => {
    getRun.mockResolvedValue({ run_id: 'run-1', status: 'failed', current_step: 'sequence', failure: 'Genie could not answer the question', branch_name: null, trace_id: null });
    const onFinished = vi.fn();
    const onRetry = vi.fn();
    render(<RunPanel runId="run-1" onFinished={onFinished} onRetry={onRetry} />);

    await advance(100);

    expect(screen.getByText('Run failed')).toBeInTheDocument();
    expect(screen.getByText('Genie could not answer the question')).toBeInTheDocument();
    // onFinished would unmount the panel, taking the failure with it.
    expect(onFinished).not.toHaveBeenCalled();
    await act(async () => { screen.getByRole('button', { name: 'Try again' }).click(); });
    expect(onRetry).toHaveBeenCalled();
  });

  it('hands a completed Run back to the view', async () => {
    getRun.mockResolvedValue({ run_id: 'run-1', status: 'completed', current_step: 'branch_deleted', failure: null, branch_name: null, trace_id: null });
    const onFinished = vi.fn();
    render(<RunPanel runId="run-1" onFinished={onFinished} onRetry={() => {}} />);

    await advance(100);

    expect(onFinished).toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument();
  });
});
