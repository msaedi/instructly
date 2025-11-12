"use client";

import { useEffect, useMemo, useRef, useState, useCallback } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import UserProfileDropdown from '@/components/UserProfileDropdown';
import type { StepKey, OnboardingStatusMap } from './stepStatus';
import { STEP_KEYS, createEmptyStatusMap } from './stepStatus';

const STEP_META: Record<
  StepKey,
  {
    label: string;
    href: string;
  }
> = {
  'account-setup': { label: 'Account Setup', href: '/instructor/onboarding/account-setup' },
  'skill-selection': { label: 'Add Skills', href: '/instructor/onboarding/skill-selection' },
  'verify-identity': { label: 'Verify Identity', href: '/instructor/onboarding/verification' },
  'payment-setup': { label: 'Payment Setup', href: '/instructor/onboarding/payment-setup' },
};

const STEP_DEFS = STEP_KEYS.map((key) => ({ key, ...STEP_META[key] }));

type Props = {
  activeStep: StepKey;
  statusMap: OnboardingStatusMap;
  loading?: boolean;
};

type WalkerPath = {
  start: StepKey;
  target: StepKey;
  variant: 'walk' | 'bounce';
};

const computeWalkerPath = (active: StepKey): WalkerPath => {
  if (active === 'account-setup') {
    return { start: 'account-setup', target: 'account-setup', variant: 'bounce' };
  }

  const activeIdx = Math.max(0, STEP_KEYS.indexOf(active));
  const startIdx = Math.max(0, activeIdx - 1);

  return {
    start: STEP_KEYS[startIdx] ?? 'account-setup',
    target: STEP_KEYS[activeIdx] ?? 'account-setup',
    variant: 'walk',
  };
};

const getLineClass = (state: { visited: boolean; completed: boolean }) => {
  if (state.completed) return 'w-60 h-0.5 bg-[#7E22CE]';
  if (state.visited) {
    return 'w-60 h-0.5 bg-[repeating-linear-gradient(to_right,_#7E22CE_0,_#7E22CE_10px,_transparent_10px,_transparent_18px)]';
  }
  return 'w-60 h-0.5 bg-gray-300';
};

const CrossIcon = () => (
  <svg viewBox="0 0 24 24" className="w-3 h-3 text-[#7E22CE]" fill="none" stroke="currentColor" strokeWidth="2">
    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
  </svg>
);

const CheckIcon = () => (
  <svg viewBox="0 0 24 24" className="w-3 h-3 text-white" fill="none" stroke="currentColor" strokeWidth="3">
    <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
  </svg>
);

export function OnboardingProgressHeader({ activeStep, statusMap, loading = false }: Props) {
  const router = useRouter();
  const progressRef = useRef<HTMLDivElement | null>(null);
  const stepButtonRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const [walkerLeft, setWalkerLeft] = useState(24);

  const mergedStatus = useMemo<OnboardingStatusMap>(() => {
    if (loading) {
      return createEmptyStatusMap();
    }
    const next: OnboardingStatusMap = {} as OnboardingStatusMap;
    STEP_KEYS.forEach((key) => {
      next[key] = statusMap[key] ?? { visited: false, completed: false };
    });
    return next;
  }, [statusMap, loading]);

  const walkerPath = useMemo(() => computeWalkerPath(activeStep), [activeStep]);

  const updateWalker = useCallback(() => {
    const container = progressRef.current;
    if (!container) return;

    const resolveIndex = (key: StepKey) => {
      const idx = STEP_KEYS.indexOf(key);
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
            const state = mergedStatus[step.key];
            const baseClasses =
              'w-6 h-6 rounded-full border-2 transition-colors cursor-pointer flex items-center justify-center';
            let buttonClasses = `${baseClasses} border-gray-300 bg-white text-gray-400`;
            if (isCurrent) {
              buttonClasses = `${baseClasses} border-[#D8B4FE] bg-[#F3E8FF] text-[#7E22CE]`;
            } else if (state.completed) {
              buttonClasses = `${baseClasses} border-[#7E22CE] bg-[#7E22CE] text-white`;
            } else if (state.visited) {
              buttonClasses = `${baseClasses} border-[#C084FC] bg-[#F3E8FF] text-[#7E22CE]`;
            }

            const nextStep = STEP_DEFS[index + 1];
            const lineClass = nextStep ? getLineClass(state) : '';

            const handleClick = () => {
              router.push(step.href);
            };

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
                    {!isCurrent && state.completed && <CheckIcon />}
                    {!isCurrent && !state.completed && state.visited && <CrossIcon />}
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
