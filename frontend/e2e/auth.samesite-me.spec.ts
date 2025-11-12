import { test, expect, request as pwRequest, chromium } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';
import { normalizeCookiesForContext } from './support/cookies';
import { normalizeStorageState } from './support/storageState';

const CROSS_ORIGIN_ENABLED = process.env.E2E_CROSS_ORIGIN === '1';

test.skip(!CROSS_ORIGIN_ENABLED, 'Cross-origin E2E disabled (set E2E_CROSS_ORIGIN=1 to enable).');

test.beforeEach(({}, testInfo) => {
  test.skip(testInfo.project.name !== 'instructor', `Instructor-only spec (current project: ${testInfo.project.name})`);
});

const defaultFrontend = process.env.PLAYWRIGHT_BASE_URL || process.env.E2E_BASE_URL || 'http://localhost:3100';
const previewFrontend = process.env.E2E_PREVIEW_BASE_URL || defaultFrontend;
const betaFrontend = process.env.E2E_BETA_BASE_URL || previewFrontend;

const defaultApi =
  process.env.E2E_API_BASE_URL ||
  process.env.PLAYWRIGHT_API_BASE ||
  process.env.NEXT_PUBLIC_API_BASE ||
  'http://localhost:8000';
const betaApi = process.env.E2E_BETA_API_BASE_URL || defaultApi;

const normalizeOrigin = (value: string) => {
  try {
    return new URL(value).origin;
  } catch {
    return value;
  }
};

const betaOrigin = normalizeOrigin(betaFrontend);

const apiForOrigin = (origin: string) =>
  normalizeOrigin(origin) === betaOrigin ? betaApi : defaultApi;

const rawHosts = process.env.SAMESITE_FE_ORIGINS
  ? process.env.SAMESITE_FE_ORIGINS.split(',')
      .map((origin) => origin.trim())
      .filter(Boolean)
      .map((origin) => ({
        fe: origin,
        api: apiForOrigin(origin),
      }))
  : [
      { fe: previewFrontend, api: defaultApi },
      { fe: betaFrontend, api: betaApi },
    ];

const HOSTS = rawHosts.filter(
  ({ fe, api }, index, arr) => Boolean(fe) && arr.findIndex((item) => item.fe === fe && item.api === api) === index
);

const STORAGE_DIR = path.resolve('e2e/.storage');

const storagePathForOrigin = (origin: string) => {
  const hostname = new URL(origin).hostname.replace(/[:/\\]/g, '_');
  return path.join(STORAGE_DIR, `me-${hostname}.json`);
};

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

async function ensureDir(dir: string) {
  await fs.mkdir(dir, { recursive: true });
}

async function loginForOrigin(origin: string, apiBase: string, email: string, password: string) {
  await ensureDir(STORAGE_DIR);
  const storagePath = storagePathForOrigin(origin);

  const api = await pwRequest.newContext({ baseURL: apiBase });
  const guestSessionId =
    typeof crypto !== 'undefined' && 'randomUUID' in crypto ? crypto.randomUUID() : Math.random().toString(36).slice(2);
  let response: import('@playwright/test').APIResponse | null = null;
  const maxAttempts = 4;
  let delay = 800;
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    const candidate = await api.post('/auth/login-with-session', {
      data: { email, password, guest_session_id: guestSessionId },
      timeout: 15_000,
    });
    if (candidate.status() === 200) {
      response = candidate;
      break;
    }
    if (candidate.status() === 429 && attempt < maxAttempts) {
      const retryAfter = candidate.headers()['retry-after'];
      const serverDelay = retryAfter ? Number(retryAfter) * 1000 : delay;
      await sleep(serverDelay + Math.floor(Math.random() * 200));
      delay *= 2;
      continue;
    }
    throw new Error(`login-with-session ${apiBase} failed with ${candidate.status()}`);
  }
  if (!response) {
    throw new Error(`login-with-session ${apiBase} exhausted retries`);
  }

  const state = await api.storageState();
  const cookies = normalizeCookiesForContext(state.cookies ?? [], origin);

  const browser = await chromium.launch();
  const context = await browser.newContext({ baseURL: origin });
  if (cookies.length) {
    await context.addCookies(cookies);
  }
  const rawState = await context.storageState();
  const normalizedState = normalizeStorageState(rawState, origin);
  await fs.writeFile(storagePath, JSON.stringify(normalizedState, null, 2), 'utf8');
  await context.close();
  await browser.close();
  await api.dispose();

  return storagePath;
}

test.describe('SameSite cookie smoke: /auth/me across local hosts', () => {
  test('me is 200 from each FE origin', async () => {
    test.skip(Boolean(process.env.CI) && !process.env.CI_LOCAL_E2E, 'Local-only smoke; opt-in via CI_LOCAL_E2E=1');

    const email =
      process.env.E2E_INSTRUCTOR_EMAIL ||
      process.env.E2E_USER_EMAIL ||
      process.env.E2E_ADMIN_EMAIL ||
      'sarah.chen@example.com';
    const password =
      process.env.E2E_INSTRUCTOR_PASSWORD ||
      process.env.E2E_USER_PASSWORD ||
      process.env.E2E_ADMIN_PASSWORD ||
      'Test1234';

    for (const { fe: origin, api } of HOSTS) {
      const storageStatePath = await loginForOrigin(origin, api, email, password);
      const browser = await chromium.launch();
      const context = await browser.newContext({ baseURL: origin, storageState: storageStatePath });
      const page = await context.newPage();
      await page.goto('/', { waitUntil: 'domcontentloaded' });
      const response = await page.request.get(new URL('/auth/me', api).toString(), { timeout: 15_000 });
      expect(response.status(), `${origin} /auth/me`).toBe(200);
      await context.close();
      await browser.close();
    }
  });
});
