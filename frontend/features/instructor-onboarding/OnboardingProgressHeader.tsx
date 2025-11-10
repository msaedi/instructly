"use client";

import { useEffect, useMemo, useRef, useState, useCallback } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import UserProfileDropdown from '@/components/UserProfileDropdown';

const STEP_DEFS = [
  { key: 'account-setup', label: 'Account Setup', href: '/instructor/onboarding/account-setup' },
  { key: 'skill-selection', label: 'Add Skills', href: '/instructor/onboarding/skill-selection' },
  { key: 'verify-identity', label: 'Verify Identity', href: '/instructor/onboarding/verification' },
  { key: 'payment-setup', label: 'Payment Setup', href: '/instructor/onboarding/payment-setup' },
] as const;
const STEP_ORDER = STEP_DEFS.map((step) => step.key);

export type OnboardingStepKey = (typeof STEP_DEFS)[number]['key'];
export type OnboardingStepStatus = 'pending' | 'done' | 'failed';

type Props = {
  activeStep: OnboardingStepKey;
  stepStatus?: Partial<Record<OnboardingStepKey, OnboardingStepStatus>>;
  completedSteps?: Partial<Record<OnboardingStepKey, boolean>>;
};

const defaultStatuses: Record<OnboardingStepKey, OnboardingStepStatus> = {
  'account-setup': 'pending',
  'skill-selection': 'pending',
  'verify-identity': 'pending',
  'payment-setup': 'pending',
};

type WalkerPath = {
  start: OnboardingStepKey;
  target: OnboardingStepKey;
  variant: 'walk' | 'bounce';
};

function computeWalkerPath(active: OnboardingStepKey, _completed: Partial<Record<OnboardingStepKey, boolean>>): WalkerPath {
  if (active === 'account-setup') {
    return { start: 'account-setup', target: 'account-setup', variant: 'bounce' };
  }

  const activeIdx = Math.max(0, STEP_ORDER.indexOf(active));
  const startIdx = Math.max(0, Math.min(activeIdx - 1, STEP_ORDER.length - 1));

  const startStep = STEP_ORDER[startIdx] ?? 'account-setup';
  const targetStep = STEP_ORDER[activeIdx] ?? startStep;

  return {
    start: startStep,
    target: targetStep,
    variant: 'walk',
  };
}

