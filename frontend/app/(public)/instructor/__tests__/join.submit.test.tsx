import '@testing-library/jest-dom';
import { render, fireEvent, screen, act } from '@testing-library/react';
import InstructorJoinPage from '@/app/(public)/instructor/join/page';
import { validateInviteCode } from '@/app/(public)/instructor/join/validateInvite';

const replaceMock = jest.fn();

jest.mock('next/navigation', () => ({
  useSearchParams: jest.fn(() => new URLSearchParams()),
  useRouter: () => ({ replace: replaceMock }),
}));

jest.mock('@/app/(public)/instructor/join/validateInvite', () => ({
  validateInviteCode: jest.fn(),
}));

describe('InstructorJoinPage submit guard', () => {
  beforeAll(() => {
    jest.spyOn(Storage.prototype, 'setItem').mockImplementation(() => undefined);
    jest.spyOn(Storage.prototype, 'getItem').mockImplementation(() => null);
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  afterAll(() => {
    jest.restoreAllMocks();
  });

  it('does not auto-validate on mount', () => {
    render(<InstructorJoinPage />);
    expect(validateInviteCode).not.toHaveBeenCalled();
  });

  it('calls validateInviteCode only once even if submit is triggered twice before resolve', async () => {
    let resolvePromise: ((value: { data: { valid: boolean; reason?: string | null; email?: string | null }; trimmed: string }) => void) | null = null;
    (validateInviteCode as jest.Mock).mockImplementation(
      () =>
        new Promise((resolve) => {
          resolvePromise = resolve;
        }),
    );

    render(<InstructorJoinPage />);

    const input = screen.getByLabelText(/founding instructor code/i);
    fireEvent.change(input, { target: { value: 'abc12345' } });

    const form = input.closest('form');
    expect(form).not.toBeNull();

    // Trigger submit twice before the promise resolves
    fireEvent.submit(form!);
    fireEvent.submit(form!);

    expect(validateInviteCode).toHaveBeenCalledTimes(1);

    await act(async () => {
      resolvePromise?.({ data: { valid: false, reason: 'nope', email: null }, trimmed: 'ABC12345' });
    });

    expect(replaceMock).not.toHaveBeenCalled();
  });

  it('navigates after successful validation', async () => {
    (validateInviteCode as jest.Mock).mockResolvedValue({
      data: { valid: true, email: 'user@example.com' },
      trimmed: 'CODE1234',
    });

    render(<InstructorJoinPage />);

    const input = screen.getByLabelText(/founding instructor code/i);
    fireEvent.change(input, { target: { value: 'code1234' } });

    const form = input.closest('form');
    await act(async () => {
      fireEvent.submit(form!);
    });

    expect(validateInviteCode).toHaveBeenCalledTimes(1);
    expect(replaceMock).toHaveBeenCalledTimes(1);
    expect(replaceMock.mock.calls[0][0]).toContain('/instructor/welcome');
  });
});
