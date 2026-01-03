'use client';

import { createContext, useContext, useMemo, useSyncExternalStore } from 'react';
import type { BetaConfig } from '@/lib/beta-config';
import { getBetaConfig } from '@/lib/beta-config';

interface BetaContextValue {
  config: BetaConfig;
}

const BetaContext = createContext<BetaContextValue | undefined>(undefined);
const bannerDismissedListeners = new Set<() => void>();
const bannerDismissedStore = {
  subscribe(listener: () => void) {
    bannerDismissedListeners.add(listener);
    return () => bannerDismissedListeners.delete(listener);
  },
  getSnapshot() {
    if (typeof window === 'undefined') return false;
    return sessionStorage.getItem('beta_banner_dismissed') === '1';
  },
  getServerSnapshot() {
    return false;
  },
  setDismissed() {
    if (typeof window === 'undefined') return;
    sessionStorage.setItem('beta_banner_dismissed', '1');
    bannerDismissedListeners.forEach((listener) => listener());
  },
};

export function BetaProvider({
  children,
  initialConfig,
}: {
  children: React.ReactNode;
  initialConfig?: BetaConfig;
}) {
  const config = useMemo(() => initialConfig ?? getBetaConfig(), [initialConfig]);

  const value = useMemo(() => ({ config }), [config]);
  return <BetaContext.Provider value={value}>{children}</BetaContext.Provider>;
}

export function useBeta(): BetaContextValue {
  const ctx = useContext(BetaContext);
  if (!ctx) throw new Error('useBeta must be used within a BetaProvider');
  return ctx;
}

export function BetaBanner() {
  const { config } = useBeta();
  const isDismissed = useSyncExternalStore(
    bannerDismissedStore.subscribe,
    bannerDismissedStore.getSnapshot,
    bannerDismissedStore.getServerSnapshot
  );
  const isVisible = config.site === 'beta' && config.showBanner && !isDismissed;

  if (!isVisible) return null;

  const colorClass = config.phase === 'instructor_only' ? 'bg-[#FFD400] text-black'
                    : config.phase === 'alpha' ? 'bg-blue-100 text-blue-900'
                    : 'bg-green-100 text-green-900';

  return (
    <div className={`w-full ${colorClass} py-3 px-6 text-sm font-semibold flex items-center justify-between mt-2`}>
      <span>{config.bannerMessage || (config.phase === 'instructor_only' ? 'NYC Instructor Beta' : config.phase === 'alpha' ? 'Alpha Testing' : 'Open Beta')}</span>
      <button
        className="underline"
        onClick={() => {
          bannerDismissedStore.setDismissed();
        }}
      >
        Dismiss
      </button>
    </div>
  );
}
