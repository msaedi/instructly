// frontend/lib/__tests__/deviceContext.test.ts
/**
 * Tests for device context tracking library
 */

import {
  captureDeviceContext,
  getDeviceType,
  getConnectionQuality,
  isLowEndDevice,
  getViewportCategory,
  formatDeviceContextForAnalytics,
  type DeviceContext,
} from '@/lib/deviceContext';

// Mock window and navigator objects
const mockWindow = {
  innerWidth: 1920,
  innerHeight: 1080,
  devicePixelRatio: 2,
  doNotTrack: '0',
  matchMedia: jest.fn(() => ({ matches: false })),
};

const mockNavigator = {
  userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
  language: 'en-US',
  languages: ['en-US', 'en'],
  platform: 'Win32',
  vendor: 'Google Inc.',
  cookieEnabled: true,
  doNotTrack: '0',
  maxTouchPoints: 0,
  hardwareConcurrency: 8,
  deviceMemory: 8,
  onLine: true,
  connection: {
    effectiveType: '4g',
    downlink: 10,
    rtt: 50,
    saveData: false,
  },
};

const mockScreen = {
  width: 2560,
  height: 1440,
  colorDepth: 24,
};

const mockDocument = {
  referrer: 'https://google.com',
  documentElement: {
    clientWidth: 1920,
    clientHeight: 1080,
  },
};

const mockPerformance = {
  memory: {
    jsHeapSizeLimit: 2147483648,
    totalJSHeapSize: 50000000,
    usedJSHeapSize: 25000000,
  },
};

// Setup global mocks
beforeAll(() => {
  // Remove ontouchstart from window if it exists
  // eslint-disable-next-line @typescript-eslint/no-explicit-any -- Test environment window manipulation
  delete (window as any).ontouchstart;

  Object.defineProperty(window, 'innerWidth', { value: mockWindow.innerWidth, writable: true });
  Object.defineProperty(window, 'innerHeight', { value: mockWindow.innerHeight, writable: true });
  Object.defineProperty(window, 'devicePixelRatio', { value: mockWindow.devicePixelRatio });
  Object.defineProperty(window, 'doNotTrack', { value: mockWindow.doNotTrack });
  Object.defineProperty(window, 'screen', { value: mockScreen });
  Object.defineProperty(window, 'matchMedia', { value: mockWindow.matchMedia });

  Object.defineProperty(navigator, 'userAgent', {
    value: mockNavigator.userAgent,
    configurable: true,
  });
  Object.defineProperty(navigator, 'language', { value: mockNavigator.language });
  Object.defineProperty(navigator, 'languages', { value: mockNavigator.languages });
  Object.defineProperty(navigator, 'platform', { value: mockNavigator.platform });
  Object.defineProperty(navigator, 'vendor', { value: mockNavigator.vendor });
  Object.defineProperty(navigator, 'cookieEnabled', { value: mockNavigator.cookieEnabled });
  Object.defineProperty(navigator, 'doNotTrack', { value: mockNavigator.doNotTrack });
  Object.defineProperty(navigator, 'maxTouchPoints', {
    value: mockNavigator.maxTouchPoints,
    writable: true,
  });
  Object.defineProperty(navigator, 'hardwareConcurrency', {
    value: mockNavigator.hardwareConcurrency,
  });
  Object.defineProperty(navigator, 'deviceMemory', {
    value: mockNavigator.deviceMemory,
    writable: true,
  });
  Object.defineProperty(navigator, 'onLine', { value: mockNavigator.onLine });
  Object.defineProperty(navigator, 'connection', {
    value: mockNavigator.connection,
    writable: true,
  });

  Object.defineProperty(document, 'referrer', { value: mockDocument.referrer });
  Object.defineProperty(document, 'documentElement', { value: mockDocument.documentElement });

  Object.defineProperty(performance, 'memory', { value: mockPerformance.memory });

  // Mock Intl.DateTimeFormat
  global.Intl = {
    ...global.Intl,
    DateTimeFormat: jest.fn(() => ({
      resolvedOptions: () => ({ timeZone: 'America/New_York' }),
    })),
  // eslint-disable-next-line @typescript-eslint/no-explicit-any -- Global Intl mock in test
  } as any;
});

