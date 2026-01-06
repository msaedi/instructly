// frontend/lib/beta-config.ts

import { env } from '@/lib/env';

export type BetaPhase = 'instructor_only' | 'alpha' | 'open_beta' | 'production';
export type StudentAccess = 'hidden' | 'invite_only' | 'public';
export type BetaSite = 'beta' | 'preview' | 'production';

export interface BetaConfig {
  site: BetaSite;
  phase: BetaPhase;
  studentAccess: StudentAccess;
  showBanner: boolean;
  bannerMessage?: string;
}

function normalizeHostname(hostname: string | null | undefined): string {
  if (!hostname) return '';
  let lower = hostname.toLowerCase();
  // Strip port if present (e.g., beta.instainstru.com:3000)
  const colonIndex = lower.indexOf(':');
  if (colonIndex !== -1) lower = lower.slice(0, colonIndex);
  // Strip leading www.
  return lower.startsWith('www.') ? lower.slice(4) : lower;
}

export function getBetaConfig(hostname?: string | null): BetaConfig {
  const host = normalizeHostname(hostname || (typeof window !== 'undefined' ? window.location.hostname : ''));

  // Domains from env to avoid hard-coding
  const PREVIEW_DOMAINS = [
    (env.get('NEXT_PUBLIC_PREVIEW_DOMAIN') || '').toLowerCase().trim(),
    (env.get('NEXT_PUBLIC_PREVIEW_ALTERNATE_DOMAIN') || '').toLowerCase().trim(),
    'preview.instainstru.com',
    'instainstru-preview.vercel.app',
    'instructly-ten.vercel.app',
  ].filter(Boolean);

  if (host === 'beta.instainstru.com') {
    return {
      site: 'beta',
      phase: 'instructor_only',
      studentAccess: 'hidden',
      showBanner: true,
      bannerMessage: 'NYC Instructor Beta',
    };
  }

  // Local alias for beta testing
  if (host === 'beta-local.instainstru.com') {
    return {
      site: 'beta',
      phase: 'instructor_only',
      studentAccess: 'hidden',
      showBanner: true,
      bannerMessage: 'NYC Instructor Beta (Local)',
    };
  }

  if (PREVIEW_DOMAINS.includes(host)) {
    // Preview environment (staff gate enforced at proxy level)
    return {
      site: 'preview',
      phase: 'production',
      studentAccess: 'public',
      showBanner: false,
    };
  }

  // Default production-like behavior
  return {
    site: 'production',
    phase: 'production',
    studentAccess: 'public',
    showBanner: false,
  };
}

type HeadersLike = Pick<Headers, 'get'>;

export function getBetaConfigFromHeaders(headers: HeadersLike): BetaConfig {
  const host = headers.get('host');
  return getBetaConfig(host || undefined);
}

export function useBetaConfig(): BetaConfig {
  // Client-only hook; fall back to default if called on server erroneously
  return getBetaConfig(typeof window !== 'undefined' ? window.location.hostname : undefined);
}

export function isRouteAccessible(pathname: string, config: BetaConfig): boolean {
  if (config.site !== 'beta') return true;

  // Instructor-only: restrict student and public browsing routes
  if (config.phase === 'instructor_only') {
    const blockedPrefixes = [
      '/student',
      '/search',
      '/services',
      '/book',
      '/instructors', // public browsing of instructor profiles
    ];
    if (pathname === '/' || blockedPrefixes.some((p) => pathname === p || pathname.startsWith(p + '/'))) {
      return false;
    }
  }
  return true;
}

export function getBetaRedirect(pathname: string, config: BetaConfig, _userRole?: 'instructor' | 'student' | 'admin' | null): string | null {
  if (config.site !== 'beta') return null;

  if (config.phase === 'instructor_only') {
    // Root goes to instructor code gate
    if (pathname === '/') return '/instructor/join';

    // Student/public routes redirect to instructor join page
    const blockedPrefixes = ['/student', '/search', '/services', '/book', '/instructors'];
    if (blockedPrefixes.some((p) => pathname === p || pathname.startsWith(p + '/'))) {
      return '/instructor/join';
    }
  }
  return null;
}
