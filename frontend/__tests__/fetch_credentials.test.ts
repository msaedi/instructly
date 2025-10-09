// Jest-style test using the existing frontend test runner

describe('cleanFetch', () => {
  it('defaults credentials to include', async () => {
    const { cleanFetch } = await import('../features/shared/api/client');
    const mockResponse = {
      ok: true,
      status: 200,
      headers: new Headers(),
      json: async () => ({ ok: true })
    } as Response;
    const spy = jest.spyOn(global, 'fetch').mockResolvedValue(mockResponse);
    await cleanFetch('/api/echo', {} as RequestInit);
    const args = spy.mock.calls[0]?.[1] || {};
    expect(args.credentials).toBe('include');
    spy.mockRestore();
  });
});

describe('fetchAPI', () => {
  const originalEnv = { ...process.env };

  afterEach(() => {
    jest.resetModules();
    Object.assign(process.env, originalEnv);
  });

  it('includes credentials on absolute backend fetches', async () => {
    process.env.NEXT_PUBLIC_API_BASE = 'http://localhost:8000';
    const mockResponse = {
      ok: true,
      status: 200,
      headers: new Headers(),
      json: async () => ({}),
    } as Response;
    const spy = jest.spyOn(global, 'fetch').mockResolvedValue(mockResponse);
    const { fetchAPI } = await import('../lib/api');
    await fetchAPI('/auth/ping');
    expect(spy).toHaveBeenCalled();
    const init = spy.mock.calls[0]?.[1] || {};
    expect(init.credentials).toBe('include');
    spy.mockRestore();
  });
});
