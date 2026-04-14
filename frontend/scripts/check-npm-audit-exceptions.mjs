#!/usr/bin/env node

import fs from 'node:fs';

const reportPath = process.argv[2];

if (!reportPath) {
  console.error('Usage: node scripts/check-npm-audit-exceptions.mjs <audit-report.json>');
  process.exit(1);
}

const allowedAdvisories = new Set(['GHSA-q4gf-8mx6-v5v3']);
const blockingSeverities = new Set(['high', 'critical']);

function advisoryId(viaItem) {
  if (!viaItem || typeof viaItem !== 'object') return null;
  if (typeof viaItem.url === 'string') {
    const match = viaItem.url.match(/GHSA-[0-9a-z]{4}-[0-9a-z]{4}-[0-9a-z]{4}$/i);
    if (match) return match[0];
  }
  if (typeof viaItem.source === 'string' && viaItem.source.startsWith('GHSA-')) {
    return viaItem.source;
  }
  return null;
}

const report = JSON.parse(fs.readFileSync(reportPath, 'utf8'));
const vulnerabilities = Object.values(report.vulnerabilities ?? {});

const ignored = [];
const blocked = [];

for (const vulnerability of vulnerabilities) {
  const severity = String(vulnerability.severity ?? '').toLowerCase();
  if (!blockingSeverities.has(severity)) continue;

  const viaItems = Array.isArray(vulnerability.via)
    ? vulnerability.via
    : vulnerability.via
      ? [vulnerability.via]
      : [];
  const advisoryObjects = viaItems.filter((item) => item && typeof item === 'object');
  const advisoryIds = [...new Set(advisoryObjects.map(advisoryId).filter(Boolean))];

  if (
    advisoryObjects.length > 0 &&
    advisoryIds.length > 0 &&
    advisoryIds.every((id) => allowedAdvisories.has(id))
  ) {
    ignored.push({
      name: vulnerability.name,
      severity,
      ids: advisoryIds,
      range: vulnerability.range,
      fixAvailable: vulnerability.fixAvailable,
    });
    continue;
  }

  blocked.push({
    name: vulnerability.name,
    severity,
    ids: advisoryIds,
    range: vulnerability.range,
    fixAvailable: vulnerability.fixAvailable,
  });
}

if (blocked.length > 0) {
  console.error('Blocking npm audit vulnerabilities found:');
  for (const vulnerability of blocked) {
    const ids = vulnerability.ids.length > 0 ? vulnerability.ids.join(', ') : 'unidentified-advisory';
    console.error(
      `- ${vulnerability.name} (${vulnerability.severity}) [${ids}] range=${vulnerability.range ?? 'unknown'}`
    );
  }
  process.exit(1);
}

if (ignored.length > 0) {
  console.log('Ignoring allowlisted npm audit vulnerabilities:');
  for (const vulnerability of ignored) {
    console.log(
      `- ${vulnerability.name} (${vulnerability.severity}) [${vulnerability.ids.join(', ')}] range=${vulnerability.range ?? 'unknown'}`
    );
  }
} else {
  console.log('No blocking npm audit vulnerabilities found.');
}
