// CI-only endpoint to verify environment variables during testing
export const dynamic = 'force-dynamic';

export async function GET(request: Request) {
  // Double-gate: CI environment AND special header required
  const headers = request.headers;
  const ciHeader = headers.get('x-ci-check');

  if (process.env['CI'] !== 'true' || ciHeader !== '1') {
    return new Response('Not Found', { status: 404 });
  }

  // Return ONLY public environment variables (never secrets)
  return Response.json(
    {
      apiBase: process.env['NEXT_PUBLIC_API_BASE'],
      appEnv: process.env['NEXT_PUBLIC_APP_ENV'],
      useProxy: process.env['NEXT_PUBLIC_USE_PROXY'],
      appUrl: process.env['NEXT_PUBLIC_APP_URL'],
    },
    {
      headers: {
        'Cache-Control': 'no-store, no-cache, must-revalidate',
        'X-Robots-Tag': 'noindex',
      },
    }
  );
}
