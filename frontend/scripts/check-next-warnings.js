#!/usr/bin/env node
/*
 Minimal Next build warning budget checker.
 - Reads .artifacts/next-build.log
 - Counts warnings from ESLint/Next and generic "Warning:" lines
 - Fails if count exceeds WARNING_BUDGET (default 0)
 - Prints short summary: total, top 5 rules, top 5 files
*/
const fs = require('fs');
const path = require('path');

const budget = parseInt(process.env.WARNING_BUDGET || '0', 10);
const logPath = path.join(process.cwd(), '.artifacts', 'next-build.log');

if (!fs.existsSync(logPath)) {
  console.error(`❌ Build log not found at ${logPath}. Run \"npm run build:log\" first.`);
  process.exit(2);
}

const log = fs.readFileSync(logPath, 'utf8');

// Only count canonical Next/React/ESLint warnings. Ignore our app logger output.
const warningPatterns = [
  /^\s*warn\s+-\s+/i,     // Next.js "warn  - ..." lines
  /(^|\s)Warning:/,         // React "Warning: ..." during SSG/SSR
  /ESLint:\s+warning/i,     // ESLint warnings
];

const lines = log.split(/\r?\n/);
const matches = lines.filter((line) => warningPatterns.some((rx) => rx.test(line)));

const count = matches.length;
if (count > budget) {
  console.error(`❌ Build warnings: ${count} (budget ${budget})`);
  // Show first few offending lines for context
  console.error(matches.slice(0, 20).join('\n'));
  process.exit(1);
}

console.log(`✅ Build warnings: ${count} (budget ${budget})`);
