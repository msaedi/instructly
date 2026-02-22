import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';

import { AddressSelector } from '../AddressSelector';
import { useSavedAddresses } from '@/hooks/useSavedAddresses';
import { useServiceAreaCheck } from '@/hooks/useServiceAreaCheck';

jest.mock('@/hooks/useSavedAddresses', () => {
  const actual = jest.requireActual('@/hooks/useSavedAddresses');
  return {
    ...actual,
    useSavedAddresses: jest.fn(),
  };
});

jest.mock('@/hooks/useServiceAreaCheck', () => ({
  useServiceAreaCheck: jest.fn(),
}));

const useSavedAddressesMock = useSavedAddresses as jest.Mock;
const useServiceAreaCheckMock = useServiceAreaCheck as jest.Mock;

const sampleAddresses = [
  {
    id: 'addr-1',
    label: 'home',
    street_line1: '123 Main St',
    locality: 'New York',
    administrative_area: 'NY',
    postal_code: '10001',
    latitude: 40.7,
    longitude: -73.9,
    is_active: true,
    is_default: true,
  },
  {
    id: 'addr-2',
    label: 'work',
    street_line1: '456 Market St',
    street_line2: 'Suite 200',
    locality: 'San Francisco',
    administrative_area: 'CA',
    postal_code: '94105',
    latitude: 37.79,
    longitude: -122.39,
    is_active: true,
  },
];

