describe('OpenTelemetry instrumentation', () => {
  const originalEnv = process.env;

  beforeEach(() => {
    jest.resetModules();
    process.env = { ...originalEnv };
  });

  afterAll(() => {
    process.env = originalEnv;
  });

  it('does not initialize OTel when ENABLE_OTEL is false', async () => {
    process.env.ENABLE_OTEL = 'false';

    const registerOTel = jest.fn();
    const loggerMock = { info: jest.fn() };
    jest.doMock('@vercel/otel', () => ({
      registerOTel,
    }));
    jest.doMock('@/lib/logger', () => ({
      logger: loggerMock,
    }));

    const { register } = await import('../instrumentation');
    await register();

    expect(registerOTel).not.toHaveBeenCalled();
    expect(loggerMock.info).toHaveBeenCalledWith(expect.stringContaining('disabled'));
  });

  it('initializes OTel when ENABLE_OTEL is true', async () => {
    process.env.ENABLE_OTEL = 'true';
    process.env.OTEL_SERVICE_NAME = 'instainstru-web-test';

    const registerOTel = jest.fn();
    const loggerMock = { info: jest.fn() };
    jest.doMock('@vercel/otel', () => ({
      registerOTel,
    }));
    jest.doMock('@/lib/logger', () => ({
      logger: loggerMock,
    }));

    const { register } = await import('../instrumentation');
    await register();

    expect(registerOTel).toHaveBeenCalledWith(
      expect.objectContaining({
        serviceName: 'instainstru-web-test',
        instrumentationConfig: expect.objectContaining({
          fetch: expect.objectContaining({
            propagateContextUrls: expect.any(Array),
          }),
        }),
      })
    );
    expect(loggerMock.info).toHaveBeenCalledWith(expect.stringContaining('initialized'));
  });
});
