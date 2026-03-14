import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { TAG_NO_TRAVEL, TAG_NONE, TAG_ONLINE_ONLY } from '@/lib/calendar/bitset';
import FormatTagPaintToolbar from '../FormatTagPaintToolbar';

describe('FormatTagPaintToolbar', () => {
  it('renders the availability label, ordered options, descriptions, and notifies on change', async () => {
    const user = userEvent.setup();
    const onChange = jest.fn();

    render(
      <FormatTagPaintToolbar
        availableTagOptions={[TAG_ONLINE_ONLY, TAG_NO_TRAVEL]}
        value={TAG_NONE}
        onChange={onChange}
      />
    );

    expect(screen.getByText('Availability')).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: /All.*All lesson formats/i })).toHaveAttribute(
      'aria-checked',
      'true'
    );
    expect(screen.getByRole('radio', { name: /No Travel.*Online and studio only/i })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: /Online.*Online lessons only/i })).toBeInTheDocument();
    expect(screen.getByTestId('paint-mode-no-travel-icon')).toBeInTheDocument();
    expect(screen.getAllByRole('radio').map((item) => item.textContent)).toEqual([
      expect.stringContaining('All'),
      expect.stringContaining('No Travel'),
      expect.stringContaining('Online'),
    ]);

    await user.click(screen.getByRole('radio', { name: /No Travel.*Online and studio only/i }));

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
      screen.queryByRole('radio', { name: /Online.*Online lessons only/i })
    ).not.toBeInTheDocument();
  });
});
