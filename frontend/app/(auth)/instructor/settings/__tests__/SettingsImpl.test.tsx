import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { SettingsImpl } from '../SettingsImpl';
import { fetchWithAuth } from '@/lib/api';
import { notificationPreferencesApi } from '@/features/shared/api/notificationPreferences';
import { useSession } from '@/src/api/hooks/useSession';
import { useUserAddresses, useInvalidateUserAddresses } from '@/hooks/queries/useUserAddresses';
import { usePushNotifications } from '@/features/shared/hooks/usePushNotifications';
import { usePhoneVerification } from '@/features/shared/hooks/usePhoneVerification';

jest.mock('@/components/UserProfileDropdown', () => {
  function MockUserProfileDropdown() {
    return <div>User menu</div>;
  }

  return MockUserProfileDropdown;
});

jest.mock('@/features/referrals/RewardsPanel', () => {
  function MockRewardsPanel() {
    return <div>Rewards panel</div>;
  }

  return MockRewardsPanel;
});

jest.mock('@/lib/api', () => ({
  fetchWithAuth: jest.fn(),
  API_ENDPOINTS: {
    ME: '/api/v1/me',
  },
}));

jest.mock('@/features/shared/api/notificationPreferences', () => ({
  notificationPreferencesApi: {
    getPreferences: jest.fn(),
    updatePreference: jest.fn(),
  },
}));

jest.mock('@/features/shared/hooks/useAuth', () => ({
  useAuth: () => ({ isAuthenticated: true }),
}));

jest.mock('@/src/api/hooks/useSession', () => ({
  useSession: jest.fn(),
}));

jest.mock('@/hooks/queries/useUserAddresses', () => ({
  useUserAddresses: jest.fn(),
  useInvalidateUserAddresses: jest.fn(),
}));

jest.mock('@/features/shared/hooks/usePushNotifications', () => ({
  usePushNotifications: jest.fn(),
}));

jest.mock('@/features/shared/hooks/usePhoneVerification', () => ({
  usePhoneVerification: jest.fn(),
}));

const fetchWithAuthMock = fetchWithAuth as jest.Mock;
const getPreferencesMock = notificationPreferencesApi.getPreferences as jest.Mock;
const updatePreferenceMock = notificationPreferencesApi.updatePreference as jest.Mock;
const useSessionMock = useSession as jest.Mock;
const useUserAddressesMock = useUserAddresses as jest.Mock;
const useInvalidateUserAddressesMock = useInvalidateUserAddresses as jest.Mock;
const usePushNotificationsMock = usePushNotifications as jest.Mock;
const usePhoneVerificationMock = usePhoneVerification as jest.Mock;

const defaultPreferences = {
  lesson_updates: { email: true, push: true, sms: false },
  messages: { email: false, push: true, sms: false },
  reviews: { email: true, push: true, sms: false },
  learning_tips: { email: true, push: true, sms: false },
  system_updates: { email: true, push: false, sms: false },
  promotional: { email: false, push: false, sms: false },
};

function renderEmbeddedSettings() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  render(
    <QueryClientProvider client={queryClient}>
      <SettingsImpl embedded />
    </QueryClientProvider>
  );

  return { queryClient };
}

