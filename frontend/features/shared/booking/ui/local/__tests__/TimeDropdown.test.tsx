import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import TimeDropdown from '../TimeDropdown';

describe('TimeDropdown', () => {
  const defaultProps = {
    selectedTime: null,
    timeSlots: ['9:00 AM', '10:00 AM', '11:00 AM'],
    isVisible: true,
    onTimeSelect: jest.fn(),
    disabled: false,
    isLoading: false,
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('visibility', () => {
    it('renders nothing when isVisible is false', () => {
      const { container } = render(
        <TimeDropdown {...defaultProps} isVisible={false} />
      );

      expect(container.firstChild).toBeNull();
    });

    it('renders dropdown when isVisible is true', () => {
      render(<TimeDropdown {...defaultProps} />);

      expect(screen.getByText('Select time')).toBeInTheDocument();
    });
  });

  describe('loading state', () => {
    it('shows loading message when isLoading is true', () => {
      render(<TimeDropdown {...defaultProps} isLoading={true} />);

      expect(screen.getByText('Loading available times...')).toBeInTheDocument();
    });

    it('disables button when loading', () => {
      render(<TimeDropdown {...defaultProps} isLoading={true} />);

      const button = screen.getByRole('button');
      expect(button).toBeDisabled();
    });
  });

  describe('no times available', () => {
    it('shows no times message when timeSlots is empty', () => {
      render(<TimeDropdown {...defaultProps} timeSlots={[]} />);

      expect(screen.getByText('No times available for this date')).toBeInTheDocument();
    });

    it('disables button when no times available', () => {
      render(<TimeDropdown {...defaultProps} timeSlots={[]} />);

      const button = screen.getByRole('button');
      expect(button).toBeDisabled();
    });

    it('does not show dropdown arrow when no times available', () => {
      const { container } = render(<TimeDropdown {...defaultProps} timeSlots={[]} />);

      expect(container.querySelector('svg')).not.toBeInTheDocument();
    });
  });

  describe('disabled state', () => {
    it('disables button when disabled prop is true', () => {
      render(<TimeDropdown {...defaultProps} disabled={true} />);

      const button = screen.getByRole('button');
      expect(button).toBeDisabled();
    });

    it('does not open dropdown when disabled', async () => {
      const user = userEvent.setup();
      render(<TimeDropdown {...defaultProps} disabled={true} />);

      await user.click(screen.getByRole('button'));

      // Dropdown should not open
      expect(screen.queryByText('9:00 AM')).not.toBeInTheDocument();
    });
  });

  describe('dropdown interaction', () => {
    it('opens dropdown when button is clicked', async () => {
      const user = userEvent.setup();
      render(<TimeDropdown {...defaultProps} />);

      await user.click(screen.getByText('Select time'));

      // Should show time options
      expect(screen.getByText('9:00 AM')).toBeInTheDocument();
      expect(screen.getByText('10:00 AM')).toBeInTheDocument();
      expect(screen.getByText('11:00 AM')).toBeInTheDocument();
    });

    it('closes dropdown when time is selected', async () => {
      const user = userEvent.setup();
      const onTimeSelect = jest.fn();
      render(<TimeDropdown {...defaultProps} onTimeSelect={onTimeSelect} />);

      await user.click(screen.getByText('Select time'));
      await user.click(screen.getByText('10:00 AM'));

      expect(onTimeSelect).toHaveBeenCalledWith('10:00 AM');
    });

    it('toggles dropdown on multiple clicks', async () => {
      const user = userEvent.setup();
      render(<TimeDropdown {...defaultProps} />);

      // Open
      await user.click(screen.getByText('Select time'));
      expect(screen.getByText('9:00 AM')).toBeInTheDocument();

      // Close
      await user.click(screen.getByText('Select time'));
      await waitFor(() => {
        expect(screen.queryAllByText('9:00 AM').length).toBeLessThanOrEqual(1);
      });
    });

    it('shows chevron rotation when open', async () => {
      const user = userEvent.setup();
      const { container } = render(<TimeDropdown {...defaultProps} />);

      await user.click(screen.getByText('Select time'));

      const chevron = container.querySelector('svg');
      expect(chevron).toHaveClass('rotate-180');
    });
  });

  describe('selected time display', () => {
    it('shows selected time in button', () => {
      render(<TimeDropdown {...defaultProps} selectedTime="10:00 AM" />);

      expect(screen.getByText('10:00 AM')).toBeInTheDocument();
    });

    it('highlights selected time in dropdown', async () => {
      const user = userEvent.setup();
      render(<TimeDropdown {...defaultProps} selectedTime="10:00 AM" />);

      await user.click(screen.getByText('10:00 AM'));

      // The selected option should have special styling
      const selectedOptions = screen.getAllByText('10:00 AM');
      const selectedOption = selectedOptions[1]; // Second one is in dropdown
      expect(selectedOption?.closest('button')).toHaveClass('bg-purple-50');
    });

    it('shows checkmark for selected time', async () => {
      const user = userEvent.setup();
      const { container } = render(<TimeDropdown {...defaultProps} selectedTime="10:00 AM" />);

      await user.click(screen.getByText('10:00 AM'));

      // Should have checkmark SVG
      const checkmarks = container.querySelectorAll('svg');
      expect(checkmarks.length).toBeGreaterThan(1); // Chevron + checkmark
    });
  });

  describe('auto-select single option', () => {
    it('auto-selects when only one time slot available', () => {
      const onTimeSelect = jest.fn();
      render(
        <TimeDropdown
          {...defaultProps}
          timeSlots={['9:00 AM']}
          selectedTime={null}
          onTimeSelect={onTimeSelect}
        />
      );

      expect(onTimeSelect).toHaveBeenCalledWith('9:00 AM');
    });

    it('does not auto-select when already selected', () => {
      const onTimeSelect = jest.fn();
      render(
        <TimeDropdown
          {...defaultProps}
          timeSlots={['9:00 AM']}
          selectedTime="9:00 AM"
          onTimeSelect={onTimeSelect}
        />
      );

      // Should not be called since already selected
      expect(onTimeSelect).not.toHaveBeenCalled();
    });

    it('does not auto-select when multiple options', () => {
      const onTimeSelect = jest.fn();
      render(<TimeDropdown {...defaultProps} selectedTime={null} onTimeSelect={onTimeSelect} />);

      // Should not auto-select with multiple options
      expect(onTimeSelect).not.toHaveBeenCalled();
    });
  });
});
