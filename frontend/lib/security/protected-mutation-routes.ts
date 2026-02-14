export const PROTECTED_PATH_PREFIXES = [
  '/api/v1/auth',
  '/api/v1/2fa',
  '/api/v1/bookings',
  '/api/v1/payments',
  '/api/v1/reviews',
  '/api/v1/referrals',
  '/api/v1/public/referrals',
  '/api/v1/messages',
  '/api/v1/conversations',
] as const;

export const PROTECTED_MUTATION_METHODS = ['POST', 'PUT', 'PATCH', 'DELETE'] as const;

export type ProtectedMutationMethod = (typeof PROTECTED_MUTATION_METHODS)[number];

export type BotIdProtectRule = {
  path: string;
  method: ProtectedMutationMethod;
};

const PROTECTED_METHOD_SET = new Set<string>(PROTECTED_MUTATION_METHODS);

function normalizePath(rawPath: string): string {
  const trimmed = rawPath.trim();
  if (!trimmed) {
    return '/';
  }

  if (/^https?:\/\//i.test(trimmed)) {
    try {
      const parsed = new URL(trimmed);
      return `${parsed.pathname}${parsed.search}`;
    } catch {
      return '/';
    }
  }

  if (trimmed.startsWith('/')) {
    return trimmed;
  }

  return `/${trimmed}`;
}

function normalizeMethod(rawMethod?: string): string {
  return (rawMethod ?? 'GET').toUpperCase();
}

function stripQuery(path: string): string {
  const [pathname] = path.split('?', 1);
  return pathname || '/';
}

function matchesPrefix(pathname: string, prefix: string): boolean {
  return pathname === prefix || pathname.startsWith(`${prefix}/`);
}

export function isProtectedMutationRequest(path: string, method?: string): boolean {
  const normalizedMethod = normalizeMethod(method);
  if (!PROTECTED_METHOD_SET.has(normalizedMethod)) {
    return false;
  }

  const pathname = stripQuery(normalizePath(path));
  return PROTECTED_PATH_PREFIXES.some((prefix) => matchesPrefix(pathname, prefix));
}

export const BOTID_PROTECT_RULES: BotIdProtectRule[] = PROTECTED_PATH_PREFIXES.flatMap((prefix) =>
  PROTECTED_MUTATION_METHODS.flatMap((method) => [
    { path: prefix, method },
    { path: `${prefix}/*`, method },
  ])
);
