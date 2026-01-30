import * as Sentry from '@sentry/nextjs';

jest.mock('@/lib/publicEnv', () => ({
  SENTRY_DSN: 'https://example@sentry.invalid/1',
}));

import { captureFetchError, clearSentryUser, setSentryUser } from '@/lib/sentry';

type MockScope = {
  setTag: jest.Mock;
  setContext: jest.Mock;
  setLevel: jest.Mock;
  setUser: jest.Mock;
};

const mockScope = (Sentry as unknown as { __mockScope: MockScope }).__mockScope;

describe('sentry helpers', () => {
  const originalNodeEnv = process.env.NODE_ENV;
  beforeEach(() => {
    Object.defineProperty(process.env, 'NODE_ENV', {
      value: 'production',
      writable: true,
      configurable: true,
    });
  });

  afterEach(() => {
    Object.defineProperty(process.env, 'NODE_ENV', {
      value: originalNodeEnv,
      writable: true,
      configurable: true,
    });
  });

  it('sets user context when provided', () => {
    setSentryUser({
      id: 'user-1',
      email: 'user@example.com',
      first_name: 'Test',
      last_name: 'User',
    });

    expect(Sentry.setUser).toHaveBeenCalledWith({
      id: 'user-1',
      email: 'user@example.com',
      username: 'Test User',
    });
  });

  it('clears user context when requested', () => {
    clearSentryUser();
    expect(Sentry.setUser).toHaveBeenCalledWith(null);
  });

  it('captures network errors with tags', () => {
    const error = new Error('network failed');
    captureFetchError({ url: 'https://api.example.com/test', method: 'GET', error });

    expect(mockScope.setTag).toHaveBeenCalledWith('http.method', 'GET');
    expect(mockScope.setTag).toHaveBeenCalledWith('http.url', 'https://api.example.com/test');
    expect(Sentry.captureException).toHaveBeenCalledWith(error);
  });

  it('captures 5xx responses', () => {
    captureFetchError({ url: 'https://api.example.com/test', method: 'POST', status: 502 });

    expect(mockScope.setTag).toHaveBeenCalledWith('http.status_code', '502');
    expect(Sentry.captureMessage).toHaveBeenCalledWith(
      'HTTP 502 POST https://api.example.com/test',
      'error'
    );
  });
});
