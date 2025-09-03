// frontend/lib/deviceContext.ts
/**
 * Device Context Tracking
 *
 * Captures rich device and browser information from the client side
 * to enhance analytics and improve user experience.
 */

export interface DeviceContext {
  // Screen information
  screenWidth: number;
  screenHeight: number;
  viewportWidth: number;
  viewportHeight: number;
  devicePixelRatio: number;
  colorDepth: number;

  // Device capabilities
  touchSupport: boolean;
  maxTouchPoints: number;
  hardwareConcurrency: number;
  deviceMemory?: number; // GB, only in Chrome

  // Connection information
  connectionType?: string;
  effectiveType?: string;
  downlink?: number;
  rtt?: number;
  saveData?: boolean;

  // Browser features
  cookieEnabled: boolean;
  doNotTrack: boolean;
  language: string;
  languages: string[];
  platform?: string; // Deprecated but included for compatibility
  vendor?: string; // Deprecated but included for compatibility
  userAgentData?: {
    brands: Array<{ brand: string; version: string }>;
    mobile: boolean;
    platform: string;
  };

  // Timing
  timezone: string;
  timezoneOffset: number;

  // Performance
  jsHeapSizeLimit?: number;
  usedJsHeapSize?: number;

  // Additional context
  referrer: string;
  isOnline: boolean;

  // Client timestamp
  capturedAt: string;
}

interface NetworkInformation extends EventTarget {
  type?: string;
  effectiveType?: string;
  downlink?: number;
  rtt?: number;
  saveData?: boolean;
}

declare global {
  interface Navigator {
    connection?: NetworkInformation;
    mozConnection?: NetworkInformation;
    webkitConnection?: NetworkInformation;
    deviceMemory?: number;
    hardwareConcurrency: number;
    userAgentData?: {
      brands: Array<{ brand: string; version: string }>;
      mobile: boolean;
      platform: string;
      getHighEntropyValues(hints: string[]): Promise<{
        brands?: Array<{ brand: string; version: string }>;
        mobile?: boolean;
        platform?: string;
        platformVersion?: string;
        architecture?: string;
        bitness?: string;
        model?: string;
        uaFullVersion?: string;
      }>;
    };
  }

  interface Performance {
    memory?: {
      jsHeapSizeLimit: number;
      totalJSHeapSize: number;
      usedJSHeapSize: number;
    };
  }
}

/**
 * Capture comprehensive device context from the browser
 */
export function captureDeviceContext(): DeviceContext {
  const nav = navigator;
  const win = window;
  const screen = win.screen;
  const doc = document;

  // Get connection information
  const connection = nav.connection || nav.mozConnection || nav.webkitConnection;

  const context: DeviceContext = {
    // Screen information
    screenWidth: screen.width,
    screenHeight: screen.height,
    viewportWidth: win.innerWidth || doc.documentElement.clientWidth,
    viewportHeight: win.innerHeight || doc.documentElement.clientHeight,
    devicePixelRatio: win.devicePixelRatio || 1,
    colorDepth: screen.colorDepth,

    // Device capabilities
    touchSupport: 'ontouchstart' in win || nav.maxTouchPoints > 0,
    maxTouchPoints: nav.maxTouchPoints || 0,
    hardwareConcurrency: nav.hardwareConcurrency || 1,
    ...(nav.deviceMemory && { deviceMemory: nav.deviceMemory }),

    // Connection information (if available)
    ...(connection?.type && { connectionType: connection.type }),
    ...(connection?.effectiveType && { effectiveType: connection.effectiveType }),
    ...(connection?.downlink && { downlink: connection.downlink }),
    ...(connection?.rtt && { rtt: connection.rtt }),
    ...(connection?.saveData !== undefined && { saveData: connection.saveData }),

    // Browser features
    cookieEnabled: nav.cookieEnabled,
    doNotTrack: (nav as Navigator & { doNotTrack?: string }).doNotTrack === '1' || (win as Window & { doNotTrack?: string }).doNotTrack === '1',
    language: nav.language,
    languages: nav.languages ? [...nav.languages] : [nav.language],
    // Include deprecated properties for compatibility
    ...(nav.platform && { platform: nav.platform }),
    ...(nav.vendor && { vendor: nav.vendor }),
    // Include modern User-Agent Client Hints if available
    ...(nav.userAgentData && {
      userAgentData: {
        brands: nav.userAgentData.brands,
        mobile: nav.userAgentData.mobile,
        platform: nav.userAgentData.platform,
      }
    }),

    // Timing
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    timezoneOffset: new Date().getTimezoneOffset(),

    // Performance (Chrome only)
    ...(performance.memory?.jsHeapSizeLimit && { jsHeapSizeLimit: performance.memory.jsHeapSizeLimit }),
    ...(performance.memory?.usedJSHeapSize && { usedJsHeapSize: performance.memory.usedJSHeapSize }),

    // Additional context
    referrer: doc.referrer,
    isOnline: nav.onLine,

    // Client timestamp
    capturedAt: new Date().toISOString(),
  };

  return context;
}

/**
 * Get device type based on screen size and touch support
 */
