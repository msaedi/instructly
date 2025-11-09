/* eslint-disable @typescript-eslint/no-require-imports */
const budgets = require('./lhci.budgets.json');
/* eslint-enable @typescript-eslint/no-require-imports */

const isMain = process.env.GITHUB_REF === 'refs/heads/main';
const parsedPort =
  process.env.LHCI_PORT && Number.parseInt(process.env.LHCI_PORT, 10) > 0
    ? Number.parseInt(process.env.LHCI_PORT, 10)
    : undefined;
const lhciPort = parsedPort || 4010;
const collectPaths = ['/', '/login', '/lhci/instructor', '/instructor/availability'];
const collectUrls = collectPaths.map((path) => `http://localhost:${lhciPort}${path}`);
const startServerCommand = `PORT=${lhciPort} NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 next start -p ${lhciPort}`;
const startServerReadyPattern = 'Ready in .*ms';

module.exports = {
  ci: {
    collect: {
      numberOfRuns: 3,
      startServerCommand,
      startServerReadyPattern,
      url: collectUrls,
      settings: {
        budgets,
        emulatedFormFactor: 'desktop',
        throttlingMethod: 'devtools',
      },
    },
    assert: {
      assertions: {
        'categories:performance': [isMain ? 'error' : 'warn', { minScore: isMain ? 0.9 : 0.85 }],
        'largest-contentful-paint': [isMain ? 'error' : 'warn', { maxNumericValue: 3000 }],
        'total-blocking-time': [isMain ? 'error' : 'warn', { maxNumericValue: 200 }],
        'uses-long-cache-ttl': isMain ? 'warn' : 'off',
      },
    },
    upload: {
      target: 'temporary-public-storage',
    },
  },
};
