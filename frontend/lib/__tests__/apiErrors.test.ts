import { extractApiErrorMessage, extractUnknownErrorMessage } from '@/lib/apiErrors';

describe('apiErrors', () => {
  it('extracts string detail messages', () => {
    expect(extractUnknownErrorMessage({ detail: '  Something went wrong  ' })).toBe(
      'Something went wrong'
    );
  });

  it('extracts structured detail.message values', () => {
    expect(
      extractUnknownErrorMessage({
        detail: {
          message: 'Structured failure',
        },
      })
    ).toBe('Structured failure');
  });

  it('extracts top-level message values', () => {
    expect(extractUnknownErrorMessage({ message: 'Top level failure' })).toBe(
      'Top level failure'
    );
  });

  it('unwraps nested data payloads before using outer error messages', () => {
    const wrappedError = {
      message: 'HTTP 409: Conflict',
      data: {
        detail: {
          message: 'Nested conflict detail',
        },
      },
    };

    expect(extractUnknownErrorMessage(wrappedError)).toBe('Nested conflict detail');
  });

  it('returns fallback messages when nothing usable is present', () => {
    expect(extractUnknownErrorMessage({ detail: { code: 'invalid' } })).toBeNull();
    expect(extractApiErrorMessage({ detail: { code: 'invalid' } }, 'Fallback message')).toBe(
      'Fallback message'
    );
  });
});