describe('captureDeviceContext', () => {
  it('should capture screen information', () => {
    const context = captureDeviceContext();

    expect(context.screenWidth).toBe(2560);
    expect(context.screenHeight).toBe(1440);
    expect(context.viewportWidth).toBe(1920);
    expect(context.viewportHeight).toBe(1080);
    expect(context.devicePixelRatio).toBe(2);
    expect(context.colorDepth).toBe(24);
  });

  it('should capture device capabilities', () => {
    const context = captureDeviceContext();

    expect(context.touchSupport).toBe(false);
    expect(context.maxTouchPoints).toBe(0);
    expect(context.hardwareConcurrency).toBe(8);
    expect(context.deviceMemory).toBe(8);
  });

  it('should capture connection information', () => {
    const context = captureDeviceContext();

    expect(context.effectiveType).toBe('4g');
    expect(context.downlink).toBe(10);
    expect(context.rtt).toBe(50);
    expect(context.saveData).toBe(false);
  });

  it('should capture browser features', () => {
    const context = captureDeviceContext();

    expect(context.cookieEnabled).toBe(true);
    expect(context.doNotTrack).toBe(false);
    expect(context.language).toBe('en-US');
    expect(context.languages).toEqual(['en-US', 'en']);
    expect(context.platform).toBe('Win32');
    expect(context.vendor).toBe('Google Inc.');
  });

  it('should capture timing and additional context', () => {
    const context = captureDeviceContext();

    expect(context.timezone).toBe('America/New_York');
    expect(context.timezoneOffset).toBeDefined();
    expect(context.referrer).toBe('https://google.com');
    expect(context.isOnline).toBe(true);
    expect(context.capturedAt).toBeDefined();
  });

  it('should handle missing navigator.connection', () => {
    // Temporarily remove connection
    const originalConnection = navigator.connection;
    Object.defineProperty(navigator, 'connection', { value: undefined, writable: true });

    const context = captureDeviceContext();

    expect(context.connectionType).toBeUndefined();
    expect(context.effectiveType).toBeUndefined();
    expect(context.downlink).toBeUndefined();
    expect(context.rtt).toBeUndefined();

    // Restore
    Object.defineProperty(navigator, 'connection', { value: originalConnection, writable: true });
  });
});

describe('getDeviceType', () => {
  it('should identify mobile device', () => {
    const mobileContext = {
      viewportWidth: 375,
      touchSupport: true,
    };

    expect(getDeviceType(mobileContext as Partial<DeviceContext> as DeviceContext)).toBe('mobile');
  });

  it('should identify tablet device', () => {
    const tabletContext = {
      viewportWidth: 768,
      touchSupport: true,
    };

    // Based on implementation, touch devices < 1024px are considered mobile
    expect(getDeviceType(tabletContext as Partial<DeviceContext> as DeviceContext)).toBe('mobile');
  });

  it('should identify desktop device', () => {
    const desktopContext = {
      viewportWidth: 1920,
      touchSupport: false,
    };

    expect(getDeviceType(desktopContext as Partial<DeviceContext> as DeviceContext)).toBe('desktop');
  });

  it('should identify large touch devices as mobile', () => {
    const largePhoneContext = {
      viewportWidth: 800,
      touchSupport: true,
    };

    expect(getDeviceType(largePhoneContext as Partial<DeviceContext> as DeviceContext)).toBe('mobile');
  });
});

describe('getConnectionQuality', () => {
  it('should return fast for 4g effective type', () => {
    const context = { effectiveType: '4g' };
    expect(getConnectionQuality(context as Partial<DeviceContext> as DeviceContext)).toBe('fast');
  });

  it('should return medium for 3g effective type', () => {
    const context = { effectiveType: '3g' };
    expect(getConnectionQuality(context as Partial<DeviceContext> as DeviceContext)).toBe('medium');
  });

  it('should return slow for 2g effective type', () => {
    const context = { effectiveType: '2g' };
    expect(getConnectionQuality(context as Partial<DeviceContext> as DeviceContext)).toBe('slow');
  });

  it('should use downlink speed when effective type not available', () => {
    expect(getConnectionQuality({ downlink: 0.5 } as Partial<DeviceContext> as DeviceContext)).toBe('slow');
    expect(getConnectionQuality({ downlink: 2 } as Partial<DeviceContext> as DeviceContext)).toBe('medium');
    expect(getConnectionQuality({ downlink: 10 } as Partial<DeviceContext> as DeviceContext)).toBe('fast');
  });

  it('should use RTT when other metrics not available', () => {
    expect(getConnectionQuality({ rtt: 600 } as Partial<DeviceContext> as DeviceContext)).toBe('slow');
    expect(getConnectionQuality({ rtt: 300 } as Partial<DeviceContext> as DeviceContext)).toBe('medium');
    expect(getConnectionQuality({ rtt: 100 } as Partial<DeviceContext> as DeviceContext)).toBe('fast');
  });

  it('should return unknown when no metrics available', () => {
    expect(getConnectionQuality({} as Partial<DeviceContext> as DeviceContext)).toBe('unknown');
  });
});

