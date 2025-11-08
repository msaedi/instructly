// frontend/scripts/contract-check.mjs
import { execSync } from 'node:child_process';
import { mkdirSync, readFileSync, writeFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';

const isCI = !!(process.env.CI || process.env.GITHUB_ACTIONS);

const args = process.argv.slice(2);
const shouldWrite = args.includes('--write') || args.includes('-w');
const shouldMinify = args.includes('--minify');

const SPEC = join(process.cwd(), '..', 'backend', 'openapi', 'openapi.json');
const TARGET = join(process.cwd(), 'types', 'generated', 'api.d.ts');
const SNAPSHOT = join(process.cwd(), '..', 'backend', '.artifacts', 'api.expected.d.ts');

if (!isCI) {
  // Local dev: regenerate the spec first (uses Python & orjson on dev machines)
  execSync('npm run contract:export', { stdio: 'inherit', cwd: process.cwd() });
}

const tmpOut = join(tmpdir(), `oas-${Date.now()}-api.d.ts`);
mkdirSync(join(process.cwd(), '.artifacts'), { recursive: true });
mkdirSync(join(process.cwd(), '..', 'backend', '.artifacts'), { recursive: true });

console.log('[contract-check] Generating TS types with pinned openapi-typescript@7.9.1...');
execSync(
  `npx -y openapi-typescript@7.9.1 "${SPEC}" -o "${tmpOut}" --export-type`,
  { stdio: 'inherit' }
);

const targetCurrent = existsSync(TARGET) ? readFileSync(TARGET, 'utf8') : '';
const actual = readFileSync(tmpOut, 'utf8');
const snapshotCurrent = existsSync(SNAPSHOT) ? readFileSync(SNAPSHOT, 'utf8') : '';

function minifyDts(input) {
  if (!shouldMinify) {
    return input;
  }
  let out = input.replace(/\/\*[\s\S]*?\*\//g, '');
  out = out.replace(/^[ \t]*\/\/.*$/gm, '');
  out = out.replace(/^\s*[\r\n]/gm, '');
  out = out.replace(/[ \t]+/g, ' ');
  out = out.replace(/\n{2,}/g, '\n');
  return out.trim() + '\n';
}

const actualSnapshot = minifyDts(actual);
const snapshotExpected = minifyDts(snapshotCurrent);

const hasTargetDrift = targetCurrent !== actual;
const hasSnapshotDrift = snapshotExpected !== actualSnapshot;

if (shouldWrite) {
  writeFileSync(TARGET, actual);
  writeFileSync(SNAPSHOT, actualSnapshot);
  const sizeKB = Math.round(Buffer.byteLength(actualSnapshot, 'utf8') / 1024);
  console.log(
    `[contract-check] Refreshed generated api.d.ts and snapshot (minify=${shouldMinify}).`
  );
  console.log(`📦 api.expected.d.ts size: ${sizeKB} KB`);
  if (!hasTargetDrift && !hasSnapshotDrift) {
    console.log('✅ Contract OK (no drift).');
    process.exit(0);
  }
}

if (hasTargetDrift || hasSnapshotDrift) {
  if (!shouldWrite) {
    writeFileSync(
      join(process.cwd(), '.artifacts', 'api.actual.d.ts'),
      shouldMinify ? actualSnapshot : actual
    );
    writeFileSync(
      join(process.cwd(), '.artifacts', 'api.expected.d.ts'),
      shouldMinify ? snapshotExpected : snapshotCurrent
    );
    if (hasTargetDrift) {
      console.error('❌ Contract drift: frontend/types/generated/api.d.ts is stale.');
    }
    if (hasSnapshotDrift) {
      console.error('❌ Contract drift: backend/.artifacts/api.expected.d.ts differs from generated output.');
    }
    console.error('   See .artifacts/api.expected.d.ts vs .artifacts/api.actual.d.ts');
    process.exit(1);
  } else {
    console.log('ℹ️ Contract files were out of date; snapshots updated.');
  }
} else {
  console.log('✅ Contract OK (no drift).');
}
