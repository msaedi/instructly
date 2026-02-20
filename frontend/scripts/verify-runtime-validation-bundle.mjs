#!/usr/bin/env node
import { execSync } from 'node:child_process';

function run(cmd) {
  try {
    return execSync(cmd, { stdio: 'pipe', encoding: 'utf8' }).trim();
  } catch {
    return '';
  }
}

// Check Next.js client chunks for any reference to 'zod' (the library).
// We scope to .next/static/chunks to avoid false positives in server/chunk traces.
// Use -w (word boundary) to avoid matching substrings like "zodiac" (emoji-mart data).
const grepCmd = "grep -R -n -w --include='*.js' zod .next/static/chunks || true";
const out = run(grepCmd);

if (out && out.length > 0) {
  console.error('❌ zod found in client chunks. Runtime validation must not ship in prod bundles.');
  console.error(out.split('\n').slice(0, 20).join('\n'));
  process.exit(1);
}

console.log('✅ zod not present in client chunks.');
