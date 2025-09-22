// frontend/scripts/contract-check.mjs
import { execSync } from 'node:child_process';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';

const isCI = !!(process.env.CI || process.env.GITHUB_ACTIONS);

const args = process.argv.slice(2);
const shouldWrite = args.includes('--write') || args.includes('-w');

const SPEC = join(process.cwd(), '..', 'backend', 'openapi', 'openapi.json');
const TARGET = join(process.cwd(), 'types', 'generated', 'api.d.ts');

if (!isCI) {
  // Local dev: regenerate the spec first (uses Python & orjson on dev machines)
  execSync('npm run contract:export', { stdio: 'inherit', cwd: process.cwd() });
}

const tmpOut = join(tmpdir(), `oas-${Date.now()}-api.d.ts`);
mkdirSync(join(process.cwd(), '.artifacts'), { recursive: true });

console.log('[contract-check] Generating TS types with pinned openapi-typescript@7.9.1...');
execSync(
  `npx -y openapi-typescript@7.9.1 "${SPEC}" -o "${tmpOut}" --export-type`,
  { stdio: 'inherit' }
);

const expected = readFileSync(TARGET, 'utf8');
const actual = readFileSync(tmpOut, 'utf8');

if (expected !== actual) {
  if (shouldWrite) {
    writeFileSync(TARGET, actual);
    console.log('[contract-check] Updated committed api.d.ts to match generated output.');
  } else {
    writeFileSync(join(process.cwd(), '.artifacts', 'api.actual.d.ts'), actual);
    writeFileSync(join(process.cwd(), '.artifacts', 'api.expected.d.ts'), expected);
    console.error('❌ Contract drift detected between committed types and generated output.');
    console.error('   See .artifacts/api.expected.d.ts vs .artifacts/api.actual.d.ts');
    process.exit(1);
  }
}

console.log('✅ Contract OK (no drift).');
