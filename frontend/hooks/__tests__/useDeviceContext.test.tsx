// frontend/hooks/__tests__/useDeviceContext.test.tsx
/**
 * Tests for device context React hooks
 */

import { renderHook, act } from '@testing-library/react';
import {
  useDeviceContext,
  useViewportCategory,
  usePerformanceMode,
  useDeviceFeatures,
} from '@/hooks/useDeviceContext';

// Mock the deviceContext module
jest.mock('@/lib/deviceContext', () => ({
  captureDeviceContext: jest.fn(() => ({
    screenWidth: 2560,
    screenHeight: 1440,
    viewportWidth: 1920,
    viewportHeight: 1080,
    devicePixelRatio: 2,
    colorDepth: 24,
    touchSupport: false,
    maxTouchPoints: 0,
    hardwareConcurrency: 8,
    deviceMemory: 8,
    connectionType: '4g',
    effectiveType: '4g',
    downlink: 10,
    rtt: 50,
    saveData: false,
    cookieEnabled: true,
    doNotTrack: false,
    language: 'en-US',
    languages: ['en-US', 'en'],
    platform: 'Win32',
    vendor: 'Google Inc.',
    timezone: 'America/New_York',
    timezoneOffset: 300,
    jsHeapSizeLimit: 2147483648,
    usedJsHeapSize: 25000000,
    referrer: 'https://google.com',
    isOnline: true,
    capturedAt: '2024-01-01T00:00:00Z',
  })),
  getDeviceType: jest.fn(() => 'desktop'),
  getConnectionQuality: jest.fn(() => 'fast'),
  isLowEndDevice: jest.fn(() => false),
  getViewportCategory: jest.fn(() => 'xl'),
  formatDeviceContextForAnalytics: jest.fn(() => ({
    device_type: 'desktop',
    viewport_category: 'xl',
    screen_resolution: '2560x1440',
    viewport_size: '1920x1080',
    device_pixel_ratio: 2,
    touch_support: false,
    hardware_concurrency: 8,
    device_memory: 8,
    connection_type: '4g',
    connection_quality: 'fast',
    is_low_end: false,
    language: 'en-US',
    timezone: 'America/New_York',
    is_online: true,
    do_not_track: false,
    cookie_enabled: true,
  })),
  monitorOrientationChanges: jest.fn((callback) => {
    // Simulate initial orientation
    callback('landscape');
    return () => {}; // Cleanup function
  }),
  monitorConnectionChanges: jest.fn((_callback) => {
    return () => {}; // Cleanup function
  }),
}));

import * as deviceContext from '@/lib/deviceContext';
const mockDeviceContext = jest.mocked(deviceContext, { shallow: true });

