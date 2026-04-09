import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { SettingsImpl } from '../SettingsImpl';
import { fetchWithAuth } from '@/lib/api';
import { notificationPreferencesApi } from '@/features/shared/api/notificationPreferences';
import { useSession } from '@/src/api/hooks/useSession';
import { queryKeys } from '@/src/api/queryKeys';
import { useUserAddresses, useInvalidateUserAddresses } from '@/hooks/queries/useUserAddresses';
import { usePushNotifications } from '@/features/shared/hooks/usePushNotifications';
import { usePhoneVerification } from '@/features/shared/hooks/usePhoneVerification';
import {
  useInvalidateTrustedDevices,
  useRevokeAllTrustedDevices,
  useRevokeTrustedDevice,
  useTrustedDevices,
} from '@/hooks/queries/useTrustedDevices';
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

jest.mock('@/hooks/queries/useTrustedDevices', () => ({
  useTrustedDevices: jest.fn(),
  useInvalidateTrustedDevices: jest.fn(),
  useRevokeTrustedDevice: jest.fn(),
  useRevokeAllTrustedDevices: jest.fn(),
}));

jest.mock('@/features/shared/hooks/usePushNotifications', () => ({
  usePushNotifications: jest.fn(),
}));

jest.mock('@/features/shared/hooks/usePhoneVerification', () => ({
  usePhoneVerification: jest.fn(),
}));

jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: jest.fn(),
  }),
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
const useTrustedDevicesMock = useTrustedDevices as jest.Mock;
const useInvalidateTrustedDevicesMock = useInvalidateTrustedDevices as jest.Mock;
const useRevokeTrustedDeviceMock = useRevokeTrustedDevice as jest.Mock;
const useRevokeAllTrustedDevicesMock = useRevokeAllTrustedDevices as jest.Mock;
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

