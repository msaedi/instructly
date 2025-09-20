#!/usr/bin/env node
import { execSync } from 'node:child_process';
import { appendFileSync, existsSync } from 'node:fs';
import { dirname } from 'node:path';

const SAFE_FILES = new Set([
  'frontend/lib/publicEnv.ts',
  'frontend/lib/env.ts',
]);

const PATTERNS = [
  /process\.env\s*(?:\[|\.)\s*['"`]?NEXT_PUBLIC_[A-Z0-9_]*['"`]?/i,
  /\benv\.(?:get|require|getOrDefault)\s*\(\s*['"`]NEXT_PUBLIC_[A-Z0-9_]*['"`]/i,
];

function getBaseRef() {
  try {
    const fromGithub = process.env.GITHUB_BASE_REF;
    if (fromGithub) {
      return execSync(`git rev-parse ${fromGithub}`, { stdio: 'pipe', encoding: 'utf8' }).trim();
    }
    return execSync('git merge-base HEAD origin/main', { stdio: 'pipe', encoding: 'utf8' }).trim();
  } catch {
    return 'HEAD~1';
  }
}

function getDiff(base) {
  try {
    return execSync(`git diff ${base}...HEAD --unified=0 -- frontend`, {
      stdio: 'pipe',
      encoding: 'utf8',
    });
  } catch {
    return '';
  }
}

function analyzeDiff(diff) {
  const results = [];
  let currentFile = null;
  let currentLine = 0;
  for (const rawLine of diff.split('\n')) {
    if (rawLine.startsWith('+++ b/')) {
      const filePath = rawLine.slice(6).trim();
      currentFile = filePath !== '/dev/null' ? filePath : null;
      continue;
    }
    if (rawLine.startsWith('@@')) {
      const match = /@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@/.exec(rawLine);
      currentLine = match ? parseInt(match[1], 10) : 0;
      continue;
    }
    if (!currentFile) continue;
    if (SAFE_FILES.has(currentFile)) continue;

    if (rawLine.startsWith('+') && !rawLine.startsWith('+++')) {
      const content = rawLine.slice(1);
      if (PATTERNS.some((regex) => regex.test(content))) {
        results.push({ file: currentFile, line: currentLine, snippet: content.trim() });
      }
      currentLine += 1;
    } else if (rawLine.startsWith('-') && !rawLine.startsWith('---')) {
      // removal; do not increment new line counter
      continue;
    } else {
      currentLine += 1;
    }
  }
  return results;
}

function appendSummary(message) {
  const summaryPath = process.env.GITHUB_STEP_SUMMARY;
  if (!summaryPath) return;
  const dir = dirname(summaryPath);
  if (!existsSync(dir)) {
    return;
  }
  appendFileSync(summaryPath, `${message}\n`);
}

const base = getBaseRef();
const diff = getDiff(base);
const violations = analyzeDiff(diff);

if (violations.length > 0) {
  console.error('\n❌ Public env misuse detected in added/modified lines.');
  console.error("Fix it: use `getPublicEnv('FOO')` from '@/lib/publicEnv' or an existing helper (e.g. `withApiBase`) instead of accessing NEXT_PUBLIC_* directly in client code.");
  for (const v of violations) {
    console.error(`- ${v.file}:${v.line} → ${v.snippet}`);
  }
  appendSummary(`public-env: FAIL (${violations.length} new NEXT_PUBLIC_* references)`);
  process.exit(1);
}

console.log('✅ Public env usage looks good.');
appendSummary('public-env: OK');
