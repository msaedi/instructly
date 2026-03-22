import { buildAuthHref, claimReferralCode } from '../referralAuth';
import { fetchAPI } from '@/lib/api';
import { logger } from '@/lib/logger';

jest.mock('@/lib/api', () => ({
  fetchAPI: jest.fn(),
}));

jest.mock('@/lib/logger', () => ({
  logger: {
    warn: jest.fn(),
  },
}));

const fetchAPIMock = fetchAPI as jest.MockedFunction<typeof fetchAPI>;
const loggerWarnMock = logger.warn as jest.MockedFunction<typeof logger.warn>;

describe('buildAuthHref', () => {
  it('returns the base path when called without options', () => {
    expect(buildAuthHref('/login')).toBe('/login');
  });

  it('preserves redirect, role, ref, and registered state', () => {
    expect(
      buildAuthHref('/login', {
        redirect: '/student/checkout',
        role: 'student',
        ref: 'fnvc6kdw',
        registered: true,
      })
    ).toBe('/login?role=student&redirect=%2Fstudent%2Fcheckout&ref=fnvc6kdw&registered=true');
  });

  it('omits empty values', () => {
    expect(buildAuthHref('/signup', { redirect: '/', ref: '', role: null })).toBe('/signup');
  });
});

describe('claimReferralCode', () => {
  beforeEach(() => {
    fetchAPIMock.mockReset();
    loggerWarnMock.mockReset();
  });

  it('returns false without a referral code', async () => {
    await expect(claimReferralCode('')).resolves.toBe(false);
    expect(fetchAPIMock).not.toHaveBeenCalled();
  });

  it('returns false when the referral code is null', async () => {
    await expect(claimReferralCode(null)).resolves.toBe(false);
    expect(fetchAPIMock).not.toHaveBeenCalled();
  });

  it('posts the normalized code to the claim endpoint', async () => {
    fetchAPIMock.mockResolvedValue(
      {
        ok: true,
        json: async () => ({ attributed: true }),
      } as Response
    );

    await expect(claimReferralCode(' fnvc6kdw ')).resolves.toBe(true);
    expect(fetchAPIMock).toHaveBeenCalledWith('/api/v1/referrals/claim', {
      method: 'POST',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ code: 'FNVC6KDW' }),
    });
  });

  it('returns false when the claim request fails', async () => {
    fetchAPIMock.mockResolvedValue(
      {
        ok: false,
        json: async () => ({ attributed: false }),
      } as Response
    );

    await expect(claimReferralCode('FNVC6KDW')).resolves.toBe(false);
  });

  it('returns false and logs when the claim request throws', async () => {
    fetchAPIMock.mockRejectedValue(new Error('network down'));

    await expect(claimReferralCode('fnvc6kdw')).resolves.toBe(false);

    expect(loggerWarnMock).toHaveBeenCalledWith('Unable to claim referral code after signup', {
      code: 'FNVC6KDW',
      error: 'network down',
    });
  });

  it('stringifies non-Error throw values when logging claim failures', async () => {
    fetchAPIMock.mockRejectedValue('offline');

    await expect(claimReferralCode('fnvc6kdw')).resolves.toBe(false);

    expect(loggerWarnMock).toHaveBeenCalledWith('Unable to claim referral code after signup', {
      code: 'FNVC6KDW',
      error: 'offline',
    });
  });
});
