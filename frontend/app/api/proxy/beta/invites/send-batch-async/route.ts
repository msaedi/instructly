import { NextRequest } from 'next/server';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export async function POST(req: NextRequest) {
  const auth = req.headers.get('authorization');
  const body = await req.text();
  const res = await fetch(`${API_BASE_URL}/api/beta/invites/send-batch-async`, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      ...(auth ? { Authorization: auth } : {}),
    },
    body,
    cache: 'no-store',
  });
  const text = await res.text();
  return new Response(text, { status: res.status, headers: { 'content-type': res.headers.get('content-type') || 'application/json' } });
}