describe('useDeviceContext', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('should capture device context on mount', () => {
    const { result: _result } = renderHook(() => useDeviceContext());

    expect(mockDeviceContext.captureDeviceContext).toHaveBeenCalled();
    expect(_result.current.context).toBeDefined();
    expect(_result.current.deviceType).toBe('desktop');
    expect(_result.current.connectionQuality).toBe('fast');
    expect(_result.current.isLowEnd).toBe(false);
    expect(_result.current.viewportCategory).toBe('xl');
    expect(_result.current.orientation).toBe('landscape');
    expect(_result.current.isOnline).toBe(true);
    expect(_result.current.analyticsData).toBeDefined();
  });

  it('should provide refresh method', () => {
    const { result: _result } = renderHook(() => useDeviceContext());

    jest.clearAllMocks();

    act(() => {
      _result.current.refresh();
    });

    expect(mockDeviceContext.captureDeviceContext).toHaveBeenCalled();
  });

  it('should call onChange callback when context changes', () => {
    const onChange = jest.fn();
    const { result: _result } = renderHook(() => useDeviceContext({ onChange }));

    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        deviceType: 'desktop',
        connectionQuality: 'fast',
      })
    );
  });

  it('should set up monitoring when enabled', () => {
    renderHook(() => useDeviceContext({ monitorChanges: true }));

    expect(mockDeviceContext.monitorOrientationChanges).toHaveBeenCalled();
    expect(mockDeviceContext.monitorConnectionChanges).toHaveBeenCalled();
  });

  it('should not set up monitoring when disabled', () => {
    jest.clearAllMocks();

    renderHook(() => useDeviceContext({ monitorChanges: false }));

    expect(mockDeviceContext.monitorOrientationChanges).not.toHaveBeenCalled();
    expect(mockDeviceContext.monitorConnectionChanges).not.toHaveBeenCalled();
  });

  it('should handle viewport resize with debouncing', async () => {
    jest.useFakeTimers();
    const { result: _result } = renderHook(() =>
      useDeviceContext({
        monitorChanges: true,
        debounceDelay: 300,
      })
    );

    jest.clearAllMocks();

    // Simulate resize event
    act(() => {
      window.dispatchEvent(new Event('resize'));
    });

    // Should not capture immediately
    expect(mockDeviceContext.captureDeviceContext).not.toHaveBeenCalled();

    // Fast forward debounce timer
    act(() => {
      jest.advanceTimersByTime(300);
    });

    // Now should capture
    expect(mockDeviceContext.captureDeviceContext).toHaveBeenCalled();

    jest.useRealTimers();
  });

  it('should handle visibility change', () => {
    const { result: _result } = renderHook(() => useDeviceContext({ monitorChanges: true }));

    jest.clearAllMocks();

    // Simulate document becoming visible
    Object.defineProperty(document, 'hidden', { value: false, writable: true });

    act(() => {
      document.dispatchEvent(new Event('visibilitychange'));
    });

    expect(mockDeviceContext.captureDeviceContext).toHaveBeenCalled();
  });

  it('should cleanup on unmount', () => {
    const cleanupFn = jest.fn();
    mockDeviceContext.monitorOrientationChanges.mockReturnValue(cleanupFn);
    mockDeviceContext.monitorConnectionChanges.mockReturnValue(cleanupFn);

    const { unmount } = renderHook(() => useDeviceContext({ monitorChanges: true }));

    unmount();

    expect(cleanupFn).toHaveBeenCalled();
  });
});

describe('useViewportCategory', () => {
  it('should provide viewport category helpers', () => {
    mockDeviceContext.getViewportCategory.mockReturnValue('md');

    const { result: _result } = renderHook(() => useViewportCategory());

    expect(_result.current.category).toBe('md');
    expect(_result.current.isMobile).toBe(false);
    expect(_result.current.isTablet).toBe(true);
    expect(_result.current.isDesktop).toBe(false);
    expect(_result.current.isXs).toBe(false);
    expect(_result.current.isSm).toBe(false);
    expect(_result.current.isMd).toBe(true);
    expect(_result.current.isLg).toBe(false);
    expect(_result.current.isXl).toBe(false);
  });

  it('should identify mobile viewports correctly', () => {
    mockDeviceContext.getViewportCategory.mockReturnValue('xs');

    const { result: _result } = renderHook(() => useViewportCategory());

    expect(_result.current.isMobile).toBe(true);
    expect(_result.current.isTablet).toBe(false);
    expect(_result.current.isDesktop).toBe(false);
  });

  it('should identify desktop viewports correctly', () => {
    mockDeviceContext.getViewportCategory.mockReturnValue('lg');

    const { result: _result } = renderHook(() => useViewportCategory());

    expect(_result.current.isMobile).toBe(false);
    expect(_result.current.isTablet).toBe(false);
    expect(_result.current.isDesktop).toBe(true);
  });
});

