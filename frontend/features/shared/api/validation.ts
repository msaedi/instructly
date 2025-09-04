// features/shared/api/validation.ts
// Dev/test-only Zod validation. Never runs in production builds.

import type { ZodTypeAny } from 'zod';
import { logger } from '@/lib/logger';

export type SchemaLoader = () => Promise<{ schema: ZodTypeAny }>;

export const RUNTIME_VALIDATE: boolean =
  process.env.NODE_ENV !== 'production' &&
  (process.env['NEXT_PUBLIC_RUNTIME_VALIDATE'] === '1' ||
    process.env['RUNTIME_VALIDATE'] === '1' ||
    process.env.NODE_ENV === 'test');

export async function validateWithZod<T>(
  schemaLoader: SchemaLoader,
  data: unknown,
  ctx: { endpoint: string; note?: string | undefined } = { endpoint: 'unknown', note: undefined }
): Promise<T> {
  if (!RUNTIME_VALIDATE) return data as T;
  const { schema } = await schemaLoader();
  const result = schema.safeParse(data);
  if (result.success) return result.data as T;
  const summary = result.error.issues
    .slice(0, 5)
    .map((i, idx) => `#${idx + 1} path=${i.path.join('.') || '<root>'} code=${i.code} msg=${i.message}`)
    .join('\n');
  logger.warn(`[RUNTIME SCHEMA MISMATCH] ${ctx.endpoint}${ctx.note ? ` — ${ctx.note}` : ''}`, { summary });
  throw new Error(`Schema mismatch for ${ctx.endpoint}`);
}
