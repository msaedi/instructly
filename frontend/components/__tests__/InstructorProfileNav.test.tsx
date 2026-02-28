import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import InstructorProfileNav from '../InstructorProfileNav';
import { useRouter } from 'next/navigation';

jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
}));

const useRouterMock = useRouter as jest.Mock;

describe('InstructorProfileNav', () => {
  const back = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
    useRouterMock.mockReturnValue({ back });
  });

  it('renders instructor name', () => {
    render(<InstructorProfileNav instructorName="Jamie Doe" />);

    expect(screen.getByText('Jamie Doe')).toBeInTheDocument();
  });

  it('navigates back with icon button', async () => {
    const user = userEvent.setup();
    render(<InstructorProfileNav instructorName="Jamie Doe" />);

    await user.click(screen.getByRole('button', { name: /go back/i }));
    expect(back).toHaveBeenCalled();
  });

  it('navigates back with text button', async () => {
    const user = userEvent.setup();
    render(<InstructorProfileNav instructorName="Jamie Doe" />);

    await user.click(screen.getByRole('button', { name: /^back$/i }));
    expect(back).toHaveBeenCalled();
  });

  it('renders two back controls', () => {
    render(<InstructorProfileNav instructorName="Jamie Doe" />);

    expect(screen.getAllByRole('button').length).toBeGreaterThanOrEqual(2);
  });

  it('keeps navigation bar structure', () => {
    const { container } = render(<InstructorProfileNav instructorName="Jamie Doe" />);

    expect(container.querySelector('nav')).toBeInTheDocument();
  });
});