describe('SettingsImpl', () => {
  let currentTfaEnabled = true;

  beforeEach(() => {
    jest.clearAllMocks();
    currentTfaEnabled = true;

    useSessionMock.mockReturnValue({
      data: {
        first_name: 'Alex',
        last_name: 'Morgan',
        email: 'alex@example.com',
        phone: '+12125551001',
      },
      isLoading: false,
    });

    useUserAddressesMock.mockReturnValue({
      data: {
        items: [{ id: 'addr-1', postal_code: '10001', is_default: true }],
      },
      isLoading: false,
    });

    useInvalidateUserAddressesMock.mockReturnValue(jest.fn());

    usePushNotificationsMock.mockReturnValue({
      isSupported: true,
      permission: 'granted',
      isSubscribed: true,
      isLoading: false,
      error: null,
      subscribe: jest.fn(),
      unsubscribe: jest.fn(),
    });

    usePhoneVerificationMock.mockReturnValue({
      phoneNumber: '+12125551001',
      isVerified: true,
      isLoading: false,
    });

    getPreferencesMock.mockResolvedValue(defaultPreferences);
    updatePreferenceMock.mockResolvedValue({
      id: 'pref-1',
      category: 'promotional',
      channel: 'email',
      enabled: true,
      locked: false,
    });

    fetchWithAuthMock.mockImplementation(async (url: string) => {
      if (url === '/api/v1/2fa/status') {
        return {
          ok: true,
          json: async () => ({ enabled: currentTfaEnabled }),
        };
      }

      if (url === '/api/v1/2fa/disable') {
        currentTfaEnabled = false;
        return {
          ok: true,
          json: async () => ({}),
        };
      }

      throw new Error(`Unhandled request: ${url}`);
    });
  });

  it('keeps only one embedded accordion section open and shows formatted read-only phone', async () => {
    const user = userEvent.setup();

    renderEmbeddedSettings();

    await user.click(screen.getByRole('button', { name: /Account details/i }));

    expect(await screen.findByDisplayValue('(212) 555-1001')).toBeDisabled();
    expect(screen.getByLabelText(/ZIP code/i)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /Preferences/i }));

    expect(screen.queryByLabelText(/ZIP code/i)).not.toBeInTheDocument();
    expect(screen.getByText('Notifications')).toBeInTheDocument();
    expect(screen.queryByText(/Phone number \(for SMS\)/i)).not.toBeInTheDocument();
  });

  it('renders the cleaned About links', async () => {
    const user = userEvent.setup();

    renderEmbeddedSettings();

    await user.click(screen.getByRole('button', { name: /^About\b/i }));

    expect(screen.queryByText('Acknowledgments')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Privacy Policy' })).toHaveAttribute('href', '/legal#privacy');
    expect(screen.getByRole('link', { name: 'Terms & Conditions' })).toHaveAttribute('href', '/legal#terms');
    expect(screen.getByRole('link', { name: 'Support' })).toHaveAttribute('href', '/support');
  });

  it('only disables the toggled notification preference while an update is pending', async () => {
    const user = userEvent.setup();
    let resolveUpdate: (() => void) | undefined;

    updatePreferenceMock.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveUpdate = () =>
            resolve({
              id: 'pref-2',
              category: 'promotional',
              channel: 'email',
              enabled: true,
              locked: false,
            });
        })
    );

    renderEmbeddedSettings();

    await user.click(screen.getByRole('button', { name: /Preferences/i }));

    const promotionalEmailToggle = await screen.findByRole('switch', {
      name: 'Promotional Email notifications',
    });

    await user.click(promotionalEmailToggle);

    await waitFor(() => {
      expect(screen.getByRole('switch', { name: 'Promotional Email notifications' })).toBeDisabled();
    });
    expect(screen.getByRole('switch', { name: 'Lesson Updates Email notifications' })).not.toBeDisabled();

    act(() => {
      resolveUpdate?.();
    });

    await waitFor(() => {
      expect(screen.getByRole('switch', { name: 'Promotional Email notifications' })).not.toBeDisabled();
    });
  });

  it('shows Set up again after a successful 2FA disable', async () => {
    const user = userEvent.setup();

    renderEmbeddedSettings();

    await user.click(screen.getByRole('button', { name: /Account security/i }));

    const turnOffButton = await screen.findByRole('button', { name: 'Turn off' });
    await user.click(turnOffButton);

    const passwordInput = await screen.findByPlaceholderText('Current password');
    await user.type(passwordInput, 'password');
    await user.click(screen.getByRole('button', { name: 'Disable 2FA' }));

    await waitFor(() => {
      expect(screen.getByText('Two-factor authentication has been disabled.')).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: 'Close' }));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Set up' })).toBeInTheDocument();
    });
  });
});
