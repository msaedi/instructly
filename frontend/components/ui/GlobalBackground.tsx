// frontend/components/ui/GlobalBackground.tsx
'use client';

import React from 'react';
import { usePathname } from 'next/navigation';
import { detectViewport, getActivityBackground, getAuthBackground, getLowQualityUrl, getOptimizedUrl, getSmartBackgroundForService, getViewportQuality, getViewportWidth, hasMultipleVariantsForService } from '@/lib/services/assetService';
import { uiConfig } from '@/lib/config/uiConfig';
import { useBackgroundConfig } from '@/lib/config/backgroundProvider';

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
type Props = {
  overrides?: Partial<typeof uiConfig.backgrounds>;
  activity?: string;
};

export default function GlobalBackground({ overrides, activity }: Props): React.ReactElement | null {
  const pathname = usePathname();
  const { activity: ctxActivity, overrides: ctxOverrides, setActivity: setCtxActivity } = useBackgroundConfig();
  const [bgUrl, setBgUrl] = React.useState<string | null>(null);
  const [lqUrl, setLqUrl] = React.useState<string | null>(null);
  const [isLowReady, setIsLowReady] = React.useState(false);
  const [isLoaded, setIsLoaded] = React.useState(false);
  const [hasMounted, setHasMounted] = React.useState(false);
  const [canAutoRotate, setCanAutoRotate] = React.useState(false);
  const [rotationTick, setRotationTick] = React.useState(0);

  React.useEffect(() => {
    setHasMounted(true);
  }, []);

  React.useEffect(() => {
    const viewport = detectViewport();
    const merged = { ...uiConfig.backgrounds, ...(ctxOverrides || {}), ...(overrides || {}) };

    const generateLowQuality = (url: string | null): string | null => {
      if (!url) return null;
      const match = url.match(/\/cdn-cgi\/image\/[^/]+(\/.+)$/);
      if (match) {
        const originalPath = match[1];
        return getLowQualityUrl(originalPath);
      }
      try {
        const u = new URL(url);
        return getLowQualityUrl(u.pathname);
      } catch {
        return url;
      }
    };

    async function resolveBg() {
      let resolvedUrl: string | null = null;

      const isAuthOrHome = pathname === '/' || pathname === '' || pathname.startsWith('/login') || pathname.startsWith('/signup');
      const effectiveActivity = isAuthOrHome ? (activity || null) : (activity || ctxActivity || null);
      if (effectiveActivity) {
        // Determine if this activity has multiple variants to decide if timer should run
        const multi = await hasMultipleVariantsForService(effectiveActivity);
        setCanAutoRotate(!!multi && merged.enableRotation && merged.rotationInterval > 0);

        const cleanPath = await getSmartBackgroundForService(effectiveActivity, undefined, {
          enableRotation: merged.enableRotation,
          rotationIntervalMs: merged.rotationInterval,
        });
        if (cleanPath) {
          resolvedUrl = getOptimizedUrl(cleanPath, {
            width: getViewportWidth(viewport),
            quality: getViewportQuality(viewport),
            format: 'auto',
            fit: 'cover',
          });
        }
      }

      if (!resolvedUrl) {
        if (pathname === '/' || pathname === '') {
          // Skip background for home page - it has its own hero background
          resolvedUrl = null;
        } else if (pathname.startsWith('/login') || pathname.startsWith('/signup')) {
          resolvedUrl = getAuthBackground('default', viewport) || getActivityBackground('home', viewport);
        } else {
          resolvedUrl = getActivityBackground('home', viewport);
        }
      }

      // If URL didn't change, avoid resetting state to prevent stuck blur
      const urlChanged = resolvedUrl !== bgUrl;
      if (urlChanged) {
        setBgUrl(resolvedUrl);
        setIsLoaded(false);
        setIsLowReady(false);
        const low = generateLowQuality(resolvedUrl);
        setLqUrl(low);
      } else {
        // No change; ensure we are considered loaded
        setIsLoaded(true);
        setIsLowReady(true);
      }

      if (resolvedUrl && urlChanged) {
        const img = new Image();
        img.src = resolvedUrl;
        img.onload = () => {
          const commit = () => setIsLoaded(true);
          if (!hasMounted) {
            requestAnimationFrame(() => requestAnimationFrame(commit));
          } else {
            setTimeout(commit, 80);
          }
        };
        img.onerror = () => setIsLoaded(true);
      }

      if (urlChanged && lqUrl) {
        const lq = new Image();
        lq.src = lqUrl;
        lq.onload = () => setIsLowReady(true);
        lq.onerror = () => setIsLowReady(true);
      }
    }

    resolveBg();
  }, [pathname, ctxActivity, ctxOverrides, overrides, activity, hasMounted, rotationTick]);

  // Auto-rotate while staying on the same page when multiple variants exist
  React.useEffect(() => {
    const merged = { ...uiConfig.backgrounds, ...(ctxOverrides || {}), ...(overrides || {}) };
    if (!canAutoRotate || !merged.enableRotation || merged.rotationInterval <= 0) return;

    const id = window.setInterval(() => {
      if (typeof document !== 'undefined' && document.visibilityState !== 'visible') return;
      setRotationTick((v) => v + 1);
    }, merged.rotationInterval);
    return () => window.clearInterval(id);
  }, [canAutoRotate, ctxOverrides, overrides]);

  // Clear activity when entering home/login/signup routes so background resets immediately
  React.useEffect(() => {
    if (pathname === '/' || pathname === '' || pathname.startsWith('/login') || pathname.startsWith('/signup')) {
      setCtxActivity(null);
    }
  }, [pathname, setCtxActivity]);

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
