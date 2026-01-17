import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import BookingModal from '../BookingModal';
import type { Instructor } from '../../types';
import { useAuth } from '../../hooks/useAuth';
import { useRouter } from 'next/navigation';

jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
}));

jest.mock('../../hooks/useAuth', () => ({
  useAuth: jest.fn(),
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
    { id: 'service-2', skill: 'Guitar', hourly_rate: 80, duration_options: [30, 60], duration: 30 },
  ],
};

const renderModal = (props?: Partial<React.ComponentProps<typeof BookingModal>>) => {
  const onClose = jest.fn();
  const onContinueToBooking = jest.fn();
  render(
    <BookingModal
      isOpen
      onClose={onClose}
      onContinueToBooking={onContinueToBooking}
      instructor={instructor}
      selectedDate="2025-01-01"
      selectedTime="10:00"
      {...props}
    />
  );
  return { onClose, onContinueToBooking };
};

const getTextInputs = () => screen.getAllByRole('textbox') as HTMLInputElement[];

describe('BookingModal', () => {
  const replaceMock = jest.fn();

  beforeEach(() => {
    useRouterMock.mockReturnValue({ push: replaceMock });
    replaceMock.mockReset();
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
      <BookingModal
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

  it('redirects unauthenticated users to login and stores booking intent', async () => {
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

  it('shows booking form for authenticated users', async () => {
    useAuthMock.mockReturnValue({
      user: { full_name: 'Jane Doe', email: 'jane@example.com' },
      isAuthenticated: true,
      redirectToLogin: jest.fn(),
    });

    renderModal();

    expect(screen.getByText('Your Information')).toBeInTheDocument();
    const inputs = getTextInputs();
    expect(inputs.length).toBeGreaterThanOrEqual(2);
    const nameInput = inputs[0]!;
    const emailInput = inputs[1]!;
    expect(nameInput).toHaveValue('Jane Doe');
    expect(emailInput).toHaveValue('jane@example.com');
  });

  it('validates required fields before submission', async () => {
    useAuthMock.mockReturnValue({
      user: { full_name: 'Jane Doe', email: 'jane@example.com' },
      isAuthenticated: true,
      redirectToLogin: jest.fn(),
    });

    renderModal();

    const inputs = getTextInputs();
    expect(inputs.length).toBeGreaterThanOrEqual(3);
    const nameInput = inputs[0]!;
    const emailInput = inputs[1]!;
    const phoneInput = inputs[2]!;
    await userEvent.clear(nameInput);
    await userEvent.clear(emailInput);
    await userEvent.clear(phoneInput);

    const continueButton = screen.getByRole('button', { name: 'Continue to Payment' });
    expect(continueButton).toBeDisabled();
    expect(window.alert).not.toHaveBeenCalled();
  });

  it('submits valid booking and navigates to confirmation', async () => {
    useAuthMock.mockReturnValue({
      user: { full_name: 'Jane Doe', email: 'jane@example.com' },
      isAuthenticated: true,
      redirectToLogin: jest.fn(),
    });

    renderModal();

    const inputs = getTextInputs();
    expect(inputs.length).toBeGreaterThanOrEqual(3);
    const nameInput = inputs[0]!;
    const emailInput = inputs[1]!;
    const phoneInput = inputs[2]!;
    await userEvent.clear(nameInput);
    await userEvent.type(nameInput, 'Jane Doe');
    await userEvent.clear(emailInput);
    await userEvent.type(emailInput, 'jane@example.com');
    await userEvent.type(phoneInput, '555-1111');

    await userEvent.click(screen.getByRole('checkbox'));

    await userEvent.click(screen.getByRole('button', { name: 'Continue to Payment' }));

    await waitFor(() => {
      expect(replaceMock).toHaveBeenCalledWith('/student/booking/confirm');
    });
    expect(window.sessionStorage.setItem).toHaveBeenCalledWith('bookingData', expect.any(String));
  });
});
