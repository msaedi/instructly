import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { DashboardTabStrip } from '../DashboardTabStrip';

describe('DashboardTabStrip', () => {
  const tabs = [
    { value: 'first', label: 'First' },
    { value: 'second', label: 'Second' },
    { value: 'third', label: 'Third' },
  ] as const;

  it('renders evenly distributed tabs with the active underline on the button', () => {
    render(
      <DashboardTabStrip
        ariaLabel="Example tabs"
        tabs={tabs}
        value="second"
        onChange={jest.fn()}
      />
    );

    const activeTab = screen.getByRole('tab', { name: 'Second' });
    const inactiveTab = screen.getByRole('tab', { name: 'First' });

    expect(activeTab).toHaveClass(
      'flex-1',
      'border-b-2',
      'border-(--color-brand-dark)',
      'text-(--color-brand-dark)'
    );
    expect(inactiveTab).toHaveClass('flex-1', 'border-transparent');
    expect(screen.getByRole('tablist', { name: 'Example tabs' })).toHaveClass('flex', 'border-b');
  });

  it('emits changes and preserves tab semantics', async () => {
    const user = userEvent.setup();
    const onChange = jest.fn();

    render(
      <DashboardTabStrip
        ariaLabel="Example tabs"
        tabs={tabs}
        value="first"
        onChange={onChange}
      />
    );

    await user.click(screen.getByRole('tab', { name: 'Third' }));

    expect(onChange).toHaveBeenCalledWith('third');
    expect(screen.getByRole('tab', { name: 'First' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: 'Third' })).toHaveAttribute('aria-selected', 'false');
  });
});
