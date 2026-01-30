describe('Sentry config files', () => {
  it('load without crashing', () => {
    expect(() => {
      jest.isolateModules(() => {
        require('../sentry.client.config');
        require('../sentry.server.config');
        require('../sentry.edge.config');
      });
    }).not.toThrow();
  });
});
