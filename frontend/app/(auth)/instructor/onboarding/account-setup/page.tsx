'use client';

import { useRef, useState, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import InstructorProfileForm, { type InstructorProfileFormHandle } from '@/features/instructor-profile/InstructorProfileForm';
import { OnboardingProgressHeader, type OnboardingStepStatus } from '@/features/instructor-onboarding/OnboardingProgressHeader';
import { useOnboardingStepStatus } from '@/features/instructor-onboarding/useOnboardingStepStatus';

export default function AccountSetupPage() {
  const router = useRouter();
  const formRef = useRef<InstructorProfileFormHandle>(null);
  const [ctaPending, setCtaPending] = useState(false);
  // Use unified step status evaluation
  const { stepStatus: evaluatedStepStatus } = useOnboardingStepStatus();
  const [localAccountStatus, setLocalAccountStatus] = useState<OnboardingStepStatus | null>(null);

  // Use local status if set (after save), otherwise use evaluated status
  const stepStatus = useMemo(() => ({
    ...evaluatedStepStatus,
    'account-setup': localAccountStatus || evaluatedStepStatus['account-setup'],
  }), [evaluatedStepStatus, localAccountStatus]);

  const handleProgressStatus = (status: 'done' | 'failed') => {
    setLocalAccountStatus(status);
  };

  const handleSaveContinue = async () => {
    if (!formRef.current) return;
    try {
      setCtaPending(true);
      await formRef.current.save({ redirectTo: '/instructor/onboarding/skill-selection' });
    } finally {
      setCtaPending(false);
    }
  };

  const handleSkip = () => {
    if (ctaPending) return;
    router.push('/instructor/onboarding/skill-selection');
  };

  return (
    <div className="min-h-screen insta-onboarding-page">
      <OnboardingProgressHeader activeStep="account-setup" stepStatus={stepStatus} />
      <div className="container mx-auto px-8 lg:px-32 py-8 max-w-6xl">
        <div className="insta-surface-card insta-onboarding-header">
          <h1 className="insta-onboarding-title">Tell students what to expect</h1>
          <p className="insta-onboarding-subtitle">
            Complete your personal details, teaching areas, and preferred locations to unlock the rest of onboarding.
          </p>
        </div>
        <div className="insta-onboarding-divider" />

        <InstructorProfileForm ref={formRef} context="onboarding" onStepStatusChange={handleProgressStatus} />

        <div className="mt-8 flex items-center justify-end gap-3">
          <button
            type="button"
            onClick={handleSkip}
            disabled={ctaPending}
            data-testid="skip-account-setup"
            className="insta-secondary-btn w-40 px-5 py-2.5 rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-[#7E22CE]/20 justify-center disabled:opacity-60"
          >
            Skip for now
          </button>
          <button
            type="button"
            onClick={handleSaveContinue}
            disabled={ctaPending}
            className="insta-primary-btn w-56 whitespace-nowrap px-5 py-2.5 rounded-lg text-white disabled:opacity-50 shadow-sm justify-center"
          >
            {ctaPending ? 'Saving...' : 'Save & Continue'}
          </button>
        </div>
      </div>
    </div>
  );
}
