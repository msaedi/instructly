import { NextRequest } from 'next/server';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export async function GET(req: NextRequest) {
  const url = new URL(req.url);
  const category = url.searchParams.get('category');
  const backendUrl = new URL(`${API_BASE}/services/catalog`);
  if (category) backendUrl.searchParams.set('category', category);

  const res = await fetch(backendUrl.toString(), { cache: 'no-store' });
  const text = await res.text();
  return new Response(text, {
    status: res.status,
    headers: { 'content-type': res.headers.get('content-type') || 'application/json' },
  });
}
