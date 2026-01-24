import { fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React, { useState } from 'react';

import { FilterBar } from '../FilterBar';
import { DEFAULT_FILTERS, type FilterState } from '../filterTypes';

const Harness = ({ initialFilters = DEFAULT_FILTERS }: { initialFilters?: FilterState }) => {
  const [filters, setFilters] = useState<FilterState>(initialFilters);

  return (
    <FilterBar
      filters={filters}
      onFiltersChange={setFilters}
      rightSlot={<div>Sort</div>}
    />
  );
};

describe('FilterBar', () => {
  it('renders filter buttons and keeps only one dropdown open at a time', async () => {
    const user = userEvent.setup();
    render(<Harness />);

    expect(screen.getByRole('button', { name: 'Date' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Time' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Price' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Location' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /more filters/i })).toBeInTheDocument();
    expect(screen.getByText('Sort')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Date' }));
    expect(screen.getByText('Select Date')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Time' }));
    expect(screen.getByText('Time of Day')).toBeInTheDocument();
    expect(screen.queryByText('Select Date')).not.toBeInTheDocument();
  });

  it('applies date, time, price, and location filters', async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(screen.getByRole('button', { name: 'Date' }));
    const dateInput = screen.getByLabelText('Select date') as HTMLInputElement;
    fireEvent.change(dateInput, { target: { value: '2025-01-20' } });
    await user.click(screen.getByRole('button', { name: 'Apply' }));
    expect(screen.getByRole('button', { name: /jan 20/i })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Time' }));
    const morningLabel = screen.getByText('Morning').closest('label');
    expect(morningLabel).toBeTruthy();
    if (morningLabel) {
      await user.click(morningLabel);
    }
    await user.click(screen.getByRole('button', { name: 'Apply' }));
    expect(screen.getByRole('button', { name: 'Morning' })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Price' }));
    const spinbuttons = screen.getAllByRole('spinbutton');
    if (!spinbuttons[0] || !spinbuttons[1]) {
      throw new Error('Expected price inputs');
    }
    fireEvent.change(spinbuttons[0], { target: { value: '50' } });
    fireEvent.change(spinbuttons[1], { target: { value: '200' } });
    await user.click(screen.getByRole('button', { name: 'Apply' }));
    expect(screen.getByRole('button', { name: '$50 - $200' })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Location' }));
    await user.click(screen.getByLabelText('Online only'));
    await user.click(screen.getByRole('button', { name: 'Apply' }));
    expect(screen.getByRole('button', { name: 'Online only' })).toBeInTheDocument();
  });

  it('applies more filters and shows count badge', async () => {
    const user = userEvent.setup();
    render(<Harness />);

    const moreButton = screen.getByRole('button', { name: /more filters/i });
    await user.click(moreButton);

    await user.click(screen.getByText('30 min'));
    await user.click(screen.getByText('Beginner'));
    await user.click(screen.getByText('Kids (under 18)'));
    await user.click(screen.getByText('4.5+ stars'));

    await user.click(screen.getByRole('button', { name: 'Apply' }));

    const badge = within(screen.getByRole('button', { name: /more filters/i })).getByText('4');
    expect(badge).toBeInTheDocument();
  });

  it('closes dropdowns on escape', async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(screen.getByRole('button', { name: 'Location' }));
    expect(screen.getByRole('heading', { name: 'Location' })).toBeInTheDocument();

    await user.keyboard('{Escape}');
    expect(screen.queryByRole('heading', { name: 'Location' })).not.toBeInTheDocument();
  });

  it('clears active filters from dropdowns and modal', async () => {
    const user = userEvent.setup();
    render(
      <Harness
        initialFilters={{
          date: '2025-01-20',
          timeOfDay: ['morning', 'evening'],
          duration: [30],
          priceMin: 50,
          priceMax: 200,
          location: 'online',
          level: ['beginner'],
          audience: ['kids'],
          minRating: '4',
        }}
      />
    );

    expect(screen.getByRole('button', { name: '2 times' })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /jan 20/i }));
    await user.click(screen.getByRole('button', { name: 'Clear' }));
    expect(screen.getByRole('button', { name: 'Date' })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: '2 times' }));
    await user.click(screen.getByRole('button', { name: 'Clear' }));
    expect(screen.getByRole('button', { name: 'Time' })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: '$50 - $200' }));
    await user.click(screen.getByRole('button', { name: 'Clear' }));
    expect(screen.getByRole('button', { name: 'Price' })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Online only' }));
    await user.click(screen.getByRole('button', { name: 'Clear' }));
    expect(screen.getByRole('button', { name: 'Location' })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /more filters/i }));
    await user.click(screen.getByRole('button', { name: /clear all/i }));
    const moreButton = screen.getByRole('button', { name: /more filters/i });
    expect(within(moreButton).queryByText('4')).not.toBeInTheDocument();
  });
});
