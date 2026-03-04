#!/usr/bin/env node
/**
 * Migrate no-op text hovers: hover:text-[#7E22CE] → hover:text-purple-900 dark:hover:text-purple-300
 *
 * These are elements with text-[#7E22CE] that also have hover:text-[#7E22CE] — the hover
 * changes text to the exact same color, providing zero visual feedback. This script replaces
 * them with a visible darkening on hover + a dark mode counterpart.
 *
 * Usage: node scripts/migrate-text-hover-noop.mjs
 * Idempotent: second run produces 0 modifications.
 */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const FRONTEND_ROOT = (
  fs.existsSync(path.join(process.cwd(), 'app')) &&
  fs.existsSync(path.join(process.cwd(), 'components'))
)
  ? path.resolve(process.cwd())
  : path.resolve(SCRIPT_DIR, '..');

const SEARCH_DIRS = ['app', 'components', 'features'];
const VALID_EXT = new Set(['.ts', '.tsx']);
const TEST_FILE_RE = /\.(test|spec)\.[jt]sx?$/i;

// Match standalone hover:text-[#7E22CE] but NOT group-hover:text-[#7E22CE] or peer-hover:text-[#7E22CE]
const STANDALONE_HOVER_RE = /(?<![a-z-])hover:text-\[#7E22CE\]/g;
const NEW_TOKENS = 'hover:text-purple-900 dark:hover:text-purple-300';

function isTestLike(filePath) {
  if (filePath.includes(`${path.sep}node_modules${path.sep}`)) return true;
  if (filePath.includes(`${path.sep}__tests__${path.sep}`)) return true;
  return TEST_FILE_RE.test(filePath);
}

function collectFiles(dir, out) {
  if (!fs.existsSync(dir)) return;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === 'node_modules' || entry.name === '__tests__') continue;
      collectFiles(fullPath, out);
      continue;
    }
    const ext = path.extname(entry.name);
    if (!VALID_EXT.has(ext)) continue;
    if (isTestLike(fullPath)) continue;
    out.push(fullPath);
  }
}

function processFile(filePath) {
  const content = fs.readFileSync(filePath, 'utf8');
  if (!content.includes('hover:text-[#7E22CE]')) {
    return { filePath, modified: false, replacements: 0 };
  }

  let count = 0;
  let updated = content.replace(new RegExp(STANDALONE_HOVER_RE.source, 'g'), () => {
    count++;
    return NEW_TOKENS;
  });

  // Deduplicate: if the original already had dark:hover:text-purple-300 adjacent,
  // remove the duplicate introduced by our insertion
  updated = updated.replace(/dark:hover:text-purple-300(\s+)dark:hover:text-purple-300/g, 'dark:hover:text-purple-300');

  if (updated !== content) {
    fs.writeFileSync(filePath, updated, 'utf8');
    return { filePath, modified: true, replacements: count };
  }

  return { filePath, modified: false, replacements: 0 };
}

function main() {
  const files = [];
  for (const d of SEARCH_DIRS) {
    collectFiles(path.join(FRONTEND_ROOT, d), files);
  }

  const results = [];
  for (const filePath of files) {
    results.push(processFile(filePath));
  }

  const modified = results.filter((r) => r.modified);
  const totalReplacements = results.reduce((sum, r) => sum + r.replacements, 0);

  console.log('No-op text hover migration complete.');
  console.log(`Files scanned: ${results.length}`);
  console.log(`Files modified: ${modified.length}`);
  console.log(`Total replacements: ${totalReplacements}`);

  if (modified.length > 0) {
    console.log('\nModified files:');
    for (const r of modified) {
      console.log(`  ${path.relative(FRONTEND_ROOT, r.filePath)} (${r.replacements} replacements)`);
    }
  }
}

main();
