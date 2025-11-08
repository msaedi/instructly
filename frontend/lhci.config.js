/* eslint-disable @typescript-eslint/no-require-imports */
const budgets = require('./lhci.budgets.json');
/* eslint-enable @typescript-eslint/no-require-imports */

const isMain = process.env.GITHUB_REF === 'refs/heads/main';

module.exports = {
  ci: {
    collect: {
      numberOfRuns: 2,
      startServerCommand: null,
      url: [
        'http://localhost:3100/',
        'http://localhost:3100/login',
        'http://localhost:3100/lhci/instructor',
        'http://localhost:3100/instructor/availability',
      ],
      settings: {
        budgets,
        preset: 'desktop',
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
