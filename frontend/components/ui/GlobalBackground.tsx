// frontend/components/ui/GlobalBackground.tsx
'use client';

import React from 'react';
import { usePathname } from 'next/navigation';
import { getActivityBackground, getAuthBackground } from '@/lib/services/assetService';

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
  const [isLoaded, setIsLoaded] = React.useState(false);

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

    if (resolvedUrl) {
      const img = new Image();
      img.src = resolvedUrl;
      img.onload = () => setIsLoaded(true);
      img.onerror = () => setIsLoaded(true);
    }
  }, [pathname]);

  if (!bgUrl) {
    return null;
  }

  return (
    <>
      {/* Blur-up layer: fades out after load */}
      <div
        aria-hidden="true"
        className="fixed inset-0 z-0 transition-opacity duration-500"
        style={{
          backgroundImage: `url('${bgUrl}')`,
          backgroundSize: 'cover',
          backgroundPosition: 'center',
          backgroundRepeat: 'no-repeat',
          backgroundAttachment: 'fixed',
          filter: 'blur(12px)',
          transform: 'scale(1.05)',
          opacity: isLoaded ? 0 : 1,
        }}
      />
      {/* Actual background image */}
      <div
        className="fixed inset-0 z-0"
        aria-hidden="true"
        style={{
          backgroundImage: `url('${bgUrl}')`,
          backgroundSize: 'cover',
          backgroundPosition: 'center',
          backgroundRepeat: 'no-repeat',
          backgroundAttachment: 'fixed',
        }}
      />
      {/* Readability overlay */}
      <div className="fixed inset-0 z-0 bg-white/60 dark:bg-black/60" aria-hidden="true" />
    </>
  );
}
