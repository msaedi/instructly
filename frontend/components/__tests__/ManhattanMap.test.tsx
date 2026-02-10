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

  // ---- empty highlightedAreas ----

  it('shows all areas as non-highlighted when highlightedAreas is empty', () => {
    render(<ManhattanMap highlightedAreas={[]} />);

    expect(screen.getByText('Inwood').className).toMatch(/bg-gray-100/);
    expect(screen.getByText('Washington Heights').className).toMatch(/bg-gray-100/);
    expect(screen.getByText('Midtown').className).toMatch(/bg-purple-100/);
    expect(screen.getByText('Chinatown').className).toMatch(/bg-gray-100/);
    expect(screen.getByText('Battery').className).toMatch(/bg-gray-100/);
  });

  // ---- bidirectional matching: "Harlem" highlights both W. Harlem and E. Harlem ----

  it('highlights both W. Harlem and E. Harlem when "Harlem" is specified', () => {
    render(<ManhattanMap highlightedAreas={['Harlem']} />);

    const wHarlem = screen.getByText('W. Harlem');
    const eHarlem = screen.getByText('E. Harlem');
    expect(wHarlem.className).toMatch(/bg-purple-100/);
    expect(eHarlem.className).toMatch(/bg-purple-100/);
  });

  it('highlights W. Harlem when "West Harlem" is specified', () => {
    render(<ManhattanMap highlightedAreas={['West Harlem']} />);

    const wHarlem = screen.getByText('W. Harlem');
    expect(wHarlem.className).toMatch(/bg-purple-100/);
  });

  it('highlights E. Harlem when "East Harlem" is specified', () => {
    render(<ManhattanMap highlightedAreas={['East Harlem']} />);

    const eHarlem = screen.getByText('E. Harlem');
    expect(eHarlem.className).toMatch(/bg-purple-100/);
  });

  // ---- individual area highlight branches ----

  it('highlights Inwood', () => {
    render(<ManhattanMap highlightedAreas={['Inwood']} />);

    expect(screen.getByText('Inwood').className).toMatch(/bg-purple-100/);
  });

  it('highlights Washington Heights', () => {
    render(<ManhattanMap highlightedAreas={['Washington Heights']} />);

    expect(screen.getByText('Washington Heights').className).toMatch(/bg-purple-100/);
  });

  it('highlights Upper West Side via UWS abbreviation', () => {
    render(<ManhattanMap highlightedAreas={['UWS']} />);

    const uws = screen.getByText(/Upper\s*West Side/i);
    expect(uws.className).toMatch(/bg-purple-200/);
  });

  it('highlights Upper West Side by full name', () => {
    render(<ManhattanMap highlightedAreas={['Upper West Side']} />);

    const uws = screen.getByText(/Upper\s*West Side/i);
    expect(uws.className).toMatch(/bg-purple-200/);
  });

  it("highlights Hell's Kitchen", () => {
    render(<ManhattanMap highlightedAreas={["Hell's Kitchen"]} />);

    const hk = screen.getByText(/Hell/);
    expect(hk.className).toMatch(/bg-purple-100/);
  });

  it('highlights Murray Hill', () => {
    render(<ManhattanMap highlightedAreas={['Murray Hill']} />);

    const mh = screen.getByText(/Murray/);
    expect(mh.className).toMatch(/bg-purple-100/);
  });

  it('highlights Midtown', () => {
    render(<ManhattanMap highlightedAreas={['Midtown']} />);

    expect(screen.getByText('Midtown').className).toMatch(/bg-purple-200/);
  });

  it('highlights Chelsea', () => {
    render(<ManhattanMap highlightedAreas={['Chelsea']} />);

    expect(screen.getByText('Chelsea').className).toMatch(/bg-purple-200/);
  });

  it('highlights Flatiron', () => {
    render(<ManhattanMap highlightedAreas={['Flatiron']} />);

    expect(screen.getByText('Flatiron').className).toMatch(/bg-purple-100/);
  });

  it('highlights Gramercy', () => {
    render(<ManhattanMap highlightedAreas={['Gramercy']} />);

    expect(screen.getByText('Gramercy').className).toMatch(/bg-purple-100/);
  });

  it('highlights West Village', () => {
    render(<ManhattanMap highlightedAreas={['West Village']} />);

    const wv = screen.getByText(/West\s*Village/);
    expect(wv.className).toMatch(/bg-purple-200/);
  });

  it('highlights Greenwich Village by full name', () => {
    render(<ManhattanMap highlightedAreas={['Greenwich Village']} />);

    const gv = screen.getByText(/Greenwich\s*Village/);
    expect(gv.className).toMatch(/bg-purple-200/);
  });

  it('highlights Greenwich Village by partial name "Greenwich"', () => {
    render(<ManhattanMap highlightedAreas={['Greenwich']} />);

    const gv = screen.getByText(/Greenwich\s*Village/);
    expect(gv.className).toMatch(/bg-purple-200/);
  });

  it('highlights East Village', () => {
    render(<ManhattanMap highlightedAreas={['East Village']} />);

    const ev = screen.getByText(/East\s*Village/);
    expect(ev.className).toMatch(/bg-purple-100/);
  });

  it('highlights SoHo', () => {
    render(<ManhattanMap highlightedAreas={['SoHo']} />);

    expect(screen.getByText('SoHo').className).toMatch(/bg-purple-100/);
  });

  it('highlights Little Italy via "Nolita"', () => {
    render(<ManhattanMap highlightedAreas={['Nolita']} />);

    const littleItaly = screen.getByText(/Little\s*Italy/);
    expect(littleItaly.className).toMatch(/bg-purple-100/);
  });

  it('highlights Little Italy via "Little Italy"', () => {
    render(<ManhattanMap highlightedAreas={['Little Italy']} />);

    const littleItaly = screen.getByText(/Little\s*Italy/);
    expect(littleItaly.className).toMatch(/bg-purple-100/);
  });

  it('highlights Lower East Side via "LES"', () => {
    render(<ManhattanMap highlightedAreas={['LES']} />);

    expect(screen.getByText('LES').className).toMatch(/bg-purple-100/);
  });

  it('highlights Lower East Side by full name', () => {
    render(<ManhattanMap highlightedAreas={['Lower East Side']} />);

    expect(screen.getByText('LES').className).toMatch(/bg-purple-100/);
  });

  it('highlights Tribeca', () => {
    render(<ManhattanMap highlightedAreas={['Tribeca']} />);

    expect(screen.getByText('Tribeca').className).toMatch(/bg-purple-200/);
  });

  it('highlights Tribeca via "TriBeCa" casing', () => {
    render(<ManhattanMap highlightedAreas={['TriBeCa']} />);

    expect(screen.getByText('Tribeca').className).toMatch(/bg-purple-200/);
  });

  it('highlights Chinatown', () => {
    render(<ManhattanMap highlightedAreas={['Chinatown']} />);

    expect(screen.getByText('Chinatown').className).toMatch(/bg-purple-100/);
  });

  it('highlights Financial District via "FiDi"', () => {
    render(<ManhattanMap highlightedAreas={['FiDi']} />);

    expect(screen.getByText('FiDi').className).toMatch(/bg-purple-100/);
  });

  it('highlights Financial District by full name', () => {
    render(<ManhattanMap highlightedAreas={['Financial District']} />);

    expect(screen.getByText('FiDi').className).toMatch(/bg-purple-100/);
  });

  it('highlights Battery via "Battery"', () => {
    render(<ManhattanMap highlightedAreas={['Battery']} />);

    expect(screen.getByText('Battery').className).toMatch(/bg-purple-100/);
  });

  // ---- multiple areas ----

  it('highlights multiple areas simultaneously', () => {
    render(<ManhattanMap highlightedAreas={['Inwood', 'Chelsea', 'SoHo']} />);

    expect(screen.getByText('Inwood').className).toMatch(/bg-purple-100/);
    expect(screen.getByText('Chelsea').className).toMatch(/bg-purple-200/);
    expect(screen.getByText('SoHo').className).toMatch(/bg-purple-100/);
    // Non-highlighted areas remain gray
    expect(screen.getByText('Chinatown').className).toMatch(/bg-gray-100/);
  });
});
