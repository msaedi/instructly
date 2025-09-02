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
const lines = log.split(/\r?\n/);

// Capture lines that clearly indicate warnings
const warningRegex = /(\bwarn\b|Warning:|ESLint:\s+warning)/i;
const fileHeaderRegex = /^\.\/.+\.(t|j)sx?/; // lines like ./path/to/file.tsx

let currentFile = null;
const warnLines = [];
const ruleCounts = new Map();
const fileCounts = new Map();

for (const line of lines) {
  if (fileHeaderRegex.test(line)) {
    currentFile = line.trim();
    continue;
  }
  if (warningRegex.test(line)) {
    warnLines.push(line);
    if (currentFile) {
      fileCounts.set(currentFile, (fileCounts.get(currentFile) || 0) + 1);
    }
    // Heuristically extract rule ids
    const ruleMatch = line.match(/@?([a-z0-9-]+\/[a-z0-9-]+|@typescript-eslint\/[a-z0-9-]+|react\/[a-z0-9-]+|no-[a-z0-9-]+)/i);
    if (ruleMatch) {
      const rule = ruleMatch[0];
      ruleCounts.set(rule, (ruleCounts.get(rule) || 0) + 1);
    }
  }
}

const total = warnLines.length;

function topN(map, n) {
  return Array.from(map.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, n);
}

const topRules = topN(ruleCounts, 5);
const topFiles = topN(fileCounts, 5);

if (total > budget) {
  console.error(`\n❌ Build warnings: ${total} (budget ${budget})`);
  if (topRules.length) {
    console.error('Top rules:');
    for (const [r, c] of topRules) console.error(`  ${r}: ${c}`);
  }
  if (topFiles.length) {
    console.error('Top files:');
    for (const [f, c] of topFiles) console.error(`  ${f}: ${c}`);
  }
  process.exit(1);
} else {
  console.log(`\n✅ Build warnings within budget: ${total}/${budget}`);
  if (total > 0) {
    console.log('Top rules:');
    for (const [r, c] of topRules) console.log(`  ${r}: ${c}`);
    console.log('Top files:');
    for (const [f, c] of topFiles) console.log(`  ${f}: ${c}`);
  }
}
