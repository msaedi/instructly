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
const ADOPTION_JSON = join(ARTIFACT_DIR, 'contract-adoption.json');
const ADOPTION_MD = join(ARTIFACT_DIR, 'contract-adoption.md');

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

function grepLiteral(pattern, dir) {
  // ripgrep literal search with file+line output
  const cmd = `rg -n --glob '!node_modules' --glob '!types/generated/**' --glob '!e2e/**' "${pattern}" ${dir}`;
  const res = safe(cmd);
  if (!res.ok) return [];
  return res.out.split('\n').filter(Boolean);
}

function writeArtifacts(json, md) {
  writeFileSync(REPORT_JSON, JSON.stringify(json, null, 2));
  writeFileSync(REPORT, md);
}

async function main() {
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
    if (!isCi) console.log(report);
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
    if (!isCi) console.log(report);
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
    String.raw`\b(interface|type)\s+\w+(Request|Response|Result|Payload)\b`,
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
  const directAllCmd = `grep -r "from.*@/types/generated/api" --include="*.ts" --include="*.tsx" ${ROOT}`;
  const shimAllCmd = `grep -r "from.*@/features/shared/api/types" --include="*.ts" --include="*.tsx" ${ROOT}`;
  // Allowed layers: the entire features/shared/api/** directory (shim + clients)
  const allowedDirPattern = `/features/shared/api/`;
  const directOutsideCmd = `${directAllCmd} | grep -v "${allowedDirPattern}" | wc -l`;
  const directAllowedCmd = `${directAllCmd} | grep "${allowedDirPattern}" | wc -l`;
  const shimCountCmd = `${shimAllCmd} | wc -l`;

  const directOutside = parseInt(safe(directOutsideCmd).out || '0');
  const directAllowed = parseInt(safe(directAllowedCmd).out || '0');
  const viaShimCount = parseInt(safe(shimCountCmd).out || '0');

  report += `Found **${directOutside + directAllowed + viaShimCount}** import sites using generated types (by layer):\n`;
  report += `- Direct imports outside allowed layers: ${directOutside}\n`;
  report += `- Direct imports in allowed layers (shim/clients): ${directAllowed}\n`;
  report += `- Via type shim \`@/features/shared/api/types\`: ${viaShimCount}\n`;

  // Build details for JSON output (file lists)
  const listCmd = (cmd) => (safe(cmd).out || '').split('\n').filter(Boolean);
  const cutUnique = (lines) => Array.from(new Set(lines.map((l) => l.split(':')[0])));
  const directAllList = listCmd(directAllCmd);
  const shimAllList = listCmd(shimAllCmd);
  const directImportFilesOutside = cutUnique(directAllList.filter((l) => !l.includes(allowedDirPattern)));
  const directImportFilesAllowed = cutUnique(directAllList.filter((l) => l.includes(allowedDirPattern)));
  const viaShimFiles = cutUnique(shimAllList);

  // 6) Adoption potential via ts-morph (best-effort)
  const adHocAny = [];
  try {
    const { Project, SyntaxKind } = await import('ts-morph');
    const project = new Project({ tsConfigFilePath: join(ROOT, 'tsconfig.json'), skipAddingFilesFromTsConfig: false });
    // Include only frontend src, exclude generated/tests/out dirs
    project.addSourceFilesAtPaths([
      join(ROOT, '**/*.ts'),
      join(ROOT, '**/*.tsx'),
      '!' + join(ROOT, 'types/generated/**'),
      '!' + join(ROOT, '**/__tests__/**'),
      '!' + join(ROOT, 'e2e/**'),
      '!' + join(ROOT, '.next/**'),
      '!' + join(ROOT, 'node_modules/**'),
      '!' + join(__dirname, '**/contract-audit.mjs'),
    ]);

    const isShimType = (typeText) => typeText.includes("@/features/shared/api/types") || /components\['schemas'\]\['/.test(typeText);

    const knownWrappers = new Set(['fetch', 'axios', 'httpJson', 'cleanFetch', 'optionalAuthFetch', 'authFetch']);

    project.getSourceFiles().forEach((sf) => {
      const rel = relative(ROOT, sf.getFilePath());
      if (rel.includes('types/generated/') || rel.includes('__tests__/') || rel.includes('/e2e/')) return;
      if (rel.startsWith('features/shared/api/')) return; // allowed layer
      sf.forEachDescendant((node) => {
        // Detect calls
        if (node.getKind() === SyntaxKind.CallExpression) {
          const call = node;
          const exprText = call.getExpression().getText();
          const name = exprText.split('.').slice(-1)[0];
          if (!knownWrappers.has(name)) return;

          // Attempt to get generic argument
          const typeArgs = call.getTypeArguments();
          const hasGeneric = typeArgs.length > 0;
          const typeArgText = hasGeneric ? typeArgs[0].getText() : '';

          // Classify
          let typingKind = 'untyped';
          if (hasGeneric) {
            typingKind = isShimType(typeArgText) ? 'viaShim' : (typeArgText.includes("@/types/generated/api") ? 'forbidden' : 'local-interface');
          } else {
            // Look for any-casts on res.json or variable declarations as any/unknown
            const anyCast = node.getText().includes(' as any') || node.getText().includes('<any>');
            typingKind = anyCast ? 'any' : 'untyped';
          }

          if (typingKind === 'viaShim') return; // not a target

          // Guess method and path
          let httpMethod = 'GET';
          if (exprText.includes('.post') || exprText.includes("method: 'POST'")) httpMethod = 'POST';
          if (exprText.includes('.put') || exprText.includes("method: 'PUT'")) httpMethod = 'PUT';
          if (exprText.includes('.delete') || exprText.includes("method: 'DELETE'")) httpMethod = 'DELETE';

          let pathGuess = '';
          const arg0 = call.getArguments()[0];
          if (arg0 && (arg0.getKind() === SyntaxKind.StringLiteral || arg0.getKind() === SyntaxKind.NoSubstitutionTemplateLiteral)) {
            const v = arg0.getText().slice(1, -1);
            if (v.includes('/')) pathGuess = v;
          } else {
            const txt = call.getText();
            const m = txt.match(/['\"](\/[a-zA-Z0-9_\-\/]+)['\"]/);
            if (m) pathGuess = m[1];
          }

          // Suggestion placeholder: if path matches known segments, suggest a Gen.* stub
          let suggestShimType = '';
          if (pathGuess.includes('/bookings')) suggestShimType = 'Gen.BookingResponse';
          else if (pathGuess.includes('/instructors')) suggestShimType = 'Gen.InstructorProfileResponse';
          else if (pathGuess.includes('/services/catalog')) suggestShimType = 'Gen.CatalogServiceResponse';
          else if (pathGuess.includes('/services/categories')) suggestShimType = 'Gen.CategoryResponse';

          // Confidence heuristic
          let confidence = 0.4;
          if (pathGuess && suggestShimType) confidence += 0.4;
          if (['GET','POST','PUT','DELETE'].includes(httpMethod)) confidence += 0.2;
          if (confidence > 1) confidence = 1;

          adHocAny.push({
            file: rel,
            function: '',
            httpMethod,
            pathGuess,
            typingKind: hasGeneric ? typingKind : (typingKind === 'any' ? 'any' : 'untyped'),
            suggestShimType,
            confidence: Number(confidence.toFixed(2)),
            notes: hasGeneric ? `Generic: ${typeArgText}` : 'No generic; result inferred',
          });
        }
      });
    });
  } catch {
    // ts-morph may not be installed; skip with note
  }

  const adoptionPotential = adHocAny
    .filter(i => i.typingKind !== 'forbidden')
    .sort((a, b) => b.confidence - a.confidence)
    .slice(0, 100);

  const adHocAnyCallSites = adHocAny.filter(i => i.typingKind === 'untyped' || i.typingKind === 'any' || i.typingKind === 'local-interface').length;

  const drift = !(diffRes.ok && diffRes.out.trim().length === 0);
  const json = {
    drift,
    directImports: {
      outsideAllowed: directOutside,
      allowedLayer: directAllowed,
    },
    viaShimCount,
    details: {
      viaShimFiles,
      directImportFilesOutside,
      directImportFilesAllowed,
    },
  };

  // Emit legacy JSON and MD
  writeArtifacts(json, report);

  // Emit new adoption artifacts
  const adoptionJson = {
    viaShimCount,
    directImportsOutsideAllowed: directOutside,
    adHocAnyCallSites,
    adoptionPotential,
  };
  writeFileSync(ADOPTION_JSON, JSON.stringify(adoptionJson, null, 2));

  let md = `# Contract Adoption Potential\nGenerated: ${new Date().toISOString()}\n\n`;
  md += `- viaShimCount: ${viaShimCount}\n`;
  md += `- directImportsOutsideAllowed: ${directOutside}\n`;
  md += `- adHocAnyCallSites: ${adHocAnyCallSites}\n`;
  md += `\n## Top Targets (up to 10)\n`;
  adoptionPotential.slice(0, 10).forEach((t, i) => {
    md += `${i + 1}. ${t.file} — ${t.httpMethod} ${t.pathGuess} [${t.typingKind}]${t.suggestShimType ? ` → ${t.suggestShimType}` : ''} (conf: ${t.confidence})\n`;
  });
  writeFileSync(ADOPTION_MD, md);

  if (!isCi) {
    console.log(`Wrote ${relative(ROOT, ADOPTION_JSON)} and ${relative(ROOT, ADOPTION_MD)}`);
  }

  // Exit 0 to keep this audit non-blocking
  process.exit(0);
}

main();
