import { NextRequest, NextResponse } from 'next/server';
import { env } from '@/lib/env';

/**
 * Development proxy route handler
 * Forwards all requests to the backend API when NEXT_PUBLIC_USE_PROXY is enabled
 *
 * SECURITY: This proxy is ONLY available in local development.
 * Preview and production builds will always return 404 regardless of settings.
 */

// Guard against non-local environments
const IS_LOCAL = env.get('NEXT_PUBLIC_APP_ENV') === 'local' ||
                 (env.isDevelopment() && !env.get('NEXT_PUBLIC_APP_ENV'));

// Only active in local development when proxy mode is explicitly enabled
const PROXY_ENABLED = IS_LOCAL && env.get('NEXT_PUBLIC_USE_PROXY') === 'true';
const BACKEND_URL = env.get('NEXT_PUBLIC_API_BASE') || 'http://localhost:8000';

async function handler(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  // Guard against non-local environments first
  if (!IS_LOCAL) {
    return NextResponse.json(
      { error: 'Proxy mode is not enabled' },
      { status: 404 }
    );
  }

  // Check if proxy is enabled
  if (!PROXY_ENABLED) {
    return NextResponse.json(
      { error: 'Proxy mode is not enabled' },
      { status: 404 }
    );
  }

  try {
    // Construct the target URL
    const pathString = path.join('/');
    const queryString = request.nextUrl.search;
    const targetUrl = `${BACKEND_URL}/${pathString}${queryString}`;

    // Prepare headers - forward most headers but clean up some
    const headers = new Headers();
    request.headers.forEach((value, key) => {
      // Skip headers that shouldn't be forwarded
      if (
        key.toLowerCase() === 'host' ||
        key.toLowerCase() === 'connection' ||
        key.toLowerCase().startsWith('cf-') ||
        key.toLowerCase().startsWith('x-forwarded-')
      ) {
        return;
      }
      headers.set(key, value);
    });

    // Prepare the request options
    const fetchOptions: RequestInit = {
      method: request.method,
      headers,
      // Disable caching
      cache: 'no-store',
      // Include credentials for cookie handling
      credentials: 'include',
    };

    // Forward body for non-GET requests
    if (request.method !== 'GET' && request.method !== 'HEAD') {
      const contentType = request.headers.get('content-type');
      if (contentType?.includes('application/json')) {
        fetchOptions.body = await request.text();
      } else if (contentType?.includes('application/x-www-form-urlencoded')) {
        fetchOptions.body = await request.text();
      } else if (contentType?.includes('multipart/form-data')) {
        // Let fetch handle FormData boundary
        const formData = await request.formData();
        fetchOptions.body = formData;
        headers.delete('content-type'); // Let fetch set the boundary
      } else {
        fetchOptions.body = await request.text();
      }
    }

    // Make the request to the backend
    const response = await fetch(targetUrl, fetchOptions);

    // Read the response body
    const responseBody = await response.text();

    // Create response with the backend's status
    const proxyResponse = new NextResponse(responseBody, {
      status: response.status,
      statusText: response.statusText,
    });

    // Forward response headers, especially Set-Cookie
    response.headers.forEach((value, key) => {
      // Skip headers that shouldn't be forwarded
      if (
        key.toLowerCase() === 'content-encoding' ||
        key.toLowerCase() === 'content-length' ||
        key.toLowerCase() === 'transfer-encoding'
      ) {
        return;
      }
      proxyResponse.headers.set(key, value);
    });

    // Ensure no caching
    proxyResponse.headers.set('Cache-Control', 'no-store');

    return proxyResponse;
  } catch (error) {
    // Return error response without logging to console (ESLint no-console rule)
    return NextResponse.json(
      { error: 'Proxy request failed', details: error instanceof Error ? error.message : 'Unknown error' },
      { status: 502 }
    );
  }
}

// Export handlers for all HTTP methods
export const GET = handler;
export const POST = handler;
export const PUT = handler;
export const PATCH = handler;
export const DELETE = handler;
export const OPTIONS = handler;
