import type { FullConfig } from '@playwright/test';
import { promises as fs } from 'fs';
import path from 'path';

interface StorageState {
  cookies: Array<{
    name: string;
    value: string;
    domain: string;
    path: string;
    expires: number;
    httpOnly: boolean;
    secure: boolean;
    sameSite: 'Strict' | 'Lax' | 'None';
  }>;
  origins: unknown[];
}

async function readEnvToken(projectRoot: string): Promise<string | null> {
  const candidates = ['.env.local', '.env'];
  for (const filename of candidates) {
    const envPath = path.join(projectRoot, filename);
    try {
      const content = await fs.readFile(envPath, 'utf8');
      const lines = content.split(/\r?\n/);
      for (const rawLine of lines) {
        const line = rawLine.trim();
        if (!line || line.startsWith('#')) continue;
        const eq = line.indexOf('=');
        if (eq === -1) continue;
        const key = line.slice(0, eq).trim();
        let value = line.slice(eq + 1).trim();
        if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
          value = value.slice(1, -1);
        }
        if (key === 'STAFF_ACCESS_TOKEN' || key === 'staff_access_token') {
          return value;
        }
      }
    } catch {
      // ignore missing file
    }
  }
  // Also allow env var directly
  return process.env.STAFF_ACCESS_TOKEN || process.env.staff_access_token || null;
}

async function ensureDir(dirPath: string) {
  try {
    await fs.mkdir(dirPath, { recursive: true });
  } catch {
    // ignore
  }
}

async function globalSetup(_config: FullConfig) {
  const projectRoot = process.cwd();
  const storageDir = path.join(projectRoot, 'e2e', '.auth');
  const storageFile = path.join(storageDir, 'state.json');
  await ensureDir(storageDir);

  const token = await readEnvToken(projectRoot);

  const thirtyDaysFromNow = Math.floor(Date.now() / 1000) + 60 * 60 * 24 * 30;

  const storageState: StorageState = {
    cookies: [],
    origins: [],
  };

  if (token) {
    storageState.cookies.push({
      name: 'staff_access_token',
      value: token,
      domain: 'localhost',
      path: '/',
      httpOnly: true,
      secure: false,
      sameSite: 'Lax',
      expires: thirtyDaysFromNow,
    });
  }

  await fs.writeFile(storageFile, JSON.stringify(storageState, null, 2), 'utf8');
}

export default globalSetup;
