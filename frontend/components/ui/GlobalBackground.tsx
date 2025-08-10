// frontend/components/ui/GlobalBackground.tsx
'use client';

import React from 'react';
import { usePathname } from 'next/navigation';
import { getActivityBackground, getAuthBackground, getLowQualityUrl, getOptimizedUrl } from '@/lib/services/assetService';

/**
 * GlobalBackground
 *
 * Renders a site-wide fixed background image with a blur-up transition
 * and a readability overlay. Chooses an appropriate background based on route.
 *
 * - '/' → activity 'home'
 * - '/login' or '/signup' → auth 'default' (reuses activity 'home' fallback if desired)
 * - other routes → no background (can be extended later)
 */
export default function GlobalBackground(): React.ReactElement | null {
  const pathname = usePathname();
  const [bgUrl, setBgUrl] = React.useState<string | null>(null);
  const [lqUrl, setLqUrl] = React.useState<string | null>(null);
  const [isLowReady, setIsLowReady] = React.useState(false);
  const [isLoaded, setIsLoaded] = React.useState(false);
  const [hasMounted, setHasMounted] = React.useState(false);

  React.useEffect(() => {
    setHasMounted(true);
  }, []);

  React.useEffect(() => {
    const vw = typeof window !== 'undefined' ? window.innerWidth : 1024;
    const viewport: 'mobile' | 'tablet' | 'desktop' = vw < 640 ? 'mobile' : vw < 1024 ? 'tablet' : 'desktop';

    let resolvedUrl: string | null = null;
    if (pathname === '/' || pathname === '') {
      resolvedUrl = getActivityBackground('home', viewport);
    } else if (pathname.startsWith('/login') || pathname.startsWith('/signup')) {
      // Use dedicated auth background from R2
      resolvedUrl = getAuthBackground('default', viewport) || getActivityBackground('home', viewport);
    } else {
      // Default global background on all other routes: use 'home'
      resolvedUrl = getActivityBackground('home', viewport);
    }

    setBgUrl(resolvedUrl);
    setIsLoaded(false);
    setIsLowReady(false);

    // Generate a low-quality version for blur-up effect
    // Extract path from the optimized URL to generate LQIP
    const generateLowQuality = (url: string | null): string | null => {
      if (!url) return null;
      // The URL is already optimized, extract the path portion
      const match = url.match(/\/cdn-cgi\/image\/[^/]+(\/.+)$/);
      if (match) {
        // This is an optimized URL, extract the original path
        const originalPath = match[1];
        return getLowQualityUrl(originalPath);
      }
      // Fallback: try to extract path from regular URL
      try {
        const u = new URL(url);
        return getLowQualityUrl(u.pathname);
      } catch {
        return url;
      }
    };

    const low = generateLowQuality(resolvedUrl);
    setLqUrl(low);

    if (resolvedUrl) {
      const img = new Image();
      img.src = resolvedUrl;
      img.onload = () => {
        // Ensure at least one paint with blur visible before showing sharp image
        const commit = () => setIsLoaded(true);
        if (!hasMounted) {
          // Defer to next frames to guarantee transition after first paint
          requestAnimationFrame(() => requestAnimationFrame(commit));
        } else {
          // Even when cached, add a tiny delay so transition is visible
          setTimeout(commit, 80);
        }
      };
      img.onerror = () => setIsLoaded(true);
    }

    if (low) {
      const lq = new Image();
      lq.src = low;
      lq.onload = () => setIsLowReady(true);
      lq.onerror = () => setIsLowReady(true);
    } else {
      setIsLowReady(true);
    }
  }, [pathname]);

  if (!bgUrl) {
    return null;
  }

  return (
    <>
      {/* Blur-up layer (low-res): above sharp bg, fades to 0 after hi-res load */}
      <div
        aria-hidden="true"
        className="fixed inset-0 -z-20 transition-opacity duration-1000"
        style={{
          backgroundImage: lqUrl ? `url('${lqUrl}')` : bgUrl ? `url('${bgUrl}')` : undefined,
          backgroundSize: 'cover',
          backgroundPosition: 'center',
          backgroundRepeat: 'no-repeat',
          backgroundAttachment: 'fixed',
          filter: 'blur(12px)',
          transform: 'scale(1.05)',
          opacity: isLoaded ? 0 : isLowReady ? 1 : 0,
        }}
      />
      {/* Actual background image */}
      <div
        className="fixed inset-0 -z-30 transition-opacity duration-1500"
        aria-hidden="true"
        style={{
          backgroundImage: `url('${bgUrl}')`,
          backgroundSize: 'cover',
          backgroundPosition: 'center',
          backgroundRepeat: 'no-repeat',
          backgroundAttachment: 'fixed',
          opacity: isLoaded ? 1 : 0,
        }}
      />
      {/* Readability overlay */}
      <div className="fixed inset-0 -z-10 bg-white/40 dark:bg-black/60" aria-hidden="true" />
    </>
  );
}
