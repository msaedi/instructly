import { request as pwRequest, type FullConfig } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';

const API_BASE_URL =
  process.env['E2E_API_BASE_URL'] ||
  process.env['NEXT_PUBLIC_API_BASE'] ||
  process.env['NEXT_PUBLIC_API_BASE_URL'] ||
  process.env['PLAYWRIGHT_API_BASE_URL'] ||
  'http://localhost:8000';
const STORAGE_DIR = path.resolve('e2e/.storage');
const INSTRUCTOR_STATE = path.join(STORAGE_DIR, 'instructor.json');
const ADMIN_STATE = path.join(STORAGE_DIR, 'admin.json');

const INSTRUCTOR_EMAIL = process.env['E2E_INSTRUCTOR_EMAIL'] || 'sarah.chen@example.com';
const INSTRUCTOR_PASSWORD = process.env['E2E_INSTRUCTOR_PASSWORD'] || 'Test1234';
const ADMIN_EMAIL = process.env['E2E_ADMIN_EMAIL'] || 'admin@instainstru.com';
const ADMIN_PASSWORD = process.env['E2E_ADMIN_PASSWORD'] || 'ChangeMeSuperSecure123!';

type StateConfig = {
  email: string;
  password: string;
  statePath: string;
};

const STATE_CONFIGS: StateConfig[] = [
  { email: INSTRUCTOR_EMAIL, password: INSTRUCTOR_PASSWORD, statePath: INSTRUCTOR_STATE },
  { email: ADMIN_EMAIL, password: ADMIN_PASSWORD, statePath: ADMIN_STATE },
];

async function ensureDir(dir: string) {
  try {
    await fs.mkdir(dir, { recursive: true });
  } catch {
    // ignore
  }
}

async function wait(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function loginWithSession({ email, password, statePath }: StateConfig): Promise<void> {
  const ctx = await pwRequest.newContext({ baseURL: API_BASE_URL });
  const maxAttempts = 4;
  let delay = 800;

  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    const response = await ctx.post('/auth/login-with-session', {
      data: {
        email,
        password,
        guest_session_id: `e2e-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`,
      },
      timeout: 15_000,
    });

    if (response.status() === 200) {
      await ensureDir(path.dirname(statePath));
      await ctx.storageState({ path: statePath });
      await ctx.dispose();
      return;
    }

    if (response.status() === 429 && attempt < maxAttempts) {
      const retryAfter = response.headers()['retry-after'];
      const serverDelay = retryAfter ? Number(retryAfter) * 1000 : delay;
      const jitter = Math.floor(Math.random() * 200);
      await wait(serverDelay + jitter);
      delay *= 2;
      continue;
    }

    const body = await response.text();
    await ctx.dispose();
    throw new Error(`login-with-session failed: ${response.status()} ${body}`);
  }

  await ctx.dispose();
  throw new Error('Unable to obtain session cookies after retries');
}

async function globalSetup(_config: FullConfig) {
  await ensureDir(STORAGE_DIR);
  const lockPath = path.join(STORAGE_DIR, '.lock');

  const acquireLock = async () => {
    try {
      await fs.writeFile(lockPath, String(process.pid), { flag: 'wx' });
      return true;
    } catch (error) {
      const err = error as NodeJS.ErrnoException;
      if (err.code === 'EEXIST') {
        return false;
      }
      throw err;
    }
  };

  const waitForSharedState = async (statePath: string) => {
    let remaining = 20;
    while (remaining > 0) {
      try {
        await fs.access(statePath);
        return;
      } catch {
        remaining -= 1;
        await wait(1000);
      }
    }
    throw new Error(`Timed out waiting for shared storage state at ${statePath}`);
  };

  const lockAcquired = await acquireLock();
  if (lockAcquired) {
    try {
      for (const config of STATE_CONFIGS) {
        try {
          await fs.unlink(config.statePath);
        } catch {
          // ignore
        }
        await loginWithSession(config);
      }
    } finally {
      try {
        await fs.unlink(lockPath);
      } catch {
        // ignore
      }
    }
    return;
  }

  for (const config of STATE_CONFIGS) {
    await waitForSharedState(config.statePath);
  }
}

export default globalSetup;
