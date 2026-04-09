import { fireEvent, render, screen } from '@testing-library/react';

import { ToggleSwitch } from '../ToggleSwitch';

describe('ToggleSwitch', () => {
  it('renders the checked state with the shared purple track and custom class name', () => {
    const onChange = jest.fn();

    render(
      <ToggleSwitch
        checked
        onChange={onChange}
        ariaLabel="Marketing emails"
        title="Marketing emails"
        className="ring-2"
      />
    );

    const toggle = screen.getByRole('switch', { name: 'Marketing emails' });
    expect(toggle).toHaveClass('bg-(--color-brand-dark)', 'cursor-pointer', 'ring-2');
    expect(toggle).toHaveAttribute('title', 'Marketing emails');

    fireEvent.click(toggle);
    expect(onChange).toHaveBeenCalledTimes(1);
  });

  it('renders the disabled unchecked state with the neutral track', () => {
    render(<ToggleSwitch checked={false} onChange={jest.fn()} ariaLabel="SMS alerts" disabled />);

    const toggle = screen.getByRole('switch', { name: 'SMS alerts' });
    expect(toggle).toHaveClass('bg-gray-200', 'cursor-not-allowed', 'opacity-50');
    expect(toggle).toHaveAttribute('aria-checked', 'false');
    expect(toggle).toHaveAttribute('aria-disabled', 'true');
  });
});
