import { render, screen } from '@testing-library/react';
import { Alert, AlertDescription, AlertTitle } from '../alert';

describe('Alert', () => {
  it('renders content with role alert', () => {
    render(<Alert>Message</Alert>);

    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.getByText('Message')).toBeInTheDocument();
  });

  it('supports destructive variant styling', () => {
    render(<Alert variant="destructive">Error</Alert>);

    expect(screen.getByRole('alert').className).toMatch(/bg-red-600\/10/);
  });

  it('supports muted variant styling', () => {
    render(<Alert variant="muted">Muted</Alert>);

    expect(screen.getByRole('alert').className).toMatch(/bg-gray-100\/30/);
  });

  it('renders title and description', () => {
    render(
      <Alert>
        <AlertTitle>Title</AlertTitle>
        <AlertDescription>Details</AlertDescription>
      </Alert>
    );

    expect(screen.getByText('Title')).toBeInTheDocument();
    expect(screen.getByText('Details')).toBeInTheDocument();
  });

  it('applies custom className', () => {
    render(<Alert className="custom-class">Message</Alert>);

    expect(screen.getByRole('alert')).toHaveClass('custom-class');
  });
});
