import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { formatPhoneDisplay } from '@/lib/phone';
import {
  E164_PHONE_PATTERN,
  formatPhoneForApi,
  formatPhoneVerificationInput,
} from '@/lib/phoneVerification';
import { usePhoneVerification } from '@/features/shared/hooks/usePhoneVerification';

type PhoneVerificationFlowOptions = {
  initialPhoneNumber?: string;
  resendCooldownSeconds?: number;
  onVerified?: (() => void | Promise<void>) | undefined;
};

export type PhoneVerificationFlow = ReturnType<typeof usePhoneVerificationFlow>;

export function usePhoneVerificationFlow(options?: PhoneVerificationFlowOptions) {
  const {
    initialPhoneNumber = '',
    resendCooldownSeconds = 60,
    onVerified,
  } = options ?? {};
  const {
    phoneNumber,
    isVerified,
    isLoading,
    updatePhone,
    sendVerification,
    confirmVerification,
  } = usePhoneVerification();

  const [phoneInput, setPhoneInput] = useState(() =>
    initialPhoneNumber ? formatPhoneDisplay(initialPhoneNumber) : ''
  );
  const [phoneCode, setPhoneCode] = useState('');
  const [hasPhoneVerificationCodeSent, setHasPhoneVerificationCodeSent] = useState(false);
  const [resendCooldown, setResendCooldown] = useState(0);
  const [localVerified, setLocalVerified] = useState(false);
  const [hasEditedPhoneInput, setHasEditedPhoneInput] = useState(false);

  useEffect(() => {
    if (resendCooldown <= 0) {
      return;
    }

    const timer = window.setTimeout(() => {
      setResendCooldown((value) => Math.max(0, value - 1));
    }, 1000);

    return () => window.clearTimeout(timer);
  }, [resendCooldown]);

  const normalizedExistingPhone = formatPhoneForApi(phoneNumber || '');
  const sourcePhone = phoneNumber || initialPhoneNumber;
  const resolvedPhoneInput =
    hasEditedPhoneInput || !sourcePhone ? phoneInput : formatPhoneDisplay(sourcePhone);
  const normalizedPhoneInput = formatPhoneForApi(resolvedPhoneInput);
  const effectivePhoneVerified = isVerified || localVerified;
  const hasPhoneValue = normalizedPhoneInput.length > 0;
  const isPhoneDirty = normalizedPhoneInput !== normalizedExistingPhone;
  const showVerifiedPhoneState =
    !hasPhoneVerificationCodeSent &&
    Boolean(phoneNumber || normalizedPhoneInput) &&
    effectivePhoneVerified &&
    !isPhoneDirty;
  const showPendingPhoneState = hasPhoneVerificationCodeSent;
  const showVerifyPhoneAction =
    !showPendingPhoneState && hasPhoneValue && (!effectivePhoneVerified || isPhoneDirty);

  const handlePhoneInputChange = (value: string) => {
    setHasEditedPhoneInput(true);
    setPhoneInput(formatPhoneVerificationInput(value));
    setPhoneCode('');
    setHasPhoneVerificationCodeSent(false);
    setResendCooldown(0);
    setLocalVerified(false);
  };

  const sendCode = async () => {
    const phoneForApi = normalizedPhoneInput;
    if (!phoneForApi || !E164_PHONE_PATTERN.test(phoneForApi)) {
      toast.error('Enter a valid phone number.');
      return;
    }

    try {
      let activePhone = phoneForApi;
      if (phoneForApi !== normalizedExistingPhone) {
        const updated = await updatePhone.mutateAsync(phoneForApi);
        activePhone = updated.phone_number || phoneForApi;
        setHasEditedPhoneInput(true);
        setPhoneInput(formatPhoneDisplay(activePhone));
      }

      setLocalVerified(false);
      await sendVerification.mutateAsync();
      setPhoneCode('');
      setHasPhoneVerificationCodeSent(true);
      setResendCooldown(resendCooldownSeconds);
      toast.success(
        phoneForApi !== normalizedExistingPhone
          ? 'Phone number saved. Verification code sent.'
          : 'Verification code sent.'
      );
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : 'Failed to send verification code.'
      );
    }
  };

  const confirmCode = async () => {
    const trimmedCode = phoneCode.trim();
    if (trimmedCode.length !== 6) {
      toast.error('Enter the 6-digit verification code.');
      return;
    }

    try {
      await confirmVerification.mutateAsync(trimmedCode);
      setLocalVerified(true);
      setPhoneCode('');
      setHasPhoneVerificationCodeSent(false);
      setResendCooldown(0);
      setHasEditedPhoneInput(true);
      setPhoneInput(formatPhoneDisplay(normalizedPhoneInput));
      if (onVerified) {
        await onVerified();
      }
      toast.success('Phone number verified.');
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Verification failed.');
    }
  };

  return {
    phoneNumber,
    phoneVerified: effectivePhoneVerified,
    phoneLoading: isLoading,
    phoneInput: resolvedPhoneInput,
    phoneCode,
    resendCooldown,
    hasPhoneVerificationCodeSent,
    showVerifiedPhoneState,
    showPendingPhoneState,
    showVerifyPhoneAction,
    updatePhonePending: updatePhone.isPending,
    sendVerificationPending: sendVerification.isPending,
    confirmVerificationPending: confirmVerification.isPending,
    handlePhoneInputChange,
    setPhoneCode,
    sendCode,
    confirmCode,
  };
}
