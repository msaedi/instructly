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
    // 1) Forbid circular dependencies anywhere
    { name: 'no-cycles', severity: 'error', from: {}, to: { circular: true } },

    // 2) Generated types boundary - only the API shim may import generated types
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

    // 3) Feature isolation - features/* cannot import other features/* (except features/shared/**)
    {
      name: 'feature-isolation',
      severity: 'error',
      from: { path: '^features/([^/]+)/' },
      to: { path: '^features/(?!shared/)[^/]+/' },
    },

    // 4) Components guard - components/** must not import features/**
    {
      name: 'components-no-features',
      severity: 'error',
      from: { path: '^components/' },
      to: { path: '^features/' },
    },
  ],
};
