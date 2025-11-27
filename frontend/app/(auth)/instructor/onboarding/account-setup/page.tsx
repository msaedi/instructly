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
    <div className="min-h-screen">
      <OnboardingProgressHeader activeStep="account-setup" stepStatus={stepStatus} />
      <div className="container mx-auto px-8 lg:px-32 py-8 max-w-6xl">
        <div className="mb-4 sm:mb-6 bg-transparent border-0 rounded-none p-4 sm:bg-white sm:rounded-lg sm:p-6 sm:border sm:border-gray-200">
          <h1 className="text-3xl font-bold text-gray-800 mb-2">Tell students what to expect</h1>
          <p className="text-gray-600">
            Complete your personal details, teaching areas, and preferred locations to unlock the rest of onboarding.
          </p>
        </div>
        <div className="sm:hidden h-px bg-gray-200/80 -mx-4" />

        <InstructorProfileForm ref={formRef} context="onboarding" onStepStatusChange={handleProgressStatus} />

        <div className="mt-8 flex items-center justify-end gap-3">
          <button
            type="button"
            onClick={handleSkip}
            disabled={ctaPending}
            data-testid="skip-account-setup"
            className="w-40 px-5 py-2.5 rounded-lg text-[#7E22CE] bg-white border border-purple-200 hover:bg-gray-50 hover:border-purple-300 transition-colors focus:outline-none focus:ring-2 focus:ring-[#7E22CE]/20 justify-center disabled:opacity-60"
          >
            Skip for now
          </button>
          <button
            type="button"
            onClick={handleSaveContinue}
            disabled={ctaPending}
            className="w-56 whitespace-nowrap px-5 py-2.5 rounded-lg text-white bg-[#7E22CE] hover:!bg-[#7E22CE] hover:!text-white disabled:opacity-50 shadow-sm justify-center"
          >
            {ctaPending ? 'Saving...' : 'Save & Continue'}
          </button>
        </div>
      </div>
    </div>
  );
}
