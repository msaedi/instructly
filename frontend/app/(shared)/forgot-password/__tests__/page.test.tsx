import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import ForgotPasswordPage from '@/app/(shared)/forgot-password/page';

const mockFetchAPI = jest.fn((_endpoint: string, _options?: RequestInit) =>
  Promise.resolve(jsonResponse(200, {}))
);
const mockToastError = jest.fn();

jest.mock('@/lib/api', () => ({
  fetchAPI: (...args: [string, RequestInit?]) => mockFetchAPI(...args),
}));

jest.mock('@/lib/logger', () => ({
  logger: {
    debug: jest.fn(),
    error: jest.fn(),
    info: jest.fn(),
    time: jest.fn(),
    timeEnd: jest.fn(),
  },
}));

jest.mock('@/lib/services/assetService', () => ({
  getAuthBackground: jest.fn(() => null),
}));

jest.mock('sonner', () => ({
  toast: {
    error: (...args: [string]) => mockToastError(...args),
  },
}));

function jsonResponse(status: number, body: object): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: jest.fn(async () => body),
  } as unknown as Response;
}

async function submitForgotPassword(email = 'alex@example.com') {
  const user = userEvent.setup();
  render(<ForgotPasswordPage />);

  await user.type(screen.getByLabelText(/email/i), email);
  await user.click(screen.getByRole('button', { name: /send reset link/i }));
}

describe('ForgotPasswordPage', () => {
  beforeEach(() => {
    mockFetchAPI.mockReset();
    mockToastError.mockReset();
  });

  it('shows the check email success state after a successful request', async () => {
    mockFetchAPI.mockResolvedValueOnce(
      jsonResponse(200, { message: 'Check your email for the reset link.' })
    );

    await submitForgotPassword();

    expect(await screen.findByRole('heading', { name: /check your email/i })).toBeInTheDocument();
    expect(screen.getByText('alex@example.com')).toBeInTheDocument();
  });

  it('shows an inline account-not-found error for 404 responses', async () => {
    mockFetchAPI.mockResolvedValueOnce(
      jsonResponse(404, {
        detail: "We couldn't find an account with that email. Please double-check and try again.",
      })
    );

    await submitForgotPassword();

    expect(
      await screen.findByText(
        "We couldn't find an account with that email. Please double-check and try again."
      )
    ).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: /check your email/i })).not.toBeInTheDocument();
  });

  it('shows an inline rate-limit error for 429 responses', async () => {
    mockFetchAPI.mockResolvedValueOnce(
      jsonResponse(429, { detail: 'Too many password reset attempts.' })
    );

    await submitForgotPassword();

    expect(
      await screen.findByText('Too many requests. Please wait a few minutes and try again.')
    ).toBeInTheDocument();
  });

  it('shows an error toast for reset email delivery failures', async () => {
    mockFetchAPI.mockResolvedValueOnce(
      jsonResponse(503, {
        detail: "Couldn't send reset email. Please try again or contact support.",
      })
    );

    await submitForgotPassword();

    await waitFor(() => {
      expect(mockToastError).toHaveBeenCalledWith(
        "Couldn't send reset email. Please try again or contact support."
      );
    });
    expect(
      screen.getByText("Couldn't send reset email. Please try again or contact support.")
    ).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: /check your email/i })).not.toBeInTheDocument();
  });

  it('shows a generic inline error for unexpected failures', async () => {
    mockFetchAPI.mockResolvedValueOnce(jsonResponse(500, { detail: 'boom' }));

    await submitForgotPassword();

    expect(await screen.findByText('Something went wrong. Please try again.')).toBeInTheDocument();
  });

  it('shows generic error when fetchAPI rejects', async () => {
    mockFetchAPI.mockRejectedValueOnce(new Error('network down'));

    await submitForgotPassword();

    expect(await screen.findByText('Something went wrong. Please try again.')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: /check your email/i })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /send reset link/i })).toBeInTheDocument();
  });
});
