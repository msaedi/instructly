import { Suspense } from 'react';
import Image from 'next/image';
import LoginClient from './LoginClient';
import { getAuthBackground } from '@/lib/services/assetService';

const LOGIN_BACKGROUND_DESKTOP = getAuthBackground('default', 'desktop');
const LOGIN_BACKGROUND_TABLET = getAuthBackground('default', 'tablet');
const LOGIN_BACKGROUND_MOBILE = getAuthBackground('default', 'mobile');

const loginFallback = (
  <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
    <div className="insta-surface-card py-8 px-4 shadow sm:px-10">
      <div className="animate-pulse">
        <div className="h-10 bg-gray-200 rounded mb-4" />
        <div className="h-10 bg-gray-200 rounded mb-4" />
        <div className="h-10 bg-gray-200 rounded" />
      </div>
    </div>
  </div>
);

type LoginSearchParams = {
  redirect?: string | string[];
  returnTo?: string | string[];
};

type LoginPageProps = {
  searchParams?: Promise<LoginSearchParams>;
};

function sanitizeRedirect(value?: string | string[]): string | undefined {
  if (typeof value === 'string' && value.trim()) {
    return value;
  }
  if (Array.isArray(value)) {
    return value.find((entry) => typeof entry === 'string' && entry.trim());
  }
  return undefined;
}

function LoginBackgroundLayers() {
  const desktopSrc = LOGIN_BACKGROUND_DESKTOP ?? LOGIN_BACKGROUND_TABLET ?? LOGIN_BACKGROUND_MOBILE;

  if (!desktopSrc) {
    return null;
  }

  return (
    <>
      <div className="hidden sm:block absolute inset-0 z-0 pointer-events-none" aria-hidden="true">
        <Image
          src={desktopSrc}
          alt=""
          width={1920}
          height={1080}
          sizes="100vw"
          className="object-cover h-full w-full"
          style={{ filter: 'blur(12px)', transform: 'scale(1.05)' }}
          draggable={false}
          priority
          fetchPriority="high"
        />
      </div>
      <div className="hidden sm:block absolute inset-0 z-[1] pointer-events-none" aria-hidden="true">
        <Image
          src={desktopSrc}
          alt=""
          width={1920}
          height={1080}
          sizes="100vw"
          className="object-cover h-full w-full"
          priority
          fetchPriority="high"
          draggable={false}
        />
        <div className="absolute inset-0 bg-white/40 dark:bg-black/60" />
      </div>
      {LOGIN_BACKGROUND_MOBILE && (
        <div className="sm:hidden absolute inset-0 z-0 pointer-events-none" aria-hidden="true">
          <Image
            src={LOGIN_BACKGROUND_MOBILE}
            alt=""
            width={1200}
            height={1600}
            sizes="100vw"
            className="object-cover h-full w-full"
            priority
            fetchPriority="high"
            draggable={false}
          />
          <div className="absolute inset-0 bg-white/60 dark:bg-black/70" />
        </div>
      )}
    </>
  );
}

export default async function LoginPage({ searchParams }: LoginPageProps) {
  const resolvedSearchParams = (await searchParams) ?? {};
  const redirectCandidate = sanitizeRedirect(resolvedSearchParams.redirect);
  const returnToCandidate = sanitizeRedirect(resolvedSearchParams.returnTo);
  const redirect = redirectCandidate ?? returnToCandidate ?? '/';

  return (
    <div className="relative min-h-screen flex flex-col justify-center py-12 sm:px-6 lg:px-8" style={{ isolation: 'isolate' }}>
      <LoginBackgroundLayers />
      <div className="relative z-10">
        <Suspense fallback={loginFallback}>
          <LoginClient redirect={redirect} />
        </Suspense>
      </div>
    </div>
  );
}
