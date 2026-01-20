import { httpDelete, httpGet, httpJson, httpPost, httpPut } from '../http';
import { validateWithZod } from '@/features/shared/api/validation';
import { ApiProblemError, fetchJson } from '@/lib/api/fetch';

jest.mock('@/features/shared/api/validation', () => ({
  validateWithZod: jest.fn(),
}));

jest.mock('@/lib/api/fetch', () => {
  class ApiProblemError extends Error {}
  return {
    fetchJson: jest.fn(),
    ApiProblemError,
  };
});

const fetchJsonMock = fetchJson as jest.Mock;
const validateWithZodMock = validateWithZod as jest.Mock;

describe('httpJson', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('passes context options and validates when schema loader is provided', async () => {
    fetchJsonMock.mockResolvedValue({ ok: true });
    validateWithZodMock.mockReturnValue({ ok: 'validated' });
    const schemaLoader = jest.fn();

    const result = await httpJson(
      '/api/test',
      { headers: { 'X-Test': '1' } },
      schemaLoader,
      {
        endpoint: '/api/test',
        note: 'note',
        dedupeKey: 'dedupe',
        retries: 2,
        financial: true,
      },
    );

    expect(fetchJsonMock).toHaveBeenCalledWith(
      '/api/test',
      expect.objectContaining({
        headers: { 'X-Test': '1' },
        dedupeKey: 'dedupe',
        retries: 2,
        financial: true,
      }),
    );
    expect(validateWithZodMock).toHaveBeenCalledWith(schemaLoader, { ok: true }, {
      endpoint: '/api/test',
      note: 'note',
    });
    expect(result).toEqual({ ok: 'validated' });
  });

  it('returns raw data when schema loader is missing', async () => {
    fetchJsonMock.mockResolvedValue({ ok: true });

    const result = await httpJson('/api/raw');

    expect(result).toEqual({ ok: true });
    expect(validateWithZodMock).not.toHaveBeenCalled();
  });

  it('falls back to input when ctx endpoint is empty', async () => {
    fetchJsonMock.mockResolvedValue({ ok: true });
    validateWithZodMock.mockReturnValue({ ok: 'validated' });
    const schemaLoader = jest.fn();

    await httpJson('/api/fallback', undefined, schemaLoader, { endpoint: '', note: 'fallback' });

    expect(validateWithZodMock).toHaveBeenCalledWith(schemaLoader, { ok: true }, {
      endpoint: '/api/fallback',
      note: 'fallback',
    });
  });

  it('rethrows ApiProblemError', async () => {
    const error = new ApiProblemError({ title: 'problem' } as unknown as never, {} as Response);
    fetchJsonMock.mockRejectedValue(error);

    await expect(httpJson('/api/error')).rejects.toBe(error);
  });

  it('rethrows non-ApiProblemError', async () => {
    const error = new Error('boom');
    fetchJsonMock.mockRejectedValue(error);

    await expect(httpJson('/api/error')).rejects.toBe(error);
  });
});

describe('http verbs', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    fetchJsonMock.mockResolvedValue({ ok: true });
  });

  it('uses GET and DELETE methods', async () => {
    await httpGet('/api/get');
    await httpDelete('/api/delete');

    expect(fetchJsonMock.mock.calls[0]?.[1]?.method).toBe('GET');
    expect(fetchJsonMock.mock.calls[1]?.[1]?.method).toBe('DELETE');
  });

  it('serializes bodies and sets headers for POST/PUT', async () => {
    await httpPost('/api/post', { foo: 'bar' }, { headers: { 'X-Trace': '1' } });
    await httpPost('/api/post-empty');
    await httpPut('/api/put', { foo: 'baz' });
    await httpPut('/api/put-empty');

    const postOptions = fetchJsonMock.mock.calls[0]?.[1] as RequestInit;
    const postEmptyOptions = fetchJsonMock.mock.calls[1]?.[1] as RequestInit;
    const putOptions = fetchJsonMock.mock.calls[2]?.[1] as RequestInit;
    const putEmptyOptions = fetchJsonMock.mock.calls[3]?.[1] as RequestInit;

    expect(postOptions.method).toBe('POST');
    expect(postOptions.headers).toEqual(
      expect.objectContaining({
        'Content-Type': 'application/json',
        'X-Trace': '1',
      }),
    );
    expect(postOptions.body).toBe(JSON.stringify({ foo: 'bar' }));
    expect(postEmptyOptions.body).toBeNull();
    expect(putOptions.method).toBe('PUT');
    expect(putOptions.body).toBe(JSON.stringify({ foo: 'baz' }));
    expect(putEmptyOptions.body).toBeNull();
  });
});
