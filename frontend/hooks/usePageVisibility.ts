import { useSyncExternalStore } from 'react';

export function usePageVisibility(): boolean {
  return useSyncExternalStore(
    (onStoreChange) => {
      document.addEventListener('visibilitychange', onStoreChange);
      return () => {
        document.removeEventListener('visibilitychange', onStoreChange);
      };
    },
    () => document.visibilityState === 'visible',
    () => true,
  );
}
