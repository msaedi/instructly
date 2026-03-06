export const clearPendingCloseTimeout = (
  closeTimeoutRef: { current: ReturnType<typeof setTimeout> | null },
): void => {
  if (closeTimeoutRef.current) {
    clearTimeout(closeTimeoutRef.current);
    closeTimeoutRef.current = null;
  }
};
