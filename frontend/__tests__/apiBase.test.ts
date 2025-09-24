/**
 * Tests for API Base URL configuration
 * Ensures NEXT_PUBLIC_API_BASE is the single source of truth
 */

describe('API Base Configuration', () => {
  const originalEnv = process.env;

  function withoutWindow<T>(run: () => T): T {
    const globalObj = global as Record<string, unknown>;
    const existingWindow = globalObj.window;
    delete globalObj.window;
    try {
      return run();
    } finally {
      if (existingWindow !== undefined) {
        globalObj.window = existingWindow;
      }
    }
  }

  beforeEach(() => {
    // Reset modules before each test
    jest.resetModules();
    // Clear environment
    const env = process.env as Record<string, string | undefined>;
    Object.keys(env).forEach((key) => {
      delete env[key];
    });
    Object.assign(process.env, originalEnv);
    delete process.env['NEXT_PUBLIC_API_URL'];
    delete process.env['NEXT_PUBLIC_API_BASE'];
    delete process.env['NEXT_PUBLIC_USE_PROXY'];
  });

  afterAll(() => {
    process.env = originalEnv;
  });

  describe('Phase A.2: Guard against deprecated NEXT_PUBLIC_API_URL', () => {
    it('should throw error in development when NEXT_PUBLIC_API_URL is set', () => {
      process.env = { ...process.env, NODE_ENV: 'development' } as NodeJS.ProcessEnv;
      process.env['NEXT_PUBLIC_API_URL'] = 'http://old-api.example.com';
      process.env['NEXT_PUBLIC_API_BASE'] = 'http://api.example.com';

      expect(() => {
        // eslint-disable-next-line @typescript-eslint/no-require-imports
      require('@/lib/apiBase');
      }).toThrow('NEXT_PUBLIC_API_URL is deprecated. Use NEXT_PUBLIC_API_BASE.');
    });

    it('should log error in production when NEXT_PUBLIC_API_URL is set', () => {
      process.env = { ...process.env, NODE_ENV: 'production' } as NodeJS.ProcessEnv;
      process.env['NEXT_PUBLIC_API_URL'] = 'http://old-api.example.com';
      process.env['NEXT_PUBLIC_API_BASE'] = 'http://api.example.com';

      const mockError = jest.spyOn(console, 'error').mockImplementation();

      // eslint-disable-next-line @typescript-eslint/no-require-imports
      require('@/lib/apiBase');

      expect(mockError).toHaveBeenCalledWith(
        expect.stringContaining('NEXT_PUBLIC_API_URL is deprecated')
      );

      mockError.mockRestore();
    });
  });

  describe('Phase A.1: Single source of truth', () => {
    it('should default to localhost when NEXT_PUBLIC_API_BASE is not set', () => {
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      const { API_BASE, getApiBase } = require('@/lib/apiBase');

      expect(API_BASE).toBe('http://localhost:8000');
      expect(getApiBase()).toBe('http://localhost:8000');
    });

    it('should use NEXT_PUBLIC_API_BASE when set', () => {
      withoutWindow(() => {
        jest.isolateModules(() => {
          process.env['NEXT_PUBLIC_USE_PROXY'] = 'false';
          process.env['NEXT_PUBLIC_APP_ENV'] = 'test';
          process.env['NEXT_PUBLIC_API_BASE'] = 'https://api.example.com';
          expect(process.env['NEXT_PUBLIC_API_BASE']).toBe('https://api.example.com');
          // eslint-disable-next-line @typescript-eslint/no-require-imports
          const { getApiBase } = require('@/lib/apiBase');
          expect(getApiBase()).toBe('https://api.example.com');
        });
      });
    });

    it('should remove trailing slashes from API_BASE', () => {
      withoutWindow(() => {
        jest.isolateModules(() => {
          process.env['NEXT_PUBLIC_USE_PROXY'] = 'false';
          process.env['NEXT_PUBLIC_APP_ENV'] = 'test';
          process.env['NEXT_PUBLIC_API_BASE'] = 'https://api.example.com///';
          // eslint-disable-next-line @typescript-eslint/no-require-imports
          const { getApiBase } = require('@/lib/apiBase');
          expect(getApiBase()).toBe('https://api.example.com');
        });
      });
    });

    it('should use proxy path when USE_PROXY is enabled in local env', () => {
      process.env['NEXT_PUBLIC_APP_ENV'] = 'local';
      process.env['NEXT_PUBLIC_USE_PROXY'] = 'true';
      process.env['NEXT_PUBLIC_API_BASE'] = 'http://localhost:8000';

      // eslint-disable-next-line @typescript-eslint/no-require-imports
      const { API_BASE } = require('@/lib/apiBase');

      expect(API_BASE).toBe('/api/proxy');
    });

    it('should not use proxy when USE_PROXY is false', () => {
      process.env['NEXT_PUBLIC_APP_ENV'] = 'local';
      process.env['NEXT_PUBLIC_USE_PROXY'] = 'false';
      process.env['NEXT_PUBLIC_API_BASE'] = 'http://localhost:8000';

      // eslint-disable-next-line @typescript-eslint/no-require-imports
      const { API_BASE } = require('@/lib/apiBase');

      expect(API_BASE).toBe('http://localhost:8000');
    });

    it('should return beta-local API base when window host matches', () => {
      jest.isolateModules(() => {
        process.env['NEXT_PUBLIC_USE_PROXY'] = 'false';
        process.env['NEXT_PUBLIC_APP_ENV'] = 'local';
        process.env['NEXT_PUBLIC_API_BASE'] = 'https://api.example.com';
        (global as unknown as { window?: { location: { hostname: string } } }).window = {
          location: { hostname: 'beta-local.instainstru.com' },
        };

        // eslint-disable-next-line @typescript-eslint/no-require-imports
        const { getApiBase } = require('@/lib/apiBase');
        expect(getApiBase()).toBe('http://api.beta-local.instainstru.com:8000');

        delete (global as { window?: unknown }).window;
      });
    });
  });

  describe('withApiBase helper', () => {
    beforeEach(() => {
      delete (process.env as Record<string, string | undefined>)['NEXT_PUBLIC_API_BASE'];
    });

    it('should build correct URL with leading slash', () => {
      withoutWindow(() => {
        jest.isolateModules(() => {
          process.env['NEXT_PUBLIC_USE_PROXY'] = 'false';
          process.env['NEXT_PUBLIC_APP_ENV'] = 'test';
          process.env['NEXT_PUBLIC_API_BASE'] = 'https://api.example.com';
          // eslint-disable-next-line @typescript-eslint/no-require-imports
          const { withApiBase } = require('@/lib/apiBase');
          expect(withApiBase('/users/123')).toBe('https://api.example.com/users/123');
        });
      });
    });

    it('should build correct URL without leading slash', () => {
      withoutWindow(() => {
        jest.isolateModules(() => {
          process.env['NEXT_PUBLIC_USE_PROXY'] = 'false';
          process.env['NEXT_PUBLIC_APP_ENV'] = 'test';
          process.env['NEXT_PUBLIC_API_BASE'] = 'https://api.example.com';
          // eslint-disable-next-line @typescript-eslint/no-require-imports
          const { withApiBase } = require('@/lib/apiBase');
          expect(withApiBase('users/123')).toBe('https://api.example.com/users/123');
        });
      });
    });

    it('should handle multiple leading slashes', () => {
      withoutWindow(() => {
        jest.isolateModules(() => {
          process.env['NEXT_PUBLIC_USE_PROXY'] = 'false';
          process.env['NEXT_PUBLIC_APP_ENV'] = 'test';
          process.env['NEXT_PUBLIC_API_BASE'] = 'https://api.example.com';
          // eslint-disable-next-line @typescript-eslint/no-require-imports
          const { withApiBase } = require('@/lib/apiBase');
          expect(withApiBase('///users/123')).toBe('https://api.example.com/users/123');
        });
      });
    });
  });
});
