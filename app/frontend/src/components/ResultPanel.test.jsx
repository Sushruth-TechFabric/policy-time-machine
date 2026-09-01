import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import ResultPanel from './ResultPanel.jsx';

describe('ResultPanel no_access state', () => {
  it('renders the quiet governance copy, not an error', () => {
    const node = {
      question: 'Show policies where coverage increased',
      genie: { status: 'no_access', columns: [], rows: [], error: 'You don’t have access…' },
    };
    render(<ResultPanel node={node} loading={false} onPolicyClick={() => {}} />);

    expect(screen.getByText(/don't have access to this data/i)).toBeInTheDocument();
    expect(screen.getByText(/workspace admin/i)).toBeInTheDocument();
    expect(screen.queryByText(/could not answer/i)).not.toBeInTheDocument();
  });
});
