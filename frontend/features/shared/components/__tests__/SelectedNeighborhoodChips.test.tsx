/**
 * @jest-environment jsdom
 */
import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import {
  SelectedNeighborhoodChips,
  type SelectedNeighborhood,
} from '../SelectedNeighborhoodChips';

describe('SelectedNeighborhoodChips', () => {
  const mockOnRemove = jest.fn();

  beforeEach(() => {
    mockOnRemove.mockClear();
  });

  it('returns null when selected array is empty', () => {
    const { container } = render(
      <SelectedNeighborhoodChips selected={[]} onRemove={mockOnRemove} />
    );

    expect(container).toBeEmptyDOMElement();
  });

  it('renders chips for each selected neighborhood', () => {
    const selected: SelectedNeighborhood[] = [
      { neighborhood_id: 'n1', name: 'Upper West Side' },
      { neighborhood_id: 'n2', name: 'Chelsea' },
    ];

    render(<SelectedNeighborhoodChips selected={selected} onRemove={mockOnRemove} />);

    expect(screen.getByText('Upper West Side')).toBeInTheDocument();
    expect(screen.getByText('Chelsea')).toBeInTheDocument();
  });

  it('renders remove buttons for each chip', () => {
    const selected: SelectedNeighborhood[] = [
      { neighborhood_id: 'n1', name: 'Upper West Side' },
    ];

    render(<SelectedNeighborhoodChips selected={selected} onRemove={mockOnRemove} />);

    expect(screen.getByRole('button', { name: 'Remove Upper West Side' })).toBeInTheDocument();
  });

  it('calls onRemove with correct id when remove button is clicked', () => {
    const selected: SelectedNeighborhood[] = [
      { neighborhood_id: 'n1', name: 'Upper West Side' },
      { neighborhood_id: 'n2', name: 'Chelsea' },
    ];

    render(<SelectedNeighborhoodChips selected={selected} onRemove={mockOnRemove} />);

    fireEvent.click(screen.getByRole('button', { name: 'Remove Upper West Side' }));

    expect(mockOnRemove).toHaveBeenCalledWith('n1');
    expect(mockOnRemove).toHaveBeenCalledTimes(1);
  });

  it('shows fallback text when neighborhood name is empty', () => {
    const selected: SelectedNeighborhood[] = [
      { neighborhood_id: 'n1', name: '' },
    ];

    render(<SelectedNeighborhoodChips selected={selected} onRemove={mockOnRemove} />);

    expect(screen.getByText('Neighborhood')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Remove neighborhood' })).toBeInTheDocument();
  });

  it('has proper test ids for container and chips', () => {
    const selected: SelectedNeighborhood[] = [
      { neighborhood_id: 'n1', name: 'SoHo' },
    ];

    render(<SelectedNeighborhoodChips selected={selected} onRemove={mockOnRemove} />);

    expect(screen.getByTestId('selected-neighborhood-chip-list')).toBeInTheDocument();
    expect(screen.getByTestId('selected-neighborhood-chip')).toBeInTheDocument();
  });

  it('truncates long neighborhood names with title attribute', () => {
    const longName = 'This is a very long neighborhood name that should be truncated';
    const selected: SelectedNeighborhood[] = [
      { neighborhood_id: 'n1', name: longName },
    ];

    render(<SelectedNeighborhoodChips selected={selected} onRemove={mockOnRemove} />);

    const nameSpan = screen.getByTitle(longName);
    expect(nameSpan).toHaveClass('truncate');
  });
});