describe('AddressSelector', () => {
  beforeEach(() => {
    useSavedAddressesMock.mockReset();
    useServiceAreaCheckMock.mockReset();
  });

  it('shows saved addresses when available', () => {
    useSavedAddressesMock.mockReturnValue({ addresses: sampleAddresses, isLoading: false });
    useServiceAreaCheckMock.mockReturnValue({ data: { is_covered: true }, isLoading: false });

    render(
      <AddressSelector
        instructorId="inst-1"
        locationType="student_location"
        selectedAddress={null}
        onSelectAddress={jest.fn()}
        onEnterNewAddress={jest.fn()}
      />
    );

    expect(screen.getByText('Home')).toBeInTheDocument();
    expect(screen.getByText('Work')).toBeInTheDocument();
    expect(screen.getByText('123 Main St, New York, NY 10001')).toBeInTheDocument();
    expect(screen.getByText('456 Market St, Suite 200, San Francisco, CA 94105')).toBeInTheDocument();
  });

  it('shows loading state while fetching addresses', () => {
    useSavedAddressesMock.mockReturnValue({ addresses: [], isLoading: true });
    useServiceAreaCheckMock.mockReturnValue({ data: null, isLoading: false });

    render(
      <AddressSelector
        instructorId="inst-1"
        locationType="student_location"
        selectedAddress={null}
        onSelectAddress={jest.fn()}
        onEnterNewAddress={jest.fn()}
      />
    );

    expect(screen.getByText(/Loading addresses/i)).toBeInTheDocument();
  });

  it('shows "no addresses" message when empty', () => {
    useSavedAddressesMock.mockReturnValue({ addresses: [], isLoading: false });
    useServiceAreaCheckMock.mockReturnValue({ data: null, isLoading: false });

    render(
      <AddressSelector
        instructorId="inst-1"
        locationType="student_location"
        selectedAddress={null}
        onSelectAddress={jest.fn()}
        onEnterNewAddress={jest.fn()}
      />
    );

    expect(screen.getByText(/No saved addresses/i)).toBeInTheDocument();
  });

  it('uses neutral location copy when location type is neutral_location', () => {
    useSavedAddressesMock.mockReturnValue({ addresses: sampleAddresses, isLoading: false });
    useServiceAreaCheckMock.mockReturnValue({ data: { is_covered: true }, isLoading: false });

    render(
      <AddressSelector
        instructorId="inst-1"
        locationType="neutral_location"
        selectedAddress={null}
        onSelectAddress={jest.fn()}
        onEnterNewAddress={jest.fn()}
      />
    );

    expect(screen.getByText(/Where would you like to meet/i)).toBeInTheDocument();
  });

  it('highlights selected address', () => {
    useSavedAddressesMock.mockReturnValue({ addresses: sampleAddresses, isLoading: false });
    useServiceAreaCheckMock.mockReturnValue({ data: { is_covered: true }, isLoading: false });

    render(
      <AddressSelector
        instructorId="inst-1"
        locationType="student_location"
        selectedAddress={sampleAddresses[0] ?? null}
        onSelectAddress={jest.fn()}
        onEnterNewAddress={jest.fn()}
      />
    );

    const selectedButton = screen.getByText('Home').closest('button');
    expect(selectedButton).toHaveClass('bg-purple-50');
  });

  it('disables address missing coordinates', () => {
    const missingCoords = {
      id: 'addr-3',
      label: 'other',
      street_line1: '987 Pine St',
      locality: 'Seattle',
      administrative_area: 'WA',
      postal_code: '98101',
      is_active: true,
    };
    useSavedAddressesMock.mockReturnValue({ addresses: [missingCoords], isLoading: false });
    useServiceAreaCheckMock.mockReturnValue({ data: null, isLoading: false });

    render(
      <AddressSelector
        instructorId="inst-1"
        locationType="student_location"
        selectedAddress={null}
        onSelectAddress={jest.fn()}
        onEnterNewAddress={jest.fn()}
      />
    );

    const button = screen.getByText('Other').closest('button');
    expect(button).toBeDisabled();
    expect(screen.getByText(/Missing coordinates/i)).toBeInTheDocument();
  });

  it('disables addresses outside service area', () => {
    useSavedAddressesMock.mockReturnValue({ addresses: sampleAddresses, isLoading: false });
    useServiceAreaCheckMock.mockReturnValue({ data: { is_covered: false }, isLoading: false });

    render(
      <AddressSelector
        instructorId="inst-1"
        locationType="student_location"
        selectedAddress={null}
        onSelectAddress={jest.fn()}
        onEnterNewAddress={jest.fn()}
      />
    );

    const button = screen.getByText('Home').closest('button');
    expect(button).toBeDisabled();
    expect(screen.getAllByText(/Not in service area/i).length).toBeGreaterThan(0);
  });

  it('shows service area warning for selected out-of-area address', () => {
    useSavedAddressesMock.mockReturnValue({ addresses: sampleAddresses, isLoading: false });
    useServiceAreaCheckMock.mockImplementation(({ lat }: { lat?: number }) => {
      if (lat === 40.7) {
        return { data: { is_covered: false }, isLoading: false };
      }
      return { data: { is_covered: true }, isLoading: false };
    });

    render(
      <AddressSelector
        instructorId="inst-1"
        locationType="student_location"
        selectedAddress={sampleAddresses[0] ?? null}
        onSelectAddress={jest.fn()}
        onEnterNewAddress={jest.fn()}
      />
    );

    expect(screen.getByText(/outside the instructor/i)).toBeInTheDocument();
  });

  it('calls onEnterNewAddress when clicking "Use a different address"', () => {
    const onEnterNewAddress = jest.fn();
    useSavedAddressesMock.mockReturnValue({ addresses: sampleAddresses, isLoading: false });
    useServiceAreaCheckMock.mockReturnValue({ data: { is_covered: true }, isLoading: false });

    render(
      <AddressSelector
        instructorId="inst-1"
        locationType="student_location"
        selectedAddress={null}
        onSelectAddress={jest.fn()}
        onEnterNewAddress={onEnterNewAddress}
      />
    );

    fireEvent.click(screen.getByText('+ Use a different address'));
    expect(onEnterNewAddress).toHaveBeenCalledTimes(1);
  });

  it('calls onSelectAddress when clicking a covered address', () => {
    const onSelectAddress = jest.fn();
    useSavedAddressesMock.mockReturnValue({ addresses: sampleAddresses, isLoading: false });
    useServiceAreaCheckMock.mockReturnValue({ data: { is_covered: true }, isLoading: false });

    render(
      <AddressSelector
        instructorId="inst-1"
        locationType="student_location"
        selectedAddress={null}
        onSelectAddress={onSelectAddress}
        onEnterNewAddress={jest.fn()}
      />
    );

    const homeButton = screen.getByText('Home').closest('button')!;
    fireEvent.click(homeButton);

    expect(onSelectAddress).toHaveBeenCalledTimes(1);
    expect(onSelectAddress).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'addr-1', label: 'home' })
    );
  });

  it('calls onEnterNewAddress when clicking "Enter address" with no saved addresses', () => {
    const onEnterNewAddress = jest.fn();
    useSavedAddressesMock.mockReturnValue({ addresses: [], isLoading: false });
    useServiceAreaCheckMock.mockReturnValue({ data: null, isLoading: false });

    render(
      <AddressSelector
        instructorId="inst-1"
        locationType="student_location"
        selectedAddress={null}
        onSelectAddress={jest.fn()}
        onEnterNewAddress={onEnterNewAddress}
      />
    );

    fireEvent.click(screen.getByText('Enter address'));
    expect(onEnterNewAddress).toHaveBeenCalledTimes(1);
  });

  it('shows Default badge for default addresses', () => {
    useSavedAddressesMock.mockReturnValue({ addresses: sampleAddresses, isLoading: false });
    useServiceAreaCheckMock.mockReturnValue({ data: { is_covered: true }, isLoading: false });

    render(
      <AddressSelector
        instructorId="inst-1"
        locationType="student_location"
        selectedAddress={null}
        onSelectAddress={jest.fn()}
        onEnterNewAddress={jest.fn()}
      />
    );

    expect(screen.getByText('Default')).toBeInTheDocument();
  });

  it('handles address with custom_label for Other type', () => {
    const customAddress = {
      id: 'addr-4',
      label: 'other',
      custom_label: 'Gym',
      street_line1: '789 Fitness Ave',
      locality: 'New York',
      administrative_area: 'NY',
      postal_code: '10002',
      latitude: 40.71,
      longitude: -73.91,
      is_active: true,
    };
    useSavedAddressesMock.mockReturnValue({ addresses: [customAddress], isLoading: false });
    useServiceAreaCheckMock.mockReturnValue({ data: { is_covered: true }, isLoading: false });

    render(
      <AddressSelector
        instructorId="inst-1"
        locationType="student_location"
        selectedAddress={null}
        onSelectAddress={jest.fn()}
        onEnterNewAddress={jest.fn()}
      />
    );

    expect(screen.getByText('Gym')).toBeInTheDocument();
  });
});
