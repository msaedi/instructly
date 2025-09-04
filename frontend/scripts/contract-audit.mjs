#!/usr/bin/env node
import { execSync } from 'node:child_process';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, '..');
const BACKEND_OPENAPI = join(ROOT, '..', 'backend', 'openapi', 'openapi.json'); // uses committed spec
const TYPES_DIR = join(ROOT, 'types', 'generated');
const TRACKED_TYPES = join(TYPES_DIR, 'api.d.ts');
const AUDIT_TYPES = join(TYPES_DIR, 'api.audit.d.ts');
const ARTIFACT_DIR = join(ROOT, '.artifacts');
const REPORT = join(ARTIFACT_DIR, 'contract-audit-report.md');
const REPORT_JSON = join(ARTIFACT_DIR, 'contract-audit.json');

function sh(cmd, opts = {}) {
  return execSync(cmd, { stdio: 'pipe', encoding: 'utf8', ...opts }).trim();
}

function safe(cmd) {
  try { return { ok: true, out: sh(cmd) }; }
  catch (e) { return { ok: false, err: e.stdout || String(e) }; }
}

function header(text) {
  return `\n## ${text}\n`;
}

function toCamel(s) {
  return s.replace(/_([a-z])/g, (_, c) => c.toUpperCase());
}

// Removed unused function - collectTsFiles

function grepLiteral(pattern, dir) {
  // ripgrep literal search with file+line output
  const cmd = `rg -n --glob '!node_modules' --glob '!types/generated/**' --glob '!e2e/**' "${pattern}" ${dir}`;
  const res = safe(cmd);
  if (!res.ok) return [];
  return res.out.split('\n').filter(Boolean);
}

