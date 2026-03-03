#!/usr/bin/env node
import fs from 'fs';
import path from 'path';
import ts from 'typescript';
import { fileURLToPath } from 'url';

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const FRONTEND_ROOT = (
  fs.existsSync(path.join(process.cwd(), 'app')) &&
  fs.existsSync(path.join(process.cwd(), 'components'))
)
  ? path.resolve(process.cwd())
  : path.resolve(SCRIPT_DIR, '..');

const SEARCH_DIRS = ['app', 'components', 'features', 'hooks', 'lib'];
const VALID_EXT = new Set(['.ts', '.tsx']);
const TEST_FILE_RE = /\.(test|spec)\.[jt]sx?$/i;

const MAPPINGS = new Map([
  ['bg-white', ['dark:bg-gray-800']],
  ['bg-gray-50', ['dark:bg-gray-900']],
  ['bg-gray-100', ['dark:bg-gray-700']],
  ['bg-gray-200', ['dark:bg-gray-700']],
  ['text-gray-900', ['dark:text-gray-100']],
  ['text-gray-700', ['dark:text-gray-300']],
  ['text-gray-600', ['dark:text-gray-400']],
  ['text-gray-500', ['dark:text-gray-400']],
  ['text-gray-400', ['dark:text-gray-300']],
  ['text-gray-800', ['dark:text-gray-200']],
  ['text-black', ['dark:text-white']],
  ['border-gray-100', ['dark:border-gray-700']],
  ['border-gray-200', ['dark:border-gray-700']],
  ['border-gray-300', ['dark:border-gray-700']],
  ['ring-gray-300', ['dark:ring-gray-700']],
  ['divide-gray-100', ['dark:divide-gray-700']],
  ['divide-gray-200', ['dark:divide-gray-700']],
  ['bg-gray-300', ['dark:bg-gray-600']],
  ['bg-green-500', ['dark:bg-emerald-600']],
  ['bg-red-100', ['dark:bg-red-900', 'dark:text-red-200']],
  ['bg-orange-100', ['dark:bg-amber-900', 'dark:text-amber-200']],
  ['bg-blue-50', ['dark:bg-blue-900', 'dark:text-indigo-200']],
  ['text-green-700', ['dark:text-emerald-400']],
]);

function propertyGroup(cls) {
  if (cls.startsWith('bg-')) return 'bg';
  if (cls.startsWith('text-')) return 'text';
  if (cls.startsWith('border-')) return 'border';
  if (cls.startsWith('ring-')) return 'ring';
  if (cls.startsWith('divide-')) return 'divide';
  return null;
}

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

function extractTokens(text) {
  return text.match(/[^\s]+/g) ?? [];
}

function hasInstaSurfaceScope(scopeText) {
  return /\binsta-(?:card|surface(?:-[A-Za-z0-9_-]+)?)\b/.test(scopeText);
}

function initLiteralScopeState(literalText) {
  const allTokens = extractTokens(literalText);
  return {
    bg: allTokens.some((t) => /^dark:bg-/.test(t)),
    text: allTokens.some((t) => /^dark:text-/.test(t)),
    border: allTokens.some((t) => /^dark:border-/.test(t)),
    ring: allTokens.some((t) => /^dark:ring-/.test(t)),
    divide: allTokens.some((t) => /^dark:divide-/.test(t)),
  };
}

function applyTokenInsertions(text, scopeState) {
  const tokenRe = /[^\s]+/g;
  let match;
  let cursor = 0;
  let out = '';
  let insertions = 0;
  while ((match = tokenRe.exec(text)) !== null) {
    const token = match[0];
    out += text.slice(cursor, match.index);
    out += token;
    cursor = tokenRe.lastIndex;

    if (!MAPPINGS.has(token)) continue;
    const group = propertyGroup(token);
    if (!group || scopeState[group]) continue;

    const mapped = MAPPINGS.get(token);
    out += ` ${mapped.join(' ')}`;
    insertions += mapped.length;

    for (const variant of mapped) {
      const variantGroup = variant.startsWith('dark:bg-')
        ? 'bg'
        : variant.startsWith('dark:text-')
          ? 'text'
          : variant.startsWith('dark:border-')
            ? 'border'
            : variant.startsWith('dark:ring-')
              ? 'ring'
              : variant.startsWith('dark:divide-')
                ? 'divide'
            : null;
      if (variantGroup) scopeState[variantGroup] = true;
    }
  }
  out += text.slice(cursor);
  return { text: out, insertions };
}

function dedupeAndApplyEdits(original, edits) {
  if (edits.length === 0) return { text: original, changed: false };

  const uniqueMap = new Map();
  for (const e of edits) {
    const key = `${e.start}:${e.end}`;
    if (!uniqueMap.has(key)) uniqueMap.set(key, e);
  }

  const sorted = [...uniqueMap.values()].sort((a, b) => b.start - a.start);
  let next = original;
  for (const e of sorted) {
    next = next.slice(0, e.start) + e.newText + next.slice(e.end);
  }
  return { text: next, changed: next !== original };
}

