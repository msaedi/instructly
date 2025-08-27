import { NextRequest, NextResponse } from 'next/server';

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
    pathname === STAFF_LOGIN_PATH
  );
}

export function middleware(request: NextRequest) {
  const { nextUrl, cookies, url } = request;
  const pathname = nextUrl.pathname;

  // Skip protection for public assets and login page
  if (isPublicAssetPath(pathname)) {
    return NextResponse.next();
  }

  // Support lowercase env var per project convention, fallback to uppercase
  const requiredToken = process.env.staff_access_token || process.env.STAFF_ACCESS_TOKEN;

  // If no required token configured, do not block
  if (!requiredToken) {
    return NextResponse.next();
  }

  const cookieToken = cookies.get(STAFF_COOKIE_NAME)?.value;
  if (cookieToken === requiredToken) {
    return NextResponse.next();
  }

  // Check query parameter
  const providedToken = nextUrl.searchParams.get('token');
  const redirectTargetParam = nextUrl.searchParams.get('redirect');
  const safeRedirectPath = redirectTargetParam && redirectTargetParam.startsWith('/') ? redirectTargetParam : pathname;
  if (providedToken && providedToken === requiredToken) {
    // Set secure cookie for 30 days and redirect to target without token
    const response = NextResponse.redirect(new URL(safeRedirectPath || '/', request.url));
    const maxAge = 60 * 60 * 24 * 30; // 30 days in seconds
    response.cookies.set(STAFF_COOKIE_NAME, requiredToken, {
      httpOnly: true,
      secure: process.env.NODE_ENV === 'production',
      sameSite: 'lax',
      path: '/',
      maxAge,
    });
    return response;
  }

  // Otherwise, redirect to staff login
  const loginUrl = new URL(STAFF_LOGIN_PATH, request.url);
  loginUrl.searchParams.set('redirect', safeRedirectPath || pathname);
  if (providedToken && providedToken !== requiredToken) {
    loginUrl.searchParams.set('error', 'invalid');
  }
  return NextResponse.redirect(loginUrl);
}

export const config = {
  matcher: ['/((?!_next/|api/|static/|staff-login).*)'],
};