function main() {
  mkdirSync(ARTIFACT_DIR, { recursive: true });
  const isCi = process.argv.includes('--ci');

  let report = `# Contract Audit Report\nGenerated: ${new Date().toISOString()}\n`;
  report += `\n> Read-only audit to surface any pre-existing FE⇄BE mismatches.\n`;

  // 1) Regenerate types → temporary path (do NOT overwrite tracked)
  report += header('Types regeneration (temporary)');
  const genCmd = `npx openapi-typescript ${relative(ROOT, BACKEND_OPENAPI)} -o ${relative(ROOT, AUDIT_TYPES)} --export-type`;
  const genRes = safe(`cd ${ROOT} && ${genCmd}`);
  if (!genRes.ok) {
    report += `Failed to generate audit types.\n\n\`\`\`\n${genRes.err}\n\`\`\`\n`;
    writeFileSync(REPORT, report);
    console.log(report);
    process.exit(0);
  }
  report += `Generated audit types at \`${relative(ROOT, AUDIT_TYPES)}\`.\n`;

  // 2) Diff tracked vs audit types (word diff)
  report += header('Tracked vs Audit Types Diff');
  const diffRes = safe(`git diff --no-index --word-diff ${TRACKED_TYPES} ${AUDIT_TYPES} || true`);
  if (diffRes.ok && diffRes.out.trim().length > 0) {
    const snippet = diffRes.out.split('\n').slice(0, 400).join('\n');
    report += `Diff detected between tracked and freshly generated types (first 400 lines):\n\n\`\`\`diff\n${snippet}\n\`\`\`\n`;
  } else {
    report += `No diff detected — tracked generated types match a fresh generation.\n`;
  }

  // 3) Property name casing audit (snake_case → camelCase suspicious usage)
  report += header('Property casing audit (snake_case → camelCase)');
  let openapi;
  try {
    openapi = JSON.parse(readFileSync(BACKEND_OPENAPI, 'utf8'));
  } catch {
    report += `Failed to read ${relative(ROOT, BACKEND_OPENAPI)}.\n`;
    writeFileSync(REPORT, report);
    console.log(report);
    process.exit(0);
  }

  const snakeProps = new Set();
  const comps = openapi?.components?.schemas || {};
  for (const schemaName of Object.keys(comps)) {
    const sch = comps[schemaName];
    const props = sch?.properties || {};
    for (const key of Object.keys(props)) {
      if (key.includes('_')) snakeProps.add(key);
    }
  }

  const suspicious = [];
  for (const snake of snakeProps) {
    const camel = toCamel(snake);
    if (camel === snake) continue;
    const hits = grepLiteral(`\\.${camel}\\b|\\[${camel}\\]`, ROOT);
    if (hits.length) suspicious.push({ snake, camel, hits: hits.slice(0, 10) });
  }

  if (suspicious.length === 0) {
    report += `No obvious camelCase usages detected for snake_case API properties.\n`;
  } else {
    report += `Found **${suspicious.length}** property candidates where camelCase appears in code. These may indicate prior renames or manual mapping.\n`;
    for (const { snake, camel, hits } of suspicious) {
      report += `\n- \`${snake}\` → \`${camel}\` (showing up to 10 hits)\n`;
      for (const h of hits) report += `  - ${h}\n`;
    }
  }

  // 4) Ad-hoc request/response types that might shadow generated ones
  report += header('Ad-hoc Request/Response type declarations');
  const adhocMatches = grepLiteral(
    String.raw`\b(interface|type)\s+\w+(Request|Response)\b`,
    ROOT
  ).filter(l => !l.includes('types/generated'));

  if (adhocMatches.length === 0) {
    report += `No ad-hoc \`*Request|*Response\` type declarations found outside generated types.\n`;
  } else {
    report += `Found **${adhocMatches.length}** ad-hoc type declarations (these could be fine, but they might shadow API shapes):\n`;
    for (const m of adhocMatches.slice(0, 200)) report += `- ${m}\n`;
    if (adhocMatches.length > 200) report += `…and ${adhocMatches.length - 200} more.\n`;
  }

  // 5) Count of imports from generated API types (exclude allowed layers)
  report += header('Usage of generated API types (import count)');
  // Base greps
  const directAllCmd = `grep -r "from.*@/types/generated/api" --include="*.ts" --include="*.tsx" ${ROOT}`;
  const shimAllCmd = `grep -r "from.*@/features/shared/api/types" --include="*.ts" --include="*.tsx" ${ROOT}`;
  // Allowed layers to exclude from the "direct" count (shim itself)
  const allowedPathPattern = `/features/shared/api/types.ts`;
  const directOutsideCmd = `${directAllCmd} | grep -v "${allowedPathPattern}" | wc -l`;
  const directAllowedCmd = `${directAllCmd} | grep "${allowedPathPattern}" | wc -l`;
  const shimCountCmd = `${shimAllCmd} | wc -l`;

  const directOutside = parseInt(safe(directOutsideCmd).out || '0');
  const directAllowed = parseInt(safe(directAllowedCmd).out || '0');
  const shimCount = parseInt(safe(shimCountCmd).out || '0');
  const totalImports = directOutside + directAllowed + shimCount;

  report += `Found **${totalImports}** import sites using generated types (by layer):\n`;
  report += `- Direct imports outside allowed layers: ${directOutside}\n`;
  report += `- Direct imports in allowed layers (shim): ${directAllowed}\n`;
  report += `- Via type shim \`@/features/shared/api/types\`: ${shimCount}\n`;

  // Build details for JSON output (file lists)
  const listCmd = (cmd) => (safe(cmd).out || '').split('\n').filter(Boolean);
  const cutUnique = (lines) => Array.from(new Set(lines.map((l) => l.split(':')[0])));
  const directAllList = listCmd(directAllCmd);
  const shimAllList = listCmd(shimAllCmd);
  const directOutsideFiles = cutUnique(directAllList.filter((l) => !l.includes(allowedPathPattern)));
  const directAllowedFiles = cutUnique(directAllList.filter((l) => l.includes(allowedPathPattern)));
  const viaShimFiles = cutUnique(shimAllList);

  const drift = !(diffRes.ok && diffRes.out.trim().length === 0);

  const json = {
    drift,
    directImports: {
      outsideAllowed: directOutside,
      allowedLayer: directAllowed,
    },
    viaShimCount: shimCount,
    details: {
      viaShimFiles,
      directImportFilesOutside: directOutsideFiles,
      directImportFilesAllowed: directAllowedFiles,
    },
  };

  writeFileSync(REPORT_JSON, JSON.stringify(json, null, 2));

  // Write report
  writeFileSync(REPORT, report);
  if (!isCi) {
    console.log(`Wrote ${relative(ROOT, REPORT)}`);
  }

  // If running in GitHub Actions, append a brief summary
  if (process.env.GITHUB_STEP_SUMMARY) {
    let summary = `### Contract Audit (read-only)\n`;
    summary += `- Types diff: ${diffRes.out.trim().length ? '**DIFF DETECTED**' : 'none'}\n`;
    summary += `- Suspicious camelCase props: ${suspicious.length}\n`;
    summary += `- Ad-hoc \`*Request|*Response\` types: ${adhocMatches.length}\n`;
    summary += `\nFull report saved to \`${relative(ROOT, REPORT)}\` and uploaded as artifact.\n`;
    writeFileSync(process.env.GITHUB_STEP_SUMMARY, summary, { flag: 'a' });
  }

  // Exit 0 to keep this audit non-blocking
  process.exit(0);
}

main();
