/**
 * Tests for API Base URL configuration
 * Ensures NEXT_PUBLIC_API_BASE is the single source of truth
 */

describe('API Base Configuration', () => {
  const originalEnv = process.env;

  beforeEach(() => {
    // Reset modules before each test
    jest.resetModules();
    // Clear environment
    process.env = { ...originalEnv };
    delete process.env.NEXT_PUBLIC_API_URL;
    delete process.env.NEXT_PUBLIC_API_BASE;
    delete process.env.NEXT_PUBLIC_USE_PROXY;
  });

  afterAll(() => {
    process.env = originalEnv;
  });

  describe('Phase A.2: Guard against deprecated NEXT_PUBLIC_API_URL', () => {
    it('should throw error in development when NEXT_PUBLIC_API_URL is set', () => {
      process.env.NODE_ENV = 'development';
      process.env.NEXT_PUBLIC_API_URL = 'http://old-api.example.com';
      process.env.NEXT_PUBLIC_API_BASE = 'http://api.example.com';

      expect(() => {
        require('@/lib/apiBase');
      }).toThrow('NEXT_PUBLIC_API_URL is deprecated. Use NEXT_PUBLIC_API_BASE.');
    });

    it('should log error in production when NEXT_PUBLIC_API_URL is set', () => {
      process.env.NODE_ENV = 'production';
      process.env.NEXT_PUBLIC_API_URL = 'http://old-api.example.com';
      process.env.NEXT_PUBLIC_API_BASE = 'http://api.example.com';

      const mockError = jest.spyOn(console, 'error').mockImplementation();

      require('@/lib/apiBase');

      expect(mockError).toHaveBeenCalledWith(
        expect.stringContaining('NEXT_PUBLIC_API_URL is deprecated')
      );

      mockError.mockRestore();
    });
  });

  describe('Phase A.1: Single source of truth', () => {
    it('should throw error when NEXT_PUBLIC_API_BASE is not set', () => {
      expect(() => {
        require('@/lib/apiBase');
      }).toThrow('NEXT_PUBLIC_API_BASE is not set. Refusing to default to localhost.');
    });

    it('should use NEXT_PUBLIC_API_BASE when set', () => {
      process.env.NEXT_PUBLIC_API_BASE = 'https://api.example.com';

      const { API_BASE } = require('@/lib/apiBase');

      expect(API_BASE).toBe('https://api.example.com');
    });

    it('should remove trailing slashes from API_BASE', () => {
      process.env.NEXT_PUBLIC_API_BASE = 'https://api.example.com///';

      const { API_BASE } = require('@/lib/apiBase');

      expect(API_BASE).toBe('https://api.example.com');
    });

    it('should use proxy path when USE_PROXY is enabled in local env', () => {
      process.env.NEXT_PUBLIC_APP_ENV = 'local';
      process.env.NEXT_PUBLIC_USE_PROXY = 'true';
      process.env.NEXT_PUBLIC_API_BASE = 'http://localhost:8000';

      const { API_BASE } = require('@/lib/apiBase');

      expect(API_BASE).toBe('/api/proxy');
    });

    it('should not use proxy when USE_PROXY is false', () => {
      process.env.NEXT_PUBLIC_APP_ENV = 'local';
      process.env.NEXT_PUBLIC_USE_PROXY = 'false';
      process.env.NEXT_PUBLIC_API_BASE = 'http://localhost:8000';

      const { API_BASE } = require('@/lib/apiBase');

      expect(API_BASE).toBe('http://localhost:8000');
    });
  });

  describe('withApiBase helper', () => {
    beforeEach(() => {
      process.env.NEXT_PUBLIC_API_BASE = 'https://api.example.com';
    });

    it('should build correct URL with leading slash', () => {
      const { withApiBase } = require('@/lib/apiBase');

      expect(withApiBase('/users/123')).toBe('https://api.example.com/users/123');
    });

    it('should build correct URL without leading slash', () => {
      const { withApiBase } = require('@/lib/apiBase');

      expect(withApiBase('users/123')).toBe('https://api.example.com/users/123');
    });

    it('should handle multiple leading slashes', () => {
      const { withApiBase } = require('@/lib/apiBase');

      expect(withApiBase('///users/123')).toBe('https://api.example.com/users/123');
    });
  });
});
