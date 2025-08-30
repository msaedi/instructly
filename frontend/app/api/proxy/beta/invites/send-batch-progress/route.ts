import { NextRequest } from 'next/server';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export async function GET(req: NextRequest) {
  const auth = req.headers.get('authorization');
  const { searchParams } = new URL(req.url);
  const task_id = searchParams.get('task_id');
  const upstream = `${API_BASE_URL}/api/beta/invites/send-batch-progress?task_id=${encodeURIComponent(task_id || '')}`;
  const res = await fetch(upstream, {
    headers: auth ? { Authorization: auth } : undefined,
    cache: 'no-store',
  });
  const text = await res.text();
  return new Response(text, { status: res.status, headers: { 'content-type': res.headers.get('content-type') || 'application/json' } });
}
