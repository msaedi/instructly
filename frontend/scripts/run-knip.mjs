#!/usr/bin/env node
// Wrapper to run knip in warn-mode and print a short summary
import { spawn } from 'node:child_process';

function run() {
  return new Promise((resolve) => {
    const args = ['knip', '--config', 'knip.config.mjs', '--no-exit-code'];
    const child = spawn('npx', args, { stdio: ['ignore', 'pipe', 'pipe'] });
    let stdout = '';
    let stderr = '';
    child.stdout.on('data', (d) => (stdout += d.toString()));
    child.stderr.on('data', (d) => (stderr += d.toString()));
    child.on('close', (code) => {
      const filter = (s) =>
        s
          .split(/\r?\n/)
          .filter(
            (line) =>
              !line.includes('playwright.config.ts') &&
              !line.includes("@/lib/env") &&
              !line.startsWith('Require stack:')
          )
          .join('\n');
      const out = filter(stdout.trim());
      const err = filter(stderr.trim());
      if (err) console.log(err);
      if (out) console.log(out);
      if (code !== 0) console.log('[knip] non-blocking warning mode');
      resolve(0);
    });
    child.on('error', (err) => {
      console.log('[knip] failed to run:', err?.message || String(err));
      resolve(0);
    });
  });
}

run().then(() => process.exit(0));
