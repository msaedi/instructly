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
});
