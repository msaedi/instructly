import { logger } from '@/lib/logger';

jest.mock('next-axiom', () => ({
  log: {
    debug: jest.fn(),
    info: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
  },
}));

describe('logger', () => {
  beforeEach(() => {
    jest.spyOn(console, 'log').mockImplementation(() => {});
    jest.spyOn(console, 'info').mockImplementation(() => {});
    jest.spyOn(console, 'warn').mockImplementation(() => {});
    jest.spyOn(console, 'error').mockImplementation(() => {});
    jest.spyOn(console, 'debug').mockImplementation(() => {});
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('exposes debug, info, warn, error methods', () => {
    expect(typeof logger.debug).toBe('function');
    expect(typeof logger.info).toBe('function');
    expect(typeof logger.warn).toBe('function');
    expect(typeof logger.error).toBe('function');
  });

  it('calls underlying log methods with message and fields', () => {
    const { log } = require('next-axiom');
    const originalStatus = logger.getStatus();

    logger.setEnabled(true);
    logger.setLevel('debug');
    logger.info('test message', { key: 'value' });

    expect(log.info).toHaveBeenCalledWith('test message', { key: 'value' });

    logger.setEnabled(originalStatus.enabled);
    logger.setLevel(originalStatus.level);
  });
});
