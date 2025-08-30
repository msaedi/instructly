import { NextRequest } from 'next/server';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export async function GET(req: NextRequest) {
  const res = await fetch(`${API_BASE}/api/beta/settings`, {
    headers: {
      Authorization: req.headers.get('authorization') || '',
    },
    cache: 'no-store',
  });
  const contentType = res.headers.get('content-type') || 'application/json';
  let bodyText = await res.text();
  // Try to derive allow flag to set a cookie the middleware can read
  try {
    const data = JSON.parse(bodyText);
    const allow = data?.allow_signup_without_invite ? '1' : '0';
    const phase = typeof data?.beta_phase === 'string' ? data.beta_phase : 'instructor_only';
    const headers = new Headers({ 'content-type': contentType });
    headers.append('set-cookie', `beta_allow_signup_no_invite=${allow}; Path=/; SameSite=Lax; Max-Age=600`);
    headers.append('set-cookie', `beta_phase=${phase}; Path=/; SameSite=Lax; Max-Age=600`);
    return new Response(JSON.stringify(data), { status: res.status, headers });
  } catch {
    return new Response(bodyText, { status: res.status, headers: { 'content-type': contentType } });
  }
}

export async function PUT(req: NextRequest) {
  const body = await req.text();
  const res = await fetch(`${API_BASE}/api/beta/settings`, {
    method: 'PUT',
    headers: {
      Authorization: req.headers.get('authorization') || '',
      'content-type': 'application/json',
    },
    body,
    cache: 'no-store',
  });
  const contentType = res.headers.get('content-type') || 'application/json';
  let bodyText = await res.text();
  try {
    const data = JSON.parse(bodyText);
    const allow = data?.allow_signup_without_invite ? '1' : '0';
    const phase = typeof data?.beta_phase === 'string' ? data.beta_phase : 'instructor_only';
    const headers = new Headers({ 'content-type': contentType });
    headers.append('set-cookie', `beta_allow_signup_no_invite=${allow}; Path=/; SameSite=Lax; Max-Age=600`);
    headers.append('set-cookie', `beta_phase=${phase}; Path=/; SameSite=Lax; Max-Age=600`);
    return new Response(JSON.stringify(data), { status: res.status, headers });
  } catch {
    return new Response(bodyText, { status: res.status, headers: { 'content-type': contentType } });
  }
}
