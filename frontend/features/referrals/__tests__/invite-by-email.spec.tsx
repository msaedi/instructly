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
});
