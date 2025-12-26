import React from 'react';
import { render, screen } from '@testing-library/react';
import { LessonStatus } from '@/components/lessons/LessonStatus';

describe('LessonStatus', () => {
  it('renders confirmed status as Upcoming with blue color', () => {
    render(<LessonStatus status="CONFIRMED" />);

    const badge = screen.getByText('Upcoming');
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveClass('bg-blue-50', 'text-blue-700', 'border-blue-200');
  });

  it('renders in-progress status with pending styling', () => {
    render(<LessonStatus status="IN_PROGRESS" />);

    const badge = screen.getByText('In Progress');
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveClass('bg-blue-50', 'text-blue-700', 'border-blue-200');
  });

  it('renders completed status with success styling', () => {
    render(<LessonStatus status="COMPLETED" />);

    const badge = screen.getByText('Completed');
    expect(badge).toBeInTheDocument();
    // New design uses yellow for success/state consistency
    expect(badge).toHaveClass('bg-yellow-50', 'text-yellow-700', 'border-yellow-200');
  });

  it('renders cancelled status with gray color', () => {
    render(<LessonStatus status="CANCELLED" />);

    const badge = screen.getByText('Cancelled');
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveClass('bg-gray-50', 'text-gray-700', 'border-gray-200');
  });

  it('renders no show status with amber color', () => {
    render(<LessonStatus status="NO_SHOW" />);

    const badge = screen.getByText('No Show');
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveClass('bg-amber-50', 'text-amber-700', 'border-amber-200');
  });

  it('renders with correct badge structure', () => {
    const { container } = render(<LessonStatus status="CONFIRMED" />);

    const badge = container.firstChild;
    expect(badge).toHaveClass(
      'inline-flex',
      'items-center',
      'rounded-full',
      'text-xs',
      'font-medium',
      'border'
    );
  });

  it('shows icon for each status', () => {
    const { container } = render(<LessonStatus status="COMPLETED" />);

    const icon = container.querySelector('svg');
    expect(icon).toBeInTheDocument();
    expect(icon).toHaveClass('h-3', 'w-3');
  });

  it('shows just Cancelled for cancelled status', () => {
    render(<LessonStatus status="CANCELLED" />);

    expect(screen.getByText('Cancelled')).toBeInTheDocument();
  });

  it('applies correct styling for all elements', () => {
    const { container } = render(<LessonStatus status="COMPLETED" />);

    const badge = container.querySelector('span');
    const classes = badge?.className.split(' ') || [];

    expect(classes).toContain('inline-flex');
    expect(classes).toContain('items-center');
    expect(classes).toContain('px-2.5');
    expect(classes).toContain('py-1'); // Updated from py-0.5
    expect(classes).toContain('rounded-full');
    expect(classes).toContain('text-xs');
    expect(classes).toContain('font-medium');
    expect(classes).toContain('border');
  });
});
