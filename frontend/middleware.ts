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
    pathname === STAFF_LOGIN_PATH ||
    pathname === '/instructor/join' ||
    pathname === '/instructor/welcome'
  );
}

export function middleware(request: NextRequest) {
  const { nextUrl, cookies, url } = request;
  const pathname = nextUrl.pathname;

  // Detect site configuration by hostname
  const betaConfig = getBetaConfigFromHeaders(request.headers);
  const responseHeaders = new Headers();
  responseHeaders.set('x-beta-site', betaConfig.site);
  responseHeaders.set('x-beta-phase', betaConfig.phase);
  const hostHeader = request.headers.get('host') || '';
  const hostOnly = hostHeader.split(':')[0].toLowerCase();
  const isLocalHost = hostOnly === 'localhost' || hostOnly === '127.0.0.1' || hostOnly === '::1';

  // Skip protection for public assets and login page
  if (isPublicAssetPath(pathname)) {
    return NextResponse.next({ request: { headers: request.headers }, headers: responseHeaders });
  }

  // Support lowercase env var per project convention, fallback to uppercase
  const requiredToken = process.env.staff_access_token || process.env.STAFF_ACCESS_TOKEN;

  // If host is the preview site OR localhost (for local testing), enforce staff gate
  if (betaConfig.site === 'preview' || (isLocalHost && requiredToken)) {
    // If no required token configured, do not block preview
    if (!requiredToken) {
      return NextResponse.next({ request: { headers: request.headers }, headers: responseHeaders });
    }

    const cookieToken = cookies.get(STAFF_COOKIE_NAME)?.value;
    if (cookieToken === requiredToken) {
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
      return response;
    }

    const loginUrl = new URL(STAFF_LOGIN_PATH, request.url);
    loginUrl.searchParams.set('redirect', safeRedirectPath || pathname);
    const providedTokenForPreview = nextUrl.searchParams.get('token');
    if (providedTokenForPreview && providedTokenForPreview !== requiredToken) {
      loginUrl.searchParams.set('error', 'invalid');
    }
    return NextResponse.redirect(loginUrl);
  }

  // For beta site: apply phase-aware routing; keep staff gate logic untouched here
  if (betaConfig.site === 'beta') {
    if (!isRouteAccessible(pathname, betaConfig)) {
      const redirectPath = getBetaRedirect(pathname, betaConfig, undefined);
      if (redirectPath) {
        const res = NextResponse.redirect(new URL(redirectPath, request.url));
        res.headers.set('x-beta-site', betaConfig.site);
        res.headers.set('x-beta-phase', betaConfig.phase);
        return res;
      }
      const res = NextResponse.rewrite(new URL('/404', request.url));
      res.headers.set('x-beta-site', betaConfig.site);
      res.headers.set('x-beta-phase', betaConfig.phase);
      return res;
    }

    if (pathname === '/') {
      const redirectPath = getBetaRedirect(pathname, betaConfig, undefined);
      if (redirectPath) {
        const res = NextResponse.redirect(new URL(redirectPath, request.url));
        res.headers.set('x-beta-site', betaConfig.site);
        res.headers.set('x-beta-phase', betaConfig.phase);
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
