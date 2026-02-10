import React, { useState } from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { LocationFilter } from '../LocationFilter';
import type { FilterState } from '../../filterTypes';

type LocationValue = FilterState['location'];

/**
 * Harness wraps LocationFilter with local state so the dropdown actually opens.
 */
function Harness({ initialValue = 'any' }: { initialValue?: LocationValue }) {
  const [isOpen, setOpen] = useState(false);
  const [value, setValue] = useState<LocationValue>(initialValue);

  return (
    <LocationFilter
      isOpen={isOpen}
      onToggle={() => setOpen((prev) => !prev)}
      value={value}
      onChange={setValue}
      onClose={() => setOpen(false)}
    />
  );
}

describe('LocationFilter', () => {
  it('shows "Location" label when value is "any"', () => {
    render(<Harness />);

    expect(screen.getByRole('button', { name: 'Location' })).toBeInTheDocument();
  });

  it('shows the option label when a specific location is selected', () => {
    render(<Harness initialValue="online" />);

    expect(screen.getByRole('button', { name: 'Online only' })).toBeInTheDocument();
  });

  it('shows "Travels to me" label for travels value', () => {
    render(<Harness initialValue="travels" />);

    expect(screen.getByRole('button', { name: 'Travels to me' })).toBeInTheDocument();
  });

  it('shows "At their studio" label for studio value', () => {
    render(<Harness initialValue="studio" />);

    expect(screen.getByRole('button', { name: 'At their studio' })).toBeInTheDocument();
  });

  it('falls back to "Location" label when value does not match any option', () => {
    const onChange = jest.fn();
    const onToggle = jest.fn();
    const onClose = jest.fn();

    // Force an unrecognized value to cover the `|| 'Location'` fallback
    render(
      <LocationFilter
        isOpen={false}
        onToggle={onToggle}
        value={'nonexistent' as LocationValue}
        onChange={onChange}
        onClose={onClose}
      />
    );

    expect(screen.getByRole('button', { name: 'Location' })).toBeInTheDocument();
  });

  it('resets draft when re-opening the dropdown after unsaved changes', async () => {
    const user = userEvent.setup();
    render(<Harness initialValue="online" />);

    // Open
    await user.click(screen.getByRole('button', { name: 'Online only' }));

    // Change selection to "Travels to me"
    await user.click(screen.getByRole('radio', { name: 'Travels to me' }));

    // Close without applying (exercises isOpen=true path of handleToggle)
    await user.click(screen.getByRole('button', { name: 'Online only' }));

    // Re-open: draft should be reset to the committed value (online)
    await user.click(screen.getByRole('button', { name: 'Online only' }));

    expect(screen.getByRole('radio', { name: 'Online only' })).toBeChecked();
    expect(screen.getByRole('radio', { name: 'Travels to me' })).not.toBeChecked();
  });

  it('preserves draft changes while the dropdown stays open (isOpen=true path)', async () => {
    const user = userEvent.setup();
    render(<Harness initialValue="online" />);

    // Open
    await user.click(screen.getByRole('button', { name: 'Online only' }));

    // Change selection in draft
    await user.click(screen.getByRole('radio', { name: 'At their studio' }));

    // Apply -- proves draft edits survived while open
    await user.click(screen.getByRole('button', { name: 'Apply' }));

    expect(screen.getByRole('button', { name: 'At their studio' })).toBeInTheDocument();
  });

  it('applies the selected location', async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(screen.getByRole('button', { name: 'Location' }));
    await user.click(screen.getByRole('radio', { name: 'At their studio' }));
    await user.click(screen.getByRole('button', { name: 'Apply' }));

    expect(screen.getByRole('button', { name: 'At their studio' })).toBeInTheDocument();
  });

  it('clears the filter back to "any" and closes the dropdown', async () => {
    const user = userEvent.setup();
    render(<Harness initialValue="studio" />);

    await user.click(screen.getByRole('button', { name: 'At their studio' }));
    await user.click(screen.getByRole('button', { name: 'Clear' }));

    expect(screen.getByRole('button', { name: 'Location' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Location' })).not.toBeInTheDocument();
  });
});
