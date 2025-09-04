#!/usr/bin/env node
import { execSync } from 'node:child_process';

const patterns = [
  "rg -n --no-heading \"env\\.get\\('NEXT_PUBLIC_\" frontend || true",
  "rg -n --no-heading \"process\\.env\\[['\\\"`]NEXT_PUBLIC_\" frontend || true",
];

let violations = [];
for (const cmd of patterns) {
  try {
    const out = execSync(cmd, { stdio: 'pipe', encoding: 'utf8' });
    if (out.trim()) violations.push(out.trim());
  } catch {
    try {
      const out = execSync(cmd.replace(/^rg/, 'grep -R'), { stdio: 'pipe', encoding: 'utf8' });
      if (out.trim()) violations.push(out.trim());
    } catch {}
  }
}

if (violations.length) {
  console.error('\n❌ Public env misuse detected. Use `@/lib/publicEnv` or helpers like withApiBase in client code.\n');
  console.error(violations.join('\n'));
  process.exit(1);
}

console.log('✅ Public env usage looks good.');
