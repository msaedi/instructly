import React from 'react';
import { act, render, waitFor } from '@testing-library/react';
import GlobalBackground from '../GlobalBackground';
import { usePathname } from 'next/navigation';
import { useBackgroundConfig } from '@/lib/config/backgroundProvider';
import {
  detectViewport,
  getActivityBackground,
  getAuthBackground,
  getLowQualityUrl,
  getOptimizedUrl,
  getSmartBackgroundForService,
  getViewportQuality,
  getViewportWidth,
  hasMultipleVariantsForService,
} from '@/lib/services/assetService';

jest.mock('@/lib/config/backgroundProvider', () => ({
  useBackgroundConfig: jest.fn(),
}));

jest.mock('@/lib/services/assetService', () => ({
  detectViewport: jest.fn(),
  getActivityBackground: jest.fn(),
  getAuthBackground: jest.fn(),
  getLowQualityUrl: jest.fn(),
  getOptimizedUrl: jest.fn(),
  getSmartBackgroundForService: jest.fn(),
  getViewportQuality: jest.fn(),
  getViewportWidth: jest.fn(),
  hasMultipleVariantsForService: jest.fn(),
}));

const mockUsePathname = usePathname as jest.Mock;
const mockUseBackgroundConfig = useBackgroundConfig as jest.Mock;

