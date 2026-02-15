const initBotIdMock = jest.fn();
const captureRouterTransitionStartMock = jest.fn();

jest.mock('botid/client/core', () => ({
  initBotId: (...args: unknown[]) => initBotIdMock(...args),
}));

jest.mock('@sentry/nextjs', () => ({
  captureRouterTransitionStart: (...args: unknown[]) =>
    captureRouterTransitionStartMock(...args),
}));

describe('BotID client instrumentation', () => {
  afterEach(() => {
    initBotIdMock.mockReset();
    jest.resetModules();
  });

  it('initializes BotID with protected mutation routes', async () => {
    const env = process.env as Record<string, string | undefined>;
    const originalEnv = env['NODE_ENV'];
    env['NODE_ENV'] = 'production';
    const instrumentationClient = await import('../../instrumentation-client');
    env['NODE_ENV'] = originalEnv;

    expect(initBotIdMock).toHaveBeenCalledTimes(1);
    expect(instrumentationClient.onRouterTransitionStart).toBeDefined();
    const [payload] = initBotIdMock.mock.calls[0] as [
      { protect: Array<{ path: string; method: string }> },
    ];

    expect(Array.isArray(payload.protect)).toBe(true);
    expect(payload.protect).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ path: '/api/v1/auth', method: 'POST' }),
        expect.objectContaining({ path: '/api/v1/auth/*', method: 'POST' }),
        expect.objectContaining({ path: '/api/v1/bookings', method: 'PATCH' }),
        expect.objectContaining({ path: '/api/v1/payments/*', method: 'DELETE' }),
        expect.objectContaining({ path: '/api/v1/messages', method: 'PUT' }),
        expect.objectContaining({ path: '/api/v1/conversations/*', method: 'POST' }),
      ])
    );
  });
});
