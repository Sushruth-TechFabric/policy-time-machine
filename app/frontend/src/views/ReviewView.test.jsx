import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

// Each client function is a spy over its mock-mode implementation, so a
// single test can override one (a denied timeline, a failed Run) without
// rewriting the fixture for everyone else.
vi.mock('../api/client.js', async () => {
  const mockData = await import('../api/mockData.js');
  return {
    MOCK_MODE: true,
    getTimeline: vi.fn(mockData.mockGetTimeline),
    getPatterns: vi.fn(mockData.mockGetPatterns),
    getReviewQueue: vi.fn(mockData.mockGetReviewQueue),
    getReviewClaim: vi.fn(mockData.mockGetReviewClaim),
    prepareBrief: vi.fn(mockData.mockPrepareBrief),
    getRun: vi.fn(mockData.mockGetRun),
    recordDisposition: vi.fn(mockData.mockRecordDisposition),
  };
});

const client = await import('../api/client.js');
const { default: ReviewView } = await import('./ReviewView.jsx');

describe('ReviewView (mock mode)', () => {
  afterEach(() => { vi.resetAllMocks(); });

  it('lists the queue with the routing rule and opens a Brief with four sections', async () => {
    render(<ReviewView selectedClaimId={null} onSelectClaim={() => {}} onOpenAsInvestigation={() => {}} />);
    await waitFor(() => expect(screen.getAllByText('High-severity claim reported in the last 90 days.')).toHaveLength(2));
    fireEvent.click(screen.getByRole('button', { name: /C-10000001/ }));
    await waitFor(() => expect(screen.getByText('The sequence')).toBeInTheDocument());
    expect(screen.getByText('The relevant changes')).toBeInTheDocument();
    expect(screen.getByText('How common this is')).toBeInTheDocument();
    expect(screen.getByText('Similar histories')).toBeInTheDocument();
    expect(screen.queryByText(/summary/i)).not.toBeInTheDocument();
  });

  it('shows a withheld sentence and lets the reviewer record a Disposition', async () => {
    render(<ReviewView selectedClaimId="C-10000001" onSelectClaim={() => {}} onOpenAsInvestigation={() => {}} />);
    await waitFor(() => expect(screen.getByText(/sentence withheld/i)).toBeInTheDocument());
    fireEvent.click(screen.getByRole('radio', { name: 'Nothing noteworthy' }));
    fireEvent.click(screen.getByRole('button', { name: 'Record disposition' }));
    await waitFor(() => expect(screen.getByText(/Recorded by/)).toBeInTheDocument());
  });

  it('starts a Run for a claim without a Brief and narrates the harness steps', async () => {
    render(<ReviewView selectedClaimId="C-10000002" onSelectClaim={() => {}} onOpenAsInvestigation={() => {}} />);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Prepare a Brief' })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'Prepare a Brief' }));
    // The branch suffix only renders once getRun has returned a run with a branch_name.
    await waitFor(() => expect(screen.getByText('Working Branch created: run-C-10000002')).toBeInTheDocument());
    // The Brief heading only renders once the mock Run reaches promoted/branch_deleted,
    // onFinished fires, and the detail reloads with a Brief.
    await waitFor(() => expect(screen.getByText('The sequence')).toBeInTheDocument(), { timeout: 5000 });
  });

  it('says the last Run failed when there is no Brief and no live Run', async () => {
    const base = await client.getReviewClaim('C-10000002');
    vi.mocked(client.getReviewClaim).mockImplementation(() => ({
      ...base,
      brief: null,
      active_run: null,
      // The failed Run requeued the claim and cleared active_run_id; last_run
      // is the only record of it.
      last_run: { run_id: 'run-old', claim_id: 'C-10000002', status: 'failed', failure: 'Genie could not answer the frequency question', started_at: '2026-09-17T07:00:00Z' },
    }));
    render(<ReviewView selectedClaimId="C-10000002" onSelectClaim={() => {}} onOpenAsInvestigation={() => {}} />);
    await waitFor(() => expect(screen.getByText(/The last Run failed: Genie could not answer the frequency question/)).toBeInTheDocument());
    expect(screen.getByRole('button', { name: 'Prepare a Brief' })).toBeInTheDocument();
  });

  it('"Open as investigation" hands the frequency question up', async () => {
    const open = vi.fn();
    render(<ReviewView selectedClaimId="C-10000001" onSelectClaim={() => {}} onOpenAsInvestigation={open} />);
    await waitFor(() => expect(screen.getAllByRole('button', { name: 'Open as investigation' }).length).toBe(4));
    fireEvent.click(screen.getAllByRole('button', { name: 'Open as investigation' })[2]);
    expect(open).toHaveBeenCalledWith(expect.stringMatching(/compared|versus/i));
  });
});
