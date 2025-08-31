// Jest-style test using the existing frontend test runner

describe('cleanFetch', () => {
  it('defaults credentials to include', async () => {
    const { cleanFetch } = await import('../features/shared/api/client');
    const spy = jest.spyOn(global as any, 'fetch').mockResolvedValue({ ok: true, status: 200, headers: new Headers(), json: async () => ({ ok: true }) } as any);
    await cleanFetch('/api/echo', {} as any);
    const args = (spy as any).mock.calls[0]?.[1] || {};
    expect(args.credentials).toBe('include');
    (spy as any).mockRestore();
  });
});
