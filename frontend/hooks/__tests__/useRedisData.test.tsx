import { act, renderHook, waitFor } from '@testing-library/react';

import { useRedisData } from '../useRedisData';
import { redisApi } from '@/lib/redisApi';
import { logger } from '@/lib/logger';

jest.mock('@/lib/redisApi', () => ({
  redisApi: {
    getHealth: jest.fn(),
    testConnection: jest.fn(),
    getStats: jest.fn(),
    getCeleryQueues: jest.fn(),
    getConnectionAudit: jest.fn(),
  },
}));

jest.mock('@/lib/logger', () => ({
  logger: {
    error: jest.fn(),
  },
}));

const getHealthMock = redisApi.getHealth as jest.Mock;
const testConnectionMock = redisApi.testConnection as jest.Mock;
const getStatsMock = redisApi.getStats as jest.Mock;
const getCeleryQueuesMock = redisApi.getCeleryQueues as jest.Mock;
const getConnectionAuditMock = redisApi.getConnectionAudit as jest.Mock;
const loggerErrorMock = logger.error as jest.Mock;

describe('useRedisData', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('fetches health and test connection when no token is provided', async () => {
    getHealthMock.mockResolvedValue({ status: 'ok' });
    testConnectionMock.mockResolvedValue({ status: undefined, ping: 0, message: undefined });

    const { result } = renderHook(() => useRedisData(null));

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(getHealthMock).toHaveBeenCalledTimes(1);
    expect(testConnectionMock).toHaveBeenCalledTimes(1);
    expect(getStatsMock).not.toHaveBeenCalled();
    expect(getCeleryQueuesMock).not.toHaveBeenCalled();
    expect(getConnectionAuditMock).not.toHaveBeenCalled();
    expect(result.current.data.stats).toBeNull();
    expect(result.current.data.testConnection).toEqual({
      status: 'unknown',
      ping: false,
      message: '',
    });
  });

  it('fetches authenticated data when token is provided', async () => {
    getHealthMock.mockResolvedValue({ status: 'ok' });
    testConnectionMock.mockResolvedValue({ status: 'ok', ping: true, message: 'pong' });
    getStatsMock.mockResolvedValue({ server: { redis_version: '7.0' } });
    getCeleryQueuesMock.mockResolvedValue({ queues: { default: 2 }, total_pending: 2 });
    getConnectionAuditMock.mockResolvedValue({ service_connections: { api_service: { host: 'localhost' } } });

    const { result } = renderHook(() => useRedisData('token-123'));

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(getStatsMock).toHaveBeenCalledWith('token-123');
    expect(getCeleryQueuesMock).toHaveBeenCalledWith('token-123');
    expect(getConnectionAuditMock).toHaveBeenCalledWith('token-123');
    expect(result.current.data.stats).toEqual({ server: { redis_version: '7.0' } });
    expect(result.current.data.queues).toEqual({ queues: { default: 2 }, total_pending: 2 });
    expect(result.current.data.connectionAudit).toEqual({
      service_connections: { api_service: { host: 'localhost' } },
    });
  });

  it('normalizes test connection ping values to boolean', async () => {
    getHealthMock.mockResolvedValue({ status: 'ok' });
    testConnectionMock.mockResolvedValue({ status: 'ok', ping: 1, message: 'pong' });

    const { result } = renderHook(() => useRedisData(null));

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.data.testConnection).toEqual({
      status: 'ok',
      ping: true,
      message: 'pong',
    });
  });

  it('reports errors when fetching fails', async () => {
    getHealthMock.mockRejectedValueOnce(new Error('Redis down'));
    testConnectionMock.mockResolvedValue({ status: 'ok', ping: true, message: 'pong' });

    const { result } = renderHook(() => useRedisData('token-123'));

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.error).toBe('Redis down');
    expect(loggerErrorMock).toHaveBeenCalledWith(
      'Failed to fetch Redis data',
      expect.any(Error)
    );
  });

  it('refetch triggers another request cycle', async () => {
    getHealthMock.mockResolvedValue({ status: 'ok' });
    testConnectionMock.mockResolvedValue({ status: 'ok', ping: true, message: 'pong' });
    getStatsMock.mockResolvedValue({ server: { redis_version: '7.0' } });
    getCeleryQueuesMock.mockResolvedValue({ queues: { default: 2 }, total_pending: 2 });
    getConnectionAuditMock.mockResolvedValue({ service_connections: {} });

    const { result } = renderHook(() => useRedisData('token-123'));

    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.refetch();
    });

    expect(getHealthMock).toHaveBeenCalledTimes(2);
    expect(testConnectionMock).toHaveBeenCalledTimes(2);
  });
});
