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

  it('shows label with only min set (max defaults to PRICE_MAX)', () => {
    render(<Harness initialMin={50} initialMax={null} />);

    // Label should show "$50 - $300" since max is null and falls back to PRICE_MAX
    expect(screen.getByRole('button', { name: '$50 - $300' })).toBeInTheDocument();
  });

  it('shows label with only max set (min defaults to PRICE_MIN)', () => {
    render(<Harness initialMin={null} initialMax={200} />);

    // Label should show "$30 - $200" since min is null and falls back to PRICE_MIN
    expect(screen.getByRole('button', { name: '$30 - $200' })).toBeInTheDocument();
  });

  it('preserves draft changes while the dropdown stays open (isOpen=true path)', async () => {
    const user = userEvent.setup();
    render(<Harness initialMin={50} initialMax={200} />);

    // Open
    await user.click(screen.getByRole('button', { name: '$50 - $200' }));

    // Modify draft min
    const spinbuttons = screen.getAllByRole('spinbutton');
    fireEvent.change(spinbuttons[0]!, { target: { value: '80' } });

    // Apply -- proves draft edits survived while open (isOpen=true path of handleToggle)
    await user.click(screen.getByRole('button', { name: 'Apply' }));

    expect(screen.getByRole('button', { name: '$80 - $200' })).toBeInTheDocument();
  });

  it('resets draft when re-opening the dropdown after unsaved changes', async () => {
    const user = userEvent.setup();
    render(<Harness initialMin={50} initialMax={200} />);

    // Open
    await user.click(screen.getByRole('button', { name: '$50 - $200' }));

    // Change the min draft
    const spinbuttons = screen.getAllByRole('spinbutton');
    fireEvent.change(spinbuttons[0]!, { target: { value: '100' } });

    // Close without applying
    await user.click(screen.getByRole('button', { name: '$50 - $200' }));

    // Re-open: draft should be reset to committed values
    await user.click(screen.getByRole('button', { name: '$50 - $200' }));

    const resetSpinbuttons = screen.getAllByRole('spinbutton');
    expect(resetSpinbuttons[0]).toHaveValue(50);
    expect(resetSpinbuttons[1]).toHaveValue(200);
  });

  it('clamps min number input to PRICE_MIN when set below', async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(screen.getByRole('button', { name: 'Price' }));

    const spinbuttons = screen.getAllByRole('spinbutton');
    // Try to set min below PRICE_MIN (30)
    fireEvent.change(spinbuttons[0]!, { target: { value: '10' } });

    // Should be clamped to PRICE_MIN (30)
    expect(screen.getByText('$30/hr')).toBeInTheDocument();
  });

  it('clamps max number input to PRICE_MAX when set above', async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(screen.getByRole('button', { name: 'Price' }));

    const spinbuttons = screen.getAllByRole('spinbutton');
    // Try to set max above PRICE_MAX (300)
    fireEvent.change(spinbuttons[1]!, { target: { value: '500' } });

    // Should be clamped to PRICE_MAX (300)
    expect(screen.getByText('$300/hr')).toBeInTheDocument();
  });

  it('clears the filter and closes the dropdown', async () => {
    const user = userEvent.setup();
    render(<Harness initialMin={50} initialMax={200} />);

    await user.click(screen.getByRole('button', { name: '$50 - $200' }));
    await user.click(screen.getByRole('button', { name: 'Clear' }));

    expect(screen.getByRole('button', { name: 'Price' })).toBeInTheDocument();
    expect(screen.queryByText('Price Range')).not.toBeInTheDocument();
  });
});
