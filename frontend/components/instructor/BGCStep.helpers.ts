export const clearPollTimer = (pollTimerRef: { current: number | null }) => {
  if (pollTimerRef.current !== null) {
    globalThis.clearTimeout?.(pollTimerRef.current);
    pollTimerRef.current = null;
  }
};
