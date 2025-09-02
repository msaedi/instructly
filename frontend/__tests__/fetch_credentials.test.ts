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
