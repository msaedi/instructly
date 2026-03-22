import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SignUpPage from '@/app/(shared)/signup/page';
import { readPendingSignup } from '@/features/shared/auth/pendingSignup';
import { RoleName } from '@/types/enums';

const mockPush = jest.fn();
const mockHttpPost = jest.fn();

let searchParamsState: Record<string, string | null> = {};

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
  useSearchParams: () => ({
    get: (key: string) => searchParamsState[key] ?? null,
  }),
}));

jest.mock('@/lib/api', () => ({
  API_ENDPOINTS: {
    SEND_EMAIL_VERIFICATION: '/api/v1/auth/send-email-verification',
  },
  checkIsNYCZip: jest.fn(async () => ({ is_nyc: true })),
}));

jest.mock('@/lib/http', () => ({
  ApiError: class ApiError extends Error {
    status: number;

    constructor(message: string, status: number) {
      super(message);
      this.status = status;
    }
  },
  httpPost: (...args: unknown[]) => mockHttpPost(...args),
}));

jest.mock('@/lib/beta-config', () => ({
  useBetaConfig: () => ({ site: 'main', phase: 'public' }),
}));

describe('SignUpPage', () => {
  beforeEach(() => {
    mockPush.mockReset();
    mockHttpPost.mockReset();
    searchParamsState = {};
    sessionStorage.clear();
  });

  it('sends an email verification code and redirects instead of registering immediately', async () => {
    const user = userEvent.setup();
    mockHttpPost.mockResolvedValue({ message: 'Verification code sent' });

    render(<SignUpPage />);

    await user.type(screen.getByLabelText(/First Name/i), 'Alex');
    await user.type(screen.getByLabelText(/Last Name/i), 'Morgan');
    await user.type(screen.getByLabelText(/^Email$/i), 'alex@example.com');
    await user.type(screen.getByLabelText(/Phone Number/i), '2125550101');
    await user.type(screen.getByLabelText(/Zip Code/i), '10001');
    await user.type(screen.getByLabelText(/^Password$/i), 'Secret123!');
    await user.type(screen.getByLabelText(/Confirm Password/i), 'Secret123!');

    await user.click(screen.getByRole('button', { name: /Sign up as Student/i }));

    await waitFor(() => {
      expect(mockHttpPost).toHaveBeenCalledWith('/api/v1/auth/send-email-verification', {
        email: 'alex@example.com',
      });
    });

    expect(mockHttpPost).toHaveBeenCalledTimes(1);
    expect(readPendingSignup()).toMatchObject({
      email: 'alex@example.com',
      role: RoleName.STUDENT,
      firstName: 'Alex',
      lastName: 'Morgan',
    });
    expect(mockPush).toHaveBeenCalledWith('/verify-email?redirect=%2F&email=alex%40example.com');
  });
});
