/* eslint-env node */
module.exports = {
  options: {
    doNotFollow: {
      path: [
        'node_modules',
        'types/generated',
      ],
    },
    exclude: {
      path: [
        '^e2e/',
        '^.artifacts/',
        '__tests__',
        '\\.(test|spec)\\.tsx?$',
        '^type-tests/',
        '^playwright\\.config\\.ts$',
      ],
    },
    tsConfig: {
      fileName: 'tsconfig.json',
    },
    enhancedResolveOptions: {
      extensions: ['.ts', '.tsx', '.js', '.jsx', '.json']
    },
    baseDir: '.',
    reporterOptions: {
      dot: { theme: { graph: { rankdir: 'LR' } } },
    },
  },
  forbidden: [
    { name: 'no-cycles', severity: 'error', from: {}, to: { circular: true } },
    {
      name: 'no-generated-in-app-components-features',
      severity: 'error',
      from: { path: '^(app|components|features)/' },
      to: { path: '^types/generated/' },
    },
    {
      name: 'only-shim-imports-generated',
      severity: 'error',
      from: { path: '^(?!(features/shared/api/types)).*$' },
      to: { path: '^types/generated/' },
    },
    {
      name: 'feature-isolation',
      severity: 'error',
      from: { path: '^features/([^/]+)/' },
      // Allow same top-level feature (student → student), forbid other features (except shared)
      to: { path: '^features/(?!shared/)[^/]+/', pathNot: '^features/$1/' },
    },
    {
      name: 'components-no-features-except-shared',
      severity: 'error',
      from: { path: '^components/' },
      to: { path: '^features/(?!shared/)', pathNot: '^features/.*/public/' },
    },
  ],
};
