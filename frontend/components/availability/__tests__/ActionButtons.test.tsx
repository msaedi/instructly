import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import ActionButtons from '../ActionButtons';

jest.mock('@/lib/logger', () => ({
  logger: {
    info: jest.fn(),
    debug: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
  },
}));

describe('ActionButtons', () => {
  const defaultProps = {
    onSave: jest.fn(),
    onCopyPrevious: jest.fn(),
    onApplyFuture: jest.fn(),
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders all three action buttons', () => {
    render(<ActionButtons {...defaultProps} />);

    expect(screen.getByText('Copy from Previous Week')).toBeInTheDocument();
    expect(screen.getByText('Apply to Future Weeks')).toBeInTheDocument();
    expect(screen.getByText('Save This Week')).toBeInTheDocument();
  });

  it('calls onCopyPrevious when Copy button is clicked', () => {
    const onCopyPrevious = jest.fn();
    render(<ActionButtons {...defaultProps} onCopyPrevious={onCopyPrevious} />);

    fireEvent.click(screen.getByText('Copy from Previous Week'));
    expect(onCopyPrevious).toHaveBeenCalledTimes(1);
  });

  it('calls onApplyFuture when Apply button is clicked', () => {
    const onApplyFuture = jest.fn();
    render(<ActionButtons {...defaultProps} onApplyFuture={onApplyFuture} />);

    fireEvent.click(screen.getByText('Apply to Future Weeks'));
    expect(onApplyFuture).toHaveBeenCalledTimes(1);
  });

  it('calls onSave when Save button is clicked', () => {
    const onSave = jest.fn();
    render(<ActionButtons {...defaultProps} onSave={onSave} hasUnsavedChanges={true} />);

    fireEvent.click(screen.getByText('Save This Week'));
    expect(onSave).toHaveBeenCalledTimes(1);
  });

  it('disables save button when hasUnsavedChanges is false', () => {
    render(<ActionButtons {...defaultProps} hasUnsavedChanges={false} />);

    const saveButton = screen.getByRole('button', { name: /save changes for this week/i });
    expect(saveButton).toBeDisabled();
  });

  it('enables save button when hasUnsavedChanges is true', () => {
    render(<ActionButtons {...defaultProps} hasUnsavedChanges={true} />);

    const saveButton = screen.getByRole('button', { name: /save changes for this week/i });
    expect(saveButton).not.toBeDisabled();
  });

  it('disables all buttons when disabled prop is true', () => {
    render(<ActionButtons {...defaultProps} disabled={true} hasUnsavedChanges={true} />);

    const buttons = screen.getAllByRole('button');
    buttons.forEach((button) => {
      expect(button).toBeDisabled();
    });
  });

  it('shows loading state during save', () => {
    render(<ActionButtons {...defaultProps} isSaving={true} hasUnsavedChanges={true} />);

    expect(screen.getByText('Saving...')).toBeInTheDocument();
  });

  it('shows validating state during validation', () => {
    render(<ActionButtons {...defaultProps} isValidating={true} hasUnsavedChanges={true} />);

    expect(screen.getByText('Validating...')).toBeInTheDocument();
  });

  it('disables save button during saving', () => {
    render(<ActionButtons {...defaultProps} isSaving={true} hasUnsavedChanges={true} />);

    // During saving, the button shows "Saving..." text
    const saveButton = screen.getByText('Saving...');
    expect(saveButton.closest('button')).toBeDisabled();
  });

  it('disables save button during validation', () => {
    render(<ActionButtons {...defaultProps} isValidating={true} hasUnsavedChanges={true} />);

    const saveButton = screen.getByRole('button', { name: /validating changes/i });
    expect(saveButton).toBeDisabled();
  });

  it('disables copy and apply buttons during saving', () => {
    render(<ActionButtons {...defaultProps} isSaving={true} />);

    const copyButton = screen.getByRole('button', { name: /copy schedule from previous week/i });
    const applyButton = screen.getByRole('button', {
      name: /apply current schedule to future weeks/i,
    });

    expect(copyButton).toBeDisabled();
    expect(applyButton).toBeDisabled();
  });

  it('has correct aria-labels for all buttons', () => {
    render(<ActionButtons {...defaultProps} />);

    expect(
      screen.getByRole('button', { name: /copy schedule from previous week/i })
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /apply current schedule to future weeks/i })
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /save changes for this week/i })
    ).toBeInTheDocument();
  });

  it('updates aria-label during validation', () => {
    render(<ActionButtons {...defaultProps} isValidating={true} hasUnsavedChanges={true} />);

    expect(screen.getByRole('button', { name: /validating changes/i })).toBeInTheDocument();
  });
});