export function getDeviceType(context: DeviceContext): 'mobile' | 'tablet' | 'desktop' {
  const { viewportWidth, touchSupport } = context;

  // Mobile: < 768px or touch with small screen
  if (viewportWidth < 768 || (touchSupport && viewportWidth < 1024)) {
    return 'mobile';
  }

  // Tablet: touch support with medium screen
  if (touchSupport && viewportWidth >= 768 && viewportWidth < 1024) {
    return 'tablet';
  }

  // Desktop: everything else
  return 'desktop';
}

/**
 * Get connection quality estimation
 */
export function getConnectionQuality(
  context: DeviceContext
): 'slow' | 'medium' | 'fast' | 'unknown' {
  const { effectiveType, downlink, rtt } = context;

  // Use effective type if available
  if (effectiveType) {
    if (effectiveType === 'slow-2g' || effectiveType === '2g') return 'slow';
    if (effectiveType === '3g') return 'medium';
    if (effectiveType === '4g') return 'fast';
  }

  // Fallback to downlink speed
  if (downlink !== undefined) {
    if (downlink < 1) return 'slow';
    if (downlink < 5) return 'medium';
    return 'fast';
  }

  // Fallback to RTT
  if (rtt !== undefined) {
    if (rtt > 500) return 'slow';
    if (rtt > 200) return 'medium';
    return 'fast';
  }

  return 'unknown';
}

/**
 * Check if device is likely low-end based on various indicators
 */
export function isLowEndDevice(context: DeviceContext): boolean {
  const { deviceMemory, hardwareConcurrency } = context;

  // Low memory (< 4GB)
  if (deviceMemory && deviceMemory < 4) return true;

  // Low CPU cores (< 4)
  if (hardwareConcurrency < 4) return true;

  // Slow connection
  const connectionQuality = getConnectionQuality(context);
  if (connectionQuality === 'slow') return true;

  return false;
}

/**
 * Get viewport size category for responsive design
 */
export function getViewportCategory(width: number): 'xs' | 'sm' | 'md' | 'lg' | 'xl' {
  if (width < 576) return 'xs'; // Mobile
  if (width < 768) return 'sm'; // Large mobile
  if (width < 992) return 'md'; // Tablet
  if (width < 1200) return 'lg'; // Desktop
  return 'xl'; // Large desktop
}

/**
 * Format device context for analytics tracking
 */
export function formatDeviceContextForAnalytics(context: DeviceContext) {
  return {
    // Essential device info
    device_type: getDeviceType(context),
    viewport_category: getViewportCategory(context.viewportWidth),

    // Screen details
    screen_resolution: `${context.screenWidth}x${context.screenHeight}`,
    viewport_size: `${context.viewportWidth}x${context.viewportHeight}`,
    device_pixel_ratio: context.devicePixelRatio,

    // Capabilities
    touch_support: context.touchSupport,
    hardware_concurrency: context.hardwareConcurrency,
    device_memory: context.deviceMemory,

    // Connection
    connection_type: context.connectionType || context.effectiveType || 'unknown', // fallback to effectiveType if connectionType unavailable
    connection_effective_type: context.effectiveType, // effective speed (slow-2g, 2g, 3g, 4g)
    connection_quality: getConnectionQuality(context),
    is_low_end: isLowEndDevice(context),

    // Browser context
    language: context.language,
    timezone: context.timezone,
    is_online: context.isOnline,

    // Privacy
    do_not_track: context.doNotTrack,
    cookie_enabled: context.cookieEnabled,
  };
}

/**
 * Monitor device orientation changes
 */
export function monitorOrientationChanges(callback: (orientation: string) => void) {
  const getOrientation = () => {
    if (window.screen?.orientation) {
      return window.screen.orientation.type;
    }
    return window.innerWidth > window.innerHeight ? 'landscape' : 'portrait';
  };

  // Initial orientation
  callback(getOrientation());

  // Listen for changes
  const handleChange = () => callback(getOrientation());

  if (window.screen?.orientation) {
    window.screen.orientation.addEventListener('change', handleChange);
  } else {
    window.addEventListener('orientationchange', handleChange);
    window.addEventListener('resize', handleChange);
  }

  // Return cleanup function
  return () => {
    if (window.screen?.orientation) {
      window.screen.orientation.removeEventListener('change', handleChange);
    } else {
      window.removeEventListener('orientationchange', handleChange);
      window.removeEventListener('resize', handleChange);
    }
  };
}

/**
 * Monitor network connection changes
 */
export function monitorConnectionChanges(
  callback: (online: boolean, context?: DeviceContext) => void
) {
  const handleChange = () => {
    callback(navigator.onLine, captureDeviceContext());
  };

  window.addEventListener('online', handleChange);
  window.addEventListener('offline', handleChange);

  // Monitor connection quality changes if supported
  const connection = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
  if (connection) {
    connection.addEventListener('change', handleChange);
  }

  // Return cleanup function
  return () => {
    window.removeEventListener('online', handleChange);
    window.removeEventListener('offline', handleChange);
    if (connection) {
      connection.removeEventListener('change', handleChange);
    }
  };
}
