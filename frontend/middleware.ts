import { NextRequest, NextResponse } from 'next/server';
import { getBetaConfigFromHeaders, getBetaRedirect, isRouteAccessible } from '@/lib/beta-config';

// Protected preview middleware for staff-only access on Vercel
// Requirements:
// - Check cookie `staff_access_token`
// - Else accept `?token=...` query and set cookie for 30 days
// - Token value comes from env STAFF_ACCESS_TOKEN (server-side only)
// - Exclude: /api/*, /_next/*, /static/*, /staff-login

const STAFF_COOKIE_NAME = 'staff_access_token';
const STAFF_LOGIN_PATH = '/staff-login';

function isPublicAssetPath(pathname: string): boolean {
  return (
    pathname.startsWith('/_next/') ||
    pathname.startsWith('/static/') ||
    pathname.startsWith('/api/') ||
    pathname === '/robots.txt' ||
    pathname === '/logout' ||
    pathname === STAFF_LOGIN_PATH ||
    pathname === '/instructor/join' ||
    pathname === '/instructor/welcome'
  );
}

export async function middleware(request: NextRequest) {
  const { nextUrl, cookies } = request;
  const pathname = nextUrl.pathname;
  const isPreviewProject = (process.env.NEXT_PUBLIC_APP_ENV || '').toLowerCase() === 'preview';

  // Detect site configuration by hostname, then allow cookie to override phase for beta host
  const betaConfig = getBetaConfigFromHeaders(request.headers);
  // Try to read phase from backend server header for source-of-truth
  let serverPhase: string | null = null;
  let serverAllowSignup: string | null = null;
  if (betaConfig.site === 'beta') {
    try {
      const apiBase = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000';
      const healthRes = await fetch(`${apiBase}/health`, { method: 'GET', cache: 'no-store' });
      serverPhase = healthRes.headers.get('x-beta-phase');
      serverAllowSignup = healthRes.headers.get('x-beta-allow-signup');
    } catch {}
  }
  const cookiePhase = cookies.get('beta_phase')?.value || null;
  const effectivePhase = (serverPhase === 'open_beta' || serverPhase === 'instructor_only')
    ? serverPhase
    : (cookiePhase === 'open_beta' || cookiePhase === 'instructor_only')
      ? cookiePhase
      : betaConfig.phase;
  const effectiveConfig = { ...betaConfig, phase: effectivePhase } as ReturnType<typeof getBetaConfigFromHeaders>;
  const responseHeaders = new Headers();
  responseHeaders.set('x-beta-site', effectiveConfig.site);
  responseHeaders.set('x-beta-phase', effectivePhase);
  const hostHeader = request.headers.get('host') || '';
  const hostOnly = hostHeader.split(':')[0].toLowerCase();
  const isLocalHost = hostOnly === 'localhost' || hostOnly === '127.0.0.1' || hostOnly === '::1';

  // Skip protection for public assets and login page
  if (isPublicAssetPath(pathname)) {
    return NextResponse.next({ request: { headers: request.headers }, headers: responseHeaders });
  }

  // Support lowercase env var per project convention, fallback to uppercase
  const requiredToken = process.env.staff_access_token || process.env.STAFF_ACCESS_TOKEN;

  // Project-level preview gate: if this is the preview project, always enforce staff gate
  // Also enforce locally when testing with a configured token
  if (isPreviewProject || (isLocalHost && requiredToken)) {
    // If no required token configured, do not block preview
    if (!requiredToken) {
      return NextResponse.next({ request: { headers: request.headers }, headers: responseHeaders });
    }

    const cookieToken = cookies.get(STAFF_COOKIE_NAME)?.value;
    if (cookieToken === requiredToken) {
      responseHeaders.set('x-preview-gate', 'active');
      return NextResponse.next({ request: { headers: request.headers }, headers: responseHeaders });
    }

    // Check query parameter for preview
    const providedToken = nextUrl.searchParams.get('token');
    const redirectTargetParam = nextUrl.searchParams.get('redirect');
    const safeRedirectPath = redirectTargetParam && redirectTargetParam.startsWith('/') ? redirectTargetParam : pathname;
    if (providedToken && providedToken === requiredToken) {
      const response = NextResponse.redirect(new URL(safeRedirectPath || '/', request.url));
      const maxAge = 60 * 60 * 24 * 30;
      response.cookies.set(STAFF_COOKIE_NAME, requiredToken, {
        httpOnly: true,
        secure: process.env.NODE_ENV === 'production',
        sameSite: 'lax',
        path: '/',
        maxAge,
      });
      response.headers.set('x-beta-site', betaConfig.site);
      response.headers.set('x-beta-phase', betaConfig.phase);
      response.headers.set('x-preview-gate', 'active');
      return response;
    }

    const loginUrl = new URL(STAFF_LOGIN_PATH, request.url);
    loginUrl.searchParams.set('redirect', safeRedirectPath || pathname);
    const providedTokenForPreview = nextUrl.searchParams.get('token');
    if (providedTokenForPreview && providedTokenForPreview !== requiredToken) {
      loginUrl.searchParams.set('error', 'invalid');
    }
    const res = NextResponse.redirect(loginUrl);
    res.headers.set('x-preview-gate', 'redirect');
    return res;
  }

  // For beta site: apply phase-aware routing; keep staff gate logic untouched here
  if (effectiveConfig.site === 'beta') {
    // Special-case: allow signup when admin enabled flag or open_beta
    if (pathname === '/signup') {
      const allowCookie = cookies.get('beta_allow_signup_no_invite')?.value;
      const allowNoInvite = allowCookie === '1';
      const allowFromServer = serverAllowSignup === '1';
      if (effectivePhase === 'open_beta' || allowNoInvite || allowFromServer) {
        return NextResponse.next({ request: { headers: request.headers }, headers: responseHeaders });
      }
      // During instructor_only, require invite_code unless admin override is set
      if (effectivePhase === 'instructor_only') {
        const hasInvite = nextUrl.searchParams.get('invite_code');
        if (!hasInvite) {
          const res = NextResponse.redirect(new URL('/instructor/join', request.url));
          res.headers.set('x-beta-site', effectiveConfig.site);
          res.headers.set('x-beta-phase', effectivePhase);
          return res;
        }
      }
    }

    if (!isRouteAccessible(pathname, effectiveConfig)) {
      const redirectPath = getBetaRedirect(pathname, effectiveConfig, undefined);
      if (redirectPath) {
        const res = NextResponse.redirect(new URL(redirectPath, request.url));
        res.headers.set('x-beta-site', effectiveConfig.site);
        res.headers.set('x-beta-phase', effectivePhase);
        return res;
      }
      const res = NextResponse.rewrite(new URL('/404', request.url));
      res.headers.set('x-beta-site', effectiveConfig.site);
      res.headers.set('x-beta-phase', effectivePhase);
      return res;
    }

    if (pathname === '/') {
      const redirectPath = getBetaRedirect(pathname, effectiveConfig, undefined);
      if (redirectPath) {
        const res = NextResponse.redirect(new URL(redirectPath, request.url));
        res.headers.set('x-beta-site', effectiveConfig.site);
        res.headers.set('x-beta-phase', effectivePhase);
        return res;
      }
    }

    return NextResponse.next({ request: { headers: request.headers }, headers: responseHeaders });
  }

  // Default (production site or unknown host): no staff gate; proceed
  return NextResponse.next({ request: { headers: request.headers }, headers: responseHeaders });
}

export const config = {
  matcher: ['/((?!_next/|api/|static/|staff-login).*)'],
};
