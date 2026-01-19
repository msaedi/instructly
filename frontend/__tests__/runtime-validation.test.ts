/**
 * @jest-environment jsdom
 */
import { validateWithZod, RUNTIME_VALIDATE } from '@/features/shared/api/validation';
import { loadMeSchema } from '@/features/shared/api/schemas/me';

describe('runtime validation', () => {
  it('is enabled in test env', () => {
    expect(RUNTIME_VALIDATE).toBe(true);
  });

  it('accepts valid shape', async () => {
    const valid = { id: 'u1', email: 'a@b.com', roles: [] };
    const parsed: { id: string } = await validateWithZod(loadMeSchema, valid, { endpoint: 'GET /me' });
    expect(parsed.id).toBe('u1');
  });

  it('rejects invalid shape with readable error', async () => {
    const bad = { id: 123, email: 'not-an-email' } as unknown;
    await expect(validateWithZod(loadMeSchema, bad, { endpoint: 'GET /me' })).rejects.toThrow('Schema mismatch');
  });

  it('includes note in error message when provided', async () => {
    const bad = { id: 123 } as unknown;
    await expect(
      validateWithZod(loadMeSchema, bad, { endpoint: 'GET /me', note: 'user lookup' })
    ).rejects.toThrow('Schema mismatch for GET /me');
  });

  it('works with minimal context (default values)', async () => {
    const valid = { id: 'u1', email: 'a@b.com', roles: [] };
    // Call with no context object at all - uses default endpoint 'unknown'
    const parsed = await validateWithZod<{ id: string }>(loadMeSchema, valid);
    expect(parsed.id).toBe('u1');
  });
});
