"use client";

import { useEffect, useState } from 'react';

/**
 * Returns true when the onboarding avatar menu should render inline (mobile view).
 * Uses a 640px breakpoint to match Tailwind's `sm` boundary so behavior stays in sync with layout.
 */
export function useOnboardingInlineProfileMenu(breakpointPx = 640) {
  const [isInline, setIsInline] = useState(false);

  useEffect(() => {
    if (typeof window === 'undefined') return undefined;

    const mediaQuery = window.matchMedia(`(max-width: ${breakpointPx - 1}px)`);
    const updateMatch = () => setIsInline(mediaQuery.matches);
    updateMatch();

    if (typeof mediaQuery.addEventListener === 'function') {
      mediaQuery.addEventListener('change', updateMatch);
      return () => mediaQuery.removeEventListener('change', updateMatch);
    }

    // Fallback for Safari < 14
    mediaQuery.addListener(updateMatch);
    return () => mediaQuery.removeListener(updateMatch);
  }, [breakpointPx]);

  return isInline;
}
