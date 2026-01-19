import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import BackButton from '../BackButton';
import { useRouter } from 'next/navigation';

jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
}));

const useRouterMock = useRouter as jest.Mock;

describe('BackButton', () => {
  const back = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
    useRouterMock.mockReturnValue({ back });
  });

  it('renders children', () => {
    render(<BackButton>Go Back</BackButton>);

    expect(screen.getByRole('button', { name: /go back/i })).toBeInTheDocument();
  });

  it('applies className', () => {
    render(<BackButton className="custom-class">Go Back</BackButton>);

    expect(screen.getByRole('button', { name: /go back/i })).toHaveClass('custom-class');
  });

  it('calls router.back on click', async () => {
    const user = userEvent.setup();
    render(<BackButton>Go Back</BackButton>);

    await user.click(screen.getByRole('button', { name: /go back/i }));
    expect(back).toHaveBeenCalled();
  });

  it('supports nested content', () => {
    render(
      <BackButton>
        <span>Return</span>
      </BackButton>
    );

    expect(screen.getByText('Return')).toBeInTheDocument();
  });

  it('renders as a button element', () => {
    const { container } = render(<BackButton>Back</BackButton>);

    expect(container.querySelector('button')).toBeInTheDocument();
  });
});
