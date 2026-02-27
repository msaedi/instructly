const nextJest = require('next/jest');

const createJestConfig = nextJest({
  // Provide the path to your Next.js app to load next.config.js and .env files
  dir: './',
});

// Lock timezone to UTC to prevent date-dependent test flakes across local machines
process.env.TZ = 'UTC';

// Add any custom config to be passed to Jest
const customJestConfig = {
  setupFilesAfterEnv: ['<rootDir>/jest.setup.js'],
  testEnvironment: 'jsdom',
  moduleNameMapper: {
    // Handle module aliases
    '^@/(.*)$': '<rootDir>/$1',
  },
  testPathIgnorePatterns: ['<rootDir>/.next/', '<rootDir>/node_modules/', '<rootDir>/e2e/'],
  coveragePathIgnorePatterns: [
    '/node_modules/',
    '<rootDir>/features/student/payment/index\\.ts',
    '<rootDir>/components/instructor/messages/hooks/index\\.ts',
    '<rootDir>/components/instructor/messages/components/index\\.ts',
    '<rootDir>/features/student/booking/public\\.ts',
    '<rootDir>/features/shared/api/schemas\\.zod\\.ts',
    '<rootDir>/features/student/booking/index\\.ts',
    '<rootDir>/features/shared/booking/ui/index\\.ts',
  ],
  collectCoverageFrom: [
    'features/**/*.{js,jsx,ts,tsx}',
    'hooks/**/*.{js,jsx,ts,tsx}',
    'components/**/*.{js,jsx,ts,tsx}',
    '!**/*.d.ts',
    '!**/node_modules/**',
  ],
  // Coverage threshold to prevent regression
  coverageThreshold: {
    global: {
      statements: 98,
      branches: 92,
      functions: 100,
      lines: 99,
    },
  },
};

// createJestConfig is exported this way to ensure that next/jest can load the Next.js config which is async
module.exports = createJestConfig(customJestConfig);
