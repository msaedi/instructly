import React from 'react';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { usePhoneVerification } from '../usePhoneVerification';
import { phoneApi } from '@/features/shared/api/phone';

jest.mock('@/features/shared/api/phone', () => ({
  phoneApi: {
    getPhoneStatus: jest.fn(),
    updatePhoneNumber: jest.fn(),
    sendVerification: jest.fn(),
    confirmVerification: jest.fn(),
  },
}));

const phoneApiMock = phoneApi as jest.Mocked<typeof phoneApi>;

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return { wrapper, queryClient };
};

describe('usePhoneVerification', () => {
  beforeEach(() => {
    phoneApiMock.getPhoneStatus.mockReset();
    phoneApiMock.updatePhoneNumber.mockReset();
    phoneApiMock.sendVerification.mockReset();
    phoneApiMock.confirmVerification.mockReset();
    phoneApiMock.getPhoneStatus.mockResolvedValue({ phone_number: '', verified: false });
  });

  it('returns phone status data', async () => {
    phoneApiMock.getPhoneStatus.mockResolvedValueOnce({ phone_number: '+15555555555', verified: true });

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => usePhoneVerification(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.phoneNumber).toBe('+15555555555');
    expect(result.current.isVerified).toBe(true);
  });

  it('updates phone number and caches response', async () => {
    phoneApiMock.getPhoneStatus.mockResolvedValueOnce({ phone_number: '', verified: false });
    phoneApiMock.updatePhoneNumber.mockResolvedValueOnce({ phone_number: '+15551234567', verified: false });

    const { wrapper, queryClient } = createWrapper();
    const { result } = renderHook(() => usePhoneVerification(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await result.current.updatePhone.mutateAsync('+15551234567');
    });

    expect(queryClient.getQueryData(['phone-status'])).toEqual({ phone_number: '+15551234567', verified: false });
  });

  it('sends verification code', async () => {
    phoneApiMock.getPhoneStatus.mockResolvedValueOnce({ phone_number: '+15555555555', verified: false });
    phoneApiMock.sendVerification.mockResolvedValueOnce({ sent: true } as never);

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => usePhoneVerification(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await result.current.sendVerification.mutateAsync();
    });

    expect(phoneApiMock.sendVerification).toHaveBeenCalled();
  });

  it('invalidates phone status after confirmation', async () => {
    phoneApiMock.getPhoneStatus.mockResolvedValueOnce({ phone_number: '+15555555555', verified: false });
    phoneApiMock.confirmVerification.mockResolvedValueOnce({ verified: true } as never);

    const { wrapper, queryClient } = createWrapper();
    const invalidateSpy = jest.spyOn(queryClient, 'invalidateQueries');
    const { result } = renderHook(() => usePhoneVerification(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await result.current.confirmVerification.mutateAsync('123456');
    });

    expect(phoneApiMock.confirmVerification).toHaveBeenCalledWith('123456');
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['phone-status'] });
  });

  it('exposes error state when query fails', async () => {
    phoneApiMock.getPhoneStatus.mockRejectedValueOnce(new Error('Failed'));

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => usePhoneVerification(), { wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});
