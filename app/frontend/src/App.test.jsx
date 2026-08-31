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

  it('a second tab opens with fresh state and the first tab keeps its result', async () => {
    render(<App />);
    await ask('Show policies where coverage increased within 30 days before a claim.');
    await waitFor(() => expect(document.querySelector('.result-row-count')).not.toBeNull());

    fireEvent.click(screen.getByRole('button', { name: 'Open a new investigation tab' }));

    // Two tabs exist; the new one is active and shows the showcase, while the
    // first tab's answer card stays mounted but hidden.
    expect(screen.getAllByRole('tab')).toHaveLength(2);
    expect(screen.getByText('Ask your policy data anything.')).toBeVisible();
    expect(document.querySelector('.result-row-count')).not.toBeVisible();

    // Switching back restores the first tab's result untouched.
    fireEvent.click(screen.getByRole('button', { name: 'Coverage up before claims' }));
    expect(document.querySelector('.result-row-count')).toBeVisible();
  });

  it('double-clicking a tab renames it, and the typed name survives the auto-name', async () => {
    render(<App />);

    fireEvent.doubleClick(screen.getByRole('button', { name: /Investigation 1/ }));
    const input = screen.getByLabelText('Rename investigation');
    fireEvent.change(input, { target: { value: 'Fraud sweep Q3' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(screen.getByRole('button', { name: /Fraud sweep Q3/ })).toBeInTheDocument();

    // Asking a question would normally auto-name the tab — a typed name wins.
    await ask('Show policies where coverage increased within 30 days before a claim.');
    await waitFor(() => expect(document.querySelector('.result-row-count')).not.toBeNull());
    expect(screen.getByRole('button', { name: /Fraud sweep Q3/ })).toBeInTheDocument();
    expect(screen.queryByRole('tab', { name: /Coverage up before claims/ })).not.toBeInTheDocument();
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
