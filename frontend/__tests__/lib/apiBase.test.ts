import { resolveBaseForTest, resetApiBaseTestState } from '@/lib/apiBase';

type LayerWithSpy = {
  layer: {
    get(host: string): string | undefined;
    set(host: string, base: string): void;
  };
  getSpy: jest.SpyInstance<string | undefined, [host: string]>;
  setSpy: jest.SpyInstance<void, [host: string, base: string]>;
  backing: Map<string, string>;
};

const DEV_APP_ENV = 'development';

function createStorageLayer(): LayerWithSpy {
  const backing = new Map<string, string>();
  const layer = {
    get(host: string) {
      return backing.get(host);
    },
    set(host: string, base: string) {
      backing.set(host, base);
    },
  };
  return {
    layer,
    backing,
    getSpy: jest.spyOn(layer, 'get'),
    setSpy: jest.spyOn(layer, 'set'),
  };
}

describe('api base resolver (pure)', () => {
  afterEach(() => {
    jest.restoreAllMocks();
    resetApiBaseTestState();
  });

  it('derives and caches per host on the client in development', () => {
    const storage = createStorageLayer();
    const betaBase = resolveBaseForTest({
      envBase: '',
      appEnv: DEV_APP_ENV,
      host: 'beta-local.instainstru.com:3000',
      platform: 'csr',
      storage: storage.layer,
    });
    expect(betaBase).toBe('http://api.beta-local.instainstru.com:8000');
    expect(storage.setSpy).toHaveBeenCalledWith(
      'beta-local.instainstru.com:3000',
      'http://api.beta-local.instainstru.com:8000',
    );

    const cached = resolveBaseForTest({
      envBase: '',
      appEnv: DEV_APP_ENV,
      host: 'beta-local.instainstru.com:3000',
      platform: 'csr',
      storage: storage.layer,
    });
    expect(cached).toBe('http://api.beta-local.instainstru.com:8000');
    expect(storage.getSpy).toHaveBeenCalledWith('beta-local.instainstru.com:3000');
  });

  it('shares cached values between simulated bundles for the same host', () => {
    const storage = createStorageLayer();
    const first = resolveBaseForTest({
      envBase: '',
      appEnv: DEV_APP_ENV,
      host: 'beta-local.instainstru.com:3000',
      platform: 'csr',
      storage: storage.layer,
    });
    expect(first).toBe('http://api.beta-local.instainstru.com:8000');

    const secondBundle = resolveBaseForTest({
      envBase: '',
      appEnv: DEV_APP_ENV,
      host: 'beta-local.instainstru.com:3000',
      platform: 'csr',
      storage: storage.layer,
    });
    expect(secondBundle).toBe('http://api.beta-local.instainstru.com:8000');
  });

  it('derives a new base when the host changes while reusing session storage', () => {
    const storage = createStorageLayer();
    resolveBaseForTest({
      envBase: '',
      appEnv: DEV_APP_ENV,
      host: 'beta-local.instainstru.com:3000',
      platform: 'csr',
      storage: storage.layer,
    });
    const localhostBase = resolveBaseForTest({
      envBase: '',
      appEnv: DEV_APP_ENV,
      host: 'localhost:3000',
      platform: 'csr',
      storage: storage.layer,
    });
    expect(localhostBase).toBe('http://localhost:8000');
    expect(storage.backing.get('localhost:3000')).toBe('http://localhost:8000');
  });

  it('maps LAN IPv4 hosts to port 8000', () => {
    const lanBase = resolveBaseForTest({
      envBase: '',
      appEnv: DEV_APP_ENV,
      host: '10.0.0.23:3000',
      platform: 'csr',
    });
    expect(lanBase).toBe('http://10.0.0.23:8000');
  });

  it('falls back to appEnv mapping on SSR and does not access caches', () => {
    const previewBase = resolveBaseForTest({
      envBase: '',
      appEnv: 'preview',
      host: null,
      platform: 'ssr',
    });
    expect(previewBase).toBe('https://preview-api.instainstru.com');

    const prodBase = resolveBaseForTest({
      envBase: '',
      appEnv: 'beta',
      host: null,
      platform: 'ssr',
    });
    expect(prodBase).toBe('https://api.instainstru.com');

    const unknown = resolveBaseForTest({
      envBase: '',
      appEnv: 'staging',
      host: null,
      platform: 'ssr',
    });
    expect(unknown).toBe('');
  });

  it('prefers explicit env overrides and avoids cache writes', () => {
    const storage = createStorageLayer();
    const base = resolveBaseForTest({
      envBase: 'https://override.example.com',
      appEnv: DEV_APP_ENV,
      host: 'beta-local.instainstru.com:3000',
      platform: 'csr',
      storage: storage.layer,
    });
    expect(base).toBe('https://override.example.com');
    expect(storage.backing.size).toBe(0);
  });

  it('rejects mismatched cached bases via integrity checks', () => {
    const storage = createStorageLayer();
    storage.layer.set('beta-local.instainstru.com:3000', 'http://localhost:8000');
    const base = resolveBaseForTest({
      envBase: '',
      appEnv: DEV_APP_ENV,
      host: 'beta-local.instainstru.com:3000',
      platform: 'csr',
      storage: storage.layer,
    });
    expect(base).toBe('http://api.beta-local.instainstru.com:8000');
    expect(storage.backing.get('beta-local.instainstru.com:3000')).toBe('http://api.beta-local.instainstru.com:8000');
  });

  it('leaves development cache untouched when returning remote bases', () => {
    const storage = createStorageLayer();
    const base = resolveBaseForTest({
      envBase: '',
      appEnv: 'beta',
      host: 'beta-local.instainstru.com:3000',
      platform: 'csr',
      storage: storage.layer,
    });
    expect(base).toBe('https://api.instainstru.com');
    expect(storage.backing.size).toBe(0);
  });
});
