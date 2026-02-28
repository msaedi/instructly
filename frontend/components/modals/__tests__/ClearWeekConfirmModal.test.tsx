import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import ClearWeekConfirmModal from '../ClearWeekConfirmModal';

// Mock the base Modal component
jest.mock('@/components/Modal', () => {
  const MockModal = ({
    isOpen,
    onClose,
    title,
    children,
  }: {
    isOpen: boolean;
    onClose: () => void;
    title: string;
    children: React.ReactNode;
  }) => {
    if (!isOpen) return null;
    const labelId = 'clear-week-confirm-modal-title';
    return (
      <div role="dialog" aria-modal="true" aria-labelledby={labelId} data-testid="modal">
        <h2 id={labelId}>{title}</h2>
        <button onClick={onClose} aria-label="Close modal">
          Close
        </button>
        {children}
      </div>
    );
  };
  MockModal.displayName = 'MockModal';
  return MockModal;
});

jest.mock('@/lib/logger', () => ({
  logger: {
    info: jest.fn(),
    debug: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
  },
}));

describe('ClearWeekConfirmModal', () => {
  const defaultProps = {
    isOpen: true,
    onClose: jest.fn(),
    onConfirm: jest.fn(),
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders nothing when isOpen is false', () => {
    render(<ClearWeekConfirmModal {...defaultProps} isOpen={false} />);
    expect(screen.queryByTestId('modal')).not.toBeInTheDocument();
  });

  it('renders modal when isOpen is true', () => {
    render(<ClearWeekConfirmModal {...defaultProps} />);
    expect(screen.getByTestId('modal')).toBeInTheDocument();
  });

  it('displays the modal title', () => {
    render(<ClearWeekConfirmModal {...defaultProps} />);
    expect(screen.getByText('Clear Week Schedule')).toBeInTheDocument();
  });

  it('displays the confirmation question', () => {
    render(<ClearWeekConfirmModal {...defaultProps} />);
    expect(
      screen.getByText(/Are you sure you want to clear all availability for this week/)
    ).toBeInTheDocument();
  });

  it('displays the warning about action being irreversible', () => {
    render(<ClearWeekConfirmModal {...defaultProps} />);
    expect(screen.getByText(/This action cannot be undone/)).toBeInTheDocument();
  });

  it('does not show booked slots note when bookedSlotsCount is 0', () => {
    render(<ClearWeekConfirmModal {...defaultProps} bookedSlotsCount={0} />);
    expect(screen.queryByText(/with existing bookings will be preserved/)).not.toBeInTheDocument();
  });

  it('shows booked slots note with singular form when bookedSlotsCount is 1', () => {
    render(<ClearWeekConfirmModal {...defaultProps} bookedSlotsCount={1} />);
    expect(screen.getByText(/1 time slot with existing bookings will be preserved/)).toBeInTheDocument();
  });

  it('shows booked slots note with plural form when bookedSlotsCount is more than 1', () => {
    render(<ClearWeekConfirmModal {...defaultProps} bookedSlotsCount={3} />);
    expect(screen.getByText(/3 time slots with existing bookings will be preserved/)).toBeInTheDocument();
  });

  it('calls onConfirm when Clear Week button is clicked', () => {
    const onConfirm = jest.fn();
    render(<ClearWeekConfirmModal {...defaultProps} onConfirm={onConfirm} />);

    fireEvent.click(screen.getByRole('button', { name: 'Clear Week' }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it('calls onClose when Cancel button is clicked', () => {
    const onClose = jest.fn();
    render(<ClearWeekConfirmModal {...defaultProps} onClose={onClose} />);

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('renders both Cancel and Clear Week buttons', () => {
    render(<ClearWeekConfirmModal {...defaultProps} />);

    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Clear Week' })).toBeInTheDocument();
  });

  it('has accessible modal structure', () => {
    render(<ClearWeekConfirmModal {...defaultProps} />);

    const modal = screen.getByRole('dialog');
    expect(modal).toHaveAttribute('aria-modal', 'true');
  });
});
