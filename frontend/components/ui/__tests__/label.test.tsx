import { render, screen } from '@testing-library/react';
import { createRef } from 'react';
import { Label } from '../label';

describe('Label', () => {
  it('renders with children text', () => {
    render(<Label>Username</Label>);

    expect(screen.getByText('Username')).toBeInTheDocument();
  });

  it('renders as a label element', () => {
    render(<Label>Email</Label>);

    expect(screen.getByText('Email').tagName).toBe('LABEL');
  });

  it('applies htmlFor attribute', () => {
    render(<Label htmlFor="email-input">Email</Label>);

    expect(screen.getByText('Email')).toHaveAttribute('for', 'email-input');
  });

  it('applies custom className', () => {
    render(<Label className="custom-label">Password</Label>);

    expect(screen.getByText('Password')).toHaveClass('custom-label');
  });

  it('preserves default styling classes', () => {
    render(<Label>Name</Label>);

    const label = screen.getByText('Name');
    expect(label).toHaveClass('text-sm');
    expect(label).toHaveClass('font-medium');
  });

  it('forwards ref to label element', () => {
    const ref = createRef<HTMLLabelElement>();
    render(<Label ref={ref}>Test</Label>);

    expect(ref.current).toBeInstanceOf(HTMLLabelElement);
    expect(ref.current?.textContent).toBe('Test');
  });

  it('passes through additional HTML attributes', () => {
    render(<Label data-testid="my-label" id="label-id">Field</Label>);

    const label = screen.getByTestId('my-label');
    expect(label).toHaveAttribute('id', 'label-id');
  });

  it('renders with complex children', () => {
    render(
      <Label>
        Required <span>*</span>
      </Label>
    );

    expect(screen.getByText('Required')).toBeInTheDocument();
    expect(screen.getByText('*')).toBeInTheDocument();
  });

  it('has correct displayName', () => {
    expect(Label.displayName).toBe('Label');
  });
});
