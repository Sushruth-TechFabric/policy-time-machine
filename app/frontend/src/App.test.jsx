import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

vi.mock('./api/client.js', async () => {
  const mockData = await import('./api/mockData.js');
  return {
    MOCK_MODE: true,
    createInvestigation: mockData.mockCreateInvestigation,
    sendMessage: mockData.mockSendMessage,
    getTimeline: mockData.mockGetTimeline,
    getSimilar: mockData.mockGetSimilar,
    getPatterns: mockData.mockGetPatterns,
    getChips: mockData.mockGetChips,
  };
});

const { default: App } = await import('./App.jsx');

async function ask(question) {
  const input = screen.getByLabelText('Ask about policy history');
  fireEvent.change(input, { target: { value: question } });
  fireEvent.submit(input.closest('form'));
}

describe('App smoke test (mock mode)', () => {
  it('opens on a blank result panel with three starter chips and no timeline', async () => {
    render(<App />);
    expect(screen.queryByText(/^Timeline$/)).not.toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getAllByRole('button', { name: /./ }).filter((b) => b.className === 'chip').length).toBeGreaterThanOrEqual(3);
    });
  });

  it('P-18492 fixture renders as grouped endorsement cards, a distinct claim card, and a severity badge', async () => {
    render(<App />);
    await ask('What changed on P-18492 in the last year?');

    // Timeline resolves and opens the 40/60 split.
    await waitFor(() => expect(screen.getByText('P-18492')).toBeInTheDocument());

    // The address change and COLL limit increase collapse into one
    // endorsement card with two deltas. (The fallback genie echo of this
    // policy's own history also lists these labels as table rows, so the
    // text appears more than once on screen — assert presence, not count.)
    expect(await screen.findByText('2 changes · one endorsement')).toBeInTheDocument();
    expect(screen.getAllByText('Address changed').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/Collision limit increased/).length).toBeGreaterThanOrEqual(1);

    // The claim renders as its own card carrying the severity band.
    expect(screen.getByText('$24,700')).toBeInTheDocument();
    expect(screen.getByText('severe')).toBeInTheDocument();
  });

  it('an unknown policy id gets an explicit not-found state, never a blank timeline', async () => {
    render(<App />);
    await ask('What changed on P-18499?');

    expect(await screen.findByText(/No policy P-18499 found/)).toBeInTheDocument();
  });

  it('zero detected policy ids keeps the result panel full width (no timeline region content)', async () => {
    render(<App />);
    await ask('Which material changes happen most frequently before high-severity claims?');

    await waitFor(() => expect(document.querySelector('.result-row-count')).not.toBeNull());
    expect(screen.queryByText(/^Timeline$/)).not.toBeInTheDocument();
  });

  it('the evidence drawer is collapsed by default and expands to show the generated SQL', async () => {
    render(<App />);
    await ask('Show policies where coverage increased within 30 days before a claim.');

    const toggle = await screen.findByText(/Evidence: 47 rows · view query/);
    expect(screen.queryByText(/SELECT/)).not.toBeInTheDocument();
    fireEvent.click(toggle);
    expect(await screen.findByText(/SELECT/)).toBeInTheDocument();
  });
});
