'use client';

import { createContext, useContext, useMemo, useState, useEffect } from 'react';
import type { BetaConfig } from '@/lib/beta-config';
import { getBetaConfig } from '@/lib/beta-config';

interface BetaContextValue {
  config: BetaConfig;
}

const BetaContext = createContext<BetaContextValue | undefined>(undefined);

export function BetaProvider({ children }: { children: React.ReactNode }) {
  const [config, setConfig] = useState<BetaConfig>(() => getBetaConfig());

  useEffect(() => {
    // On mount in client, recompute using window hostname (guards SSR mismatch)
    setConfig(getBetaConfig());
  }, []);

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
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (config.site !== 'beta' || !config.showBanner) {
      setVisible(false);
      return;
    }
    const dismissed = typeof window !== 'undefined' && sessionStorage.getItem('beta_banner_dismissed');
    setVisible(!dismissed);
  }, [config]);

  if (!visible) return null;

  const colorClass = config.phase === 'instructor_only' ? 'bg-amber-100 text-amber-900 border-amber-300'
                    : config.phase === 'alpha' ? 'bg-blue-100 text-blue-900 border-blue-300'
                    : 'bg-green-100 text-green-900 border-green-300';

  return (
    <div className={`w-full ${colorClass} border-b py-2 px-4 text-sm flex items-center justify-between`}>
      <span>{config.bannerMessage || (config.phase === 'instructor_only' ? 'NYC Instructor Beta' : config.phase === 'alpha' ? 'Alpha Testing' : 'Open Beta')}</span>
      <button
        className="underline"
        onClick={() => {
          sessionStorage.setItem('beta_banner_dismissed', '1');
          setVisible(false);
        }}
      >
        Dismiss
      </button>
    </div>
  );
}
