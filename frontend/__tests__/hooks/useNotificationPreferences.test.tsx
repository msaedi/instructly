import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useNotificationPreferences } from '@/features/shared/hooks/useNotificationPreferences';
import { notificationPreferencesApi } from '@/features/shared/api/notificationPreferences';

jest.mock('@/features/shared/api/notificationPreferences', () => ({
  notificationPreferencesApi: {
    getPreferences: jest.fn(),
    updatePreference: jest.fn(),
  },
}));

jest.mock('@/features/shared/hooks/useAuth', () => ({
  useAuth: () => ({ isAuthenticated: true }),
}));

describe('useNotificationPreferences', () => {
  const mockedApi = notificationPreferencesApi as jest.Mocked<typeof notificationPreferencesApi>;

  const createWrapper = () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    const Wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
    Wrapper.displayName = 'NotificationPreferencesTestWrapper';
    return Wrapper;
  };

  beforeEach(() => {
    jest.clearAllMocks();
    mockedApi.getPreferences.mockResolvedValue({
      lesson_updates: { email: true, push: true, sms: false },
      messages: { email: false, push: true, sms: false },
      reviews: { email: true, push: true, sms: false },
      learning_tips: { email: true, push: true, sms: false },
      system_updates: { email: true, push: false, sms: false },
      promotional: { email: false, push: false, sms: false },
    });
  });

  it('loads preferences', async () => {
    const { result } = renderHook(() => useNotificationPreferences(), { wrapper: createWrapper() });

    await waitFor(() => {
      expect(result.current.preferences?.lesson_updates.email).toBe(true);
    });
  });

  it('updates preference with optimistic update', async () => {
    const initialPreferences = {
      lesson_updates: { email: true, push: true, sms: false },
      messages: { email: false, push: true, sms: false },
      reviews: { email: true, push: true, sms: false },
      learning_tips: { email: true, push: true, sms: false },
      system_updates: { email: true, push: false, sms: false },
      promotional: { email: false, push: false, sms: false },
    };
    const updatedPreferences = {
      ...initialPreferences,
      promotional: { ...initialPreferences.promotional, email: true },
    };

    mockedApi.getPreferences.mockReset();
    mockedApi.getPreferences
      .mockResolvedValueOnce(initialPreferences)
      .mockResolvedValueOnce(updatedPreferences);
    mockedApi.updatePreference.mockResolvedValue({
      id: 'pref-1',
      category: 'promotional',
      channel: 'email',
      enabled: true,
      locked: false,
    });

    const { result } = renderHook(() => useNotificationPreferences(), { wrapper: createWrapper() });

    await waitFor(() => {
      expect(result.current.preferences?.promotional.email).toBe(false);
    });

    act(() => {
      result.current.updatePreference('promotional', 'email', true);
    });

    await waitFor(() => {
      expect(mockedApi.updatePreference).toHaveBeenCalledWith('promotional', 'email', true);
      expect(result.current.preferences?.promotional.email).toBe(true);
    });
  });

  it('rolls back optimistic update on mutation error', async () => {
    const initialPreferences = {
      lesson_updates: { email: true, push: true, sms: false },
      messages: { email: false, push: true, sms: false },
      reviews: { email: true, push: true, sms: false },
      learning_tips: { email: true, push: true, sms: false },
      system_updates: { email: true, push: false, sms: false },
      promotional: { email: false, push: false, sms: false },
    };

    mockedApi.getPreferences.mockReset();
    mockedApi.getPreferences.mockResolvedValue(initialPreferences);
    mockedApi.updatePreference.mockRejectedValue(new Error('Network error'));

    const { result } = renderHook(() => useNotificationPreferences(), { wrapper: createWrapper() });

    await waitFor(() => {
      expect(result.current.preferences?.promotional.email).toBe(false);
    });

    act(() => {
      result.current.updatePreference('promotional', 'email', true);
    });

    // Wait for mutation to fail and rollback
    await waitFor(() => {
      expect(mockedApi.updatePreference).toHaveBeenCalledWith('promotional', 'email', true);
      // Value should be rolled back to original after error
      expect(result.current.preferences?.promotional.email).toBe(false);
    });
  });
});
