import type { ReferralLedger } from '@/features/shared/referrals/api';
import { fetchReferralLedger } from '@/features/shared/referrals/api';

type ReferralCacheState = {
  ledger: ReferralLedger | null;
  promise: Promise<ReferralLedger> | null;
  hydrated: boolean;
};

const GLOBAL_CACHE_KEY = '__instReferralsLedgerCache';
const globalScope = globalThis as unknown as Record<string, ReferralCacheState | undefined>;
globalScope[GLOBAL_CACHE_KEY] ??= {
  ledger: null,
  promise: null,
  hydrated: false,
};

const STORAGE_KEY = '__inst_referrals_ledger';

function safeParse(raw: string | null): ReferralLedger | null {
  if (!raw) return null;
  try {
    return JSON.parse(raw) as ReferralLedger;
  } catch {
    return null;
  }
}

function persistLedger(data: ReferralLedger | null) {
  if (typeof window === 'undefined' || typeof sessionStorage === 'undefined') return;
  try {
    if (data) {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(data));
    } else {
      sessionStorage.removeItem(STORAGE_KEY);
    }
  } catch {
    // ignore storage failures
  }
}

function hydrateFromStorage(cache: ReferralCacheState) {
  if (cache.hydrated || typeof window === 'undefined' || typeof sessionStorage === 'undefined') {
    cache.hydrated = true;
    return;
  }
  cache.hydrated = true;
  const stored = safeParse(sessionStorage.getItem(STORAGE_KEY));
  if (stored) {
    cache.ledger = stored;
  }
}

function getCache(): ReferralCacheState {
  const cache = globalScope[GLOBAL_CACHE_KEY] as ReferralCacheState;
  hydrateFromStorage(cache);
  return cache;
}

export function getCachedReferralLedger(): ReferralLedger | null {
  return getCache().ledger;
}

export function primeReferralLedgerCache(data: ReferralLedger | null) {
  const cache = getCache();
  cache.ledger = data;
  persistLedger(data);
}

export function invalidateReferralLedgerCache() {
  const cache = getCache();
  cache.ledger = null;
  cache.promise = null;
  persistLedger(null);
}

export async function fetchReferralLedgerCached(signal?: AbortSignal): Promise<ReferralLedger> {
  const cache = getCache();
  if (cache.ledger) {
    return cache.ledger;
  }
  if (!cache.promise) {
    cache.promise = fetchReferralLedger(signal)
      .then((data) => {
        primeReferralLedgerCache(data);
        return data;
      })
      .finally(() => {
        cache.promise = null;
      });
  }
  return cache.promise;
}
