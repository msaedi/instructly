// frontend/hooks/useDeviceContext.ts
/**
 * React hook for device context tracking
 *
 * Provides easy access to device information and monitoring capabilities
 */

import { useEffect, useState, useCallback, useRef } from 'react';
import {
  captureDeviceContext,
  getDeviceType,
  getConnectionQuality,
  isLowEndDevice,
  getViewportCategory,
  formatDeviceContextForAnalytics,
  monitorOrientationChanges,
  monitorConnectionChanges,
} from '@/lib/deviceContext';

interface UseDeviceContextOptions {
  // Whether to monitor changes in real-time
  monitorChanges?: boolean;
  // Debounce delay for viewport changes (ms)
  debounceDelay?: number;
  // Callback when context changes
  onChange?: (context: DeviceContextState) => void;
}

interface DeviceContextState {
  // Raw context data
  context: ReturnType<typeof captureDeviceContext> | null;

  // Computed properties
  deviceType: 'mobile' | 'tablet' | 'desktop' | null;
  connectionQuality: 'slow' | 'medium' | 'fast' | 'unknown';
  isLowEnd: boolean;
  viewportCategory: 'xs' | 'sm' | 'md' | 'lg' | 'xl' | null;
  orientation: 'portrait' | 'landscape' | null;
  isOnline: boolean;

  // Analytics-ready format
  analyticsData: ReturnType<typeof formatDeviceContextForAnalytics> | null;

  // Methods
  refresh: () => void;
}

export function useDeviceContext(options: UseDeviceContextOptions = {}): DeviceContextState {
  const { monitorChanges = true, debounceDelay = 300, onChange } = options;

  const [state, setState] = useState<DeviceContextState>({
    context: null,
    deviceType: null,
    connectionQuality: 'unknown',
    isLowEnd: false,
    viewportCategory: null,
    orientation: null,
    isOnline: true,
    analyticsData: null,
    refresh: () => {},
  });

  const debounceTimerRef = useRef<NodeJS.Timeout | null>(null);
  const cleanupFunctionsRef = useRef<(() => void)[]>([]);

  // Capture and update device context
  const captureContext = useCallback(() => {
    const context = captureDeviceContext();
    const deviceType = getDeviceType(context);
    const connectionQuality = getConnectionQuality(context);
    const isLowEnd = isLowEndDevice(context);
    const viewportCategory = getViewportCategory(context.viewportWidth);
    const analyticsData = formatDeviceContextForAnalytics(context);

    const orientation = window.innerWidth > window.innerHeight ? 'landscape' : 'portrait';

    const newState: DeviceContextState = {
      context,
      deviceType,
      connectionQuality,
      isLowEnd,
      viewportCategory,
      orientation,
      isOnline: context.isOnline,
      analyticsData,
      refresh: captureContext,
    };

    setState(newState);

    // Call onChange callback if provided
    if (onChange) {
      onChange(newState);
    }

    return newState;
  }, [onChange]);

  // Debounced capture for resize events
  const debouncedCapture = useCallback(() => {
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }

    debounceTimerRef.current = setTimeout(() => {
      captureContext();
    }, debounceDelay);
  }, [captureContext, debounceDelay]);

  // Initial capture on mount
  useEffect(() => {
    captureContext();
  }, [captureContext]);

  // Set up monitoring if enabled
  useEffect(() => {
    if (!monitorChanges) return;

    const cleanupFunctions: (() => void)[] = [];

    // Monitor viewport changes
    const handleResize = () => debouncedCapture();
    window.addEventListener('resize', handleResize);
    cleanupFunctions.push(() => window.removeEventListener('resize', handleResize));

    // Monitor orientation changes
    const cleanupOrientation = monitorOrientationChanges((orientation) => {
      setState((prev) => ({ ...prev, orientation: orientation as 'portrait' | 'landscape' }));
    });
    cleanupFunctions.push(cleanupOrientation);

    // Monitor connection changes
    const cleanupConnection = monitorConnectionChanges((online, context) => {
      if (context) {
        captureContext();
      } else {
        setState((prev) => ({ ...prev, isOnline: online }));
      }
    });
    cleanupFunctions.push(cleanupConnection);

    // Monitor visibility changes
    const handleVisibilityChange = () => {
      if (!document.hidden) {
        captureContext();
      }
    };
    document.addEventListener('visibilitychange', handleVisibilityChange);
    cleanupFunctions.push(() =>
      document.removeEventListener('visibilitychange', handleVisibilityChange)
    );

    cleanupFunctionsRef.current = cleanupFunctions;

    // Cleanup
    return () => {
      cleanupFunctions.forEach((cleanup) => cleanup());
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
    };
  }, [monitorChanges, captureContext, debouncedCapture]);

  return state;
}

/**
 * Hook for responsive design based on viewport category
 */
export function useViewportCategory() {
  const { viewportCategory } = useDeviceContext({ monitorChanges: true });

  return {
    category: viewportCategory,
    isMobile: viewportCategory === 'xs' || viewportCategory === 'sm',
    isTablet: viewportCategory === 'md',
    isDesktop: viewportCategory === 'lg' || viewportCategory === 'xl',
    isXs: viewportCategory === 'xs',
    isSm: viewportCategory === 'sm',
    isMd: viewportCategory === 'md',
    isLg: viewportCategory === 'lg',
    isXl: viewportCategory === 'xl',
  };
}

/**
 * Hook for performance-aware rendering
 */
export function usePerformanceMode() {
  const { isLowEnd, connectionQuality } = useDeviceContext({ monitorChanges: true });

  return {
    isLowEnd,
    connectionQuality,
    shouldReduceMotion: isLowEnd || connectionQuality === 'slow',
    shouldLazyLoad: connectionQuality !== 'fast',
    shouldPreload: connectionQuality === 'fast' && !isLowEnd,
  };
}

/**
 * Hook for device-specific features
 */
export function useDeviceFeatures() {
  const { context, deviceType } = useDeviceContext({ monitorChanges: false });

  return {
    hasTouchSupport: context?.touchSupport ?? false,
    deviceType,
    isStandalone: window.matchMedia('(display-mode: standalone)').matches,
    supportsVibration: 'vibrate' in navigator,
    supportsClipboard: 'clipboard' in navigator,
    supportsShare: 'share' in navigator,
    supportsNotifications: 'Notification' in window,
    supportsGeolocation: 'geolocation' in navigator,
  };
}
