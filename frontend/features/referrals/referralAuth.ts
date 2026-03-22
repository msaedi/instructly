import { fetchAPI } from '@/lib/api';
import { logger } from '@/lib/logger';

type AuthHrefOptions = {
  redirect?: string | null;
  ref?: string | null;
  role?: 'instructor' | 'student' | null;
  registered?: boolean;
};

export function buildAuthHref(basePath: string, options: AuthHrefOptions = {}): string {
  const params = new URLSearchParams();

  if (options.role) {
    params.set('role', options.role);
  }

  if (options.redirect && options.redirect !== '/') {
    params.set('redirect', options.redirect);
  }

  if (options.ref) {
    params.set('ref', options.ref);
  }

  if (options.registered) {
    params.set('registered', 'true');
  }

  const query = params.toString();
  return query ? `${basePath}?${query}` : basePath;
}

export async function claimReferralCode(code: string | null | undefined): Promise<boolean> {
  const normalizedCode = code?.trim().toUpperCase() ?? '';
  if (!normalizedCode) {
    return false;
  }

  try {
    const response = await fetchAPI('/api/v1/referrals/claim', {
      method: 'POST',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ code: normalizedCode }),
    });

    if (!response.ok) {
      return false;
    }

    const payload = (await response.json()) as { attributed?: boolean };
    return payload.attributed === true;
  } catch (error) {
    logger.warn('Unable to claim referral code after signup', {
      code: normalizedCode,
      error: error instanceof Error ? error.message : String(error),
    });
    return false;
  }
}
