import { NextRequest } from 'next/server';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export async function GET(req: NextRequest) {
  const auth = req.headers.get('authorization');
  const res = await fetch(`${API_BASE_URL}/api/beta/metrics/summary`, {
    headers: auth ? { Authorization: auth } : undefined,
    cache: 'no-store',
  });
  const body = await res.text();
  return new Response(body, { status: res.status, headers: { 'content-type': res.headers.get('content-type') || 'application/json' } });
}
