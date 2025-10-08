import type { ResolveApiBaseOptions } from '@/lib/apiBase';

const ENV_KEYS = [
  'NEXT_PUBLIC_API_BASE',
  'NEXT_PUBLIC_APP_ENV',
  'NEXT_PUBLIC_USE_PROXY',
] as const;

type EnvKey = typeof ENV_KEYS[number];

type EnvSnapshot = Record<EnvKey, string | undefined>;

const originalEnv: EnvSnapshot = {
  NEXT_PUBLIC_API_BASE: process.env.NEXT_PUBLIC_API_BASE,
  NEXT_PUBLIC_APP_ENV: process.env.NEXT_PUBLIC_APP_ENV,
  NEXT_PUBLIC_USE_PROXY: process.env.NEXT_PUBLIC_USE_PROXY,
};

const clearTestEnv = () => {
  for (const key of ENV_KEYS) {
    delete process.env[key];
  }
};

const restoreEnv = () => {
  clearTestEnv();
  for (const key of ENV_KEYS) {
    const value = originalEnv[key];
    if (value !== undefined) {
      (process.env as Record<string, string>)[key] = value;
    }
  }
};

describe('getApiBase resolver', () => {
  beforeEach(() => {
    jest.resetModules();
    clearTestEnv();
    process.env.NEXT_PUBLIC_USE_PROXY = 'false';
  });

  afterEach(() => {
    restoreEnv();
    jest.resetModules();
  });

  afterAll(() => {
    restoreEnv();
  });

  const loadApiBase = async () => {
    const mod = await import('@/lib/apiBase');
    return mod;
  };

  it('returns the explicit env override when set (sanitized)', async () => {
    process.env.NEXT_PUBLIC_API_BASE = 'https://api.example.com/';
    const { getApiBase, resetApiBaseMemoForTests } = await loadApiBase();
    try {
      expect(getApiBase()).toBe('https://api.example.com');
    } finally {
      resetApiBaseMemoForTests();
    }
  });

  it('falls back to preview mapping when env unset and app env = preview', async () => {
    process.env.NEXT_PUBLIC_APP_ENV = 'preview';
    const { getApiBase, resetApiBaseMemoForTests } = await loadApiBase();
    try {
      expect(getApiBase()).toBe('https://preview-api.instainstru.com');
    } finally {
      resetApiBaseMemoForTests();
    }
  });

  it('falls back to production API for beta/prod app env', async () => {
    process.env.NEXT_PUBLIC_APP_ENV = 'beta';
    const { getApiBase, resetApiBaseMemoForTests } = await loadApiBase();
    try {
      expect(getApiBase()).toBe('https://api.instainstru.com');
    } finally {
      resetApiBaseMemoForTests();
    }
  });

});

describe('resolveApiBase', () => {
  const loadResolver = async () => {
    const mod = await import('@/lib/apiBase');
    return mod.resolveApiBase as (options: ResolveApiBaseOptions) => string;
  };

  it('prefers envBase over other fallbacks', async () => {
    const resolve = await loadResolver();
    expect(resolve({ envBase: 'https://example.com/api/', appEnv: 'beta', host: 'beta-local.instainstru.com' }))
      .toBe('https://example.com/api');
  });

  it('maps beta-local host to the beta-local API', async () => {
    const resolve = await loadResolver();
    expect(resolve({ appEnv: '', host: 'beta-local.instainstru.com' }))
      .toBe('http://api.beta-local.instainstru.com:8000');
  });

  it('maps localhost host to the local API', async () => {
    const resolve = await loadResolver();
    expect(resolve({ host: 'localhost' })).toBe('http://localhost:8000');
  });

  it('throws with context when host cannot be resolved', async () => {
    const resolve = await loadResolver();
    expect(() => resolve({ host: 'unknown.example.com' })).toThrow(
      'NEXT_PUBLIC_API_BASE must be set or resolvable (host=unknown.example.com, appEnv=unset)',
    );
  });
});
