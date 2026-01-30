const mockScope = {
  setTag: jest.fn(),
  setContext: jest.fn(),
  setLevel: jest.fn(),
  setUser: jest.fn(),
};

module.exports = {
  init: jest.fn(),
  logger: {
    info: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
  },
  addBreadcrumb: jest.fn(),
  captureException: jest.fn(),
  captureMessage: jest.fn(),
  replayIntegration: jest.fn(() => ({ name: 'Replay' })),
  setUser: jest.fn(),
  withScope: (callback) => callback(mockScope),
  __mockScope: mockScope,
};
