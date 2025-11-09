/* eslint-disable @typescript-eslint/no-require-imports */
const budgets = require('./lhci.budgets.json');
/* eslint-enable @typescript-eslint/no-require-imports */

const isMain = process.env.GITHUB_REF === 'refs/heads/main';
const lhciPort =
  (process.env.LHCI_PORT && Number.parseInt(process.env.LHCI_PORT, 10)) || 4010;
const collectUrls = [
  `http://localhost:${lhciPort}/`,
  `http://localhost:${lhciPort}/login`,
  `http://localhost:${lhciPort}/lhci/instructor`,
  `http://localhost:${lhciPort}/instructor/availability`,
];

module.exports = {
  ci: {
    collect: {
      numberOfRuns: 3,
      startServerCommand: `PORT=${lhciPort} NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 next start -p ${lhciPort}`,
      startServerReadyPattern: 'started server on .*:(\\d+)',
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