describe('GlobalBackground', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockUseBackgroundConfig.mockReturnValue({
      activity: null,
      overrides: null,
      setActivity: jest.fn(),
      setOverrides: jest.fn(),
      clearOverrides: jest.fn(),
    });
    (detectViewport as jest.Mock).mockReturnValue('desktop');
    (getViewportWidth as jest.Mock).mockReturnValue(1400);
    (getViewportQuality as jest.Mock).mockReturnValue(80);
    (getOptimizedUrl as jest.Mock).mockImplementation((path: string) => `https://cdn.example.com${path}`);
    (getLowQualityUrl as jest.Mock).mockImplementation((path: string) => `https://cdn.example.com/lq${path}`);
    (hasMultipleVariantsForService as jest.Mock).mockResolvedValue(false);
    (getSmartBackgroundForService as jest.Mock).mockResolvedValue(null);
    class MockImage {
      onload: (() => void) | null = null;
      onerror: (() => void) | null = null;
      set src(_value: string) {
        if (this.onload) this.onload();
      }
    }
    global.Image = MockImage as unknown as typeof Image;
  });

  it('returns null on the home route when no background is set', () => {
    mockUsePathname.mockReturnValue('/');
    (getActivityBackground as jest.Mock).mockReturnValue(null);

    const { container } = render(<GlobalBackground />);

    expect(container.querySelector('[aria-hidden="true"]')).not.toBeInTheDocument();
  });

  it('uses the auth background on login routes', async () => {
    const setActivity = jest.fn();
    mockUsePathname.mockReturnValue('/login');
    mockUseBackgroundConfig.mockReturnValue({
      activity: 'ignored',
      overrides: null,
      setActivity,
      setOverrides: jest.fn(),
      clearOverrides: jest.fn(),
    });
    (getAuthBackground as jest.Mock).mockReturnValue('/auth.jpg');
    (getActivityBackground as jest.Mock).mockReturnValue('/home.jpg');

    const { container } = render(<GlobalBackground />);

    await waitFor(() => {
      const bg = container.querySelector('div[aria-hidden="true"]') as HTMLDivElement | null;
      expect(bg).toBeInTheDocument();
      expect(bg?.style.backgroundImage).toContain('auth.jpg');
    });
    expect(setActivity).toHaveBeenCalledWith(null);
  });

  it('uses smart backgrounds when an activity is provided', async () => {
    mockUsePathname.mockReturnValue('/lessons');
    (getSmartBackgroundForService as jest.Mock).mockResolvedValue('/activities/guitar.jpg');
    (hasMultipleVariantsForService as jest.Mock).mockResolvedValue(true);

    const { container } = render(<GlobalBackground activity="guitar" />);

    await waitFor(() => {
      const bg = container.querySelector('div[aria-hidden="true"]') as HTMLDivElement | null;
      expect(bg?.style.backgroundImage).toContain('guitar.jpg');
    });
    expect(getSmartBackgroundForService).toHaveBeenCalled();
  });

  it('skips background rendering on mobile signup routes', () => {
    mockUsePathname.mockReturnValue('/signup');
    Object.defineProperty(window, 'innerWidth', { value: 500, writable: true });
    (getAuthBackground as jest.Mock).mockReturnValue('/auth.jpg');

    const { container } = render(<GlobalBackground />);

    expect(container.querySelector('[aria-hidden="true"]')).not.toBeInTheDocument();
  });

  it('falls back to the home activity background on non-auth routes', async () => {
    mockUsePathname.mockReturnValue('/profile');
    (getActivityBackground as jest.Mock).mockReturnValue('/home.jpg');

    const { container } = render(<GlobalBackground />);

    await waitFor(() => {
      const bg = container.querySelector('div[aria-hidden="true"]') as HTMLDivElement | null;
      expect(bg?.style.backgroundImage).toContain('home.jpg');
    });
  });

  it('extracts the original image path from Cloudflare image URLs for low-quality blur', async () => {
    mockUsePathname.mockReturnValue('/login');
    (
      getAuthBackground as jest.Mock
    ).mockReturnValue(
      'https://cdn.example.com/cdn-cgi/image/width=1600,quality=80/activities/piano.jpg'
    );

    render(<GlobalBackground />);

    await waitFor(() => {
      expect(getLowQualityUrl).toHaveBeenCalledWith('/activities/piano.jpg');
    });
  });

  it('does not rotate backgrounds while the document is hidden', async () => {
    jest.useFakeTimers();

    const originalVisibilityDescriptor = Object.getOwnPropertyDescriptor(
      document,
      'visibilityState'
    );

    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      get: () => 'hidden',
    });

    mockUsePathname.mockReturnValue('/lessons');
    (hasMultipleVariantsForService as jest.Mock).mockResolvedValue(true);
    (getSmartBackgroundForService as jest.Mock).mockResolvedValue('/activities/guitar.jpg');

    render(
      <GlobalBackground
        activity="guitar"
        overrides={{ enableRotation: true, rotationInterval: 50 }}
      />
    );

    await waitFor(() => {
      expect(getSmartBackgroundForService).toHaveBeenCalled();
    });

    const beforeAdvance = (getSmartBackgroundForService as jest.Mock).mock.calls.length;

    act(() => {
      jest.advanceTimersByTime(200);
    });

    const afterAdvance = (getSmartBackgroundForService as jest.Mock).mock.calls.length;
    expect(afterAdvance).toBe(beforeAdvance);

    if (originalVisibilityDescriptor) {
      Object.defineProperty(document, 'visibilityState', originalVisibilityDescriptor);
    }
    jest.useRealTimers();
  });

  it('rotates backgrounds while the document is visible', async () => {
    jest.useFakeTimers();

    const originalVisibilityDescriptor = Object.getOwnPropertyDescriptor(
      document,
      'visibilityState'
    );

    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      get: () => 'visible',
    });

    mockUsePathname.mockReturnValue('/lessons');
    (hasMultipleVariantsForService as jest.Mock).mockResolvedValue(true);
    (getSmartBackgroundForService as jest.Mock).mockResolvedValue('/activities/guitar.jpg');

    render(
      <GlobalBackground
        activity="guitar"
        overrides={{ enableRotation: true, rotationInterval: 50 }}
      />
    );

    await waitFor(() => {
      expect(getSmartBackgroundForService).toHaveBeenCalled();
    });

    const beforeAdvance = (getSmartBackgroundForService as jest.Mock).mock.calls.length;

    act(() => {
      jest.advanceTimersByTime(200);
    });

    await waitFor(() => {
      expect((getSmartBackgroundForService as jest.Mock).mock.calls.length).toBeGreaterThan(
        beforeAdvance
      );
    });

    if (originalVisibilityDescriptor) {
      Object.defineProperty(document, 'visibilityState', originalVisibilityDescriptor);
    }
    jest.useRealTimers();
  });

  it('handles image load error gracefully by setting isLoaded to true', async () => {
    // Ensure desktop viewport (previous tests may have changed innerWidth)
    Object.defineProperty(window, 'innerWidth', { value: 1024, writable: true, configurable: true });

    // Override the MockImage to trigger onerror after handlers are attached
    // Source sets: img.src = url, then img.onload = ..., then img.onerror = ...
    // So we defer the error trigger with queueMicrotask
    class ErrorImage {
      onload: (() => void) | null = null;
      onerror: (() => void) | null = null;
      set src(_value: string) {
        // Defer so that onerror handler is attached before we fire it
        queueMicrotask(() => {
          if (this.onerror) this.onerror();
        });
      }
    }
    global.Image = ErrorImage as unknown as typeof Image;

    mockUsePathname.mockReturnValue('/profile');
    (getActivityBackground as jest.Mock).mockReturnValue('/home.jpg');

    const { container } = render(<GlobalBackground />);

    // Even on error, the background should still render (graceful degradation)
    await waitFor(() => {
      const bgs = container.querySelectorAll('div[aria-hidden="true"]');
      expect(bgs.length).toBeGreaterThan(0);
      // The actual bg div (second aria-hidden div) should have opacity 1 after onerror sets isLoaded
      const actualBg = bgs[1] as HTMLDivElement | undefined;
      expect(actualBg?.style.opacity).toBe('1');
    });
  });

  it('uses getLowQualityUrl fallback for URLs without /cdn-cgi/image/ prefix', async () => {
    mockUsePathname.mockReturnValue('/profile');
    // Return a plain URL without Cloudflare prefix
    (getActivityBackground as jest.Mock).mockReturnValue('https://assets.example.com/photos/home.jpg');

    render(<GlobalBackground />);

    await waitFor(() => {
      // Should use URL pathname fallback: new URL(url).pathname
      expect(getLowQualityUrl).toHaveBeenCalledWith('/photos/home.jpg');
    });
  });

  it('does not reset state when the resolved URL remains unchanged', async () => {
    mockUsePathname.mockReturnValue('/profile');
    (getActivityBackground as jest.Mock).mockReturnValue('/home.jpg');

    const { rerender } = render(<GlobalBackground />);

    // Wait for initial load
    await waitFor(() => {
      expect(getActivityBackground).toHaveBeenCalled();
    });

    // Clear call counts after initial render
    (getLowQualityUrl as jest.Mock).mockClear();

    // Re-render with identical props — URL should not change
    rerender(<GlobalBackground />);

    await waitFor(() => {
      // getLowQualityUrl should NOT be called again since URL didn't change
      expect(getLowQualityUrl).not.toHaveBeenCalled();
    });
  });

  it('clears context activity when navigating to /login', () => {
    const setActivity = jest.fn();
    mockUsePathname.mockReturnValue('/login');
    mockUseBackgroundConfig.mockReturnValue({
      activity: 'guitar',
      overrides: null,
      setActivity,
      setOverrides: jest.fn(),
      clearOverrides: jest.fn(),
    });
    (getAuthBackground as jest.Mock).mockReturnValue(null);
    (getActivityBackground as jest.Mock).mockReturnValue(null);

    render(<GlobalBackground />);

    expect(setActivity).toHaveBeenCalledWith(null);
  });

  it('clears context activity when navigating to /signup', () => {
    const setActivity = jest.fn();
    mockUsePathname.mockReturnValue('/signup');
    mockUseBackgroundConfig.mockReturnValue({
      activity: 'piano',
      overrides: null,
      setActivity,
      setOverrides: jest.fn(),
      clearOverrides: jest.fn(),
    });
    (getAuthBackground as jest.Mock).mockReturnValue(null);
    (getActivityBackground as jest.Mock).mockReturnValue(null);

    render(<GlobalBackground />);

    expect(setActivity).toHaveBeenCalledWith(null);
  });

  it('suppresses background on mobile for /login route', () => {
    mockUsePathname.mockReturnValue('/login');
    Object.defineProperty(window, 'innerWidth', { value: 400, writable: true });
    (getAuthBackground as jest.Mock).mockReturnValue('/auth.jpg');

    const { container } = render(<GlobalBackground />);

    expect(container.querySelector('[aria-hidden="true"]')).not.toBeInTheDocument();
  });

  it('suppresses background on mobile for /instructor/profile route', () => {
    mockUsePathname.mockReturnValue('/instructor/profile');
    Object.defineProperty(window, 'innerWidth', { value: 320, writable: true });
    (getActivityBackground as jest.Mock).mockReturnValue('/home.jpg');

    const { container } = render(<GlobalBackground />);

    expect(container.querySelector('[aria-hidden="true"]')).not.toBeInTheDocument();
  });

  it('suppresses background on mobile for /instructor/onboarding/account-setup route', () => {
    mockUsePathname.mockReturnValue('/instructor/onboarding/account-setup');
    Object.defineProperty(window, 'innerWidth', { value: 500, writable: true });
    (getActivityBackground as jest.Mock).mockReturnValue('/home.jpg');

    const { container } = render(<GlobalBackground />);

    expect(container.querySelector('[aria-hidden="true"]')).not.toBeInTheDocument();
  });

  it('falls back to url itself when generateLowQuality cannot parse URL', async () => {
    mockUsePathname.mockReturnValue('/profile');
    // Return an invalid URL that new URL() cannot parse
    (getActivityBackground as jest.Mock).mockReturnValue('not-a-valid-url');

    render(<GlobalBackground />);

    await waitFor(() => {
      // The catch block returns the url as-is when URL parsing fails
      expect(getLowQualityUrl).not.toHaveBeenCalled();
    });
  });

  it('triggers Image onload callback and transitions to loaded state', async () => {
    Object.defineProperty(window, 'innerWidth', { value: 1024, writable: true, configurable: true });

    // MockImage that fires onload asynchronously (after handlers are assigned)
    class OnloadImage {
      onload: (() => void) | null = null;
      onerror: (() => void) | null = null;
      set src(_value: string) {
        queueMicrotask(() => {
          if (this.onload) this.onload();
        });
      }
    }
    global.Image = OnloadImage as unknown as typeof Image;

    mockUsePathname.mockReturnValue('/profile');
    (getActivityBackground as jest.Mock).mockReturnValue('/home.jpg');

    const { container } = render(<GlobalBackground />);

    await waitFor(() => {
      const bgs = container.querySelectorAll('div[aria-hidden="true"]');
      expect(bgs.length).toBeGreaterThan(0);
      // After onload, the actual background div should have opacity 1
      const actualBg = bgs[1] as HTMLDivElement | undefined;
      expect(actualBg?.style.opacity).toBe('1');
    });
  });

  it('triggers low-quality Image onload for blur-up layer', async () => {
    Object.defineProperty(window, 'innerWidth', { value: 1024, writable: true, configurable: true });

    // Track which images get created
    const createdImages: Array<{ src: string; onload: (() => void) | null }> = [];

    class TrackingImage {
      onload: (() => void) | null = null;
      onerror: (() => void) | null = null;
      private _src = '';
      get src() { return this._src; }
      set src(value: string) {
        this._src = value;
        createdImages.push({ src: value, onload: this.onload });
        queueMicrotask(() => {
          if (this.onload) this.onload();
        });
      }
    }
    global.Image = TrackingImage as unknown as typeof Image;

    mockUsePathname.mockReturnValue('/profile');
    (getActivityBackground as jest.Mock).mockReturnValue('/home.jpg');
    (getLowQualityUrl as jest.Mock).mockReturnValue('https://cdn.example.com/lq/home.jpg');

    const { container } = render(<GlobalBackground />);

    await waitFor(() => {
      const bgs = container.querySelectorAll('div[aria-hidden="true"]');
      expect(bgs.length).toBeGreaterThan(0);
      // Both hi-res and low-quality images should have been loaded
      expect(createdImages.length).toBeGreaterThanOrEqual(2);
    });
  });

  it('handles low-quality Image onerror gracefully', async () => {
    Object.defineProperty(window, 'innerWidth', { value: 1024, writable: true, configurable: true });

    let imageCount = 0;
    class MixedImage {
      onload: (() => void) | null = null;
      onerror: (() => void) | null = null;
      set src(_value: string) {
        imageCount++;
        queueMicrotask(() => {
          if (imageCount === 1) {
            // First image (hi-res) succeeds
            if (this.onload) this.onload();
          } else {
            // Second image (low-quality) fails
            if (this.onerror) this.onerror();
          }
        });
      }
    }
    global.Image = MixedImage as unknown as typeof Image;

    mockUsePathname.mockReturnValue('/profile');
    (getActivityBackground as jest.Mock).mockReturnValue('/home.jpg');
    (getLowQualityUrl as jest.Mock).mockReturnValue('https://cdn.example.com/lq/home.jpg');

    const { container } = render(<GlobalBackground />);

    await waitFor(() => {
      const bgs = container.querySelectorAll('div[aria-hidden="true"]');
      expect(bgs.length).toBeGreaterThan(0);
      // Even with low-quality error, the actual bg should still load
      const actualBg = bgs[1] as HTMLDivElement | undefined;
      expect(actualBg?.style.opacity).toBe('1');
    });
  });

  it('generates low-quality URL from Cloudflare CDN path pattern', async () => {
    mockUsePathname.mockReturnValue('/profile');
    (getActivityBackground as jest.Mock).mockReturnValue(
      'https://cdn.example.com/cdn-cgi/image/width=1600,quality=80/photos/yoga.jpg'
    );

    render(<GlobalBackground />);

    await waitFor(() => {
      // The generateLowQuality function should extract the original path from the CDN URL
      expect(getLowQualityUrl).toHaveBeenCalledWith('/photos/yoga.jpg');
    });
  });

  it('generates low-quality URL from plain URL using pathname', async () => {
    mockUsePathname.mockReturnValue('/profile');
    (getActivityBackground as jest.Mock).mockReturnValue(
      'https://assets.example.com/images/background.jpg'
    );

    render(<GlobalBackground />);

    await waitFor(() => {
      // Falls back to new URL(url).pathname
      expect(getLowQualityUrl).toHaveBeenCalledWith('/images/background.jpg');
    });
  });

  it('returns the url as-is for invalid URLs in generateLowQuality catch block', async () => {
    mockUsePathname.mockReturnValue('/profile');
    // Invalid URL that cannot be parsed by new URL()
    (getActivityBackground as jest.Mock).mockReturnValue(':::invalid-url:::');

    render(<GlobalBackground />);

    await waitFor(() => {
      // The catch block falls back to the raw URL itself
      // getLowQualityUrl should not be called since new URL() throws
      expect(getLowQualityUrl).not.toHaveBeenCalled();
    });
  });
});
