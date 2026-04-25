/**
 * @jest-environment node
 */

import { NextRequest } from 'next/server';

import { proxy } from '@/proxy';

describe('proxy auth recovery staff-gate bypass', () => {
  const originalEnv = process.env;

  beforeEach(() => {
    jest.resetModules();
    process.env = {
      ...originalEnv,
      NEXT_PUBLIC_APP_ENV: 'preview',
      STAFF_ACCESS_TOKEN: 'staff-secret',
    };
  });

  afterEach(() => {
    process.env = originalEnv;
  });

  async function runProxy(path: string) {
    return proxy(new NextRequest(`https://preview.instainstru.com${path}`));
  }

  it('lets reset-password token links reach the page intact', async () => {
    const response = await runProxy('/reset-password?token=reset-token');

    expect(response.headers.get('location')).toBeNull();
    expect(response.headers.get('x-preview-gate')).not.toBe('redirect');
  });

  it('lets forgot-password reach the page without staff access', async () => {
    const response = await runProxy('/forgot-password');

    expect(response.headers.get('location')).toBeNull();
    expect(response.headers.get('x-preview-gate')).not.toBe('redirect');
  });

  it('bypasses staff gate for verify-email subpaths', async () => {
    const response = await runProxy('/verify-email/abc123?token=email-token');

    expect(response.headers.get('location')).toBeNull();
    expect(response.headers.get('x-preview-gate')).not.toBe('redirect');
  });

  it('still sends unrelated tokenized pages through the staff gate', async () => {
    const response = await runProxy('/some-other-page?token=reset-token');

    expect(response.headers.get('location')).toBe(
      'https://preview.instainstru.com/staff-login?redirect=%2Fsome-other-page&error=invalid'
    );
    expect(response.headers.get('x-preview-gate')).toBe('redirect');
  });

  it('keeps staff-login public', async () => {
    const response = await runProxy('/staff-login');

    expect(response.headers.get('location')).toBeNull();
    expect(response.headers.get('x-preview-gate')).not.toBe('redirect');
  });
});
