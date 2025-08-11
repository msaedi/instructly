/**
 * Navigation State Manager for Instructor Booking Flow
 *
 * This manager handles the complex state persistence requirements for the booking flow:
 * - Preserves slot selection when using back button from payment page
 * - Clears slot selection when navigating fresh from search/home
 * - Implements TTL to prevent stale data
 * - Tracks navigation source to differentiate flow types
 */

export interface NavigationState {
  selectedSlot: {
    date: string;
    time: string;
    duration: number;
    instructorId: string;
  } | null;
  timestamp: number;
  source: 'search' | 'profile' | 'payment' | 'login' | 'direct';
  flowId: string; // Unique ID for this booking flow
}

const STORAGE_KEY = 'booking_navigation_state';
const TTL_MS = 30000; // 30 seconds

export class NavigationStateManager {
  private static instance: NavigationStateManager;

  private constructor() {}

  static getInstance(): NavigationStateManager {
    if (!NavigationStateManager.instance) {
      NavigationStateManager.instance = new NavigationStateManager();
    }
    return NavigationStateManager.instance;
  }

  /**
   * Generate a unique flow ID for tracking booking sessions
   */
  private generateFlowId(): string {
    return `flow_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }

  /**
   * Save navigation state when proceeding to payment
   */
  saveBookingFlow(
    slot: NavigationState['selectedSlot'],
    source: NavigationState['source'] = 'profile'
  ): string {
    if (!slot) {
      return '';
    }

    const flowId = this.generateFlowId();
    const state: NavigationState = {
      selectedSlot: slot,
      timestamp: Date.now(),
      source,
      flowId
    };

    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    return flowId;
  }

  /**
   * Retrieve navigation state if valid (not expired and matching instructor)
   */
  getBookingFlow(instructorId: string): NavigationState['selectedSlot'] | null {
    try {
      const stored = sessionStorage.getItem(STORAGE_KEY);

      if (!stored) {
        return null;
      }

      const state: NavigationState = JSON.parse(stored);

      // Check TTL
      const age = Date.now() - state.timestamp;
      const isWithinTTL = age <= TTL_MS;

      if (!isWithinTTL) {
        this.clearBookingFlow();
        return null;
      }

      // Check instructor match
      const instructorMatch = String(state.selectedSlot?.instructorId) === String(instructorId);

      if (!instructorMatch) {
        return null;
      }

      // Check if we're coming from booking flow pages (back button scenario)
      // When navigating back from payment page, we stored source as 'payment'
      const isFromPaymentFlow = state.source === 'payment';

      const referrer = document.referrer;
      const bookingFlowPages = [
        '/student/booking/confirm',  // Payment/confirmation page
        '/booking/confirmation',      // Alternative confirmation URL
        '/payment',                   // Payment page
        '/login',                     // Login page
        '/signup'                     // Signup page
      ];

      const referrerMatchesBookingFlow = bookingFlowPages.some(page => {
        return referrer.includes(page);
      });

      // Restore if either:
      // 1. We saved from payment page (source === 'payment'), OR
      // 2. Document referrer shows we're coming from a booking flow page
      const shouldRestore = isFromPaymentFlow || referrerMatchesBookingFlow;

      if (shouldRestore) {
        return state.selectedSlot;
      }

      return null;

    } catch (e) {
      return null;
    }
  }

  /**
   * Clear navigation state - called when starting fresh from search
   */
  clearBookingFlow(): void {
    sessionStorage.removeItem(STORAGE_KEY);
  }

  /**
   * Check if current navigation is part of active booking flow
   */
  isActiveBookingFlow(flowId: string): boolean {
    try {
      const stored = sessionStorage.getItem(STORAGE_KEY);
      if (!stored) return false;

      const state: NavigationState = JSON.parse(stored);
      const age = Date.now() - state.timestamp;

      return state.flowId === flowId && age < TTL_MS;
    } catch {
      return false;
    }
  }

  /**
   * Update timestamp to keep flow alive during active booking
   */
  touchBookingFlow(): void {
    try {
      const stored = sessionStorage.getItem(STORAGE_KEY);
      if (!stored) return;

      const state: NavigationState = JSON.parse(stored);
      state.timestamp = Date.now();
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch (e) {
      // Silent failure
    }
  }
}

// Export singleton instance
export const navigationStateManager = NavigationStateManager.getInstance();
