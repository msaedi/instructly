import React, { useState } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { PriceFilter } from '../PriceFilter';

/**
 * Harness wraps PriceFilter with local state so the dropdown actually opens
 * (FilterButton needs `isOpen` flipped via onToggle to render portal content).
 */
function Harness({
  initialMin = null,
  initialMax = null,
}: {
  initialMin?: number | null;
  initialMax?: number | null;
}) {
  const [isOpen, setOpen] = useState(false);
  const [min, setMin] = useState<number | null>(initialMin);
  const [max, setMax] = useState<number | null>(initialMax);

  return (
    <PriceFilter
      isOpen={isOpen}
      onToggle={() => setOpen((prev) => !prev)}
      min={min}
      max={max}
      onChange={(newMin, newMax) => {
        setMin(newMin);
        setMax(newMax);
      }}
      onClose={() => setOpen(false)}
    />
  );
}

describe('PriceFilter', () => {
  it('opens dropdown on click and shows the range sliders', async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(screen.getByRole('button', { name: 'Price' }));

    expect(screen.getByText('Price Range')).toBeInTheDocument();
    const sliders = screen.getAllByRole('slider');
    expect(sliders).toHaveLength(2);
  });

  it('enforces min gap when dragging the min range slider near max', async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(screen.getByRole('button', { name: 'Price' }));

    const sliders = screen.getAllByRole('slider');
    const minSlider = sliders[0]!;

    // Try to set min slider to a value near the max (300) — should be capped at max - 10
    fireEvent.change(minSlider, { target: { value: '295' } });

    // The min display should show $290/hr (300 - MIN_GAP of 10)
    expect(screen.getByText('$290/hr')).toBeInTheDocument();
  });

  it('enforces min gap when dragging the max range slider near min', async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(screen.getByRole('button', { name: 'Price' }));

    const sliders = screen.getAllByRole('slider');
    const maxSlider = sliders[1]!;

    // Try to set max below min (30) — should be capped at min + 10
    fireEvent.change(maxSlider, { target: { value: '25' } });

    // The max display should show $40/hr (30 + MIN_GAP of 10)
    expect(screen.getByText('$40/hr')).toBeInTheDocument();
  });

  it('keeps both values null when applying at default boundaries', async () => {
    const user = userEvent.setup();
    render(<Harness />);

    // Open the dropdown
    await user.click(screen.getByRole('button', { name: 'Price' }));

    // Apply with default values (min=30, max=300 — both at boundary → null)
    await user.click(screen.getByRole('button', { name: 'Apply' }));

    // Button should still show "Price" (inactive) because no actual filter is applied
    expect(screen.getByRole('button', { name: 'Price' })).toBeInTheDocument();
  });

  it('sends actual values when inside the boundary range', async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(screen.getByRole('button', { name: 'Price' }));

    // Change the number inputs (spinbuttons)
    const spinbuttons = screen.getAllByRole('spinbutton');
    fireEvent.change(spinbuttons[0]!, { target: { value: '50' } });
    fireEvent.change(spinbuttons[1]!, { target: { value: '200' } });

    await user.click(screen.getByRole('button', { name: 'Apply' }));

    // Now the button label should reflect the applied filter
    expect(screen.getByRole('button', { name: '$50 - $200' })).toBeInTheDocument();
  });
});
