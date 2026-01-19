import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Input } from '../input';

describe('Input', () => {
  it('renders with placeholder', () => {
    render(<Input placeholder="Enter text" />);

    expect(screen.getByPlaceholderText('Enter text')).toBeInTheDocument();
  });

  it('uses default type text', () => {
    render(<Input />);

    expect(screen.getByRole('textbox')).toHaveAttribute('type', 'text');
  });

  it('supports custom type', () => {
    render(<Input type="password" aria-label="Password" />);

    expect(screen.getByLabelText('Password')).toHaveAttribute('type', 'password');
  });

  it('fires onChange', async () => {
    const onChange = jest.fn();
    const user = userEvent.setup();
    render(<Input onChange={onChange} />);

    await user.type(screen.getByRole('textbox'), 'hello');
    expect(onChange).toHaveBeenCalled();
  });

  it('applies custom className', () => {
    render(<Input className="custom-class" />);

    expect(screen.getByRole('textbox')).toHaveClass('custom-class');
  });
});
