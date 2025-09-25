import { resolveApiBase } from '@/lib/apiBase';

describe('resolveApiBase', () => {
  it('SSR no env -> localhost:8000', () => {
    expect(resolveApiBase({ isServer: true, envBase: undefined })).toBe('http://localhost:8000');
  });

  it('SSR with env -> env', () => {
    expect(resolveApiBase({ isServer: true, envBase: 'https://api.example.com' })).toBe('https://api.example.com');
  });

  it('local preview host -> localhost:8000', () => {
    expect(resolveApiBase({ isServer: false, host: 'localhost' })).toBe('http://localhost:8000');
  });

  it('beta-local host -> api.beta-local:8000', () => {
    expect(resolveApiBase({ isServer: false, host: 'beta-local.instainstru.com' }))
      .toBe('http://api.beta-local.instainstru.com:8000');
  });

  it('hosted host with env -> env', () => {
    expect(resolveApiBase({
      isServer: false,
      host: 'preview.instainstru.com',
      envBase: 'https://preview-api.instainstru.com',
    })).toBe('https://preview-api.instainstru.com');
  });

  it('hosted host without env -> throws', () => {
    expect(() => resolveApiBase({ isServer: false, host: 'beta.instainstru.com' })).toThrow();
  });
});