function gatherLiteralNodes(expr, sourceFile) {
  const literals = [];

  function visit(node) {
    if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) {
      literals.push({
        node,
        kind: 'simple',
        start: node.getStart(sourceFile) + 1,
        end: node.end - 1,
        text: sourceFile.text.slice(node.getStart(sourceFile) + 1, node.end - 1),
      });
      return;
    }

    if (ts.isTemplateExpression(node)) {
      const head = node.head;
      literals.push({
        node: head,
        kind: 'template-head',
        start: head.getStart(sourceFile) + 1,
        end: head.end - 2,
        text: sourceFile.text.slice(head.getStart(sourceFile) + 1, head.end - 2),
      });

      for (const span of node.templateSpans) {
        visit(span.expression);
        const lit = span.literal;
        const isTail = lit.kind === ts.SyntaxKind.TemplateTail;
        literals.push({
          node: lit,
          kind: isTail ? 'template-tail' : 'template-middle',
          start: lit.getStart(sourceFile) + 1,
          end: lit.end - (isTail ? 1 : 2),
          text: sourceFile.text.slice(lit.getStart(sourceFile) + 1, lit.end - (isTail ? 1 : 2)),
        });
      }
      return;
    }

    ts.forEachChild(node, visit);
  }

  visit(expr);
  return literals.filter((l) => l.end >= l.start);
}

function isCnOrClsxCall(node) {
  if (!ts.isCallExpression(node)) return false;
  if (ts.isIdentifier(node.expression)) {
    return node.expression.text === 'cn' || node.expression.text === 'clsx';
  }
  return false;
}

function processClassExpression(expr, sourceFile, edits, state) {
  const exprStart = expr.getStart(sourceFile);
  const exprEnd = expr.end;
  const scopeText = sourceFile.text.slice(exprStart, exprEnd);

  if (hasInstaSurfaceScope(scopeText)) {
    state.skippedInstaScopes += 1;
    return;
  }

  if (isCnOrClsxCall(expr)) {
    const literals = [];
    for (const arg of expr.arguments) {
      literals.push(...gatherLiteralNodes(arg, sourceFile));
    }
    if (literals.length === 0) return;

    for (const lit of literals) {
      const scopeState = initLiteralScopeState(lit.text);
      const next = applyTokenInsertions(lit.text, scopeState);
      if (next.insertions === 0 || next.text === lit.text) continue;
      edits.push({ start: lit.start, end: lit.end, newText: next.text });
      state.insertions += next.insertions;
    }
    return;
  }

  const literals = gatherLiteralNodes(expr, sourceFile);
  if (literals.length === 0) return;

  for (const lit of literals) {
    const scopeState = initLiteralScopeState(lit.text);
    const next = applyTokenInsertions(lit.text, scopeState);
    if (next.insertions === 0 || next.text === lit.text) continue;
    edits.push({ start: lit.start, end: lit.end, newText: next.text });
    state.insertions += next.insertions;
  }
}

function processFile(filePath) {
  const content = fs.readFileSync(filePath, 'utf8');
  const kind = filePath.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS;
  const sourceFile = ts.createSourceFile(filePath, content, ts.ScriptTarget.Latest, true, kind);
  const edits = [];
  const local = { insertions: 0, skippedInstaScopes: 0 };

  function visit(node) {
    if (ts.isJsxAttribute(node) && node.name.text === 'className' && node.initializer) {
      if (ts.isStringLiteral(node.initializer)) {
        const expr = node.initializer;
        processClassExpression(expr, sourceFile, edits, local);
      } else if (ts.isJsxExpression(node.initializer) && node.initializer.expression) {
        processClassExpression(node.initializer.expression, sourceFile, edits, local);
      }
    }
    ts.forEachChild(node, visit);
  }

  try {
    visit(sourceFile);
  } catch (err) {
    return {
      filePath,
      skipped: true,
      reason: `unsafe-parse: ${err?.message ?? String(err)}`,
      modified: false,
      insertions: 0,
      skippedInstaScopes: 0,
    };
  }

  const applied = dedupeAndApplyEdits(content, edits);
  if (applied.changed) {
    fs.writeFileSync(filePath, applied.text, 'utf8');
  }

  return {
    filePath,
    skipped: false,
    reason: '',
    modified: applied.changed,
    insertions: local.insertions,
    skippedInstaScopes: local.skippedInstaScopes,
  };
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
  const skipped = results.filter((r) => r.skipped);
  const untouched = results.filter((r) => !r.modified && !r.skipped);
  const totalInsertions = results.reduce((sum, r) => sum + r.insertions, 0);
  const totalSkippedInstaScopes = results.reduce((sum, r) => sum + r.skippedInstaScopes, 0);

  console.log('Dark variant migration complete.');
  console.log(`Files scanned: ${results.length}`);
  console.log(`Files modified: ${modified.length}`);
  console.log(`Total dark variant insertions: ${totalInsertions}`);
  console.log(`Files skipped (parse safety): ${skipped.length}`);
  console.log(`Files untouched (already covered / no matches): ${untouched.length}`);
  console.log(`Class scopes skipped due to insta-surface/container classes: ${totalSkippedInstaScopes}`);

  if (modified.length > 0) {
    console.log('\nModified files:');
    for (const r of modified) {
      console.log(`- ${path.relative(FRONTEND_ROOT, r.filePath)} (+${r.insertions})`);
    }
  }

  if (skipped.length > 0) {
    console.log('\nSkipped files:');
    for (const r of skipped) {
      console.log(`- ${path.relative(FRONTEND_ROOT, r.filePath)} (${r.reason})`);
    }
  }
}

main();
