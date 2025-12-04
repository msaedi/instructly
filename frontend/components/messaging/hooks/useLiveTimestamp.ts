import { useState, useEffect } from 'react';

/**
 * Hook that returns a value that changes every minute.
 * Use this as a dependency in useMemo/useEffect to trigger
 * periodic re-renders for relative timestamps.
 *
 * @param intervalMs - Update interval in milliseconds (default: 60000 = 1 minute)
 * @returns Current minute timestamp (floored to minute)
 *
 * @example
 * ```tsx
 * const tick = useLiveTimestamp();
 *
 * const formattedMessages = useMemo(() => {
 *   return messages.map(m => ({
 *     ...m,
 *     timestampLabel: formatRelativeTimestamp(m.created_at),
 *   }));
 * }, [messages, tick]); // tick causes re-render every minute
 * ```
 */
export function useLiveTimestamp(intervalMs = 60000): number {
  const [tick, setTick] = useState(() => Math.floor(Date.now() / intervalMs));

  useEffect(() => {
    const timer = setInterval(() => {
      setTick(Math.floor(Date.now() / intervalMs));
    }, intervalMs);

    return () => clearInterval(timer);
  }, [intervalMs]);

  return tick;
}