export function OnboardingProgressHeader({ activeStep, stepStatus, completedSteps }: Props) {
  const router = useRouter();
  const progressRef = useRef<HTMLDivElement | null>(null);
  const stepButtonRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const [walkerLeft, setWalkerLeft] = useState(24);

  const resolvedStatuses = useMemo(() => ({ ...defaultStatuses, ...(stepStatus || {}) }), [stepStatus]);
  const completionMap = useMemo(() => {
    if (completedSteps) return completedSteps;
    const derived: Partial<Record<OnboardingStepKey, boolean>> = {};
    (Object.keys(resolvedStatuses) as OnboardingStepKey[]).forEach((key) => {
      if (resolvedStatuses[key] === 'done') {
        derived[key] = true;
      }
    });
    return derived;
  }, [completedSteps, resolvedStatuses]);

  const walkerPath = useMemo(() => computeWalkerPath(activeStep, completionMap), [activeStep, completionMap]);

  const updateWalker = useCallback(() => {
    const container = progressRef.current;
    if (!container) return;

    const resolveIndex = (key: OnboardingStepKey) => {
      const idx = STEP_ORDER.indexOf(key);
      return idx >= 0 ? idx : 0;
    };

    const baseIndex = resolveIndex(walkerPath.start);
    const button = stepButtonRefs.current[baseIndex] ?? stepButtonRefs.current[0];

    if (!button) return;
    const containerRect = container.getBoundingClientRect();
    const targetRect = button.getBoundingClientRect();
    const offset = targetRect.left - containerRect.left + targetRect.width / 2 - 8;
    setWalkerLeft(offset);
  }, [walkerPath.start]);

  useEffect(() => {
    updateWalker();
    window.addEventListener('resize', updateWalker);
    return () => window.removeEventListener('resize', updateWalker);
  }, [updateWalker]);

  const walkerClassName = walkerPath.variant === 'bounce' ? 'inst-anim-walk-profile' : 'inst-anim-walk';
  const armClass = walkerPath.variant === 'bounce' ? 'inst-anim-leftArm-fast' : 'inst-anim-leftArm';
  const armRightClass = walkerPath.variant === 'bounce' ? 'inst-anim-rightArm-fast' : 'inst-anim-rightArm';
  const legLeftClass = walkerPath.variant === 'bounce' ? 'inst-anim-leftLeg-fast' : 'inst-anim-leftLeg';
  const legRightClass = walkerPath.variant === 'bounce' ? 'inst-anim-rightLeg-fast' : 'inst-anim-rightLeg';

  return (
    <header className="bg-white backdrop-blur-sm border-b border-gray-200 px-4 sm:px-6 py-4" data-testid="onboarding-header">
      <div className="flex items-center justify-between max-w-full relative">
        <Link href="/instructor/dashboard" className="inline-block">
          <h1 className="text-3xl font-bold text-[#7E22CE] hover:text-[#7E22CE] transition-colors cursor-pointer pl-0 sm:pl-4">iNSTAiNSTRU</h1>
        </Link>
        <div
          ref={progressRef}
          className="absolute left-1/2 transform -translate-x-1/2 items-center gap-0 hidden min-[1400px]:flex"
        >
          <div
            className={`absolute ${walkerClassName}`}
            style={{ top: '-12px', left: `${walkerLeft}px` }}
            data-testid="onboarding-header-art"
          >
            <svg width="16" height="20" viewBox="0 0 16 20" fill="none">
              <circle cx="8" cy="4" r="2.5" stroke="#7E22CE" strokeWidth="1.2" fill="none" />
              <line x1="8" y1="6.5" x2="8" y2="12" stroke="#7E22CE" strokeWidth="1.2" />
              <line x1="8" y1="8" x2="5" y2="10" stroke="#7E22CE" strokeWidth="1.2" className={armClass} />
              <line x1="8" y1="8" x2="11" y2="10" stroke="#7E22CE" strokeWidth="1.2" className={armRightClass} />
              <line x1="8" y1="12" x2="6" y2="17" stroke="#7E22CE" strokeWidth="1.2" className={legLeftClass} />
              <line x1="8" y1="12" x2="10" y2="17" stroke="#7E22CE" strokeWidth="1.2" className={legRightClass} />
            </svg>
          </div>

          {STEP_DEFS.map((step, index) => {
            const isCurrent = step.key === activeStep;
            const status = resolvedStatuses[step.key];
            const baseClasses = 'w-6 h-6 rounded-full border-2 transition-colors cursor-pointer flex items-center justify-center';
            const buttonClasses =
              status === 'done'
                ? `${baseClasses} border-[#7E22CE] bg-[#7E22CE] text-white`
                : isCurrent
                ? `${baseClasses} border-purple-300 bg-purple-100 text-[#7E22CE]`
                : `${baseClasses} border-gray-300 bg-white text-[#7E22CE] hover:border-[#7E22CE]`;

            const handleClick = () => {
              if (isCurrent) return;
              router.push(step.href);
            };

            const nextStep = STEP_DEFS[index + 1];
            const lineStatus = resolvedStatuses[step.key];
            const lineClass =
              nextStep === undefined
                ? ''
                : lineStatus === 'done'
                ? 'w-60 h-0.5 bg-[#7E22CE]'
                : lineStatus === 'failed'
                ? 'w-60 h-0.5 bg-[repeating-linear-gradient(to_right,_#7E22CE_0,_#7E22CE_8px,_transparent_8px,_transparent_16px)]'
                : 'w-60 h-0.5 bg-gray-300';

            return (
              <div className="flex items-center" key={step.key}>
                <div className="flex flex-col items-center relative">
                  <button
                    ref={(el) => {
                      stepButtonRefs.current[index] = el;
                    }}
                    id={`progress-step-${index + 1}`}
                    onClick={handleClick}
                    className={buttonClasses}
                    title={`Step ${index + 1}: ${step.label}`}
                    type="button"
                  >
                    {step.key === 'account-setup' && (
                      <>
                        <svg
                          className={`icon-check w-3 h-3 text-white ${status === 'done' ? '' : 'hidden'}`}
                          viewBox="0 0 24 24"
                          fill="none"
                          stroke="currentColor"
                          aria-hidden="true"
                        >
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" />
                        </svg>
                        <svg
                          className={`icon-cross w-3 h-3 text-white ${status === 'failed' ? '' : 'hidden'}`}
                          viewBox="0 0 24 24"
                          fill="none"
                          stroke="currentColor"
                          aria-hidden="true"
                        >
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
                        </svg>
                      </>
                    )}
                  </button>
                  <span className="text-[10px] text-gray-600 mt-1 whitespace-nowrap absolute top-7">{step.label}</span>
                </div>
                {nextStep && <div id={`progress-line-${index + 1}`} className={lineClass} />}
              </div>
            );
          })}
        </div>

        <div className="pr-4">
          <UserProfileDropdown />
        </div>
      </div>
    </header>
  );
}
