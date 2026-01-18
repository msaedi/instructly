import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import WeekNavigator from '../WeekNavigator';

jest.mock('@/lib/logger', () => ({
  logger: {
    info: jest.fn(),
    debug: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
  },
}));

describe('WeekNavigator', () => {
  // Monday, January 19, 2026
  const defaultWeekStart = new Date('2026-01-19T00:00:00');

  const defaultProps = {
    currentWeekStart: defaultWeekStart,
    onNavigate: jest.fn(),
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders the week header', () => {
    render(<WeekNavigator {...defaultProps} />);
    expect(screen.getByTestId('week-header')).toBeInTheDocument();
  });

  it('displays month and year for a week within the same month', () => {
    render(<WeekNavigator {...defaultProps} />);
    expect(screen.getByText('January 2026')).toBeInTheDocument();
  });

  it('displays both months when week spans two months', () => {
    // Monday, January 26, 2026 to Sunday, February 1, 2026
    const weekStart = new Date('2026-01-26T00:00:00');
    render(<WeekNavigator {...defaultProps} currentWeekStart={weekStart} />);
    expect(screen.getByText('January – February 2026')).toBeInTheDocument();
  });

  it('displays both years when week spans two years', () => {
    // Monday, December 28, 2026 to Sunday, January 3, 2027
    const weekStart = new Date('2026-12-28T00:00:00');
    render(<WeekNavigator {...defaultProps} currentWeekStart={weekStart} />);
    expect(screen.getByText('December 2026 – January 2027')).toBeInTheDocument();
  });

  it('renders previous week button', () => {
    render(<WeekNavigator {...defaultProps} />);
    expect(screen.getByRole('button', { name: /go to previous week/i })).toBeInTheDocument();
  });

  it('renders next week button', () => {
    render(<WeekNavigator {...defaultProps} />);
    expect(screen.getByRole('button', { name: /go to next week/i })).toBeInTheDocument();
  });

  it('calls onNavigate with "prev" when previous button is clicked', () => {
    const onNavigate = jest.fn();
    render(<WeekNavigator {...defaultProps} onNavigate={onNavigate} />);

    fireEvent.click(screen.getByRole('button', { name: /go to previous week/i }));
    expect(onNavigate).toHaveBeenCalledWith('prev');
  });

  it('calls onNavigate with "next" when next button is clicked', () => {
    const onNavigate = jest.fn();
    render(<WeekNavigator {...defaultProps} onNavigate={onNavigate} />);

    fireEvent.click(screen.getByRole('button', { name: /go to next week/i }));
    expect(onNavigate).toHaveBeenCalledWith('next');
  });

  it('disables both navigation buttons when disabled is true', () => {
    render(<WeekNavigator {...defaultProps} disabled={true} />);

    expect(screen.getByRole('button', { name: /go to previous week/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: /go to next week/i })).toBeDisabled();
  });

  it('enables both navigation buttons when disabled is false', () => {
    render(<WeekNavigator {...defaultProps} disabled={false} />);

    expect(screen.getByRole('button', { name: /go to previous week/i })).not.toBeDisabled();
    expect(screen.getByRole('button', { name: /go to next week/i })).not.toBeDisabled();
  });

  it('shows subtitle by default', () => {
    render(<WeekNavigator {...defaultProps} />);
    expect(screen.getByText(/Edit availability for this specific week/)).toBeInTheDocument();
  });

  it('hides subtitle when showSubtitle is false', () => {
    render(<WeekNavigator {...defaultProps} showSubtitle={false} />);
    expect(screen.queryByText(/Edit availability for this specific week/)).not.toBeInTheDocument();
  });

  it('shows unsaved changes warning when hasUnsavedChanges is true', () => {
    render(<WeekNavigator {...defaultProps} hasUnsavedChanges={true} />);
    expect(screen.getByText(/unsaved changes/)).toBeInTheDocument();
  });

  it('does not show unsaved changes warning when hasUnsavedChanges is false', () => {
    render(<WeekNavigator {...defaultProps} hasUnsavedChanges={false} />);
    expect(screen.queryByText(/unsaved changes/)).not.toBeInTheDocument();
  });

  it('sets data-week-start attribute with ISO date', () => {
    render(<WeekNavigator {...defaultProps} />);
    expect(screen.getByTestId('week-header')).toHaveAttribute('data-week-start', '2026-01-19');
  });

  it('has correct button titles', () => {
    render(<WeekNavigator {...defaultProps} />);

    expect(screen.getByRole('button', { name: /go to previous week/i })).toHaveAttribute(
      'title',
      'Previous week'
    );
    expect(screen.getByRole('button', { name: /go to next week/i })).toHaveAttribute(
      'title',
      'Next week'
    );
  });
});
