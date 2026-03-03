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

/* ------------------------------------------------------------------ */
/*  Hover-variant mapping table                                       */
/*  Keys: light-mode hover tokens that need a dark counterpart        */
/*  Values: dark:hover:* tokens to insert immediately after the key   */
/* ------------------------------------------------------------------ */
const HOVER_MAPPINGS = new Map([
  // hover:bg-*
  ['hover:bg-gray-50',      ['dark:hover:bg-gray-700']],
  ['hover:bg-gray-50/70',   ['dark:hover:bg-gray-700/40']],
  ['hover:bg-gray-100',     ['dark:hover:bg-gray-700']],
  ['hover:bg-gray-100/80',  ['dark:hover:bg-gray-700/60']],
  ['hover:bg-gray-200',     ['dark:hover:bg-gray-600']],
  ['hover:bg-gray-200/80',  ['dark:hover:bg-gray-700/60']],
  ['hover:bg-gray-300',     ['dark:hover:bg-gray-600']],
  ['hover:bg-purple-50',    ['dark:hover:bg-purple-900/30']],
  ['hover:bg-red-50',       ['dark:hover:bg-red-900/30']],
  ['hover:bg-red-100',      ['dark:hover:bg-red-900/40']],
  ['hover:bg-red-200',      ['dark:hover:bg-red-800']],
  ['hover:bg-blue-50',      ['dark:hover:bg-blue-900/30']],
  ['hover:bg-green-100',    ['dark:hover:bg-green-900/40']],
  ['hover:bg-yellow-50',    ['dark:hover:bg-yellow-900/30']],
  ['hover:bg-amber-50',     ['dark:hover:bg-amber-900/30']],
  ['hover:bg-indigo-50',    ['dark:hover:bg-indigo-900/20']],
  ['hover:bg-indigo-50/70', ['dark:hover:bg-indigo-900/20']],
  ['hover:bg-indigo-100',   ['dark:hover:bg-indigo-900/40']],
  ['hover:bg-purple-100',   ['dark:hover:bg-purple-900/30']],
  ['hover:bg-purple-200',   ['dark:hover:bg-purple-800/40']],
  ['hover:bg-green-50',     ['dark:hover:bg-green-900/30']],
  ['hover:bg-white',        ['dark:hover:bg-gray-700']],
  // hover:text-*
  ['hover:text-gray-900',   ['dark:hover:text-gray-100']],
  ['hover:text-gray-800',   ['dark:hover:text-gray-200']],
  ['hover:text-gray-700',   ['dark:hover:text-gray-300']],
  ['hover:text-gray-600',   ['dark:hover:text-gray-200']],
  ['hover:text-red-600',    ['dark:hover:text-red-400']],
  ['hover:text-indigo-800', ['dark:hover:text-indigo-300']],
  // hover:border-*
  ['hover:border-gray-300', ['dark:hover:border-gray-600']],
  ['hover:border-gray-400', ['dark:hover:border-gray-500']],
  ['hover:border-red-300',  ['dark:hover:border-red-500']],
]);

/* ------------------------------------------------------------------ */
/*  Brand audit: classes that should always pair with text-white /     */
/*  text-primary-foreground on interactive elements                    */
/* ------------------------------------------------------------------ */
const BRAND_BG_CLASSES = new Set([
  'bg-[#7E22CE]', 'bg-primary', 'bg-purple-600',
]);
const BRAND_TEXT_CLASSES = new Set([
  'text-white', 'text-primary-foreground',
]);

function hoverPropertyGroup(cls) {
  if (cls.startsWith('hover:bg-')) return 'hover-bg';
  if (cls.startsWith('hover:text-')) return 'hover-text';
  if (cls.startsWith('hover:border-')) return 'hover-border';
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
    'hover-bg': allTokens.some((t) => /^dark:hover:bg-/.test(t)),
    'hover-text': allTokens.some((t) => /^dark:hover:text-/.test(t)),
    'hover-border': allTokens.some((t) => /^dark:hover:border-/.test(t)),
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

    if (!HOVER_MAPPINGS.has(token)) continue;
    const group = hoverPropertyGroup(token);
    if (!group || scopeState[group]) continue;

    const mapped = HOVER_MAPPINGS.get(token);
    out += ` ${mapped.join(' ')}`;
    insertions += mapped.length;

    for (const variant of mapped) {
      const variantGroup = variant.startsWith('dark:hover:bg-')
        ? 'hover-bg'
        : variant.startsWith('dark:hover:text-')
          ? 'hover-text'
          : variant.startsWith('dark:hover:border-')
            ? 'hover-border'
            : null;
      if (variantGroup) scopeState[variantGroup] = true;
    }
  }
  out += text.slice(cursor);
  return { text: out, insertions };
}

function auditBrandText(tokens) {
  const hasBrandBg = tokens.some((t) => BRAND_BG_CLASSES.has(t));
  if (!hasBrandBg) return null;
  const hasBrandText = tokens.some((t) => BRAND_TEXT_CLASSES.has(t));
  if (hasBrandText) return null;
  const brandBg = tokens.find((t) => BRAND_BG_CLASSES.has(t));
  return `has "${brandBg}" without text-white or text-primary-foreground`;
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

  // Brand audit: check the whole expression for brand bg without text color
  const scopeTokens = extractTokens(scopeText);
  const brandWarning = auditBrandText(scopeTokens);
  if (brandWarning) {
    state.brandWarnings.push(brandWarning);
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
  const local = { insertions: 0, skippedInstaScopes: 0, brandWarnings: [] };

  function visit(node) {
    if (ts.isJsxAttribute(node) && node.name.text === 'className' && node.initializer) {
      if (ts.isStringLiteral(node.initializer)) {
        processClassExpression(node.initializer, sourceFile, edits, local);
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
      brandWarnings: [],
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
    brandWarnings: local.brandWarnings,
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
  const allBrandWarnings = results.flatMap((r) =>
    r.brandWarnings.map((w) => `${path.relative(FRONTEND_ROOT, r.filePath)}: ${w}`)
  );

  console.log('Hover variant migration complete.');
  console.log(`Files scanned: ${results.length}`);
  console.log(`Files modified: ${modified.length}`);
  console.log(`Total dark:hover:* insertions: ${totalInsertions}`);
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

  if (allBrandWarnings.length > 0) {
    console.log('\nBrand audit warnings (brand bg without text-white/text-primary-foreground):');
    for (const w of allBrandWarnings) {
      console.log(`- ${w}`);
    }
  } else {
    console.log('\nBrand audit: all brand bg elements have explicit text color.');
  }
}

main();
