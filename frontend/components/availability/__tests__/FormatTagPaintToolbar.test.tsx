import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { TAG_NO_TRAVEL, TAG_NONE, TAG_ONLINE_ONLY } from '@/lib/calendar/bitset';
import FormatTagPaintToolbar from '../FormatTagPaintToolbar';

describe('FormatTagPaintToolbar', () => {
  it('renders equal-width chips with the reviewed palette for each selection state', () => {
    const { rerender } = render(
      <FormatTagPaintToolbar
        availableTagOptions={[TAG_ONLINE_ONLY, TAG_NO_TRAVEL]}
        value={TAG_NONE}
        onChange={jest.fn()}
      />
    );

    expect(screen.getByText('Availability format:')).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: /All/i })).toHaveAttribute(
      'aria-checked',
      'true'
    );
    expect(screen.getByRole('radio', { name: /No Travel/i })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: /Online/i })).toBeInTheDocument();
    expect(screen.getByTestId('paint-mode-no-travel-icon')).toBeInTheDocument();
    expect(screen.getAllByRole('radio').map((item) => item.textContent)).toEqual([
      expect.stringContaining('All'),
      expect.stringContaining('Online'),
      expect.stringContaining('No Travel'),
    ]);
    screen.getAllByRole('radio').forEach((item) => {
      expect(item).toHaveClass('w-28');
    });
    expect(screen.getByRole('radio', { name: /All/i })).toHaveClass('bg-(--color-brand)', 'text-white');
    expect(screen.getByRole('radio', { name: /Online/i })).toHaveClass(
      'bg-(--color-online-green-light)',
      'text-(--color-online-green)'
    );
    expect(screen.getByRole('radio', { name: /No Travel/i })).toHaveClass(
      'bg-(--color-notravel-yellow-light)',
      'text-(--color-notravel-brown)'
    );

    rerender(
      <FormatTagPaintToolbar
        availableTagOptions={[TAG_ONLINE_ONLY, TAG_NO_TRAVEL]}
        value={TAG_ONLINE_ONLY}
        onChange={jest.fn()}
      />
    );

    expect(screen.getByRole('radio', { name: /Online/i })).toHaveClass(
      'bg-(--color-online-green)',
      'text-white'
    );
    expect(screen.getByRole('radio', { name: /All/i })).toHaveClass(
      'bg-(--color-brand-lavender)',
      'text-(--color-brand)'
    );

    rerender(
      <FormatTagPaintToolbar
        availableTagOptions={[TAG_ONLINE_ONLY, TAG_NO_TRAVEL]}
        value={TAG_NO_TRAVEL}
        onChange={jest.fn()}
      />
    );

    expect(screen.getByRole('radio', { name: /No Travel/i })).toHaveClass(
      'bg-(--color-notravel-yellow)',
      'text-(--color-notravel-brown)'
    );
  });

  it('notifies on change when another chip is selected', async () => {
    const user = userEvent.setup();
    const onChange = jest.fn();

    render(
      <FormatTagPaintToolbar
        availableTagOptions={[TAG_ONLINE_ONLY, TAG_NO_TRAVEL]}
        value={TAG_NONE}
        onChange={onChange}
      />
    );

    await user.click(screen.getByRole('radio', { name: /No Travel/i }));

    expect(onChange).toHaveBeenCalledWith(TAG_NO_TRAVEL);
  });

  it('renders only all and online when no-travel is unavailable', () => {
    render(
      <FormatTagPaintToolbar
        availableTagOptions={[TAG_ONLINE_ONLY]}
        value={TAG_NONE}
        onChange={jest.fn()}
      />
    );

    expect(screen.getAllByRole('radio').map((item) => item.textContent)).toEqual([
      expect.stringContaining('All'),
      expect.stringContaining('Online'),
    ]);
    expect(screen.queryByRole('radio', { name: /No Travel/i })).not.toBeInTheDocument();
  });

  it('renders only all and no-travel when online is unavailable', () => {
    render(
      <FormatTagPaintToolbar
        availableTagOptions={[TAG_NO_TRAVEL]}
        value={TAG_NONE}
        onChange={jest.fn()}
      />
    );

    expect(screen.getAllByRole('radio').map((item) => item.textContent)).toEqual([
      expect.stringContaining('All'),
      expect.stringContaining('No Travel'),
    ]);
    expect(
      screen.queryByRole('radio', { name: /Online/i })
    ).not.toBeInTheDocument();
  });
});
