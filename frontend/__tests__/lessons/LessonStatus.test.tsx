import React from 'react';
import { render, screen } from '@testing-library/react';
import { LessonStatus } from '@/components/lessons/LessonStatus';

describe('LessonStatus', () => {
  it('renders confirmed status as Upcoming with blue color', () => {
    render(<LessonStatus status="CONFIRMED" />);

    const badge = screen.getByText('Upcoming');
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveClass('insta-status-badge', 'insta-status-badge--pending');
  });

  it('renders in-progress status with pending styling', () => {
    render(<LessonStatus status="IN_PROGRESS" />);

    const badge = screen.getByText('In Progress');
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveClass('insta-status-badge', 'insta-status-badge--pending');
  });

  it('renders completed status with success styling', () => {
    render(<LessonStatus status="COMPLETED" />);

    const badge = screen.getByText('Completed');
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveClass('insta-status-badge', 'insta-status-badge--success');
  });

  it('renders cancelled status with gray color', () => {
    render(<LessonStatus status="CANCELLED" />);

    const badge = screen.getByText('Cancelled');
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveClass('insta-status-badge', 'insta-status-badge--cancelled');
  });

  it('renders no show status with amber color', () => {
    render(<LessonStatus status="NO_SHOW" />);

    const badge = screen.getByText('No Show');
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveClass('insta-status-badge', 'insta-status-badge--warning');
  });

  it('renders with correct badge structure', () => {
    render(<LessonStatus status="CONFIRMED" />);
    const badge = screen.getByText('Upcoming');
    expect(badge).toHaveClass('insta-status-badge', 'insta-status-badge--pending');
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
    render(<LessonStatus status="COMPLETED" />);
    const badge = screen.getByText('Completed');
    expect(badge.className.split(' ')).toEqual(
      expect.arrayContaining(['insta-status-badge', 'insta-status-badge--success'])
    );
  });

  it('renders unknown status with default styling and uses status as label', () => {
    // Test the default case in the switch statement
    render(<LessonStatus status={'UNKNOWN_STATUS' as 'CONFIRMED'} />);

    const badge = screen.getByText('UNKNOWN_STATUS');
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveClass('insta-status-badge', 'insta-status-badge--default');
  });
});
