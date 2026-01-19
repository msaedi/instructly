import { renderHook } from '@testing-library/react';
import { useBetaAccess } from '../useBetaAccess';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { useBeta } from '@/contexts/BetaContext';

jest.mock('@/features/shared/hooks/useAuth', () => ({
  useAuth: jest.fn(),
}));

jest.mock('@/contexts/BetaContext', () => ({
  useBeta: jest.fn(),
}));

const useAuthMock = useAuth as jest.Mock;
const useBetaMock = useBeta as jest.Mock;

describe('useBetaAccess', () => {
  beforeEach(() => {
    useAuthMock.mockReset();
    useBetaMock.mockReset();
  });

  it('returns user beta access info when available', () => {
    useAuthMock.mockReturnValue({
      user: {
        beta_access: true,
        beta_role: 'instructor',
        beta_phase: 'alpha',
        beta_invited_by: 'CODE123',
      },
    });
    useBetaMock.mockReturnValue({ config: { phase: 'alpha' } });

    const { result } = renderHook(() => useBetaAccess());

    expect(result.current).toEqual({
      sitePhase: 'alpha',
      hasUserBetaAccess: true,
      userBetaRole: 'instructor',
      userBetaPhase: 'alpha',
      invitedByCode: 'CODE123',
    });
  });

  it('returns defaults when user has no beta fields', () => {
    useAuthMock.mockReturnValue({ user: null });
    useBetaMock.mockReturnValue({ config: { phase: 'open' } });

    const { result } = renderHook(() => useBetaAccess());

    expect(result.current.hasUserBetaAccess).toBe(false);
    expect(result.current.userBetaRole).toBeUndefined();
    expect(result.current.userBetaPhase).toBeUndefined();
    expect(result.current.invitedByCode).toBeNull();
  });

  it('ignores non-string beta fields', () => {
    useAuthMock.mockReturnValue({
      user: {
        beta_access: true,
        beta_role: 123,
        beta_phase: null,
        beta_invited_by: 456,
      },
    });
    useBetaMock.mockReturnValue({ config: { phase: 'alpha' } });

    const { result } = renderHook(() => useBetaAccess());

    expect(result.current.userBetaRole).toBeUndefined();
    expect(result.current.userBetaPhase).toBeUndefined();
    expect(result.current.invitedByCode).toBeNull();
  });

  it('uses the site phase from beta context', () => {
    useAuthMock.mockReturnValue({ user: null });
    useBetaMock.mockReturnValue({ config: { phase: 'instructor_only' } });

    const { result } = renderHook(() => useBetaAccess());

    expect(result.current.sitePhase).toBe('instructor_only');
  });

  it('handles beta_access false explicitly', () => {
    useAuthMock.mockReturnValue({
      user: {
        beta_access: false,
        beta_role: 'student',
      },
    });
    useBetaMock.mockReturnValue({ config: { phase: 'alpha' } });

    const { result } = renderHook(() => useBetaAccess());

    expect(result.current.hasUserBetaAccess).toBe(false);
    expect(result.current.userBetaRole).toBe('student');
  });
});
