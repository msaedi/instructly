import React from 'react';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useNotificationPreferences } from '../useNotificationPreferences';
import { notificationPreferencesApi } from '@/features/shared/api/notificationPreferences';
import { useAuth } from '@/features/shared/hooks/useAuth';

jest.mock('@/features/shared/api/notificationPreferences', () => ({
  notificationPreferencesApi: {
    getPreferences: jest.fn(),
    updatePreference: jest.fn(),
  },
}));

jest.mock('@/features/shared/hooks/useAuth', () => ({
  useAuth: jest.fn(),
}));

const getPreferencesMock = notificationPreferencesApi.getPreferences as jest.Mock;
const updatePreferenceMock = notificationPreferencesApi.updatePreference as jest.Mock;
const useAuthMock = useAuth as jest.Mock;

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children);
  return { wrapper, queryClient };
}

describe('useNotificationPreferences', () => {
  beforeEach(() => {
    getPreferencesMock.mockReset();
    updatePreferenceMock.mockReset();
    useAuthMock.mockReset();
  });

  it('fetches preferences when authenticated', async () => {
    useAuthMock.mockReturnValue({ isAuthenticated: true });
    const prefs = {
      lesson_updates: { email: true, sms: false },
      promotional: { email: false, sms: true },
    };
    getPreferencesMock.mockResolvedValueOnce(prefs);

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useNotificationPreferences(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.preferences).toEqual(prefs);
    expect(result.current.error).toBeNull();
  });

  it('does not fetch when not authenticated', async () => {
    useAuthMock.mockReturnValue({ isAuthenticated: false });

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useNotificationPreferences(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.preferences).toBeUndefined();
    expect(getPreferencesMock).not.toHaveBeenCalled();
  });

  it('optimistically updates cache when previous data exists', async () => {
    useAuthMock.mockReturnValue({ isAuthenticated: true });
    const initialPrefs = {
      lesson_updates: { email: true, sms: false },
      promotional: { email: false, sms: true },
    };
    const updatedPrefs = {
      lesson_updates: { email: true, sms: true },
      promotional: { email: false, sms: true },
    };
    getPreferencesMock
      .mockResolvedValueOnce(initialPrefs)
      .mockResolvedValue(updatedPrefs);
    updatePreferenceMock.mockResolvedValueOnce({ success: true });

    const { wrapper, queryClient } = createWrapper();
    const { result } = renderHook(() => useNotificationPreferences(), { wrapper });

    await waitFor(() => expect(result.current.preferences).toEqual(initialPrefs));

    // Trigger the mutation
    act(() => {
      result.current.updatePreference('lesson_updates', 'sms', true);
    });

    // Optimistic update should apply immediately
    await waitFor(() => {
      const cachedData = queryClient.getQueryData(['notification-preferences']);
      expect(cachedData).toEqual({
        lesson_updates: { email: true, sms: true },
        promotional: { email: false, sms: true },
      });
    });
  });

  it('skips optimistic update when previous cache data is undefined', async () => {
    useAuthMock.mockReturnValue({ isAuthenticated: true });
    // Don't seed initial data - getPreferences will not be called
    // because we want the query to have no data yet
    getPreferencesMock.mockImplementation(() => new Promise(() => { /* never resolves */ }));
    updatePreferenceMock.mockResolvedValueOnce({ success: true });

    const { wrapper, queryClient } = createWrapper();
    const { result } = renderHook(() => useNotificationPreferences(), { wrapper });

    // Preferences are still loading, data is undefined
    expect(result.current.preferences).toBeUndefined();

    // Trigger mutation with no previous data in cache
    act(() => {
      result.current.updatePreference('promotional', 'email', true);
    });

    // Cache should still be undefined since there was no previous data to update
    const cachedData = queryClient.getQueryData(['notification-preferences']);
    expect(cachedData).toBeUndefined();
  });

  it('rolls back to previous data on mutation error', async () => {
    useAuthMock.mockReturnValue({ isAuthenticated: true });
    const initialPrefs = {
      booking_updates: { email: true, sms: false },
    };
    getPreferencesMock.mockResolvedValue(initialPrefs);

    // Make the API call fail
    updatePreferenceMock.mockRejectedValueOnce(new Error('Server error'));

    const { wrapper, queryClient } = createWrapper();
    const { result } = renderHook(() => useNotificationPreferences(), { wrapper });

    await waitFor(() => expect(result.current.preferences).toEqual(initialPrefs));

    // Trigger the mutation which will fail
    act(() => {
      result.current.updatePreference('lesson_updates', 'sms', true);
    });

    // After error, cache should be rolled back to previous data
    await waitFor(() => {
      const cachedData = queryClient.getQueryData(['notification-preferences']);
      expect(cachedData).toEqual(initialPrefs);
    });
  });

  it('does not roll back when context.previous is undefined on error', async () => {
    useAuthMock.mockReturnValue({ isAuthenticated: true });
    // No initial data was fetched
    getPreferencesMock.mockImplementation(() => new Promise(() => { /* never resolves */ }));
    updatePreferenceMock.mockRejectedValueOnce(new Error('Server error'));

    const { wrapper, queryClient } = createWrapper();
    const { result } = renderHook(() => useNotificationPreferences(), { wrapper });

    // Trigger mutation with no previous data
    act(() => {
      result.current.updatePreference('promotional', 'email', true);
    });

    // With no previous data, the error handler should not crash
    // Cache should remain undefined
    await waitFor(() => {
      const cachedData = queryClient.getQueryData(['notification-preferences']);
      expect(cachedData).toBeUndefined();
    });
  });
});
