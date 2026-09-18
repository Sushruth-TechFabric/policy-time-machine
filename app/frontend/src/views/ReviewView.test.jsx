import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

vi.mock('../api/client.js', async () => {
  const mockData = await import('../api/mockData.js');
  return {
    MOCK_MODE: true,
    getTimeline: mockData.mockGetTimeline,
    getPatterns: mockData.mockGetPatterns,
    getReviewQueue: mockData.mockGetReviewQueue,
    getReviewClaim: mockData.mockGetReviewClaim,
    prepareBrief: mockData.mockPrepareBrief,
    getRun: mockData.mockGetRun,
    recordDisposition: mockData.mockRecordDisposition,
  };
});

const { default: ReviewView } = await import('./ReviewView.jsx');

describe('ReviewView (mock mode)', () => {
  it('lists the queue with the routing rule and opens a Brief with four sections', async () => {
    render(<ReviewView selectedClaimId={null} onSelectClaim={() => {}} onOpenAsInvestigation={() => {}} />);
    await waitFor(() => expect(screen.getByText('High-severity claim reported in the last 90 days.')).toBeInTheDocument());
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
    await waitFor(() => expect(screen.getByText(/Working Branch created/)).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText(/Working Branch deleted by the harness/)).toBeInTheDocument(), { timeout: 4000 });
  });

  it('"Open as investigation" hands the frequency question up', async () => {
    const open = vi.fn();
    render(<ReviewView selectedClaimId="C-10000001" onSelectClaim={() => {}} onOpenAsInvestigation={open} />);
    await waitFor(() => expect(screen.getAllByRole('button', { name: 'Open as investigation' }).length).toBe(4));
    fireEvent.click(screen.getAllByRole('button', { name: 'Open as investigation' })[2]);
    expect(open).toHaveBeenCalledWith(expect.stringMatching(/compared|versus/i));
  });
});
