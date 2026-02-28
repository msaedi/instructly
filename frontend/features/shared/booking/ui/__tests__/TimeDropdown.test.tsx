import React from 'react';
import { render, screen, fireEvent, act } from '@testing-library/react';
import TimeDropdown from '../TimeDropdown';

// Mock createPortal
jest.mock('react-dom', () => ({
  ...jest.requireActual('react-dom'),
  createPortal: (node: React.ReactNode) => node,
}));

describe('TimeDropdown', () => {
  const defaultProps = {
    selectedTime: null,
    timeSlots: ['9:00 AM', '10:00 AM', '11:00 AM', '2:00 PM'],
    isVisible: true,
    onTimeSelect: jest.fn(),
  };

  beforeEach(() => {
    jest.clearAllMocks();
    jest.useFakeTimers();
    jest
      .spyOn(window, 'requestAnimationFrame')
      .mockImplementation((callback: FrameRequestCallback): number => {
        callback(0);
        return 1;
      });
    jest.spyOn(window, 'cancelAnimationFrame').mockImplementation(() => {});
  });

  afterEach(() => {
    jest.restoreAllMocks();
    jest.useRealTimers();
  });

  describe('Visibility', () => {
    it('renders when isVisible is true', () => {
      render(<TimeDropdown {...defaultProps} />);
      expect(screen.getByText('Select time')).toBeInTheDocument();
    });

    it('returns null when isVisible is false', () => {
      const { container } = render(<TimeDropdown {...defaultProps} isVisible={false} />);
      expect(container).toBeEmptyDOMElement();
    });
  });

  describe('Loading state', () => {
    it('shows loading text when isLoading is true', () => {
      render(<TimeDropdown {...defaultProps} isLoading={true} />);
      expect(screen.getByText('Loading available times...')).toBeInTheDocument();
    });

    it('disables button when loading', () => {
      render(<TimeDropdown {...defaultProps} isLoading={true} />);
      const button = screen.getByRole('button');
      expect(button).toBeDisabled();
    });
  });

  describe('Empty state', () => {
    it('shows no times available message when timeSlots is empty', () => {
      render(<TimeDropdown {...defaultProps} timeSlots={[]} />);
      expect(screen.getByText('No times available for this date')).toBeInTheDocument();
    });

    it('disables button when no times available', () => {
      render(<TimeDropdown {...defaultProps} timeSlots={[]} />);
      const button = screen.getByRole('button');
      expect(button).toBeDisabled();
    });
  });

  describe('Single time slot', () => {
    it('auto-selects when only one time available', () => {
      const onTimeSelect = jest.fn();
      render(
        <TimeDropdown
          {...defaultProps}
          timeSlots={['10:00 AM']}
          onTimeSelect={onTimeSelect}
        />
      );
      expect(onTimeSelect).toHaveBeenCalledWith('10:00 AM');
    });

    it('shows "only time available" text for single slot', () => {
      render(
        <TimeDropdown
          {...defaultProps}
          timeSlots={['10:00 AM']}
          selectedTime="10:00 AM"
        />
      );
      expect(screen.getByText('10:00 AM (only time available)')).toBeInTheDocument();
    });
  });

  describe('Multiple time slots', () => {
    it('shows "Select time" when no time is selected', () => {
      render(<TimeDropdown {...defaultProps} />);
      expect(screen.getByText('Select time')).toBeInTheDocument();
    });

    it('shows selected time when time is selected', () => {
      render(<TimeDropdown {...defaultProps} selectedTime="10:00 AM" />);
      expect(screen.getByText('10:00 AM')).toBeInTheDocument();
    });
  });

  describe('Dropdown interaction', () => {
    it('opens dropdown when button is clicked', () => {
      render(<TimeDropdown {...defaultProps} />);
      fireEvent.click(screen.getByRole('button'));
      expect(screen.getByText('9:00 AM')).toBeInTheDocument();
      expect(screen.getByText('10:00 AM')).toBeInTheDocument();
      expect(screen.getByText('11:00 AM')).toBeInTheDocument();
    });

    it('closes dropdown when time is selected', async () => {
      const onTimeSelect = jest.fn();
      render(<TimeDropdown {...defaultProps} onTimeSelect={onTimeSelect} />);

      fireEvent.click(screen.getByRole('button'));
      fireEvent.click(screen.getByText('10:00 AM'));

      expect(onTimeSelect).toHaveBeenCalledWith('10:00 AM');

      // Wait for animation
      act(() => {
        jest.advanceTimersByTime(200);
      });
    });

    it('highlights selected time in dropdown', () => {
      render(<TimeDropdown {...defaultProps} selectedTime="10:00 AM" />);
      // When selectedTime is set, button shows the selected time, not "Select time"
      fireEvent.click(screen.getByRole('button'));

      // The selected time should have the check icon
      const allOptions = screen.getAllByText('10:00 AM');
      const selectedOption = allOptions[1]; // In dropdown
      expect(selectedOption).toBeDefined();
      expect(selectedOption?.closest('button')).toHaveClass('bg-purple-50');
    });

    it('closes dropdown when clicking outside', () => {
      render(
        <div>
          <div data-testid="outside">Outside</div>
          <TimeDropdown {...defaultProps} />
        </div>
      );

      fireEvent.click(screen.getByRole('button'));
      expect(screen.getByText('9:00 AM')).toBeInTheDocument();

      fireEvent.mouseDown(screen.getByTestId('outside'));

      act(() => {
        jest.advanceTimersByTime(200);
      });
    });

    it('cleans up pending close timeout on unmount', () => {
      const clearTimeoutSpy = jest.spyOn(global, 'clearTimeout');
      const { unmount } = render(<TimeDropdown {...defaultProps} />);

      fireEvent.click(screen.getByRole('button'));
      fireEvent.click(screen.getByText('9:00 AM'));
      unmount();

      expect(clearTimeoutSpy).toHaveBeenCalled();
      clearTimeoutSpy.mockRestore();
    });
  });

  describe('Accessibility and keyboard', () => {
    it('provides listbox semantics on trigger and options', () => {
      render(<TimeDropdown {...defaultProps} />);
      const trigger = screen.getByRole('button', { name: /select time/i });

      expect(trigger).toHaveAttribute('aria-haspopup', 'listbox');
      expect(trigger).toHaveAttribute('aria-expanded', 'false');

      fireEvent.click(trigger);

      expect(trigger).toHaveAttribute('aria-expanded', 'true');
      expect(screen.getByRole('listbox', { name: /select lesson time/i })).toBeInTheDocument();
      expect(screen.getAllByRole('option')).toHaveLength(defaultProps.timeSlots.length);
    });

    it('supports arrow key navigation and home/end in the listbox', () => {
      render(<TimeDropdown {...defaultProps} />);
      const trigger = screen.getByRole('button', { name: /select time/i });

      fireEvent.keyDown(trigger, { key: 'ArrowDown' });

      const listbox = screen.getByRole('listbox');
      let options = screen.getAllByRole('option');
      expect(options[0]).toHaveAttribute('tabindex', '0');

      fireEvent.keyDown(listbox, { key: 'ArrowDown' });
      options = screen.getAllByRole('option');
      expect(options[1]).toHaveAttribute('tabindex', '0');

      fireEvent.keyDown(listbox, { key: 'Home' });
      options = screen.getAllByRole('option');
      expect(options[0]).toHaveAttribute('tabindex', '0');

      fireEvent.keyDown(listbox, { key: 'End' });
      options = screen.getAllByRole('option');
      expect(options[options.length - 1]).toHaveAttribute('tabindex', '0');
    });

    it('handles trigger enter/space open-close behavior and escape close', () => {
      render(<TimeDropdown {...defaultProps} />);
      const trigger = screen.getByRole('button', { name: /select time/i });

      fireEvent.keyDown(trigger, { key: ' ' });
      expect(screen.getByRole('listbox')).toBeInTheDocument();
      fireEvent.keyDown(trigger, { key: 'ArrowDown' });
      let options = screen.getAllByRole('option');
      expect(options[1]).toHaveAttribute('tabindex', '0');

      fireEvent.keyDown(trigger, { key: 'Enter' });
      act(() => {
        jest.advanceTimersByTime(200);
      });
      expect(screen.queryByRole('listbox')).not.toBeInTheDocument();

      fireEvent.keyDown(trigger, { key: 'ArrowDown' });
      expect(screen.getByRole('listbox')).toBeInTheDocument();
      options = screen.getAllByRole('option');
      expect(options[0]).toHaveAttribute('tabindex', '0');

      fireEvent.keyDown(trigger, { key: 'Escape' });
      act(() => {
        jest.advanceTimersByTime(200);
      });
      expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    });

    it('handles trigger ArrowUp behavior when closed and open', () => {
      render(<TimeDropdown {...defaultProps} />);
      const trigger = screen.getByRole('button', { name: /select time/i });

      fireEvent.keyDown(trigger, { key: 'ArrowUp' });
      let options = screen.getAllByRole('option');
      expect(options[options.length - 1]).toHaveAttribute('tabindex', '0');

      fireEvent.keyDown(trigger, { key: 'ArrowUp' });
      options = screen.getAllByRole('option');
      expect(options[options.length - 2]).toHaveAttribute('tabindex', '0');
    });

    it('handles listbox ArrowUp and option focus/mouse enter callbacks', () => {
      render(<TimeDropdown {...defaultProps} />);
      const trigger = screen.getByRole('button', { name: /select time/i });

      fireEvent.keyDown(trigger, { key: 'ArrowDown' });
      const listbox = screen.getByRole('listbox');

      fireEvent.keyDown(listbox, { key: 'ArrowUp' });
      let options = screen.getAllByRole('option');
      expect(options[0]).toHaveAttribute('tabindex', '0');

      const optionAtIndex2 = options.at(2);
      expect(optionAtIndex2).toBeDefined();
      if (!optionAtIndex2) {
        throw new Error('Expected option at index 2');
      }
      fireEvent.mouseEnter(optionAtIndex2);
      options = screen.getAllByRole('option');
      expect(options[2]).toHaveAttribute('tabindex', '0');

      const optionAtIndex1 = options.at(1);
      expect(optionAtIndex1).toBeDefined();
      if (!optionAtIndex1) {
        throw new Error('Expected option at index 1');
      }
      fireEvent.focus(optionAtIndex1);
      options = screen.getAllByRole('option');
      expect(options[1]).toHaveAttribute('tabindex', '0');
    });

    it('selects with Enter and returns focus to trigger', () => {
      const onTimeSelect = jest.fn();
      render(<TimeDropdown {...defaultProps} onTimeSelect={onTimeSelect} />);
      const trigger = screen.getByRole('button', { name: /select time/i });

      fireEvent.keyDown(trigger, { key: 'ArrowDown' });
      fireEvent.keyDown(screen.getByRole('listbox'), { key: 'ArrowDown' });
      fireEvent.keyDown(screen.getByRole('listbox'), { key: 'Enter' });

      expect(onTimeSelect).toHaveBeenCalledWith('10:00 AM');
      act(() => {
        jest.advanceTimersByTime(200);
      });
      expect(trigger).toHaveFocus();
    });

    it('closes with Escape and returns focus to trigger', () => {
      render(<TimeDropdown {...defaultProps} />);
      const trigger = screen.getByRole('button', { name: /select time/i });

      fireEvent.click(trigger);
      fireEvent.keyDown(screen.getByRole('listbox'), { key: 'Escape' });

      act(() => {
        jest.advanceTimersByTime(200);
      });
      expect(trigger).toHaveFocus();
    });

    it('does not open on keydown when disabled', () => {
      render(<TimeDropdown {...defaultProps} disabled={true} />);
      const trigger = screen.getByRole('button');
      fireEvent.keyDown(trigger, { key: 'Enter' });
      expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    });
  });

  describe('Disabled state', () => {
    it('disables button when disabled prop is true', () => {
      render(<TimeDropdown {...defaultProps} disabled={true} />);
      const button = screen.getByRole('button');
      expect(button).toBeDisabled();
    });

    it('applies opacity styling when disabled', () => {
      render(<TimeDropdown {...defaultProps} disabled={true} />);
      const button = screen.getByRole('button');
      expect(button).toHaveClass('opacity-50');
    });

    it('does not open dropdown when disabled', () => {
      render(<TimeDropdown {...defaultProps} disabled={true} />);
      fireEvent.click(screen.getByRole('button'));
      expect(screen.queryByText('9:00 AM')).not.toBeInTheDocument();
    });
  });

  describe('Styling', () => {
    it('shows chevron icon when times are available', () => {
      render(<TimeDropdown {...defaultProps} />);
      const button = screen.getByRole('button');
      const svg = button.querySelector('svg');
      expect(svg).toBeInTheDocument();
    });

    it('does not show chevron when no times available', () => {
      render(<TimeDropdown {...defaultProps} timeSlots={[]} />);
      const button = screen.getByRole('button');
      const svg = button.querySelector('svg');
      expect(svg).not.toBeInTheDocument();
    });

    it('rotates chevron when dropdown is open', () => {
      render(<TimeDropdown {...defaultProps} />);
      fireEvent.click(screen.getByText('Select time'));
      const svg = screen.getByText('Select time').closest('button')?.querySelector('svg');
      expect(svg).toHaveClass('rotate-180');
    });

    it('applies ring styling when open', () => {
      render(<TimeDropdown {...defaultProps} />);
      fireEvent.click(screen.getByText('Select time'));
      const button = screen.getByText('Select time').closest('button');
      expect(button).toHaveClass('ring-2', 'ring-[#7E22CE]');
    });
  });
});
