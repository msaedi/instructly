import { render, screen } from '@testing-library/react';
import NoTravelIcon from '../NoTravelIcon';

describe('NoTravelIcon', () => {
  it('renders with a slash overlay when a test id is provided', () => {
    render(<NoTravelIcon data-testid="no-travel-icon" />);

    expect(screen.getByTestId('no-travel-icon')).toBeInTheDocument();
    expect(screen.getByTestId('no-travel-icon-slash')).toBeInTheDocument();
    expect(screen.getByTestId('no-travel-icon-slash').querySelector('line')).toBeInTheDocument();
  });

  it('renders without exposing a slash test id when none is requested', () => {
    const { container } = render(<NoTravelIcon className="custom-icon" />);

    expect(container.querySelector('.custom-icon')).toBeInTheDocument();
    expect(screen.queryByTestId('no-travel-icon-slash')).not.toBeInTheDocument();
  });

  it('applies a custom slash class when provided', () => {
    render(<NoTravelIcon data-testid="no-travel-custom" slashClassName="text-rose-500" />);

    expect(screen.getByTestId('no-travel-custom-slash')).toHaveClass('text-rose-500');
  });
});
