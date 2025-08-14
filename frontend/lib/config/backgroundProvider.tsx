// frontend/lib/config/backgroundProvider.tsx
"use client";
import React from 'react';
import type { UIConfig } from './uiConfig';

export type BackgroundOverrides = Partial<UIConfig['backgrounds']>;

interface BackgroundContextValue {
  activity: string | null;
  overrides: BackgroundOverrides | null;
  setActivity: (activity: string | null) => void;
  setOverrides: (overrides: BackgroundOverrides | null) => void;
  clearOverrides: () => void;
}

const BackgroundContext = React.createContext<BackgroundContextValue | undefined>(undefined);

export function BackgroundProvider({ children }: { children: React.ReactNode }) {
  const [activity, setActivity] = React.useState<string | null>(null);
  const [overrides, setOverrides] = React.useState<BackgroundOverrides | null>(null);

  const value = React.useMemo<BackgroundContextValue>(() => ({
    activity,
    overrides,
    setActivity,
    setOverrides,
    clearOverrides: () => setOverrides(null),
  }), [activity, overrides]);

  return (
    <BackgroundContext.Provider value={value}>
      {children}
    </BackgroundContext.Provider>
  );
}

export function useBackgroundConfig(): BackgroundContextValue {
  const ctx = React.useContext(BackgroundContext);
  if (!ctx) {
    throw new Error('useBackgroundConfig must be used within a BackgroundProvider');
  }
  return ctx;
}
