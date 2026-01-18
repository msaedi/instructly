import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import ConflictModal from '../ConflictModal';

describe('ConflictModal', () => {
  const defaultProps = {
    open: true,
    onRefresh: jest.fn(),
    onOverwrite: jest.fn(),
    onClose: jest.fn(),
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders nothing when open is false', () => {
    render(<ConflictModal {...defaultProps} open={false} />);
    expect(screen.queryByTestId('conflict-modal')).not.toBeInTheDocument();
  });

  it('renders modal when open is true', () => {
    render(<ConflictModal {...defaultProps} />);
    expect(screen.getByTestId('conflict-modal')).toBeInTheDocument();
  });

  it('displays the conflict title', () => {
    render(<ConflictModal {...defaultProps} />);
    expect(screen.getByText('New changes detected')).toBeInTheDocument();
  });

  it('displays the conflict description', () => {
    render(<ConflictModal {...defaultProps} />);
    expect(
      screen.getByText(/Another session updated this week while you were editing/)
    ).toBeInTheDocument();
  });

  it('shows server version when provided', () => {
    render(<ConflictModal {...defaultProps} serverVersion="v1.2.3" />);
    expect(screen.getByText(/Latest version: v1.2.3/)).toBeInTheDocument();
  });

  it('does not show server version when not provided', () => {
    render(<ConflictModal {...defaultProps} />);
    expect(screen.queryByText(/Latest version:/)).not.toBeInTheDocument();
  });

  it('calls onRefresh when Refresh button is clicked', () => {
    const onRefresh = jest.fn();
    render(<ConflictModal {...defaultProps} onRefresh={onRefresh} />);

    fireEvent.click(screen.getByTestId('conflict-refresh'));
    expect(onRefresh).toHaveBeenCalledTimes(1);
  });

  it('calls onOverwrite when Overwrite button is clicked', () => {
    const onOverwrite = jest.fn();
    render(<ConflictModal {...defaultProps} onOverwrite={onOverwrite} />);

    fireEvent.click(screen.getByTestId('conflict-overwrite'));
    expect(onOverwrite).toHaveBeenCalledTimes(1);
  });

  it('calls onClose when close button is clicked', () => {
    const onClose = jest.fn();
    render(<ConflictModal {...defaultProps} onClose={onClose} />);

    fireEvent.click(screen.getByRole('button', { name: 'Close' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('calls onClose when backdrop is clicked', () => {
    const onClose = jest.fn();
    render(<ConflictModal {...defaultProps} onClose={onClose} />);

    // The backdrop has aria-hidden="true" and onClick handler
    const backdrop = screen.getByTestId('conflict-modal').previousSibling as HTMLElement;
    fireEvent.click(backdrop);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('shows loading state during refresh', () => {
    render(<ConflictModal {...defaultProps} isRefreshing={true} />);
    expect(screen.getByText('Refreshing…')).toBeInTheDocument();
  });

  it('shows loading state during overwrite', () => {
    render(<ConflictModal {...defaultProps} isOverwriting={true} />);
    expect(screen.getByText('Overwriting…')).toBeInTheDocument();
  });

  it('disables buttons during refresh', () => {
    render(<ConflictModal {...defaultProps} isRefreshing={true} />);

    expect(screen.getByTestId('conflict-refresh')).toBeDisabled();
    expect(screen.getByTestId('conflict-overwrite')).toBeDisabled();
  });

  it('disables buttons during overwrite', () => {
    render(<ConflictModal {...defaultProps} isOverwriting={true} />);

    expect(screen.getByTestId('conflict-refresh')).toBeDisabled();
    expect(screen.getByTestId('conflict-overwrite')).toBeDisabled();
  });

  it('has correct accessibility attributes', () => {
    render(<ConflictModal {...defaultProps} />);

    const modal = screen.getByRole('dialog');
    expect(modal).toHaveAttribute('aria-modal', 'true');
    expect(modal).toHaveAttribute('aria-labelledby', 'availability-conflict-title');
    expect(modal).toHaveAttribute('aria-describedby', 'availability-conflict-desc');
  });

  it('renders normal button text when not loading', () => {
    render(<ConflictModal {...defaultProps} />);

    expect(screen.getByText('Refresh')).toBeInTheDocument();
    expect(screen.getByText('Overwrite')).toBeInTheDocument();
  });
});