function renderSettings(embedded: boolean = true) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  render(
    <QueryClientProvider client={queryClient}>
      <SettingsImpl embedded={embedded} />
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
  let trustedDevicesState: Array<{
    id: string;
    device_name: string;
    created_at: string;
    last_used_at: string;
    expires_at: string;
  }>;
  let revokeTrustedDeviceMutationMock: jest.Mock;
  let revokeAllTrustedDevicesMutationMock: jest.Mock;
  let invalidateAddressesMock: jest.Mock;

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

    invalidateAddressesMock = jest.fn().mockResolvedValue(undefined);
    useInvalidateUserAddressesMock.mockReturnValue(invalidateAddressesMock);
    trustedDevicesState = [];
    revokeTrustedDeviceMutationMock = jest.fn().mockResolvedValue({
      message: 'Trusted device revoked',
    });
    revokeAllTrustedDevicesMutationMock = jest.fn().mockResolvedValue({
      message: 'All trusted devices revoked',
    });

    useTrustedDevicesMock.mockImplementation(() => ({
      data: { items: trustedDevicesState },
      isLoading: false,
    }));
    useInvalidateTrustedDevicesMock.mockReturnValue(jest.fn());
    useRevokeTrustedDeviceMock.mockReturnValue({
      mutateAsync: revokeTrustedDeviceMutationMock,
      isPending: false,
    });
    useRevokeAllTrustedDevicesMock.mockReturnValue({
      mutateAsync: revokeAllTrustedDevicesMutationMock,
      isPending: false,
    });

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

      if (url === '/api/v1/2fa/setup/initiate') {
        return {
          ok: true,
          json: async () => ({
            qr_code_data_url: 'data:image/png;base64,mock',
            secret: 'ABC123',
          }),
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

    renderSettings();

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
    renderSettings();

    expect(screen.queryByText(/Referrals & rewards/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Invite friends by email/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Your referral link/i)).not.toBeInTheDocument();
  });

  it('saves only first name and ZIP code while syncing the default address ZIP', async () => {
    const user = userEvent.setup();

    const { queryClient } = renderSettings();
    const invalidateSpy = jest
      .spyOn(queryClient, 'invalidateQueries')
      .mockResolvedValue(undefined);

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
    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('Account details updated');
    });
    expect(invalidateAddressesMock).toHaveBeenCalledTimes(1);
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: queryKeys.auth.me });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: queryKeys.instructors.me });
  });

  it('skips address sync entirely when the ZIP code is unchanged', async () => {
    const user = userEvent.setup();

    renderSettings();

    await user.click(screen.getByRole('button', { name: /Account details/i }));
    await user.clear(screen.getByLabelText(/First name/i));
    await user.type(screen.getByLabelText(/First name/i), 'Alicia');

    fetchWithAuthMock.mockClear();

    await user.click(screen.getByRole('button', { name: 'Save changes' }));

    await waitFor(() => {
      expect(fetchWithAuthMock).toHaveBeenCalledWith(
        '/api/v1/me',
        expect.objectContaining({
          method: 'PATCH',
          body: JSON.stringify({
            first_name: 'Alicia',
            zip_code: '10001',
          }),
        })
      );
    });

    expect(fetchWithAuthMock).not.toHaveBeenCalledWith('/api/v1/addresses/me');
    expect(fetchWithAuthMock).not.toHaveBeenCalledWith(
      '/api/v1/addresses/me/addr-1',
      expect.anything()
    );
    expect(toast.success).toHaveBeenCalledWith('Account details updated');
  });

  it('shows a partial-success toast when the profile saves but address sync fails', async () => {
    const user = userEvent.setup();

    renderSettings();

    fetchWithAuthMock.mockImplementation(async (url: string) => {
      if (url === '/api/v1/me') {
        return {
          ok: true,
          json: async () => ({}),
        } as Response;
      }

      if (url === '/api/v1/addresses/me') {
        return {
          ok: false,
          json: async () => ({ detail: 'failed' }),
        } as Response;
      }

      return {
        ok: true,
        json: async () => ({}),
      } as Response;
    });

    await user.click(screen.getByRole('button', { name: /Account details/i }));
    await user.clear(screen.getByLabelText(/First name/i));
    await user.type(screen.getByLabelText(/First name/i), 'Alicia');
    await user.clear(screen.getByLabelText(/ZIP code/i));
    await user.type(screen.getByLabelText(/ZIP code/i), '11211');
    await user.click(screen.getByRole('button', { name: 'Save changes' }));

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith(
        'Profile updated, but address failed to save. Please try again.'
      );
    });
    expect(toast.error).not.toHaveBeenCalledWith('Failed to update account details');
  });

  it('shows the updated blocked push notifications warning copy', async () => {
    const user = userEvent.setup();

    usePushNotificationsMock.mockReturnValue({
      isSupported: true,
      permission: 'denied',
      isSubscribed: false,
      isLoading: false,
      error: null,
      subscribe: jest.fn(),
      unsubscribe: jest.fn(),
    });

    renderSettings();

    await user.click(screen.getByRole('button', { name: /Preferences/i }));

    expect(
      screen.getByText(
        'Push notifications are currently blocked. Enable them in your browser settings to continue.'
      )
    ).toBeInTheDocument();
  });

  it('keeps the top push toggle visually enabled while a device push update is pending', async () => {
    const user = userEvent.setup();
    const unsubscribeMock = jest.fn();

    usePushNotificationsMock.mockReturnValue({
      isSupported: true,
      permission: 'granted',
      isSubscribed: true,
      isLoading: true,
      error: null,
      subscribe: jest.fn(),
      unsubscribe: unsubscribeMock,
    });

    renderSettings();

    await user.click(screen.getByRole('button', { name: /Preferences/i }));

    const pushToggle = screen.getByRole('switch', {
      name: 'Push notifications on this device',
    });

    expect(pushToggle).not.toBeDisabled();
    expect(pushToggle).not.toHaveClass('cursor-not-allowed', 'opacity-50');
    expect(screen.getByText('Updating push notifications…')).toBeInTheDocument();

    await user.click(pushToggle);

    expect(unsubscribeMock).not.toHaveBeenCalled();
  });

  it('transitions the inline phone verification flow from verified to pending and back', async () => {
    const user = userEvent.setup();

    renderSettings();

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

    renderSettings();

    await user.click(screen.getByRole('button', { name: /^About\b/i }));

    expect(screen.queryByText('Acknowledgments')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Privacy Policy' })).toHaveAttribute('href', '/legal#privacy');
    expect(screen.getByRole('link', { name: 'Terms & Conditions' })).toHaveAttribute('href', '/legal#terms');
    expect(screen.getByRole('link', { name: 'Support' })).toHaveAttribute('href', '/support');
  });

  it('renders a merged Security section with the off-state 2FA toggle and opens setup flow', async () => {
    currentTfaEnabled = false;
    const user = userEvent.setup();

    renderSettings();

    await user.click(screen.getByRole('button', { name: /Security/i }));

    expect(screen.getByText('Security')).toBeInTheDocument();
    expect(screen.queryByText('Account security')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Password$/i })).not.toBeInTheDocument();
    expect(screen.getByText('Keep your account safe')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText('Off')).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(
        screen.getByText('Add an extra layer of security with an authenticator app')
      ).toBeInTheDocument();
    });
    expect(screen.getByText('Password')).toBeInTheDocument();

    const tfaToggle = screen.getByRole('switch', { name: 'Two-factor authentication' });
    expect(tfaToggle).toHaveClass('bg-gray-200');

    fetchWithAuthMock.mockClear();

    await user.click(tfaToggle);

    await waitFor(() => {
      expect(fetchWithAuthMock).toHaveBeenCalledWith('/api/v1/2fa/setup/initiate', {
        method: 'POST',
      });
    });
    expect(fetchWithAuthMock).not.toHaveBeenCalledWith('/api/v1/2fa/status');
    await waitFor(() => {
      expect(screen.getByRole('dialog', { name: 'Connect your authenticator app' })).toBeInTheDocument();
    });
    expect(screen.getByText('Secret (manual entry):')).toBeInTheDocument();
  });

  it('renders the enabled 2FA state and opens the disable flow from the merged Security section', async () => {
    const user = userEvent.setup();

    renderSettings();

    await user.click(screen.getByRole('button', { name: /Security/i }));

    await waitFor(() => {
      expect(screen.getByText('Enabled')).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(
        screen.getByText('Your account is protected with two-factor authentication')
      ).toBeInTheDocument();
    });

    const tfaToggle = screen.getByRole('switch', { name: 'Two-factor authentication' });
    expect(tfaToggle).toHaveClass('bg-(--color-brand-dark)');

    await user.click(tfaToggle);

    await waitFor(() => {
      expect(screen.getByText('To disable 2FA, confirm your password.')).toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: 'Disable 2FA' })).toBeInTheDocument();
  });

  it('renders trusted devices in the Security section', async () => {
    const user = userEvent.setup();
    trustedDevicesState = [
      {
        id: 'device-1',
        device_name: 'Chrome on macOS',
        created_at: '2026-03-01T12:00:00Z',
        last_used_at: '2026-03-10T12:00:00Z',
        expires_at: '2026-04-01T12:00:00Z',
      },
    ];

    renderSettings();

    await user.click(screen.getByRole('button', { name: /Security/i }));

    expect(await screen.findByText('Trusted devices')).toBeInTheDocument();
    expect(screen.getByText('Chrome on macOS')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Revoke' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Revoke all' })).toBeInTheDocument();
  });

  it('revokes a single trusted device from the Security section', async () => {
    const user = userEvent.setup();
    trustedDevicesState = [
      {
        id: 'device-1',
        device_name: 'Safari on iPhone',
        created_at: '2026-03-01T12:00:00Z',
        last_used_at: '2026-03-11T12:00:00Z',
        expires_at: '2026-04-01T12:00:00Z',
      },
    ];

    renderSettings();

    await user.click(screen.getByRole('button', { name: /Security/i }));
    await user.click(await screen.findByRole('button', { name: 'Revoke' }));

    await waitFor(() => {
      expect(revokeTrustedDeviceMutationMock).toHaveBeenCalledWith('device-1');
    });
    expect(toast.success).toHaveBeenCalledWith('Trusted device revoked');
  });

  it('revokes all trusted devices from the Security section', async () => {
    const user = userEvent.setup();
    trustedDevicesState = [
      {
        id: 'device-1',
        device_name: 'Firefox on Windows',
        created_at: '2026-03-01T12:00:00Z',
        last_used_at: '2026-03-12T12:00:00Z',
        expires_at: '2026-04-01T12:00:00Z',
      },
      {
        id: 'device-2',
        device_name: 'Chrome on macOS',
        created_at: '2026-03-02T12:00:00Z',
        last_used_at: '2026-03-13T12:00:00Z',
        expires_at: '2026-04-02T12:00:00Z',
      },
    ];

    renderSettings();

    await user.click(screen.getByRole('button', { name: /Security/i }));
    await user.click(await screen.findByRole('button', { name: 'Revoke all' }));

    await waitFor(() => {
      expect(revokeAllTrustedDevicesMutationMock).toHaveBeenCalledTimes(1);
    });
    expect(toast.success).toHaveBeenCalledWith('All trusted devices revoked');
  });

  it('renders Security and Account Status sections on the standalone settings route', async () => {
    renderSettings(false);

    expect(screen.getByText('Security')).toBeInTheDocument();
    expect(screen.getByText('Keep your account safe')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByRole('switch', { name: 'Two-factor authentication' })).toBeInTheDocument();
    });
    expect(screen.getByText('Account Status')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Pause account' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Delete account' })).toBeInTheDocument();
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

    renderSettings();

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
