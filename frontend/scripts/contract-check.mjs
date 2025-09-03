#!/usr/bin/env node
/* eslint-disable no-console */

import { execSync } from 'node:child_process';
import { readFileSync, mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const CI = process.argv.includes('--ci') || process.env.CI === 'true';

// repo root -> ensure we run from /frontend for paths below
const repoRoot = execSync('git rev-parse --show-toplevel').toString().trim();
process.chdir(join(repoRoot, 'frontend'));

function sh(cmd, opts = {}) {
  return execSync(cmd, { stdio: 'pipe', encoding: 'utf8', ...opts });
}
function ish(cmd) {
  execSync(cmd, { stdio: 'inherit' });
}

function generateTypes(openapiPath, outPath) {
  ish(`npx --yes openapi-typescript ${openapiPath} -o ${outPath} --export-type`);
}

if (CI) {
  // CI MODE: pure check from tracked spec file — no Python, no backend imports
  const specPath = join(repoRoot, 'backend/openapi/openapi.json');

  // 1) Types regeneration must match tracked file exactly
  const tmpDir = mkdtempSync(join(tmpdir(), 'oats-'));
  const tmpOut = join(tmpDir, 'api.d.ts');
  try {
    generateTypes(specPath, tmpOut);

    const expected = readFileSync('types/generated/api.d.ts', 'utf8');
    const actual = readFileSync(tmpOut, 'utf8');

    if (expected !== actual) {
      console.error('❌ Contract drift: generated types differ from tracked file (frontend/types/generated/api.d.ts).');
      console.error('   Run locally: cd frontend && npm run contract:pull  # then commit both openapi.json and api.d.ts');
      process.exit(1);
    }

    // 2) Drift guard: if backend API code changed but openapi.json did NOT, fail fast
    // Ensure base is available
    try {
      sh('git fetch --no-tags --prune --depth=50 origin +refs/heads/*:refs/remotes/origin/*');
    } catch {}

    const baseRef = process.env.GITHUB_BASE_REF ? `origin/${process.env.GITHUB_BASE_REF}` : 'origin/main';
    let changed = [];
    try {
      changed = sh(`git diff --name-only ${baseRef}...HEAD`).trim().split('\n').filter(Boolean);
    } catch {
      // Fallback to HEAD~1 on push without base
      try {
        changed = sh('git diff --name-only HEAD~1...HEAD').trim().split('\n').filter(Boolean);
      } catch {}
    }

    const backendTouched = changed.some((p) =>
      /^backend\/app\/(routes|schemas|models|dependencies|api|controllers)\//.test(p)
      || p === 'backend/app/openapi_app.py'
      || p === 'backend/scripts/export_openapi.py'
    );
    const specChanged = changed.includes('backend/openapi/openapi.json');

    if (backendTouched && !specChanged) {
      console.error('❌ Backend API sources changed but backend/openapi/openapi.json did not.');
      console.error('   Action required: update spec & types locally:');
      console.error('   cd frontend && npm run contract:pull  # then commit the updated spec and types');
      process.exit(1);
    }

    console.log('✅ Contract check (CI mode) passed.');
  } finally {
    try { rmSync(tmpDir, { recursive: true, force: true }); } catch {}
  }
  process.exit(0);
}

// LOCAL MODE: full workflow (export → generate → typecheck)
ish('npm run contract:export'); // Python export (local dev only)
generateTypes(join(repoRoot, 'backend/openapi/openapi.json'), 'types/generated/api.d.ts');
ish('npm run typecheck');
console.log('✅ Contract pulled & typecheck passed (local mode).');
