'use client';

import { useEffect, useId, useRef } from 'react';
import GlobalBackground from '@/components/ui/GlobalBackground';
import Link from 'next/link';

export default function WelcomeStep() {
  const ctaRef = useRef<HTMLAnchorElement | null>(null);
  const titleId = useId();

  useEffect(() => {
    // Auto-focus CTA for a11y
    ctaRef.current?.focus();
  }, []);

  return (
    <div className="fixed inset-0 z-50 insta-onboarding-page">
      {/* Restore global background behind the overlay */}
      <GlobalBackground />
      {/* Overlay */}
      <div className="absolute inset-0 bg-black/25 dark:bg-black/50 animate-fade-in" aria-hidden="true" />

      {/* Centered modal */}
      <div className="absolute inset-0 flex items-center justify-center p-4">
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby={titleId}
          className="insta-flow-panel bg-white/80 dark:bg-gray-900/80 w-full max-w-md sm:max-w-lg rounded-2xl p-8 sm:p-12 animate-scale-in"
        >
          {/* Success icon - brand yellow */}
          <div className="mx-auto mb-6 h-12 w-12 rounded-full bg-[#FFD700] flex items-center justify-center">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden>
              <path d="M20 7L9 18L4 13" stroke="#FFFFFF" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>

          <h1 id={titleId} className="text-2xl sm:text-3xl font-bold insta-onboarding-strong-text text-center mb-2">
            Welcome aboard!
          </h1>
          <p className="text-lg insta-onboarding-subtitle text-center mb-4">
            We&apos;re thrilled to have you on <span className="font-bold">iNSTAiNSTRU</span>!
          </p>
          <div className="space-y-3 text-center text-gray-600 dark:text-gray-400 text-base">
            <p>
              Over <span className="font-semibold text-gray-900 dark:text-gray-100">500 students</span> searched for instructors in NYC this week.
            </p>
            <p>Next up, create your profile so you&apos;re launch-ready.</p>
            <p>We&apos;ll alert you the moment booking goes live!</p>
          </div>

          <div className="mt-8 flex justify-center">
            <Link
              ref={ctaRef}
              href="/instructor/onboarding/account-setup"
              className="insta-primary-btn inline-flex items-center justify-center w-52 h-12 rounded-lg text-white text-base font-medium focus:outline-none focus:ring-4 focus:ring-[#7E22CE]/20 transition"
            >
              Let&apos;s get started
            </Link>
          </div>
        </div>
      </div>

      <style jsx global>{`
        .animate-fade-in { animation: fade-in 200ms ease-out both; }
        .animate-scale-in { animation: scale-in 300ms ease-out both; }
        @keyframes fade-in { from { opacity: 0 } to { opacity: 1 } }
        @keyframes scale-in { from { opacity: 0; transform: scale(0.95) } to { opacity: 1; transform: scale(1) } }
      `}</style>
    </div>
  );
}
