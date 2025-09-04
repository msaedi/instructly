import type { ImageTransformOptions } from '@/lib/services/assetService';

describe('assetService.getOptimizedUrl', () => {
  const original = process.env.NEXT_PUBLIC_R2_URL;
  let getOptimizedUrl: (path: string, options?: ImageTransformOptions) => string | null;

  beforeAll(async () => {
    process.env.NEXT_PUBLIC_R2_URL = 'https://assets.example.com';
    jest.resetModules();
    ({ getOptimizedUrl } = await import('@/lib/services/assetService'));
  });

  afterAll(() => {
    if (original === undefined) delete process.env.NEXT_PUBLIC_R2_URL;
    else process.env.NEXT_PUBLIC_R2_URL = original;
  });

  it('builds a Cloudflare Image Transformation URL when options provided', () => {
    const url = getOptimizedUrl('/backgrounds/auth/default.webp', { width: 1200, quality: 85, format: 'auto', fit: 'cover' });
    expect(url).toBeTruthy();
    expect(url!).toContain('https://assets.example.com/cdn-cgi/image/');
    expect(url!).toContain('/backgrounds/auth/default.webp');
    expect(url!).toContain('width=1200');
    expect(url!).toContain('quality=85');
  });

  it('returns original URL when no options provided', () => {
    const url = getOptimizedUrl('/backgrounds/auth/default.webp', {});
    expect(url).toBe('https://assets.example.com/backgrounds/auth/default.webp');
  });
});
