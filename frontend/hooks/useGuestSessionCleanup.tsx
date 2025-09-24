// frontend/hooks/useGuestSessionCleanup.tsx
/**
 * Hook for cleaning up expired guest sessions on app initialization
 */

'use client';

import { useEffect } from 'react';
import { getGuestSessionId } from '@/lib/searchTracking';
import { logger } from '@/lib/logger';

export function useGuestSessionCleanup() {
  useEffect(() => {
    // Initialize guest session cleanup on app mount
    // This will check for expired sessions and create new ones if needed
    try {
      const sessionId = getGuestSessionId();
      if (sessionId) {
        logger.debug('Guest session initialized', { sessionId });
      }
    } catch (error) {
      logger.error('Error initializing guest session', error as Error);
    }
  }, []);
}
