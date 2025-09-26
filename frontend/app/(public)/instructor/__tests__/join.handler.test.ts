import type { InviteValidateResult } from '@/app/(public)/instructor/inviteTypes';
import { validateInviteCode } from '@/app/(public)/instructor/join/validateInvite';
import { httpGet } from '@/lib/http';

jest.mock('@/lib/http', () => ({
  httpGet: jest.fn(),
}));

describe('validateInviteCode', () => {
  afterEach(() => {
    jest.clearAllMocks();
  });

  it('awaits the validation request before resolving', async () => {
    const httpGetMock = httpGet as jest.MockedFunction<typeof httpGet>;
    let resolver!: (value: InviteValidateResult) => void;
    const pending = new Promise<InviteValidateResult>((resolve) => {
      resolver = resolve;
    });
    httpGetMock.mockReturnValue(pending);

    let completed = false;
    const resultPromise = validateInviteCode('abc123', null).then((result) => {
      completed = true;
      return result;
    });

    await Promise.resolve();
    expect(completed).toBe(false);

    resolver({ valid: true });

    const result = await resultPromise;
    expect(completed).toBe(true);
    expect(result.trimmed).toBe('ABC123');
    expect(result.data.valid).toBe(true);
    expect(httpGetMock).toHaveBeenCalledWith('/api/beta/invites/validate', {
      query: { invite_code: 'ABC123', email: undefined },
    });
  });
});
