import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import PresetButtons from '../PresetButtons';

// Mock the availability constants
jest.mock('@/lib/availability/constants', () => ({
  getPresetKeys: () => ['weekday_9_to_5', 'mornings_only', 'evenings_only', 'weekends_only'],
  getPresetDisplayName: (key: string) => {
    const names: Record<string, string> = {
      weekday_9_to_5: '9-5 Weekdays',
      mornings_only: 'Mornings Only',
      evenings_only: 'Evenings Only',
      weekends_only: 'Weekends Only',
    };
    return names[key] || key;
  },
}));

jest.mock('@/lib/logger', () => ({
  logger: {
    info: jest.fn(),
    debug: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
  },
}));

describe('PresetButtons', () => {
  const defaultProps = {
    onPresetSelect: jest.fn(),
    onClearWeek: jest.fn(),
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders the Quick Presets heading', () => {
    render(<PresetButtons {...defaultProps} />);
    expect(screen.getByText('Quick Presets')).toBeInTheDocument();
  });

  it('renders all preset buttons', () => {
    render(<PresetButtons {...defaultProps} />);
    expect(screen.getByText('9-5 Weekdays')).toBeInTheDocument();
    expect(screen.getByText('Mornings Only')).toBeInTheDocument();
    expect(screen.getByText('Evenings Only')).toBeInTheDocument();
    expect(screen.getByText('Weekends Only')).toBeInTheDocument();
  });

  it('renders the Clear Week button', () => {
    render(<PresetButtons {...defaultProps} />);
    expect(screen.getByText('Clear Week')).toBeInTheDocument();
  });

  it('calls onPresetSelect when a preset button is clicked', () => {
    const onPresetSelect = jest.fn();
    render(<PresetButtons {...defaultProps} onPresetSelect={onPresetSelect} />);

    fireEvent.click(screen.getByText('9-5 Weekdays'));
    expect(onPresetSelect).toHaveBeenCalledWith('weekday_9_to_5');
    expect(onPresetSelect).toHaveBeenCalledTimes(1);
  });

  it('calls onClearWeek when Clear Week button is clicked', () => {
    const onClearWeek = jest.fn();
    render(<PresetButtons {...defaultProps} onClearWeek={onClearWeek} />);

    fireEvent.click(screen.getByText('Clear Week'));
    expect(onClearWeek).toHaveBeenCalledTimes(1);
  });

  it('disables all buttons when disabled prop is true', () => {
    render(<PresetButtons {...defaultProps} disabled={true} />);

    const buttons = screen.getAllByRole('button');
    buttons.forEach((button) => {
      expect(button).toBeDisabled();
    });
  });

  it('enables all buttons when disabled prop is false', () => {
    render(<PresetButtons {...defaultProps} disabled={false} />);

    const buttons = screen.getAllByRole('button');
    buttons.forEach((button) => {
      expect(button).not.toBeDisabled();
    });
  });

  it('has correct aria-labels for preset buttons', () => {
    render(<PresetButtons {...defaultProps} />);

    expect(
      screen.getByRole('button', { name: /Apply 9-5 Weekdays schedule/i })
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /Apply Mornings Only schedule/i })
    ).toBeInTheDocument();
  });

  it('has correct aria-label for Clear Week button', () => {
    render(<PresetButtons {...defaultProps} />);

    expect(
      screen.getByRole('button', { name: /Clear all availability for this week/i })
    ).toBeInTheDocument();
  });

  it('renders button group with proper role', () => {
    render(<PresetButtons {...defaultProps} />);
    expect(screen.getByRole('group', { name: 'Schedule presets' })).toBeInTheDocument();
  });

  it('calls different preset handlers for different buttons', () => {
    const onPresetSelect = jest.fn();
    render(<PresetButtons {...defaultProps} onPresetSelect={onPresetSelect} />);

    fireEvent.click(screen.getByText('Mornings Only'));
    expect(onPresetSelect).toHaveBeenCalledWith('mornings_only');

    fireEvent.click(screen.getByText('Evenings Only'));
    expect(onPresetSelect).toHaveBeenCalledWith('evenings_only');

    fireEvent.click(screen.getByText('Weekends Only'));
    expect(onPresetSelect).toHaveBeenCalledWith('weekends_only');
  });
});
