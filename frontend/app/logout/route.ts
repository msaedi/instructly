import { NextResponse } from 'next/server';

const STAFF_COOKIE_NAME = 'staff_access_token';

export async function GET(request: Request) {
  const url = new URL('/staff-login', request.url);
  const res = NextResponse.redirect(url);
  res.cookies.set(STAFF_COOKIE_NAME, '', {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax',
    path: '/',
    maxAge: 0,
  });
  return res;
}
