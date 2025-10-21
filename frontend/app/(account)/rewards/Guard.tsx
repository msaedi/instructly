'use client';

import { useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { withApiBase } from '@/lib/apiBase';
import { API_ENDPOINTS } from '@/lib/api';

const LOGIN_REDIRECT = '/login?redirect=%2Frewards';

export default function Guard() {
  const router = useRouter();
  const didRun = useRef(false);

  useEffect(() => {
    // Avoid double-run in React Strict Mode (dev only)
    if (didRun.current) return;
    didRun.current = true;

    const controller = new AbortController();
    const url = withApiBase(API_ENDPOINTS.ME);

    fetch(url, {
      method: 'GET',
      credentials: 'include',
      headers: { accept: 'application/json' },
      signal: controller.signal,
    })
      .then((res) => {
        if (!res.ok) {
          router.replace(LOGIN_REDIRECT);
        }
      })
      .catch((err) => {
        // Ignore AbortError from Strict Mode cleanup / unmount
        if (err && (err.name === 'AbortError' || err.code === 20)) return;
        router.replace(LOGIN_REDIRECT);
      });

    return () => {
      controller.abort();
    };
  }, [router]);

  return null;
}
