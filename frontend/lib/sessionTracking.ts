// frontend/lib/sessionTracking.ts
/**
 * Browser session tracking for search analytics.
 *
 * Tracks user sessions for analytics purposes, including:
 * - Session ID generation and management
 * - Session timeout after 30 minutes of inactivity
 * - Analytics context for search tracking
 */

import { logger } from '@/lib/logger';

const SESSION_ID_KEY = 'searchSessionId';
const SESSION_TIMEOUT = 30 * 60 * 1000; // 30 minutes in milliseconds

let sessionTimeout: NodeJS.Timeout | null = null;
let pageViewCount = 0;
let sessionStartTime = Date.now(); // UTC timestamp in milliseconds

/**
 * Generate a new UUID v4
 */
function generateUUID(): string {
  if (typeof window !== 'undefined' && window.crypto && window.crypto.randomUUID) {
    return window.crypto.randomUUID();
  }

  // Fallback for older browsers
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

/**
 * Get or create session ID for analytics tracking
 */
export function getSessionId(): string {
  if (typeof window === 'undefined') return '';

  let sessionId = sessionStorage.getItem(SESSION_ID_KEY);

  if (!sessionId) {
    sessionId = generateUUID();
    sessionStorage.setItem(SESSION_ID_KEY, sessionId);
    logger.debug('Created new search session', { sessionId });
  }

  return sessionId;
}

/**
 * Reset session after timeout
 */
function resetSession(): void {
  if (typeof window === 'undefined') return;

  sessionStorage.removeItem(SESSION_ID_KEY);

  // Reset tracking data
  pageViewCount = 0;
  sessionStartTime = Date.now();

  logger.debug('Session reset due to inactivity');
}

/**
 * Refresh session timeout on activity
 */
export function refreshSession(): void {
  if (typeof window === 'undefined') return;

  // Clear existing timeout
  if (sessionTimeout) {
    clearTimeout(sessionTimeout);
  }

  // Set new timeout
  sessionTimeout = setTimeout(resetSession, SESSION_TIMEOUT);
}

/**
 * Initialize session tracking
 * Should be called once when the app loads
 */
export function initializeSessionTracking(): void {
  if (typeof window === 'undefined') return;

  // Initialize session on load
  getSessionId();
  refreshSession();

  // Increment page view count
  pageViewCount++;
  logger.debug('Page view tracked', { pageViewCount });

  // Refresh session on user activity
  const handleActivity = () => refreshSession();

  // Track various user interactions
  window.addEventListener('click', handleActivity, { passive: true });
  window.addEventListener('keypress', handleActivity, { passive: true });
  window.addEventListener('scroll', handleActivity, { passive: true });
  window.addEventListener('touchstart', handleActivity, { passive: true });

  logger.info('Session tracking initialized');
}

/**
 * Track page navigation
 * Should be called when navigating to a new page
 */
export function trackPageView(): void {
  if (typeof window === 'undefined') return;

  pageViewCount++;
  logger.debug('Page view tracked', {
    pageViewCount,
    path: window.location.pathname,
  });
}

/**
 * Clean up session tracking (for component unmount)
 */
export function cleanupSessionTracking(): void {
  if (sessionTimeout) {
    clearTimeout(sessionTimeout);
    sessionTimeout = null;
  }
}

/**
 * Get analytics context for the current page
 */
export function getAnalyticsContext(): {
  page: string;
  viewport: string;
  timestamp: string;
  page_view_count: number;
  session_duration: number;
} {
  if (typeof window === 'undefined') {
    return {
      page: '/',
      viewport: '0x0',
      timestamp: new Date().toISOString(),
      page_view_count: 0,
      session_duration: 0,
    };
  }

  const currentTime = Date.now();
  const sessionDurationSeconds = Math.floor((currentTime - sessionStartTime) / 1000);

  return {
    page: window.location.pathname,
    viewport: `${window.innerWidth}x${window.innerHeight}`,
    timestamp: new Date().toISOString(),
    page_view_count: pageViewCount,
    session_duration: sessionDurationSeconds,
  };
}
