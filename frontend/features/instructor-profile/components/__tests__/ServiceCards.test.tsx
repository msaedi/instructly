import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ServiceCards } from '../ServiceCards';

const baseService = {
  id: 'svc-1',
  skill: 'Piano',
  hourly_rate: 120,
  duration_options: [30, 60],
  age_groups: ['adults'],
  levels_taught: ['beginner', 'intermediate'],
  location_types: ['in-person'],
  description: '',
};

describe('ServiceCards', () => {
  it('shows an empty state when no services are available', () => {
    render(<ServiceCards services={[]} />);

    expect(screen.getByText(/no services available/i)).toBeInTheDocument();
  });

  it('books a service with the selected duration', async () => {
    const user = userEvent.setup();
    const onBookService = jest.fn();

    render(<ServiceCards services={[baseService]} onBookService={onBookService} />);

    await user.click(screen.getByLabelText(/60min/i));
    await user.click(screen.getByTestId('book-service-piano'));

    expect(onBookService).toHaveBeenCalledWith(expect.objectContaining({ id: 'svc-1' }), 60);
    expect(screen.getByText('$120')).toBeInTheDocument();
  });

  it('renders badges and labels for kids, levels, and formats', () => {
    const service = {
      ...baseService,
      id: 'svc-2',
      skill: 'Guitar',
      age_groups: ['kids'],
      levels_taught: ['advanced', 'beginner'],
      location_types: ['online', 'in-person'],
      description: '',
    };

    render(<ServiceCards services={[service]} />);

    const kidsBadge = screen.getByText(/kids lesson available/i);
    expect(kidsBadge).toBeInTheDocument();
    expect(kidsBadge).not.toHaveClass('opacity-0');
    expect(screen.getByText((value) => value.includes('Levels:') && value.includes('Beginner') && value.includes('Advanced'))).toBeInTheDocument();
    expect(
      screen.getByText((value) => {
        const lower = value.toLowerCase();
        return lower.includes('format:') && lower.includes('in-person') && lower.includes('online');
      })
    ).toBeInTheDocument();
  });

  it('disables booking when the selected slot cannot fit the duration', () => {
    const service = { ...baseService, duration_options: [60] };
    const selectedSlot = { date: '2025-01-06', time: '9:00 AM', duration: 60, availableDuration: 30 };

    render(<ServiceCards services={[service]} selectedSlot={selectedSlot} />);

    const button = screen.getByTestId('book-service-piano');
    expect(button).toBeDisabled();

    const card = screen.getByText('Piano').closest('.transition-all') as HTMLElement;
    fireEvent.mouseEnter(card);

    expect(screen.getByText(/only 30 minutes available from 9:00 AM/i)).toBeInTheDocument();
  });

  it('prioritizes the searched service first', () => {
    const services = [
      { ...baseService, id: 'svc-1', skill: 'Piano' },
      { ...baseService, id: 'svc-3', skill: 'Guitar' },
    ];

    render(<ServiceCards services={services} searchedService="guitar" />);

    const headings = screen.getAllByRole('heading', { level: 3 });
    expect(headings[0]).toHaveTextContent('Guitar');
  });
});
