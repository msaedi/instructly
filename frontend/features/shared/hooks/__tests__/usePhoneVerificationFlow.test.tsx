import { act, renderHook } from '@testing-library/react';
import { toast } from 'sonner';
import { usePhoneVerificationFlow } from '@/features/shared/hooks/usePhoneVerificationFlow';
import { usePhoneVerification } from '@/features/shared/hooks/usePhoneVerification';

jest.mock('sonner', () => ({
  toast: {
    success: jest.fn(),
    error: jest.fn(),
  },
}));

jest.mock('@/features/shared/hooks/usePhoneVerification', () => ({
  usePhoneVerification: jest.fn(),
}));

type PhoneVerificationHookResult = ReturnType<typeof usePhoneVerification>;

const mockToast = toast as jest.Mocked<typeof toast>;
const mockUsePhoneVerification = usePhoneVerification as jest.MockedFunction<
  typeof usePhoneVerification
>;

type MockPhoneState = {
  hookResult: PhoneVerificationHookResult;
  updatePhoneMutateAsync: jest.Mock<Promise<{ phone_number?: string; verified?: boolean }>, [string]>;
  sendVerificationMutateAsync: jest.Mock<Promise<{ sent: boolean }>, []>;
  confirmVerificationMutateAsync: jest.Mock<Promise<{ verified: boolean }>, [string]>;
};

function createMockPhoneState(
  overrides: Partial<PhoneVerificationHookResult> = {}
): MockPhoneState {
  const updatePhoneMutateAsync = jest.fn<
    Promise<{ phone_number?: string; verified?: boolean }>,
    [string]
  >(async (phoneNumber: string) => ({ phone_number: phoneNumber, verified: false }));
  const sendVerificationMutateAsync = jest.fn<Promise<{ sent: boolean }>, []>(
    async () => ({ sent: true })
  );
  const confirmVerificationMutateAsync = jest.fn<Promise<{ verified: boolean }>, [string]>(
    async () => ({ verified: true })
  );

  const hookResult: PhoneVerificationHookResult = {
    phoneNumber: '',
    isVerified: false,
    isLoading: false,
    isError: false,
    updatePhone: {
      isPending: false,
      mutateAsync: updatePhoneMutateAsync,
    } as unknown as PhoneVerificationHookResult['updatePhone'],
    sendVerification: {
      isPending: false,
      mutateAsync: sendVerificationMutateAsync,
    } as unknown as PhoneVerificationHookResult['sendVerification'],
    confirmVerification: {
      isPending: false,
      mutateAsync: confirmVerificationMutateAsync,
    } as unknown as PhoneVerificationHookResult['confirmVerification'],
    ...overrides,
  };

  return {
    hookResult,
    updatePhoneMutateAsync,
    sendVerificationMutateAsync,
    confirmVerificationMutateAsync,
  };
}

