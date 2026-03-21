import React from 'react';
import { render, screen } from '@testing-library/react';
import BookingConfirmationPage from '../page';

const pushMock = jest.fn();
const paymentSectionMock = jest.fn();

jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: pushMock,
    back: jest.fn(),
  }),
}));

jest.mock('next/link', () => {
  return function MockLink({
    children,
    href,
    className,
  }: {
    children: React.ReactNode;
    href: string;
    className?: string;
  }) {
    return (
      <a href={href} className={className}>
        {children}
      </a>
    );
  };
});

jest.mock('@/features/student/payment', () => ({
  PaymentSection: (props: unknown) => {
    paymentSectionMock(props);
    return <div data-testid="payment-section" />;
  },
}));

jest.mock('@/components/referrals/ReferralShareModal', () => {
  return function MockReferralShareModal() {
    return null;
  };
});

jest.mock('@/features/shared/referrals/api', () => ({
  fetchMyReferrals: jest.fn(),
}));

jest.mock('@/lib/navigation/navigationStateManager', () => ({
  navigationStateManager: {
    clearBookingFlow: jest.fn(),
    saveBookingFlow: jest.fn(),
  },
}));

jest.mock('@/lib/logger', () => ({
  logger: {
    info: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
  },
}));

jest.mock('@/components/UserProfileDropdown', () => {
  return function MockUserProfileDropdown() {
    return <div data-testid="user-profile-dropdown" />;
  };
});

jest.mock('@/features/shared/hooks/useAuth', () => ({
  useAuth: () => ({
    isAuthenticated: true,
    isLoading: false,
  }),
}));

describe('BookingConfirmationPage', () => {
  beforeEach(() => {
    pushMock.mockReset();
    paymentSectionMock.mockReset();
    sessionStorage.clear();
  });

  it('merges serviceId into existing booking metadata instead of replacing it', () => {
    sessionStorage.setItem(
      'bookingData',
      JSON.stringify({
        bookingId: '',
        instructorId: 'instructor-1',
        instructorName: 'Taylor R.',
        lessonType: 'Piano',
        date: '2025-05-05T00:00:00.000Z',
        startTime: '10:00',
        endTime: '11:00',
        duration: 60,
        location: 'Online',
        basePrice: 80,
        totalAmount: 92,
        bookingType: 'standard',
        paymentStatus: 'scheduled',
        metadata: {
          location_type: 'online',
          modality: 'remote',
          timezone: 'America/New_York',
        },
      }),
    );
    sessionStorage.setItem('serviceId', 'service-123');

    render(<BookingConfirmationPage />);

    expect(screen.getByTestId('payment-section')).toBeInTheDocument();
    expect(paymentSectionMock).toHaveBeenCalledTimes(1);
    expect(paymentSectionMock.mock.calls[0]?.[0]).toEqual(
      expect.objectContaining({
        bookingData: expect.objectContaining({
          metadata: expect.objectContaining({
            serviceId: 'service-123',
            location_type: 'online',
            modality: 'remote',
            timezone: 'America/New_York',
          }),
        }),
      }),
    );
  });
});
