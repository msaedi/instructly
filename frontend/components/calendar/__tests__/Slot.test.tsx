import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { Slot } from '../Slot';

// Mock radix-ui tooltip
jest.mock('@radix-ui/react-tooltip', () => ({
  Provider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  Root: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  Trigger: ({ children, asChild }: { children: React.ReactNode; asChild?: boolean }) => (
    <>{asChild ? children : <span>{children}</span>}</>
  ),
  Content: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="tooltip-content">{children}</div>
  ),
  Arrow: () => <div data-testid="tooltip-arrow" />,
}));

describe('Slot', () => {
  const defaultProps = {
    isSelected: false,
    label: '9:00 AM',
  };

  it('renders a button element', () => {
    render(<Slot {...defaultProps} />);
    expect(screen.getByRole('button')).toBeInTheDocument();
  });

  it('renders with correct aria-label', () => {
    render(<Slot {...defaultProps} label="10:00 AM" />);
    expect(screen.getByRole('button', { name: '10:00 AM' })).toBeInTheDocument();
  });

  it('has aria-pressed=false when not selected', () => {
    render(<Slot {...defaultProps} isSelected={false} />);
    expect(screen.getByRole('button')).toHaveAttribute('aria-pressed', 'false');
  });

  it('has aria-pressed=true when selected', () => {
    render(<Slot {...defaultProps} isSelected={true} />);
    expect(screen.getByRole('button')).toHaveAttribute('aria-pressed', 'true');
  });

  it('applies selected background color when isSelected is true', () => {
    render(<Slot {...defaultProps} isSelected={true} />);
    const button = screen.getByRole('button');
    expect(button).toHaveClass('bg-[#EDE3FA]');
  });

  it('applies white background when not selected and not past', () => {
    render(<Slot {...defaultProps} isSelected={false} isPast={false} />);
    const button = screen.getByRole('button');
    expect(button).toHaveClass('bg-white');
  });

  it('applies gray background when past and not selected', () => {
    render(<Slot {...defaultProps} isSelected={false} isPast={true} />);
    const button = screen.getByRole('button');
    expect(button).toHaveClass('bg-gray-50');
  });

  it('applies opacity when past', () => {
    render(<Slot {...defaultProps} isPast={true} />);
    const button = screen.getByRole('button');
    expect(button).toHaveClass('opacity-70');
  });

  it('is disabled when isConflict is true', () => {
    render(<Slot {...defaultProps} isConflict={true} />);
    expect(screen.getByRole('button')).toBeDisabled();
  });

  it('is disabled when disabled prop is true', () => {
    render(<Slot {...defaultProps} disabled={true} />);
    expect(screen.getByRole('button')).toBeDisabled();
  });

  it('is enabled when not disabled and not conflict', () => {
    render(<Slot {...defaultProps} disabled={false} isConflict={false} />);
    expect(screen.getByRole('button')).not.toBeDisabled();
  });

  it('shows conflict pattern when isConflict is true', () => {
    const { container } = render(<Slot {...defaultProps} isConflict={true} />);
    const conflictPattern = container.querySelector('.pointer-events-none');
    expect(conflictPattern).toBeInTheDocument();
  });

  it('does not show conflict pattern when isConflict is false', () => {
    const { container } = render(<Slot {...defaultProps} isConflict={false} />);
    const conflictPattern = container.querySelector('.pointer-events-none');
    expect(conflictPattern).not.toBeInTheDocument();
  });

  it('applies dragging ring style when isDragging is true', () => {
    render(<Slot {...defaultProps} isDragging={true} />);
    const button = screen.getByRole('button');
    expect(button).toHaveClass('ring-2', 'ring-[#D4B5F0]', 'ring-inset');
  });

  it('applies mobile height when isMobile is true', () => {
    render(<Slot {...defaultProps} isMobile={true} />);
    const button = screen.getByRole('button');
    expect(button).toHaveClass('min-h-[44px]');
  });

  it('applies desktop height when isMobile is false', () => {
    render(<Slot {...defaultProps} isMobile={false} />);
    const button = screen.getByRole('button');
    expect(button).toHaveClass('min-h-[32px]');
  });

  it('fires onClick when clicked', () => {
    const onClick = jest.fn();
    render(<Slot {...defaultProps} onClick={onClick} />);

    fireEvent.click(screen.getByRole('button'));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('does not fire onClick when disabled', () => {
    const onClick = jest.fn();
    render(<Slot {...defaultProps} onClick={onClick} disabled={true} />);

    fireEvent.click(screen.getByRole('button'));
    expect(onClick).not.toHaveBeenCalled();
  });

  it('renders tooltip with conflict message when isConflict and conflictMessage are set', () => {
    render(
      <Slot {...defaultProps} isConflict={true} conflictMessage="Slot is already booked" />
    );
    expect(screen.getByTestId('tooltip-content')).toHaveTextContent('Slot is already booked');
  });

  it('does not render tooltip when not a conflict', () => {
    render(<Slot {...defaultProps} isConflict={false} conflictMessage="Some message" />);
    expect(screen.queryByTestId('tooltip-content')).not.toBeInTheDocument();
  });

  it('applies cursor-not-allowed when disabled', () => {
    render(<Slot {...defaultProps} disabled={true} />);
    expect(screen.getByRole('button')).toHaveClass('cursor-not-allowed');
  });

  it('applies cursor-pointer when enabled', () => {
    render(<Slot {...defaultProps} disabled={false} isConflict={false} />);
    expect(screen.getByRole('button')).toHaveClass('cursor-pointer');
  });

  it('forwards ref to button element', () => {
    const ref = React.createRef<HTMLButtonElement>();
    render(<Slot {...defaultProps} ref={ref} />);
    expect(ref.current).toBeInstanceOf(HTMLButtonElement);
  });

  it('accepts additional className', () => {
    render(<Slot {...defaultProps} className="custom-class" />);
    expect(screen.getByRole('button')).toHaveClass('custom-class');
  });
});
