#!/usr/bin/env node
import { execSync } from 'node:child_process';

const patterns = [
  "rg -n --no-heading \"env\\.get\\('NEXT_PUBLIC_\" frontend || true",
  "rg -n --no-heading \"process\\.env\\[['\\\"`]NEXT_PUBLIC_\" frontend || true",
];

function getChangedFiles() {
  try {
    const base = process.env.GITHUB_BASE_REF || execSync('git merge-base HEAD origin/main', { stdio: 'pipe', encoding: 'utf8' }).trim();
    const diff = execSync(`git diff --name-only ${base}...HEAD -- frontend`, { stdio: 'pipe', encoding: 'utf8' });
    return diff.split('\n').filter(Boolean);
  } catch {
    return [];
  }
}

let violations = [];
const changed = new Set(getChangedFiles());
for (const cmd of patterns) {
  try {
    const out = execSync(cmd, { stdio: 'pipe', encoding: 'utf8' });
    if (out.trim()) {
      const lines = out.trim().split('\n').filter(Boolean);
      // If we have a changed-files set, filter to those; otherwise keep all
      const filtered = changed.size
        ? lines.filter((l) => changed.has(l.split(':')[0]))
        : lines;
      if (filtered.length) violations.push(filtered.join('\n'));
    }
  } catch {
    try {
      const out = execSync(cmd.replace(/^rg/, 'grep -R'), { stdio: 'pipe', encoding: 'utf8' });
      if (out.trim()) {
        const lines = out.trim().split('\n').filter(Boolean);
        const filtered = changed.size
          ? lines.filter((l) => changed.has(l.split(':')[0]))
          : lines;
        if (filtered.length) violations.push(filtered.join('\n'));
      }
    } catch {}
  }
}

if (violations.length) {
  console.error('\n❌ Public env misuse detected in changed files.');
  console.error("Fix: Use getPublicEnv('FOO') from '@/lib/publicEnv' or a helper (e.g., withApiBase) in client code instead of process.env.NEXT_PUBLIC_FOO or env.get().");
  console.error('Files:');
  console.error(violations.join('\n'));
  process.exit(1);
}

console.log('✅ Public env usage looks good.');
