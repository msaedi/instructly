import { NextRequest } from 'next/server';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export async function POST(req: NextRequest) {
  const target = `${API_BASE_URL}/auth/login`;
  const headers: HeadersInit = { 'content-type': req.headers.get('content-type') || 'application/x-www-form-urlencoded' };

  // Forward Authorization if present
  const auth = req.headers.get('authorization');
  if (auth) (headers as any)['authorization'] = auth;

  // Inject preview header only on server, only if enabled
  if (process.env.ALLOW_PREVIEW_HEADER === 'true' && process.env.STAFF_PREVIEW_TOKEN) {
    (headers as any)['x-staff-preview-token'] = process.env.STAFF_PREVIEW_TOKEN;
  }

  const body = await req.text();
  const upstream = await fetch(target, {
    method: 'POST',
    headers,
    body,
    // forward cookies upstream and back
    redirect: 'manual',
  });

  const resHeaders = new Headers();
  upstream.headers.forEach((v, k) => resHeaders.set(k, v));
  const text = await upstream.text();
  return new Response(text, { status: upstream.status, headers: resHeaders });
}
