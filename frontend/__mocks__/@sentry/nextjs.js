const mockScope = {
  setTag: jest.fn(),
  setContext: jest.fn(),
  setLevel: jest.fn(),
  setUser: jest.fn(),
};

module.exports = {
  init: jest.fn(),
  captureException: jest.fn(),
  captureMessage: jest.fn(),
  setUser: jest.fn(),
  withScope: (callback) => callback(mockScope),
  __mockScope: mockScope,
};
