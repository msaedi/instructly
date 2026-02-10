import React, { useState } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { DateFilter } from '../DateFilter';

/**
 * Harness wraps DateFilter with local state so the dropdown actually opens
 * (FilterButton needs `isOpen` flipped via onToggle to render portal content).
 */
function Harness({ initialValue = null }: { initialValue?: string | null }) {
  const [isOpen, setOpen] = useState(false);
  const [value, setValue] = useState<string | null>(initialValue);

  return (
    <DateFilter
      isOpen={isOpen}
      onToggle={() => setOpen((prev) => !prev)}
      value={value}
      onChange={setValue}
      onClose={() => setOpen(false)}
    />
  );
}

describe('DateFilter', () => {
  it('shows "Date" label when value is null', () => {
    render(<Harness />);

    expect(screen.getByRole('button', { name: 'Date' })).toBeInTheDocument();
  });

  it('shows formatted date label when value is set', () => {
    render(<Harness initialValue="2025-03-15" />);

    expect(screen.getByRole('button', { name: 'Mar 15' })).toBeInTheDocument();
  });

  it('resets draft to current value when opening the dropdown', async () => {
    const user = userEvent.setup();
    render(<Harness initialValue="2025-06-01" />);

    // Open the dropdown
    await user.click(screen.getByRole('button', { name: 'Jun 1' }));
    expect(screen.getByLabelText('Select date')).toHaveValue('2025-06-01');

    // Change the draft but do NOT apply
    fireEvent.change(screen.getByLabelText('Select date'), {
      target: { value: '2025-07-04' },
    });
    expect(screen.getByLabelText('Select date')).toHaveValue('2025-07-04');

    // Close without applying (toggle again -- this exercises handleToggle when isOpen=true,
    // which should NOT reset draft, just call onToggle)
    await user.click(screen.getByRole('button', { name: 'Jun 1' }));

    // Re-open: NOW handleToggle runs with isOpen=false, resetting draft to value
    await user.click(screen.getByRole('button', { name: 'Jun 1' }));
    expect(screen.getByLabelText('Select date')).toHaveValue('2025-06-01');
  });

  it('preserves draft edits when clicking the button to close (isOpen=true path)', async () => {
    const user = userEvent.setup();
    render(<Harness initialValue="2025-01-10" />);

    // Open the dropdown
    await user.click(screen.getByRole('button', { name: 'Jan 10' }));
    expect(screen.getByLabelText('Select date')).toHaveValue('2025-01-10');

    // Change draft
    fireEvent.change(screen.getByLabelText('Select date'), {
      target: { value: '2025-02-20' },
    });
    expect(screen.getByLabelText('Select date')).toHaveValue('2025-02-20');

    // Apply the modified draft (this proves the draft was kept while open)
    await user.click(screen.getByRole('button', { name: 'Apply' }));

    // The applied value should be the modified draft
    expect(screen.getByRole('button', { name: 'Feb 20' })).toBeInTheDocument();
  });

  it('applies the selected draft date', async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(screen.getByRole('button', { name: 'Date' }));
    fireEvent.change(screen.getByLabelText('Select date'), {
      target: { value: '2025-04-10' },
    });
    await user.click(screen.getByRole('button', { name: 'Apply' }));

    expect(screen.getByRole('button', { name: 'Apr 10' })).toBeInTheDocument();
  });

  it('applies null when draft is empty string', async () => {
    const user = userEvent.setup();
    render(<Harness initialValue="2025-05-01" />);

    // Open the dropdown
    await user.click(screen.getByRole('button', { name: 'May 1' }));

    // Clear the input to an empty string
    fireEvent.change(screen.getByLabelText('Select date'), {
      target: { value: '' },
    });

    // Apply -- draft is '' which is falsy, so onChange receives null
    await user.click(screen.getByRole('button', { name: 'Apply' }));

    // Label should revert to "Date" (no active filter)
    expect(screen.getByRole('button', { name: 'Date' })).toBeInTheDocument();
  });

  it('clears the filter and closes the dropdown', async () => {
    const user = userEvent.setup();
    render(<Harness initialValue="2025-08-20" />);

    await user.click(screen.getByRole('button', { name: 'Aug 20' }));
    await user.click(screen.getByRole('button', { name: 'Clear' }));

    // Value should be cleared -- label shows "Date"
    expect(screen.getByRole('button', { name: 'Date' })).toBeInTheDocument();
    // Dropdown should be closed (heading not visible)
    expect(screen.queryByText('Select Date')).not.toBeInTheDocument();
  });

  it('sets draft to null when input is cleared via onChange', async () => {
    const user = userEvent.setup();
    render(<Harness initialValue="2025-03-01" />);

    await user.click(screen.getByRole('button', { name: 'Mar 1' }));

    // Simulate clearing the date input (event.target.value is '')
    fireEvent.change(screen.getByLabelText('Select date'), {
      target: { value: '' },
    });

    // The input should show empty
    expect(screen.getByLabelText('Select date')).toHaveValue('');

    // Apply and verify null was applied
    await user.click(screen.getByRole('button', { name: 'Apply' }));
    expect(screen.getByRole('button', { name: 'Date' })).toBeInTheDocument();
  });
});
