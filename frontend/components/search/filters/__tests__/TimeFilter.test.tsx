import React, { useState } from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { TimeFilter } from '../TimeFilter';

type TimeValue = 'morning' | 'afternoon' | 'evening';

/**
 * Harness wraps TimeFilter with local state so the dropdown actually opens.
 */
function Harness({ initialValue = [] }: { initialValue?: TimeValue[] }) {
  const [isOpen, setOpen] = useState(false);
  const [value, setValue] = useState<TimeValue[]>(initialValue);

  return (
    <TimeFilter
      isOpen={isOpen}
      onToggle={() => setOpen((prev) => !prev)}
      value={value}
      onChange={setValue}
      onClose={() => setOpen(false)}
    />
  );
}

describe('TimeFilter', () => {
  it('shows "Time" label when no times are selected', () => {
    render(<Harness />);

    expect(screen.getByRole('button', { name: 'Time' })).toBeInTheDocument();
  });

  it('shows the single option label when exactly one time is selected', () => {
    render(<Harness initialValue={['afternoon']} />);

    expect(screen.getByRole('button', { name: 'Afternoon' })).toBeInTheDocument();
  });

  it('shows count label when multiple times are selected', () => {
    render(<Harness initialValue={['morning', 'evening']} />);

    expect(screen.getByRole('button', { name: '2 times' })).toBeInTheDocument();
  });

  it('shows count label when all three are selected', () => {
    render(<Harness initialValue={['morning', 'afternoon', 'evening']} />);

    expect(screen.getByRole('button', { name: '3 times' })).toBeInTheDocument();
  });

  it('adds a time when clicking an unchecked checkbox', async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(screen.getByRole('button', { name: 'Time' }));

    // Check "Evening" via its checkbox (avoid label text collision with button)
    const eveningCheckbox = screen.getByRole('checkbox', { name: /evening/i });
    await user.click(eveningCheckbox);

    await user.click(screen.getByRole('button', { name: 'Apply' }));

    expect(screen.getByRole('button', { name: 'Evening' })).toBeInTheDocument();
  });

  it('removes a time when clicking an already-checked checkbox', async () => {
    const user = userEvent.setup();
    render(<Harness initialValue={['morning', 'evening']} />);

    await user.click(screen.getByRole('button', { name: '2 times' }));

    // Uncheck "Morning" via its checkbox
    const morningCheckbox = screen.getByRole('checkbox', { name: /morning/i });
    await user.click(morningCheckbox);

    await user.click(screen.getByRole('button', { name: 'Apply' }));

    // Only "Evening" remains -- single label
    expect(screen.getByRole('button', { name: 'Evening' })).toBeInTheDocument();
  });

  it('resets draft when re-opening the dropdown after unsaved changes', async () => {
    const user = userEvent.setup();
    render(<Harness initialValue={['morning']} />);

    // Open and modify draft
    await user.click(screen.getByRole('button', { name: 'Morning' }));
    const eveningCheckbox = screen.getByRole('checkbox', { name: /evening/i });
    await user.click(eveningCheckbox);

    // Close without applying (toggle off -- exercises isOpen=true path of handleToggle)
    await user.click(screen.getByRole('button', { name: 'Morning' }));

    // Re-open: draft should be reset to the committed value (just morning)
    await user.click(screen.getByRole('button', { name: 'Morning' }));

    expect(screen.getByRole('checkbox', { name: /morning/i })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: /evening/i })).not.toBeChecked();
  });

  it('preserves draft changes while the dropdown stays open (isOpen=true path)', async () => {
    const user = userEvent.setup();
    render(<Harness initialValue={['morning']} />);

    // Open
    await user.click(screen.getByRole('button', { name: 'Morning' }));

    // Modify draft by toggling "Afternoon"
    const afternoonCheckbox = screen.getByRole('checkbox', { name: /afternoon/i });
    await user.click(afternoonCheckbox);

    // Apply the draft -- proves draft edits survived while open
    await user.click(screen.getByRole('button', { name: 'Apply' }));

    expect(screen.getByRole('button', { name: '2 times' })).toBeInTheDocument();
  });

  it('clears all selections and closes the dropdown', async () => {
    const user = userEvent.setup();
    render(<Harness initialValue={['morning', 'afternoon']} />);

    await user.click(screen.getByRole('button', { name: '2 times' }));
    await user.click(screen.getByRole('button', { name: 'Clear' }));

    expect(screen.getByRole('button', { name: 'Time' })).toBeInTheDocument();
    expect(screen.queryByText('Time of Day')).not.toBeInTheDocument();
  });

  it('falls back to "Time" label when single value does not match any option', () => {
    // This tests the `|| 'Time'` fallback in the label computation.
    // We force an unrecognized value via type assertion to cover the fallback branch.
    const onChange = jest.fn();
    const onToggle = jest.fn();
    const onClose = jest.fn();

    render(
      <TimeFilter
        isOpen={false}
        onToggle={onToggle}
        value={['unknown_value' as TimeValue]}
        onChange={onChange}
        onClose={onClose}
      />
    );

    // The find() won't match, so fallback label should be 'Time'
    expect(screen.getByRole('button', { name: 'Time' })).toBeInTheDocument();
  });
});