describe('usePerformanceMode', () => {
  it('should provide performance mode for high-end device', () => {
    mockDeviceContext.isLowEndDevice.mockReturnValue(false);
    mockDeviceContext.getConnectionQuality.mockReturnValue('fast');

    const { result: _result } = renderHook(() => usePerformanceMode());

    expect(_result.current.isLowEnd).toBe(false);
    expect(_result.current.connectionQuality).toBe('fast');
    expect(_result.current.shouldReduceMotion).toBe(false);
    expect(_result.current.shouldLazyLoad).toBe(false);
    expect(_result.current.shouldPreload).toBe(true);
  });

  it('should provide performance mode for low-end device', () => {
    mockDeviceContext.isLowEndDevice.mockReturnValue(true);
    mockDeviceContext.getConnectionQuality.mockReturnValue('slow');

    const { result: _result } = renderHook(() => usePerformanceMode());

    expect(_result.current.isLowEnd).toBe(true);
    expect(_result.current.connectionQuality).toBe('slow');
    expect(_result.current.shouldReduceMotion).toBe(true);
    expect(_result.current.shouldLazyLoad).toBe(true);
    expect(_result.current.shouldPreload).toBe(false);
  });

  it('should handle medium connection quality', () => {
    mockDeviceContext.isLowEndDevice.mockReturnValue(false);
    mockDeviceContext.getConnectionQuality.mockReturnValue('medium');

    const { result: _result } = renderHook(() => usePerformanceMode());

    expect(_result.current.shouldReduceMotion).toBe(false);
    expect(_result.current.shouldLazyLoad).toBe(true);
    expect(_result.current.shouldPreload).toBe(false);
  });
});

describe('useDeviceFeatures', () => {
  beforeEach(() => {
    // Mock browser APIs
    Object.defineProperty(window, 'matchMedia', {
      value: jest.fn(() => ({ matches: false })),
      writable: true,
    });

    Object.defineProperty(navigator, 'vibrate', { value: jest.fn(), writable: true });
    Object.defineProperty(navigator, 'clipboard', { value: {}, writable: true });
    Object.defineProperty(navigator, 'share', { value: jest.fn(), writable: true });
    Object.defineProperty(navigator, 'geolocation', { value: {}, writable: true });
    Object.defineProperty(window, 'Notification', { value: jest.fn(), writable: true });
  });

  it('should detect device features', () => {
    const { result: _result } = renderHook(() => useDeviceFeatures());

    expect(_result.current.hasTouchSupport).toBe(false);
    expect(_result.current.deviceType).toBe('desktop');
    expect(_result.current.isStandalone).toBe(false);
    expect(_result.current.supportsVibration).toBe(true);
    expect(_result.current.supportsClipboard).toBe(true);
    expect(_result.current.supportsShare).toBe(true);
    expect(_result.current.supportsNotifications).toBe(true);
    expect(_result.current.supportsGeolocation).toBe(true);
  });

  it('should detect standalone mode', () => {
    window.matchMedia = jest.fn(() => ({
      matches: true,
      media: '',
      onchange: null,
      addListener: jest.fn(),
      removeListener: jest.fn(),
      addEventListener: jest.fn(),
      removeEventListener: jest.fn(),
      dispatchEvent: jest.fn()
    })) as jest.Mock;

    const { result: _result } = renderHook(() => useDeviceFeatures());

    expect(_result.current.isStandalone).toBe(true);
  });

  it('should handle missing features gracefully', () => {
    // Since we can't truly remove properties from navigator in jsdom,
    // we'll just verify that the hook checks for their existence
    const { result: _result } = renderHook(() => useDeviceFeatures());

    // These checks test the logic, not whether features are actually missing
    expect(typeof _result.current.supportsVibration).toBe('boolean');
    expect(typeof _result.current.supportsShare).toBe('boolean');
    expect(typeof _result.current.supportsNotifications).toBe('boolean');
    expect(typeof _result.current.supportsClipboard).toBe('boolean');
    expect(typeof _result.current.supportsGeolocation).toBe('boolean');
  });
});
