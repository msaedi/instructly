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
import { toast } from 'sonner';

jest.mock('@/components/UserProfileDropdown', () => {
  function MockUserProfileDropdown() {
    return <div>User menu</div>;
  }

  return MockUserProfileDropdown;
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

jest.mock('sonner', () => ({
  toast: {
    success: jest.fn(),
    error: jest.fn(),
  },
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
  let phoneState: { phoneNumber: string; isVerified: boolean };
  let updatePhoneMock: jest.Mock;
  let sendVerificationMock: jest.Mock;
  let confirmVerificationMock: jest.Mock;

  beforeEach(() => {
    jest.clearAllMocks();
    currentTfaEnabled = true;
    phoneState = {
      phoneNumber: '+12125551001',
      isVerified: true,
    };
    updatePhoneMock = jest.fn(async (phoneNumber: string) => {
      phoneState = {
        phoneNumber,
        isVerified: false,
      };
      return {
        phone_number: phoneNumber,
        verified: false,
      };
    });
    sendVerificationMock = jest.fn(async () => ({ success: true }));
    confirmVerificationMock = jest.fn(async (code: string) => {
      if (code === '123456') {
        phoneState = {
          ...phoneState,
          isVerified: true,
        };
      }
      return { success: true };
    });

    useSessionMock.mockReturnValue({
      data: {
        first_name: 'Alex',
        last_name: 'Morgan',
        email: 'alex@example.com',
        phone: '+12125551001',
        zip_code: '10001',
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

    usePhoneVerificationMock.mockImplementation(() => ({
      phoneNumber: phoneState.phoneNumber,
      isVerified: phoneState.isVerified,
      isLoading: false,
      updatePhone: {
        mutateAsync: updatePhoneMock,
        isPending: false,
      },
      sendVerification: {
        mutateAsync: sendVerificationMock,
        isPending: false,
      },
      confirmVerification: {
        mutateAsync: confirmVerificationMock,
        isPending: false,
      },
    }));

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

      if (url === '/api/v1/me') {
        return {
          ok: true,
          json: async () => ({}),
        };
      }

      if (url === '/api/v1/addresses/me') {
        return {
          ok: true,
          json: async () => ({
            items: [{ id: 'addr-1', postal_code: '10001', is_default: true }],
          }),
        };
      }

      if (url === '/api/v1/addresses/me/addr-1') {
        return {
          ok: true,
          json: async () => ({}),
        };
      }

      throw new Error(`Unhandled request: ${url}`);
    });
  });

  it('renders the redesigned account details layout and keeps only one accordion section open', async () => {
    const user = userEvent.setup();

    renderEmbeddedSettings();

    await user.click(screen.getByRole('button', { name: /Account details/i }));

    expect(await screen.findByLabelText(/First name/i)).toHaveValue('Alex');
    expect(screen.getByLabelText(/Last name · verified/i)).toHaveValue('Morgan');
    expect(screen.getByLabelText(/Email · verified/i)).toHaveValue('alex@example.com');
    expect(screen.getByLabelText(/ZIP code/i)).toHaveValue('10001');
    expect(screen.getByLabelText(/Phone number/i)).toHaveValue('(212) 555-1001');
    expect(screen.getByText('Verified')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /Preferences/i }));

    expect(screen.queryByLabelText(/First name/i)).not.toBeInTheDocument();
    expect(screen.getByText('Notifications')).toBeInTheDocument();
  });

  it('does not render referral content in settings', () => {
    renderEmbeddedSettings();

    expect(screen.queryByText(/Referrals & rewards/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Invite friends by email/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Your referral link/i)).not.toBeInTheDocument();
  });

  it('saves only first name and ZIP code while syncing the default address ZIP', async () => {
    const user = userEvent.setup();

    renderEmbeddedSettings();

    await user.click(screen.getByRole('button', { name: /Account details/i }));
    await user.clear(screen.getByLabelText(/First name/i));
    await user.type(screen.getByLabelText(/First name/i), 'Alicia');
    await user.clear(screen.getByLabelText(/ZIP code/i));
    await user.type(screen.getByLabelText(/ZIP code/i), '11211');
    await user.click(screen.getByRole('button', { name: 'Save changes' }));

    await waitFor(() => {
      expect(fetchWithAuthMock).toHaveBeenCalledWith(
        '/api/v1/me',
        expect.objectContaining({
          method: 'PATCH',
          body: JSON.stringify({
            first_name: 'Alicia',
            zip_code: '11211',
          }),
        })
      );
    });

    const userPatchCall = fetchWithAuthMock.mock.calls.find(([url]) => url === '/api/v1/me');
    expect(userPatchCall?.[1]?.body).not.toContain('last_name');
    expect(fetchWithAuthMock).toHaveBeenCalledWith('/api/v1/addresses/me');
    expect(fetchWithAuthMock).toHaveBeenCalledWith(
      '/api/v1/addresses/me/addr-1',
      expect.objectContaining({
        method: 'PATCH',
        body: JSON.stringify({ postal_code: '11211' }),
      })
    );
    expect(toast.success).toHaveBeenCalledWith('Account details updated');
  });

  it('transitions the inline phone verification flow from verified to pending and back', async () => {
    const user = userEvent.setup();

    renderEmbeddedSettings();

    await user.click(screen.getByRole('button', { name: /Account details/i }));

    const phoneInput = await screen.findByLabelText(/Phone number/i);
    await user.clear(phoneInput);
    await user.type(phoneInput, '2125552000');

    expect(screen.queryByText('Verified')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Verify' })).toBeInTheDocument();
    expect(screen.getByText("We'll send a 6-digit verification code to this number.")).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Verify' }));

    await waitFor(() => {
      expect(updatePhoneMock).toHaveBeenCalledWith('+12125552000');
      expect(sendVerificationMock).toHaveBeenCalledTimes(1);
    });
    expect(screen.getByText('Pending')).toBeInTheDocument();
    expect(screen.getByText('Code sent to (XXX) XXX-2000')).toBeInTheDocument();
    expect(screen.getByLabelText(/Phone number/i)).toBeDisabled();

    await user.type(screen.getByPlaceholderText('123456'), '123456');
    await user.click(screen.getByRole('button', { name: 'Submit' }));

    await waitFor(() => {
      expect(confirmVerificationMock).toHaveBeenCalledWith('123456');
      expect(screen.getByText('Verified')).toBeInTheDocument();
    });
    expect(screen.queryByText('Pending')).not.toBeInTheDocument();
    expect(screen.queryByText(/Code sent to/i)).not.toBeInTheDocument();
    expect(screen.getByLabelText(/Phone number/i)).toHaveValue('(212) 555-2000');
    expect(toast.success).toHaveBeenCalledWith('Phone number verified.');
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
});
