import { render, screen } from '@testing-library/react';
import ManhattanMap from '../ManhattanMap';

describe('ManhattanMap', () => {
  it('renders key neighborhood labels', () => {
    render(<ManhattanMap highlightedAreas={[]} />);

    expect(screen.getByText('Inwood')).toBeInTheDocument();
    expect(screen.getByText('Midtown')).toBeInTheDocument();
    expect(screen.getByText('FiDi')).toBeInTheDocument();
  });

  it('highlights matching areas case-insensitively', () => {
    render(<ManhattanMap highlightedAreas={['upper east side']} />);

    const eastSide = screen.getByText(/Upper\s*East Side/i);
    expect(eastSide.className).toMatch(/bg-purple-200/);
  });

  it('highlights when abbreviations are provided', () => {
    render(<ManhattanMap highlightedAreas={['UES']} />);

    const eastSide = screen.getByText(/Upper\s*East Side/i);
    expect(eastSide.className).toMatch(/bg-purple-200/);
  });

  it('highlights Battery Park areas by partial match', () => {
    render(<ManhattanMap highlightedAreas={['Battery Park']} />);

    const battery = screen.getByText('Battery');
    expect(battery.className).toMatch(/bg-purple-100/);
  });

  it('keeps non-highlighted areas in gray', () => {
    render(<ManhattanMap highlightedAreas={['SoHo']} />);

    const chinatown = screen.getByText('Chinatown');
    expect(chinatown.className).toMatch(/bg-gray-100/);
  });
});
