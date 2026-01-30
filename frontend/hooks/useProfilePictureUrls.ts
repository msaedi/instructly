"use client";

import { useEffect, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';

import { fetchWithAuth } from '@/lib/api';
import { logger } from '@/lib/logger';
import type { components } from '@/features/shared/api/types';

type AvatarVariant = 'original' | 'display' | 'thumb';
type AvatarUrlMap = Record<string, string | null>;

type AvatarRequest = {
  id: string;
  version: number;
};

type PendingBatch = {
  requests: AvatarRequest[];
  variant: AvatarVariant;
  resolve: (value: AvatarUrlMap) => void;
  reject: (error: unknown) => void;
};

type CacheEntry = {
  value: string | null;
  expiresAt: number;
};

const CACHE_TTL_MS = 10 * 60 * 1000;
const REQUEST_TIMEOUT_MS = 5000;
const VERSION_DELIMITER = '::v=';

const avatarCache = new Map<string, CacheEntry>();
let pendingQueue: PendingBatch[] = [];
let flushTimer: ReturnType<typeof setTimeout> | null = null;

const parseRawId = (raw: string): AvatarRequest => {
  if (!raw) {
    return { id: '', version: 0 };
  }
  if (raw.includes(VERSION_DELIMITER)) {
    const [base = "", versionStr = "0"] = raw.split(VERSION_DELIMITER);
    const version = Number.parseInt(versionStr ?? "0", 10);
    return {
      id: base,
      version: Number.isFinite(version) ? version : 0,
    };
  }
  return { id: raw, version: 0 };
};

const compositeKey = (req: AvatarRequest): string => `${req.id}${VERSION_DELIMITER}${req.version}`;

const cacheKey = (variant: AvatarVariant, req: AvatarRequest): string =>
  `${variant}:${req.id}:${req.version}`;

const getCachedValue = (variant: AvatarVariant, req: AvatarRequest): string | null | undefined => {
  const entry = avatarCache.get(cacheKey(variant, req));
  if (!entry) return undefined;
  if (entry.expiresAt <= Date.now()) {
    avatarCache.delete(cacheKey(variant, req));
    return undefined;
  }
  return entry.value;
};

const setCachedValue = (variant: AvatarVariant, req: AvatarRequest, value: string | null) => {
  avatarCache.set(cacheKey(variant, req), {
    value,
    expiresAt: Date.now() + CACHE_TTL_MS,
  });
};

const ensureFlushScheduled = () => {
  if (!flushTimer) {
    flushTimer = setTimeout(flushPendingQueue, 0);
  }
};

const enqueueFetch = (requests: AvatarRequest[], variant: AvatarVariant): Promise<AvatarUrlMap> => {
  if (!requests.length) {
    return Promise.resolve({});
  }

  const cachedResults: AvatarUrlMap = {};
  const missing: AvatarRequest[] = [];
  requests.forEach((req) => {
    const cached = getCachedValue(variant, req);
    if (cached !== undefined) {
      cachedResults[req.id] = cached;
    } else {
      missing.push(req);
    }
  });

  if (!missing.length) {
    return Promise.resolve(cachedResults);
  }

  return new Promise<AvatarUrlMap>((resolve, reject) => {
    pendingQueue.push({
      requests,
      variant,
      resolve: (value) => resolve({ ...cachedResults, ...value }),
      reject,
    });
    ensureFlushScheduled();
  });
};

const flushPendingQueue = async (): Promise<void> => {
  const snapshot = pendingQueue;
  pendingQueue = [];
  flushTimer = null;

  const variantGroups = new Map<AvatarVariant, Map<string, AvatarRequest>>();
  snapshot.forEach((entry) => {
    let group = variantGroups.get(entry.variant);
    if (!group) {
      group = new Map();
      variantGroups.set(entry.variant, group);
    }
    entry.requests.forEach((req) => {
      if (getCachedValue(entry.variant, req) === undefined) {
        group!.set(compositeKey(req), req);
      }
    });
  });

  const variantResults = new Map<AvatarVariant, AvatarUrlMap>();

  for (const [variant, requestMap] of variantGroups.entries()) {
    if (!requestMap.size) {
      variantResults.set(variant, {});
      continue;
    }

    const requests = Array.from(requestMap.values());
    const aggregated: AvatarUrlMap = {};

    for (let i = 0; i < requests.length; i += 50) {
      const chunk = requests.slice(i, i + 50);
      const userIds = Array.from(new Set(chunk.map((req) => req.id)));
      try {
        const chunkResult = await requestProfilePictureBatch(userIds, variant);
        chunk.forEach((req) => {
          const value = chunkResult[req.id] ?? null;
          aggregated[req.id] = value;
          setCachedValue(variant, req, value);
        });
      } catch (error) {
        logger.warn('Avatar batch request failed', error);
        chunk.forEach((req) => {
          aggregated[req.id] = null;
          setCachedValue(variant, req, null);
        });
      }
    }
    variantResults.set(variant, aggregated);
  }

  snapshot.forEach((entry) => {
    const aggregated = variantResults.get(entry.variant) ?? {};
    const response: AvatarUrlMap = {};
    entry.requests.forEach((req) => {
      const cached = getCachedValue(entry.variant, req);
      if (cached !== undefined) {
        response[req.id] = cached;
      } else if (aggregated[req.id] !== undefined) {
        response[req.id] = aggregated[req.id] ?? null;
      } else {
        response[req.id] = null;
      }
    });
    entry.resolve(response);
  });
};

const requestProfilePictureBatch = async (
  ids: string[],
  variant: AvatarVariant,
): Promise<AvatarUrlMap> => {
  if (!ids.length) {
    return {};
  }

  const params = new URLSearchParams();
  params.set('ids', ids.join(','));
  params.set('variant', variant);

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  try {
    const response = await fetchWithAuth(`/api/v1/users/profile-picture-urls?${params.toString()}`, {
      method: 'GET',
      noCache: false,
      signal: controller.signal,
    });
    if (!response.ok) {
      throw new Error(`Avatar batch fetch failed (${response.status})`);
    }
    const payload = (await response.json()) as components['schemas']['ProfilePictureUrlsResponse'];
    const urls = payload.urls;
    ids.forEach((id) => {
      if (!(id in urls)) {
        urls[id] = null;
      }
    });
    return urls;
  } finally {
    clearTimeout(timeout);
  }
};

const buildFallbackMap = (requests: AvatarRequest[]): AvatarUrlMap =>
  requests.reduce<AvatarUrlMap>((acc, req) => {
    acc[req.id] = null;
    return acc;
  }, {});

export function useProfilePictureUrls(
  rawUserIds: string[] = [],
  variant: AvatarVariant = 'thumb',
): AvatarUrlMap {
  const serializedUserIds = JSON.stringify(rawUserIds ?? []);

  const dedupedRequests = useMemo(() => {
    const parsedIds = JSON.parse(serializedUserIds) as string[];
    const seen = new Set<string>();
    const ordered: AvatarRequest[] = [];
    parsedIds.forEach((raw) => {
      const req = parseRawId(raw);
      if (!req.id) return;
      const key = compositeKey(req);
      if (!seen.has(key)) {
        seen.add(key);
        ordered.push(req);
      }
    });
    return ordered;
  }, [serializedUserIds]);

  const fallbackMap = useMemo(() => buildFallbackMap(dedupedRequests), [dedupedRequests]);
  const requestKey = useMemo(
    () => dedupedRequests.map((req) => compositeKey(req)).join('|'),
    [dedupedRequests]
  );

  const { data: fetchedUrls, error } = useQuery<AvatarUrlMap, Error>({
    queryKey: ['avatar-urls', variant, requestKey],
    queryFn: () => enqueueFetch(dedupedRequests, variant),
    enabled: dedupedRequests.length > 0,
    staleTime: CACHE_TTL_MS,
  });

  useEffect(() => {
    if (error) {
      logger.warn('Falling back to placeholder avatars after batch failure', error);
    }
  }, [error]);

  return useMemo(() => {
    if (!dedupedRequests.length) return {};
    if (!fetchedUrls) return fallbackMap;
    return { ...fallbackMap, ...fetchedUrls };
  }, [dedupedRequests.length, fallbackMap, fetchedUrls]);
}

/** @internal Test helper - clears avatar cache between tests */
export function __clearAvatarCacheForTesting(): void {
  avatarCache.clear();
  pendingQueue = [];
  if (flushTimer) {
    clearTimeout(flushTimer);
    flushTimer = null;
  }
}
