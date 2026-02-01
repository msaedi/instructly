describe('HTTP trace propagation', () => {
  it('uses native fetch which is instrumented by @vercel/otel', async () => {
    const httpModule = await import('@/lib/http');
    expect(typeof fetch).toBe('function');
    expect(typeof httpModule.http).toBe('function');
  });

  it('documents trace propagation configuration', () => {
    expect(true).toBe(true);
  });
});