describe('usePhoneVerificationFlow', () => {
  let usingFakeTimers = false;

  afterEach(() => {
    jest.clearAllMocks();
    if (usingFakeTimers) {
      jest.runOnlyPendingTimers();
      usingFakeTimers = false;
    }
    jest.useRealTimers();
  });

  it('derives verified state from the existing phone status', () => {
    const state = createMockPhoneState({
      phoneNumber: '+12125550101',
      isVerified: true,
    });
    mockUsePhoneVerification.mockReturnValue(state.hookResult);

    const { result } = renderHook(() => usePhoneVerificationFlow());

    expect(result.current.phoneInput).toBe('(212) 555-0101');
    expect(result.current.phoneVerified).toBe(true);
    expect(result.current.showVerifiedPhoneState).toBe(true);
    expect(result.current.showVerifyPhoneAction).toBe(false);
  });

  it('uses the initial phone number until the user edits it', () => {
    const state = createMockPhoneState();
    mockUsePhoneVerification.mockReturnValue(state.hookResult);

    const { result } = renderHook(() =>
      usePhoneVerificationFlow({ initialPhoneNumber: '+12125550222' })
    );

    expect(result.current.phoneInput).toBe('(212) 555-0222');
    expect(result.current.showVerifyPhoneAction).toBe(true);
  });

  it('resets verification progress when the phone input changes', () => {
    const state = createMockPhoneState({
      phoneNumber: '+12125550101',
      isVerified: true,
    });
    mockUsePhoneVerification.mockReturnValue(state.hookResult);

    const { result } = renderHook(() => usePhoneVerificationFlow());

    act(() => {
      result.current.handlePhoneInputChange('6465559988');
      result.current.setPhoneCode('999999');
    });

    act(() => {
      result.current.handlePhoneInputChange('6465551234');
    });

    expect(result.current.phoneInput).toBe('(646) 555-1234');
    expect(result.current.phoneCode).toBe('');
    expect(result.current.phoneVerified).toBe(true);
    expect(result.current.showVerifiedPhoneState).toBe(false);
    expect(result.current.showVerifyPhoneAction).toBe(true);
  });

  it('sends a verification code without updating the phone when the saved number is reused', async () => {
    const state = createMockPhoneState({
      phoneNumber: '+12125550101',
      isVerified: false,
    });
    mockUsePhoneVerification.mockReturnValue(state.hookResult);

    const { result } = renderHook(() => usePhoneVerificationFlow());

    await act(async () => {
      await result.current.sendCode();
    });

    expect(state.updatePhoneMutateAsync).not.toHaveBeenCalled();
    expect(state.sendVerificationMutateAsync).toHaveBeenCalledTimes(1);
    expect(mockToast.success).toHaveBeenCalledWith('Verification code sent.');
  });

  it('rejects invalid phone numbers before sending a code', async () => {
    const state = createMockPhoneState();
    mockUsePhoneVerification.mockReturnValue(state.hookResult);

    const { result } = renderHook(() => usePhoneVerificationFlow());

    await act(async () => {
      await result.current.sendCode();
    });

    expect(mockToast.error).toHaveBeenCalledWith('Enter a valid phone number.');
    expect(state.updatePhoneMutateAsync).not.toHaveBeenCalled();
    expect(state.sendVerificationMutateAsync).not.toHaveBeenCalled();
  });

  it('updates the phone number, sends a code, and advances the resend cooldown', async () => {
    usingFakeTimers = true;
    jest.useFakeTimers();
    const state = createMockPhoneState();
    mockUsePhoneVerification.mockReturnValue(state.hookResult);

    const { result, unmount } = renderHook(() =>
      usePhoneVerificationFlow({ resendCooldownSeconds: 3 })
    );

    act(() => {
      result.current.handlePhoneInputChange('2125550101');
    });

    await act(async () => {
      await result.current.sendCode();
    });

    expect(state.updatePhoneMutateAsync).toHaveBeenCalledWith('+12125550101');
    expect(state.sendVerificationMutateAsync).toHaveBeenCalledTimes(1);
    expect(result.current.hasPhoneVerificationCodeSent).toBe(true);
    expect(result.current.resendCooldown).toBe(3);
    expect(mockToast.success).toHaveBeenCalledWith(
      'Phone number saved. Verification code sent.'
    );

    act(() => {
      jest.advanceTimersByTime(1000);
    });

    expect(result.current.resendCooldown).toBe(2);
    unmount();
  });

  it('surfaces send failures to the user', async () => {
    const state = createMockPhoneState();
    state.sendVerificationMutateAsync.mockRejectedValueOnce(new Error('SMS failed'));
    mockUsePhoneVerification.mockReturnValue(state.hookResult);

    const { result } = renderHook(() => usePhoneVerificationFlow());

    act(() => {
      result.current.handlePhoneInputChange('2125550101');
    });

    await act(async () => {
      await result.current.sendCode();
    });

    expect(mockToast.error).toHaveBeenCalledWith('SMS failed');
  });

  it('falls back to a generic error when send verification fails without an Error object', async () => {
    const state = createMockPhoneState();
    state.sendVerificationMutateAsync.mockRejectedValueOnce('unexpected');
    mockUsePhoneVerification.mockReturnValue(state.hookResult);

    const { result } = renderHook(() => usePhoneVerificationFlow());

    act(() => {
      result.current.handlePhoneInputChange('2125550101');
    });

    await act(async () => {
      await result.current.sendCode();
    });

    expect(mockToast.error).toHaveBeenCalledWith('Failed to send verification code.');
  });

  it('rejects incomplete verification codes', async () => {
    const state = createMockPhoneState();
    mockUsePhoneVerification.mockReturnValue(state.hookResult);

    const { result } = renderHook(() => usePhoneVerificationFlow());

    act(() => {
      result.current.setPhoneCode('123');
    });

    await act(async () => {
      await result.current.confirmCode();
    });

    expect(mockToast.error).toHaveBeenCalledWith('Enter the 6-digit verification code.');
    expect(state.confirmVerificationMutateAsync).not.toHaveBeenCalled();
  });

  it('confirms the code, marks the phone verified, and calls onVerified', async () => {
    const onVerified = jest.fn(async () => undefined);
    const state = createMockPhoneState();
    mockUsePhoneVerification.mockReturnValue(state.hookResult);

    const { result } = renderHook(() =>
      usePhoneVerificationFlow({ onVerified, resendCooldownSeconds: 5 })
    );

    act(() => {
      result.current.handlePhoneInputChange('2125550101');
    });

    await act(async () => {
      await result.current.sendCode();
    });

    act(() => {
      result.current.setPhoneCode('123456');
    });

    await act(async () => {
      await result.current.confirmCode();
    });

    expect(state.confirmVerificationMutateAsync).toHaveBeenCalledWith('123456');
    expect(result.current.phoneVerified).toBe(true);
    expect(result.current.hasPhoneVerificationCodeSent).toBe(false);
    expect(result.current.resendCooldown).toBe(0);
    expect(result.current.phoneCode).toBe('');
    expect(onVerified).toHaveBeenCalledTimes(1);
    expect(mockToast.success).toHaveBeenCalledWith('Phone number verified.');
  });

  it('confirms the code without requiring an onVerified callback', async () => {
    const state = createMockPhoneState();
    mockUsePhoneVerification.mockReturnValue(state.hookResult);

    const { result } = renderHook(() => usePhoneVerificationFlow());

    act(() => {
      result.current.handlePhoneInputChange('2125550101');
    });

    await act(async () => {
      await result.current.sendCode();
    });

    act(() => {
      result.current.setPhoneCode('123456');
    });

    await act(async () => {
      await result.current.confirmCode();
    });

    expect(mockToast.success).toHaveBeenCalledWith('Phone number verified.');
  });

  it('surfaces verification failures to the user', async () => {
    const state = createMockPhoneState();
    state.confirmVerificationMutateAsync.mockRejectedValueOnce(new Error('Wrong code'));
    mockUsePhoneVerification.mockReturnValue(state.hookResult);

    const { result } = renderHook(() => usePhoneVerificationFlow());

    act(() => {
      result.current.handlePhoneInputChange('2125550101');
    });

    await act(async () => {
      await result.current.sendCode();
    });

    act(() => {
      result.current.setPhoneCode('123456');
    });

    await act(async () => {
      await result.current.confirmCode();
    });

    expect(mockToast.error).toHaveBeenCalledWith('Wrong code');
  });

  it('falls back to a generic error when verification fails without an Error object', async () => {
    const state = createMockPhoneState();
    state.confirmVerificationMutateAsync.mockRejectedValueOnce('unexpected');
    mockUsePhoneVerification.mockReturnValue(state.hookResult);

    const { result } = renderHook(() => usePhoneVerificationFlow());

    act(() => {
      result.current.handlePhoneInputChange('2125550101');
    });

    await act(async () => {
      await result.current.sendCode();
    });

    act(() => {
      result.current.setPhoneCode('123456');
    });

    await act(async () => {
      await result.current.confirmCode();
    });

    expect(mockToast.error).toHaveBeenCalledWith('Verification failed.');
  });
});