describe('isLowEndDevice', () => {
  it('should identify low memory device', () => {
    const context = {
      deviceMemory: 2,
      hardwareConcurrency: 8,
    };

    expect(isLowEndDevice(context as Partial<DeviceContext> as DeviceContext)).toBe(true);
  });

  it('should identify low CPU device', () => {
    const context = {
      deviceMemory: 8,
      hardwareConcurrency: 2,
    };

    expect(isLowEndDevice(context as Partial<DeviceContext> as DeviceContext)).toBe(true);
  });

  it('should identify slow connection as low-end', () => {
    const context = {
      deviceMemory: 8,
      hardwareConcurrency: 8,
      effectiveType: '2g',
    };

    expect(isLowEndDevice(context as Partial<DeviceContext> as DeviceContext)).toBe(true);
  });

  it('should not identify high-end device as low-end', () => {
    const context = {
      deviceMemory: 8,
      hardwareConcurrency: 8,
      effectiveType: '4g',
    };

    expect(isLowEndDevice(context as Partial<DeviceContext> as DeviceContext)).toBe(false);
  });
});

describe('getViewportCategory', () => {
  it('should categorize viewport sizes correctly', () => {
    expect(getViewportCategory(320)).toBe('xs');
    expect(getViewportCategory(575)).toBe('xs');
    expect(getViewportCategory(576)).toBe('sm');
    expect(getViewportCategory(767)).toBe('sm');
    expect(getViewportCategory(768)).toBe('md');
    expect(getViewportCategory(991)).toBe('md');
    expect(getViewportCategory(992)).toBe('lg');
    expect(getViewportCategory(1199)).toBe('lg');
    expect(getViewportCategory(1200)).toBe('xl');
    expect(getViewportCategory(2560)).toBe('xl');
  });
});

describe('formatDeviceContextForAnalytics', () => {
  it('should format context for analytics', () => {
    const context = captureDeviceContext();
    const formatted = formatDeviceContextForAnalytics(context);

    expect(formatted.device_type).toBe('desktop');
    expect(formatted.viewport_category).toBe('xl');
    expect(formatted.screen_resolution).toBe('2560x1440');
    expect(formatted.viewport_size).toBe('1920x1080');
    expect(formatted.device_pixel_ratio).toBe(2);
    expect(formatted.touch_support).toBe(false);
    expect(formatted.hardware_concurrency).toBe(8);
    expect(formatted.device_memory).toBe(8);
    expect(formatted.connection_type).toBe('4g');
    expect(formatted.connection_quality).toBe('fast');
    expect(formatted.is_low_end).toBe(false);
    expect(formatted.language).toBe('en-US');
    expect(formatted.timezone).toBe('America/New_York');
    expect(formatted.is_online).toBe(true);
    expect(formatted.do_not_track).toBe(false);
    expect(formatted.cookie_enabled).toBe(true);
  });

  it('should handle touch device formatting', () => {
    // Mock touch device
    Object.defineProperty(navigator, 'maxTouchPoints', { value: 5, writable: true });
    Object.defineProperty(window, 'innerWidth', { value: 375, writable: true });

    const context = captureDeviceContext();
    const formatted = formatDeviceContextForAnalytics(context);

    expect(formatted.device_type).toBe('mobile');
    expect(formatted.viewport_category).toBe('xs');
    expect(formatted.touch_support).toBe(true);

    // Restore
    Object.defineProperty(navigator, 'maxTouchPoints', { value: 0, writable: true });
    Object.defineProperty(window, 'innerWidth', { value: 1920, writable: true });
  });
});
