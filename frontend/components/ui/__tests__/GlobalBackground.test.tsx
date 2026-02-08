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
});
