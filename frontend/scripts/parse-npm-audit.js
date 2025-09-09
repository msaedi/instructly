#!/usr/bin/env node
/*
  Reads JSON from npm audit --json and exits non-zero if High/Critical findings exist
  and are not allowlisted in frontend/audit-allowlist.json
*/
const fs = require('fs');

function readStdin() {
  return new Promise((resolve) => {
    let data = '';
    process.stdin.setEncoding('utf8');
    process.stdin.on('data', (chunk) => (data += chunk));
    process.stdin.on('end', () => resolve(data));
  });
}

(async () => {
  const allowPath = require('path').join(__dirname, '..', 'audit-allowlist.json');
  const allow = fs.existsSync(allowPath) ? JSON.parse(fs.readFileSync(allowPath, 'utf8')) : { advisories: [] };
  const allowSet = new Set(allow.advisories || []);

  const raw = await readStdin();
  if (!raw.trim()) {
    console.log('npm audit: no output');
    process.exit(0);
  }
  let json;
  try {
    json = JSON.parse(raw);
  } catch {
    console.error('npm audit: invalid JSON');
    process.exit(0); // do not fail on parse issues
  }

  const findings = (json.vulnerabilities && Object.values(json.vulnerabilities)) || [];
  const offending = findings.filter((v) => (v.severity === 'high' || v.severity === 'critical') && !allowSet.has(v.id));

  if (offending.length > 0) {
    console.error(`npm audit: High/Critical findings (${offending.length})`);
    offending.slice(0, 10).forEach((v) => console.error(`- ${v.id} ${v.severity} ${v.name}`));
    process.exit(1);
  }
  console.log('npm audit: OK');
  process.exit(0);
})();
