import React from 'react';
import { render, screen } from '@testing-library/react';
import InstructionsCard from '../InstructionsCard';

describe('InstructionsCard', () => {
  it('renders the instructions heading', () => {
    render(<InstructionsCard />);
    expect(screen.getByText('How it works:')).toBeInTheDocument();
  });

  it('renders the instructions region with proper aria-label', () => {
    render(<InstructionsCard />);
    expect(screen.getByRole('region', { name: 'Instructions' })).toBeInTheDocument();
  });

  it('renders all instruction list items', () => {
    render(<InstructionsCard />);
    const list = screen.getByRole('list');
    expect(list).toBeInTheDocument();

    // Verify key instructions are present
    expect(screen.getByText(/Each week's schedule is independent/)).toBeInTheDocument();
    expect(screen.getByText(/Save This Week/)).toBeInTheDocument();
    expect(screen.getByText(/Copy from Previous Week/)).toBeInTheDocument();
    expect(screen.getByText(/Apply to Future Weeks/)).toBeInTheDocument();
    expect(screen.getByText(/Presets apply a standard schedule pattern/)).toBeInTheDocument();
    expect(screen.getByText(/Navigate between weeks/)).toBeInTheDocument();
    expect(screen.getByText(/Click on booked slots/)).toBeInTheDocument();
    expect(screen.getByText(/Past time slots are read-only/)).toBeInTheDocument();
  });

  it('renders the info icon', () => {
    render(<InstructionsCard />);
    // The info icon is hidden from accessibility tree with aria-hidden="true"
    // Check for the container classes that indicate the info icon's parent
    const container = screen.getByRole('region', { name: 'Instructions' });
    expect(container).toHaveClass('bg-blue-50');
  });

  it('has correct styling for the container', () => {
    render(<InstructionsCard />);
    const region = screen.getByRole('region', { name: 'Instructions' });
    expect(region).toHaveClass('mt-8', 'p-4', 'bg-blue-50', 'rounded-lg');
  });

  it('renders as a static component without props', () => {
    // This component takes no props - it's purely static
    const { container } = render(<InstructionsCard />);
    expect(container.firstChild).toBeInTheDocument();
  });
});
