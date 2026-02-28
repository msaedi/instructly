import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import SkipToMainLink from '@/components/SkipToMainLink';

describe('SkipToMainLink', () => {
  it('renders a skip link and moves focus to #main-content when activated', async () => {
    const user = userEvent.setup();

    render(
      <>
        <SkipToMainLink />
        <main id="main-content" tabIndex={-1}>
          Main content
        </main>
      </>
    );

    const skipLink = screen.getByRole('link', { name: /skip to main content/i });
    expect(skipLink).toHaveAttribute('href', '#main-content');

    skipLink.focus();
    expect(skipLink).toHaveFocus();

    await user.click(skipLink);

    await waitFor(() => {
      expect(screen.getByRole('main')).toHaveFocus();
    });
  });
});
