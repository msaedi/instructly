import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import InviteByEmail from '../InviteByEmail';

jest.mock('sonner', () => ({
  toast: {
    success: jest.fn(),
    error: jest.fn(),
    info: jest.fn(),
  },
}));

jest.mock('@/features/shared/referrals/api', () => ({
  sendReferralInvites: jest.fn(),
}));

const { toast } = jest.requireMock('sonner') as {
  toast: {
    success: jest.Mock;
    error: jest.Mock;
    info: jest.Mock;
  };
};

const { sendReferralInvites } = jest.requireMock('@/features/shared/referrals/api') as {
  sendReferralInvites: jest.Mock;
};

describe('InviteByEmail', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    sendReferralInvites.mockResolvedValue(2);
  });

  it('sends invites and reports invalid addresses', async () => {
    const user = userEvent.setup();
    render(<InviteByEmail shareUrl="https://instainstru.com/r/abc123" fromName="Taylor" />);

    await user.type(
      screen.getByLabelText(/invite friends by email/i),
      'good@example.com bad-email also@ok.com good@example.com'
    );

    await user.click(screen.getByRole('button', { name: /send invites/i }));

    await waitFor(() => {
      expect(sendReferralInvites).toHaveBeenCalledWith({
        emails: ['good@example.com', 'also@ok.com'],
        shareUrl: 'https://instainstru.com/r/abc123',
        fromName: 'Taylor',
      });
    });

    expect(toast.success).toHaveBeenCalledWith('Invites sent to 2 addresses');
    expect(toast.info).toHaveBeenCalledWith('Skipped invalid: bad-email');
    expect(toast.error).not.toHaveBeenCalled();
    expect(screen.getByLabelText(/invite friends by email/i)).toHaveValue('');
  });

  // Lines 22-26: When shareUrl is missing but form is somehow submitted
  // Note: The input and button are disabled when shareUrl is empty, but we can
  // simulate the condition by calling submit directly on a form with empty shareUrl
  it('shows loading state when shareUrl is not available', () => {
    render(<InviteByEmail shareUrl="" />);

    // Input and button should be disabled
    expect(screen.getByLabelText(/invite friends by email/i)).toBeDisabled();
    expect(screen.getByRole('button', { name: /send invites/i })).toBeDisabled();
    // Status message should show loading
    expect(screen.getByText('Referral link loading…')).toBeInTheDocument();
  });

  // Lines 50-54: When no valid emails
  it('shows error when no valid emails are entered', async () => {
    const user = userEvent.setup();
    render(<InviteByEmail shareUrl="https://instainstru.com/r/abc123" />);

    await user.type(
      screen.getByLabelText(/invite friends by email/i),
      'invalid-email another-invalid'
    );

    await user.click(screen.getByRole('button', { name: /send invites/i }));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('Enter at least one valid email');
    });
    expect(sendReferralInvites).not.toHaveBeenCalled();
    expect(screen.getByText('Enter at least one valid email address.')).toBeInTheDocument();
  });

  // Lines 56-60: When more than 10 emails
  it('shows error when more than 10 valid emails are entered', async () => {
    const user = userEvent.setup();
    render(<InviteByEmail shareUrl="https://instainstru.com/r/abc123" />);

    const emails = Array.from({ length: 11 }, (_, i) => `user${i}@example.com`).join(' ');
    await user.type(screen.getByLabelText(/invite friends by email/i), emails);

    await user.click(screen.getByRole('button', { name: /send invites/i }));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('You can send up to 10 invites at a time.');
    });
    expect(sendReferralInvites).not.toHaveBeenCalled();
    expect(screen.getByText('Reduce your list to 10 email addresses or fewer.')).toBeInTheDocument();
  });

  // Lines 79-83: Error handling when API fails
  it('shows error message when API call fails', async () => {
    const user = userEvent.setup();
    sendReferralInvites.mockRejectedValue(new Error('Network error'));
    render(<InviteByEmail shareUrl="https://instainstru.com/r/abc123" />);

    await user.type(
      screen.getByLabelText(/invite friends by email/i),
      'test@example.com'
    );

    await user.click(screen.getByRole('button', { name: /send invites/i }));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('Network error');
    });
    expect(screen.getByText('Network error')).toBeInTheDocument();
  });

  it('shows generic error message when API fails without message', async () => {
    const user = userEvent.setup();
    sendReferralInvites.mockRejectedValue('Unknown error');
    render(<InviteByEmail shareUrl="https://instainstru.com/r/abc123" />);

    await user.type(
      screen.getByLabelText(/invite friends by email/i),
      'test@example.com'
    );

    await user.click(screen.getByRole('button', { name: /send invites/i }));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('Failed to send invites');
    });
  });

  it('shows Sending... text while submitting', async () => {
    const user = userEvent.setup();
    let resolveInvite: (value: number) => void;
    sendReferralInvites.mockImplementation(() => new Promise<number>((resolve) => {
      resolveInvite = resolve;
    }));
    render(<InviteByEmail shareUrl="https://instainstru.com/r/abc123" />);

    await user.type(
      screen.getByLabelText(/invite friends by email/i),
      'test@example.com'
    );

    await user.click(screen.getByRole('button', { name: /send invites/i }));

    expect(screen.getByRole('button', { name: /sending/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /sending/i })).toBeDisabled();

    // Resolve to complete the test
    resolveInvite!(1);
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /send invites/i })).toBeInTheDocument();
    });
  });

  it('uses default fromName when not provided', async () => {
    const user = userEvent.setup();
    sendReferralInvites.mockResolvedValue(1);
    render(<InviteByEmail shareUrl="https://instainstru.com/r/abc123" />);

    await user.type(
      screen.getByLabelText(/invite friends by email/i),
      'test@example.com'
    );

    await user.click(screen.getByRole('button', { name: /send invites/i }));

    await waitFor(() => {
      expect(sendReferralInvites).toHaveBeenCalledWith({
        emails: ['test@example.com'],
        shareUrl: 'https://instainstru.com/r/abc123',
        fromName: 'A friend',
      });
    });
  });

  it('handles singular invite message', async () => {
    const user = userEvent.setup();
    sendReferralInvites.mockResolvedValue(1);
    render(<InviteByEmail shareUrl="https://instainstru.com/r/abc123" />);

    await user.type(
      screen.getByLabelText(/invite friends by email/i),
      'test@example.com'
    );

    await user.click(screen.getByRole('button', { name: /send invites/i }));

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('Invites sent to 1 address');
    });
    expect(screen.getByText('Sent invites to 1 friend.')).toBeInTheDocument();
  });

  it('deduplicates email addresses case-insensitively', async () => {
    const user = userEvent.setup();
    sendReferralInvites.mockResolvedValue(1);
    render(<InviteByEmail shareUrl="https://instainstru.com/r/abc123" />);

    await user.type(
      screen.getByLabelText(/invite friends by email/i),
      'Test@Example.com test@example.com TEST@EXAMPLE.COM'
    );

    await user.click(screen.getByRole('button', { name: /send invites/i }));

    await waitFor(() => {
      expect(sendReferralInvites).toHaveBeenCalledWith({
        emails: ['Test@Example.com'],
        shareUrl: 'https://instainstru.com/r/abc123',
        fromName: 'A friend',
      });
    });
  });

  // Bug hunt: email validation edge cases
  it('handles emails with special characters correctly', async () => {
    const user = userEvent.setup();
    sendReferralInvites.mockResolvedValue(2);
    render(<InviteByEmail shareUrl="https://instainstru.com/r/abc123" />);

    await user.type(
      screen.getByLabelText(/invite friends by email/i),
      "test+tag@example.com user.name@example.co.uk"
    );

    await user.click(screen.getByRole('button', { name: /send invites/i }));

    await waitFor(() => {
      expect(sendReferralInvites).toHaveBeenCalledWith({
        emails: ['test+tag@example.com', 'user.name@example.co.uk'],
        shareUrl: 'https://instainstru.com/r/abc123',
        fromName: 'A friend',
      });
    });
  });

  it('handles semicolon-separated emails', async () => {
    const user = userEvent.setup();
    sendReferralInvites.mockResolvedValue(2);
    render(<InviteByEmail shareUrl="https://instainstru.com/r/abc123" />);

    await user.type(
      screen.getByLabelText(/invite friends by email/i),
      'user1@example.com;user2@example.com'
    );

    await user.click(screen.getByRole('button', { name: /send invites/i }));

    await waitFor(() => {
      expect(sendReferralInvites).toHaveBeenCalledWith({
        emails: ['user1@example.com', 'user2@example.com'],
        shareUrl: 'https://instainstru.com/r/abc123',
        fromName: 'A friend',
      });
    });
  });

  // Lines 22-26: Direct form submission when shareUrl becomes empty (edge case)
  it('shows error toast when form is submitted without shareUrl', async () => {
    // Render with a valid shareUrl initially
    const { container, rerender } = render(
      <InviteByEmail shareUrl="https://instainstru.com/r/abc123" />
    );

    // Type something into the input
    const input = screen.getByLabelText(/invite friends by email/i);
    await userEvent.type(input, 'test@example.com');

    // Now rerender with empty shareUrl (simulating it becoming unavailable)
    rerender(<InviteByEmail shareUrl="" />);

    // Submit the form programmatically (bypassing disabled button)
    const form = container.querySelector('form');
    expect(form).not.toBeNull();

    await waitFor(() => {
      form!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    });

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('Referral link is still loading. Try again in a moment.');
    });
    expect(screen.getByText('Referral link is still loading.')).toBeInTheDocument();
    expect(sendReferralInvites).not.toHaveBeenCalled();
  });
});
