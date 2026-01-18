import { render, screen } from '@testing-library/react';
import PreviewRibbon from '../PreviewRibbon';

describe('PreviewRibbon', () => {
  it('renders preview text', () => {
    render(<PreviewRibbon />);

    expect(screen.getByText('PREVIEW')).toBeInTheDocument();
  });

  it('applies fixed positioning styles', () => {
    render(<PreviewRibbon />);

    const ribbon = screen.getByText('PREVIEW');
    expect(ribbon).toHaveStyle({ position: 'fixed' });
    expect(ribbon).toHaveStyle({ transform: 'rotate(45deg)' });
  });

  it('sets non-interactive pointer events', () => {
    render(<PreviewRibbon />);

    const ribbon = screen.getByText('PREVIEW');
    expect(ribbon).toHaveStyle({ pointerEvents: 'none' });
  });
});
