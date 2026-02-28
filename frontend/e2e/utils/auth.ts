import { chromium, expect, type Page } from '@playwright/test';
import { promises as fs } from 'fs';
import path from 'path';
import { normalizeStorageState } from '../support/storageState';

export const ADMIN_EMAIL =
  process.env.E2E_ADMIN_EMAIL ?? process.env.ADMIN_EMAIL ?? 'admin@instainstru.com';
export const ADMIN_PASSWORD =
  process.env.E2E_ADMIN_PASSWORD ?? process.env.ADMIN_PASSWORD ?? 'ChangeMeSuperSecure123!';

const DEFAULT_BASE_URL =
  process.env.ADMIN_BASE_URL ??
  process.env.PREVIEW_BASE ??
  process.env.E2E_BASE_URL ??
  process.env.PLAYWRIGHT_BASE_URL ??
  'http://localhost:3000';
const DEFAULT_API_BASE =
  process.env.E2E_API_BASE_URL ?? process.env.NEXT_PUBLIC_API_BASE ?? 'http://localhost:8000';

export async function uiLoginAsAdmin(page: Page, loginPath = '/login') {
  await page.goto(loginPath, { waitUntil: 'domcontentloaded' });
  await page.getByLabel(/email/i).fill(ADMIN_EMAIL);
  await page.getByLabel('Password', { exact: true }).fill(ADMIN_PASSWORD);
  await page.getByRole('button', { name: /sign in|log in|submit/i }).click();
  await page.waitForLoadState('domcontentloaded');
}

export async function loginAsAdminViaApi(page: Page, apiBase = DEFAULT_API_BASE) {
  const guestSessionId = `e2e-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  const response = await page.request.post(`${apiBase}/api/v1/auth/login-with-session`, {
    data: {
      email: ADMIN_EMAIL,
      password: ADMIN_PASSWORD,
      guest_session_id: guestSessionId,
    },
    headers: { 'content-type': 'application/json' },
  });
  expect(response.ok(), `admin API login failed with status ${response.status()}`).toBeTruthy();
}

export async function ensureAdminStorageState(storagePath = 'e2e/.storage/admin.json', baseURL = DEFAULT_BASE_URL) {
  if (!ADMIN_EMAIL || !ADMIN_PASSWORD) {
    throw new Error('ADMIN_EMAIL/ADMIN_PASSWORD (or E2E_*) must be set for admin flows');
  }

  const absolutePath = path.isAbsolute(storagePath)
    ? storagePath
    : path.join(process.cwd(), storagePath);

  try {
    await fs.access(absolutePath);
    return absolutePath;
  } catch {
    // continue to build storage state
  }

  await fs.mkdir(path.dirname(absolutePath), { recursive: true });

  const browser = await chromium.launch();
  try {
    const context = await browser.newContext({ baseURL });
    const page = await context.newPage();
    await uiLoginAsAdmin(page, '/login');
    const rawState = await context.storageState();
    const normalizedState = normalizeStorageState(rawState, baseURL, { label: absolutePath });
    await fs.writeFile(absolutePath, JSON.stringify(normalizedState, null, 2), 'utf8');
    await context.close();
  } finally {
    await browser.close();
  }

  return absolutePath;
}
