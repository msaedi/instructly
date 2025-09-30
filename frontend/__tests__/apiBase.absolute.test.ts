describe('withApiBase absolute guard', () => {
  afterEach(() => {
    jest.resetModules();
  });

  it('returns absolute URLs unchanged', async () => {
    jest.resetModules();
    const { withApiBase } = await import('@/lib/apiBase');
    expect(withApiBase('http://foo/bar')).toBe('http://foo/bar');
    expect(withApiBase('https://foo/bar')).toBe('https://foo/bar');
  });

  it('prefixes relative paths once using the resolved base', async () => {
    jest.resetModules();
    const { withApiBase } = await import('@/lib/apiBase');
    const base = withApiBase('/');
    const trimmedBase = base.endsWith('/') ? base.slice(0, -1) : base;
    const result = withApiBase('/instructors/me');
    expect(result.startsWith(trimmedBase)).toBe(true);
    expect(result.endsWith('/instructors/me')).toBe(true);
  });
});
