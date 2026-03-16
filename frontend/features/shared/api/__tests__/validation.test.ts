import { validateWithZod, RUNTIME_VALIDATE } from '../validation';
import { logger } from '@/lib/logger';

jest.mock('@/lib/logger', () => ({
  logger: { warn: jest.fn(), error: jest.fn(), info: jest.fn(), debug: jest.fn() },
}));

describe('RUNTIME_VALIDATE', () => {
  it('is truthy in the test environment', () => {
    expect(RUNTIME_VALIDATE).toBe(true);
  });
});

describe('validateWithZod', () => {
  const mockSchema = {
    safeParse: jest.fn(),
  };

  const schemaLoader = async () => ({ schema: mockSchema as never });

  beforeEach(() => {
    mockSchema.safeParse.mockReset();
    (logger.warn as jest.Mock).mockClear();
  });

  it('returns parsed data on success', async () => {
    mockSchema.safeParse.mockReturnValue({ success: true, data: { name: 'John' } });

    const result = await validateWithZod(schemaLoader, { name: 'John' }, { endpoint: '/api/test' });

    expect(result).toEqual({ name: 'John' });
  });

  it('throws on schema mismatch and logs a warning', async () => {
    mockSchema.safeParse.mockReturnValue({
      success: false,
      error: {
        issues: [
          { path: ['name'], code: 'invalid_type', message: 'Expected string' },
        ],
      },
    });

    await expect(
      validateWithZod(schemaLoader, { name: 123 }, { endpoint: '/api/test' })
    ).rejects.toThrow('Schema mismatch for /api/test');

    expect(logger.warn).toHaveBeenCalledWith(
      expect.stringContaining('[RUNTIME SCHEMA MISMATCH] /api/test'),
      expect.any(Object)
    );
  });

  it('includes note in warning when provided', async () => {
    mockSchema.safeParse.mockReturnValue({
      success: false,
      error: {
        issues: [{ path: [], code: 'custom', message: 'bad' }],
      },
    });

    await expect(
      validateWithZod(schemaLoader, {}, { endpoint: '/api/test', note: 'batch call' })
    ).rejects.toThrow('Schema mismatch for /api/test');

    expect(logger.warn).toHaveBeenCalledWith(
      expect.stringContaining('batch call'),
      expect.any(Object)
    );
  });

  it('omits note from warning when note is undefined', async () => {
    mockSchema.safeParse.mockReturnValue({
      success: false,
      error: {
        issues: [{ path: [], code: 'custom', message: 'bad' }],
      },
    });

    await expect(
      validateWithZod(schemaLoader, {}, { endpoint: '/api/test', note: undefined })
    ).rejects.toThrow('Schema mismatch for /api/test');

    const warnMsg = (logger.warn as jest.Mock).mock.calls[0]?.[0] as string;
    expect(warnMsg).not.toContain(' — ');
  });

  it('uses default context when none provided', async () => {
    mockSchema.safeParse.mockReturnValue({
      success: false,
      error: { issues: [{ path: [], code: 'custom', message: 'bad' }] },
    });

    await expect(validateWithZod(schemaLoader, {})).rejects.toThrow('Schema mismatch for unknown');
  });

  it('truncates issues to first 5', async () => {
    const issues = Array.from({ length: 8 }, (_, i) => ({
      path: [`field${i}`],
      code: 'invalid_type',
      message: `Error ${i}`,
    }));

    mockSchema.safeParse.mockReturnValue({ success: false, error: { issues } });

    await expect(
      validateWithZod(schemaLoader, {}, { endpoint: '/api/test' })
    ).rejects.toThrow();

    const summary = (logger.warn as jest.Mock).mock.calls[0]?.[1]?.summary as string;
    expect(summary.match(/#\d+/g)).toHaveLength(5);
  });

  it('shows <root> for issues with empty path', async () => {
    mockSchema.safeParse.mockReturnValue({
      success: false,
      error: { issues: [{ path: [], code: 'custom', message: 'bad' }] },
    });

    await expect(
      validateWithZod(schemaLoader, {}, { endpoint: '/api/x' })
    ).rejects.toThrow();

    const summary = (logger.warn as jest.Mock).mock.calls[0]?.[1]?.summary as string;
    expect(summary).toContain('path=<root>');
  });

  it('returns raw data without loading schemas when runtime validation is disabled', async () => {
    const env = process.env as Record<string, string | undefined>;
    const previousEnv = {
      NODE_ENV: env['NODE_ENV'],
      NEXT_PUBLIC_RUNTIME_VALIDATE: env['NEXT_PUBLIC_RUNTIME_VALIDATE'],
      RUNTIME_VALIDATE: env['RUNTIME_VALIDATE'],
    };

    env['NODE_ENV'] = 'production';
    delete env['NEXT_PUBLIC_RUNTIME_VALIDATE'];
    delete env['RUNTIME_VALIDATE'];

    try {
      await jest.isolateModulesAsync(async () => {
        const validationModule = await import('../validation');
        const schemaLoader = jest.fn(async () => ({
          schema: mockSchema as never,
        }));

        await expect(
          validationModule.validateWithZod(schemaLoader, { untouched: true }, { endpoint: '/api/raw' })
        ).resolves.toEqual({ untouched: true });
        expect(schemaLoader).not.toHaveBeenCalled();
      });
    } finally {
      env['NODE_ENV'] = previousEnv.NODE_ENV;
      env['NEXT_PUBLIC_RUNTIME_VALIDATE'] = previousEnv.NEXT_PUBLIC_RUNTIME_VALIDATE;
      env['RUNTIME_VALIDATE'] = previousEnv.RUNTIME_VALIDATE;
    }
  });
});
