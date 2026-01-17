import { render, screen, waitFor } from '@testing-library/react';
import { act } from 'react-dom/test-utils';
import userEvent from '@testing-library/user-event';
import BookingModalWithPayment from '../BookingModalWithPayment';
import type { Instructor } from '../../types';
import { useAuth } from '../../hooks/useAuth';
import { useRouter } from 'next/navigation';

jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
}));

jest.mock('../../hooks/useAuth', () => ({
  useAuth: jest.fn(),
}));

jest.mock('@/components/booking/CheckoutFlow', () => ({
  __esModule: true,
  default: ({ onSuccess, onCancel }: { onSuccess: (id: string) => void; onCancel: () => void }) => (
    <div>
      <button onClick={() => onSuccess('pi_123')}>Mock Success</button>
      <button onClick={onCancel}>Mock Cancel</button>
    </div>
  ),
}));

const useAuthMock = useAuth as jest.Mock;
const useRouterMock = useRouter as jest.Mock;

const instructor: Instructor = {
  user_id: 'instructor-1',
  user: { first_name: 'Jane', last_initial: 'D' },
  bio: 'Bio',
  service_area_boroughs: ['Manhattan'],
  service_area_summary: 'NYC',
  years_experience: 5,
  services: [
    { id: 'service-1', skill: 'Piano', hourly_rate: 100, duration_options: [60], duration: 60 },
  ],
};

const renderModal = (props?: Partial<React.ComponentProps<typeof BookingModalWithPayment>>) => {
  const onClose = jest.fn();
  render(
    <BookingModalWithPayment
      isOpen
      onClose={onClose}
      instructor={instructor}
      selectedDate="2025-01-01"
      selectedTime="10:00"
      onContinueToBooking={jest.fn()}
      {...props}
    />
  );
  return { onClose };
};

const getTextInputs = () => screen.getAllByRole('textbox') as HTMLInputElement[];

describe('BookingModalWithPayment', () => {
  const pushMock = jest.fn();

  beforeEach(() => {
    useRouterMock.mockReturnValue({ push: pushMock });
    pushMock.mockReset();
    jest.spyOn(window, 'alert').mockImplementation(() => undefined);
    const storage: Record<string, string> = {};
    Object.defineProperty(window, 'sessionStorage', {
      value: {
        setItem: jest.fn((key: string, value: string) => {
          storage[key] = value;
        }),
        getItem: jest.fn((key: string) => storage[key] ?? null),
        removeItem: jest.fn((key: string) => {
          delete storage[key];
        }),
        clear: jest.fn(() => {
          Object.keys(storage).forEach((key) => delete storage[key]);
        }),
        key: jest.fn(),
        length: 0,
      },
      configurable: true,
    });
  });

  afterEach(() => {
    (window.alert as jest.Mock).mockRestore();
  });

  it('does not render when closed', () => {
    useAuthMock.mockReturnValue({
      user: null,
      isAuthenticated: false,
      redirectToLogin: jest.fn(),
    });

    const { container } = render(
      <BookingModalWithPayment
        isOpen={false}
        onClose={jest.fn()}
        onContinueToBooking={jest.fn()}
        instructor={instructor}
        selectedDate="2025-01-01"
        selectedTime="10:00"
      />
    );

    expect(container).toBeEmptyDOMElement();
  });

  it('redirects unauthenticated users and stores booking intent', async () => {
    const redirectToLogin = jest.fn();
    useAuthMock.mockReturnValue({
      user: null,
      isAuthenticated: false,
      redirectToLogin,
    });

    renderModal();

    await userEvent.click(screen.getByRole('button', { name: 'Continue to Booking' }));

    expect(redirectToLogin).toHaveBeenCalledWith('/student/booking/confirm');
    expect(window.sessionStorage.setItem).toHaveBeenCalled();
  });

  it('moves to booking details when authenticated', async () => {
    useAuthMock.mockReturnValue({
      user: { full_name: 'Jane Doe', email: 'jane@example.com' },
      isAuthenticated: true,
      redirectToLogin: jest.fn(),
    });

    renderModal();

    await userEvent.click(screen.getByRole('button', { name: 'Continue to Booking' }));

    expect(screen.getByText('Booking Details')).toBeInTheDocument();
  });

  it('validates required fields before payment', async () => {
    useAuthMock.mockReturnValue({
      user: { full_name: '', email: '' },
      isAuthenticated: true,
      redirectToLogin: jest.fn(),
    });

    renderModal();
    await userEvent.click(screen.getByRole('button', { name: 'Continue to Booking' }));

    await userEvent.click(screen.getByRole('button', { name: 'Continue to Payment' }));

    expect(window.alert).toHaveBeenCalledWith('Please fill in all required fields');
  });

  it('completes payment flow and redirects after success', async () => {
    jest.useFakeTimers();
    const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
    useAuthMock.mockReturnValue({
      user: { full_name: 'Jane Doe', email: 'jane@example.com' },
      isAuthenticated: true,
      redirectToLogin: jest.fn(),
    });

    const { onClose } = renderModal();

    await user.click(screen.getByRole('button', { name: 'Continue to Booking' }));

    const inputs = getTextInputs();
    expect(inputs.length).toBeGreaterThanOrEqual(3);
    const nameInput = inputs[0]!;
    const emailInput = inputs[1]!;
    const phoneInput = inputs[2]!;
    await user.clear(nameInput);
    await user.type(nameInput, 'Jane Doe');
    await user.clear(emailInput);
    await user.type(emailInput, 'jane@example.com');
    await user.type(phoneInput, '555-1111');
    await user.click(screen.getByRole('checkbox'));

    await user.click(screen.getByRole('button', { name: 'Continue to Payment' }));

    await user.click(screen.getByRole('button', { name: 'Mock Success' }));

    await waitFor(() => {
      expect(screen.getAllByText('Booking Confirmed!').length).toBeGreaterThan(0);
    });

    act(() => {
      jest.advanceTimersByTime(2000);
    });

    await waitFor(() => {
      expect(onClose).toHaveBeenCalled();
      expect(pushMock).toHaveBeenCalledWith('/student/dashboard');
    });

    jest.useRealTimers();
  });
});
