import { useEffect, useMemo, useState } from 'react';
import { subscribeSharedTicker } from './useSharedTicker';

function parseTarget(target: Date | string | null): number {
  if (target === null) return 0;
  const date = typeof target === 'string' ? new Date(target) : target;
  const ts = date.getTime();
  return Number.isFinite(ts) ? ts : 0;
}

function formatRemaining(seconds: number): string {
  if (seconds <= 0) return '00:00';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  const mm = String(m).padStart(2, '0');
  const ss = String(s).padStart(2, '0');
  if (h > 0) {
    return `${String(h).padStart(2, '0')}:${mm}:${ss}`;
  }
  return `${mm}:${ss}`;
}

export interface CountdownResult {
  secondsLeft: number;
  isExpired: boolean;
  formatted: string;
}

function calcSeconds(targetMs: number): number {
  if (targetMs === 0) return 0;
  return Math.max(0, Math.floor((targetMs - Date.now()) / 1000));
}

/**
 * Live countdown to a target date, updating every second.
 * Returns 0 / expired for null, past, or invalid targets.
 */
export function useCountdown(targetDate: Date | string | null): CountdownResult {
  const targetMs = useMemo(() => parseTarget(targetDate), [targetDate]);

  const [secondsLeft, setSecondsLeft] = useState(() => calcSeconds(targetMs));

  useEffect(() => {
    const update = () => {
      setSecondsLeft(calcSeconds(targetMs));
    };

    update();

    if (targetMs === 0) {
      return;
    }

    return subscribeSharedTicker(update);
  }, [targetMs]);

  return {
    secondsLeft,
    isExpired: secondsLeft <= 0,
    formatted: formatRemaining(secondsLeft),
  };
}
