#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';

const pkg = JSON.parse(fs.readFileSync(path.join('frontend', 'package.json'), 'utf8'));
const allowPath = path.join('scripts', 'pin-allowlist.json');
const allow = fs.existsSync(allowPath) ? JSON.parse(fs.readFileSync(allowPath, 'utf8')) : { packages: {} };

const targets = [
  'openapi-typescript',
  'tailwindcss',
  'eslint-config-next',
];

const offenders = [];
for (const section of ['dependencies', 'devDependencies']) {
  const deps = pkg[section] || {};
  for (const name of targets) {
    if (name in deps) {
      const v = deps[name];
      if ((v.startsWith('^') || v.startsWith('~')) && !allow.packages[name]) {
        offenders.push({ name, version: v });
      }
    }
  }
}

if (offenders.length > 0) {
  console.error('Pin check failed for the following packages:');
  for (const o of offenders) console.error(`- ${o.name}: ${o.version}`);
  process.exit(1);
}
console.log('Pin check: OK');
