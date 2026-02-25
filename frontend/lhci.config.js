const budgets = require('./lhci.budgets.json');

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
const strictLevel = isMain ? 'error' : 'warn';

const basePatterns = {
  home: '^https?://[^/]+/?$',
  login: '^https?://[^/]+/login/?$',
  instructor: '^https?://[^/]+/lhci/instructor/?$',
  availability: '^https?://[^/]+/instructor/availability/?$',
};

const strictAssertions = {
  'categories:performance': [strictLevel, { minScore: isMain ? 0.9 : 0.85 }],
  'largest-contentful-paint': [strictLevel, { maxNumericValue: 3000 }],
  'total-blocking-time': [strictLevel, { maxNumericValue: 250, aggregationMethod: 'optimistic' }],
  'uses-long-cache-ttl': 'off',
  'categories:accessibility': ['error', { minScore: 0.9 }],
};

const availabilityAssertions = {
  'categories:performance': ['warn', { minScore: 0.85 }],
  'largest-contentful-paint': ['warn', { maxNumericValue: 4500 }],
  'total-blocking-time': [strictLevel, { maxNumericValue: 250, aggregationMethod: 'optimistic' }],
  'uses-long-cache-ttl': 'off',
  'categories:accessibility': ['error', { minScore: 0.9 }],
};

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
      assertMatrix: [
        {
          matchingUrlPattern: basePatterns.home,
          assertions: strictAssertions,
        },
        {
          matchingUrlPattern: basePatterns.login,
          assertions: strictAssertions,
        },
        {
          matchingUrlPattern: basePatterns.instructor,
          assertions: strictAssertions,
        },
        {
          matchingUrlPattern: basePatterns.availability,
          assertions: availabilityAssertions,
        },
      ],
    },
    upload: {
      target: 'temporary-public-storage',
    },
  },
};
