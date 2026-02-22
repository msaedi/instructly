type TickerListener = () => void;

const listeners = new Set<TickerListener>();
let intervalId: ReturnType<typeof setInterval> | null = null;

function startTicker(): void {
  if (intervalId !== null) return;
  intervalId = setInterval(() => {
    const snapshot = Array.from(listeners);
    snapshot.forEach((listener) => listener());
  }, 1000);
}

function stopTickerIfIdle(): void {
  if (intervalId === null) return;
  if (listeners.size > 0) return;
  clearInterval(intervalId);
  intervalId = null;
}

export function subscribeSharedTicker(listener: TickerListener): () => void {
  listeners.add(listener);
  startTicker();

  return () => {
    listeners.delete(listener);
    stopTickerIfIdle();
  };
}
