import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { toast } from 'sonner';
import InstructorPausedAccountBanner from '../InstructorPausedAccountBanner';
import { accountStatusQueryKey, useAccountStatus } from '@/hooks/queries/useAccountStatus';
import { queryKeys } from '@/src/api/queryKeys';

const mockUsePathname = jest.fn();
const mockMutateAsync = jest.fn();

jest.mock('next/navigation', () => ({
  usePathname: () => mockUsePathname(),
}));

jest.mock('@/hooks/queries/useAccountStatus', () => ({
  accountStatusQueryKey: ['user', 'account', 'status'],
  useAccountStatus: jest.fn(),
  useReactivateAccount: () => ({
    mutateAsync: mockMutateAsync,
    isPending: false,
  }),
}));

jest.mock('sonner', () => ({
  toast: {
    success: jest.fn(),
    error: jest.fn(),
  },
}));

const useAccountStatusMock = useAccountStatus as jest.Mock;

function renderBanner() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  const invalidateSpy = jest.spyOn(queryClient, 'invalidateQueries');

  render(
    <QueryClientProvider client={queryClient}>
      <InstructorPausedAccountBanner />
    </QueryClientProvider>
  );

  return { invalidateSpy };
}

describe('InstructorPausedAccountBanner', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockUsePathname.mockReturnValue('/instructor/dashboard');
    mockMutateAsync.mockResolvedValue({ success: true });
    useAccountStatusMock.mockReturnValue({
      data: {
        account_status: 'suspended',
      },
    });
  });

  it('renders the paused banner outside settings and resumes with cache refresh feedback', async () => {
    const user = userEvent.setup();
    const { invalidateSpy } = renderBanner();

    expect(screen.getByText(/Your account is paused/i)).toBeInTheDocument();
    expect(screen.getByText(/Existing bookings are still active. Cancel them/i)).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Account paused' })).toBeInTheDocument();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Resume account' }));
    const dialog = screen.getByRole('dialog', { name: 'Resume your account?' });
    await user.click(within(dialog).getByRole('button', { name: 'Resume account' }));

    await waitFor(() => {
      expect(mockMutateAsync).toHaveBeenCalledTimes(1);
    });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: accountStatusQueryKey });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: queryKeys.auth.me });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: queryKeys.instructors.me });
    expect(toast.success).toHaveBeenCalledWith('Account resumed. Check your email for confirmation.');
  });

  it('does not render or query status on settings routes', () => {
    mockUsePathname.mockReturnValue('/instructor/settings');

    renderBanner();

    expect(useAccountStatusMock).toHaveBeenCalledWith(false);
    expect(screen.queryByText(/Your account is paused/i)).not.toBeInTheDocument();
  });

  it('does not render when the account is active', () => {
    useAccountStatusMock.mockReturnValue({
      data: {
        account_status: 'active',
      },
    });

    renderBanner();

    expect(useAccountStatusMock).toHaveBeenCalledWith(true);
    expect(screen.queryByText(/Your account is paused/i)).not.toBeInTheDocument();
  });

  it('closes the resume modal from the cancel button', async () => {
    const user = userEvent.setup();

    renderBanner();

    await user.click(screen.getByRole('button', { name: 'Resume account' }));
    const dialog = screen.getByRole('dialog', { name: 'Resume your account?' });
    await user.click(within(dialog).getByRole('button', { name: 'Cancel' }));

    expect(screen.queryByRole('dialog', { name: 'Resume your account?' })).not.toBeInTheDocument();
  });

  it('keeps the modal open and shows an error toast when resume fails', async () => {
    const user = userEvent.setup();
    mockMutateAsync.mockRejectedValue(new Error('Resume failed'));

    renderBanner();

    await user.click(screen.getByRole('button', { name: 'Resume account' }));
    const dialog = screen.getByRole('dialog', { name: 'Resume your account?' });
    await user.click(within(dialog).getByRole('button', { name: 'Resume account' }));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('Resume failed');
    });
    expect(screen.getByRole('dialog', { name: 'Resume your account?' })).toBeInTheDocument();
  });

  it('uses fallback copy when resume fails with a non-error value', async () => {
    const user = userEvent.setup();
    mockMutateAsync.mockRejectedValue('resume failed');

    renderBanner();

    await user.click(screen.getByRole('button', { name: 'Resume account' }));
    const dialog = screen.getByRole('dialog', { name: 'Resume your account?' });
    await user.click(within(dialog).getByRole('button', { name: 'Resume account' }));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('Failed to resume account.');
    });
  });
});
