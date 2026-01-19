import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import DurationButtons from '../DurationButtons';

describe('DurationButtons', () => {
  const defaultProps = {
    durationOptions: [
      { duration: 30, price: 30 },
      { duration: 60, price: 60 },
      { duration: 90, price: 85 },
    ],
    selectedDuration: 60,
    onDurationSelect: jest.fn(),
    disabledDurations: [],
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('rendering', () => {
    it('returns null when only one option', () => {
      const { container } = render(
        <DurationButtons
          {...defaultProps}
          durationOptions={[{ duration: 60, price: 60 }]}
        />
      );

      expect(container.firstChild).toBeNull();
    });

    it('returns null when no options', () => {
      const { container } = render(
        <DurationButtons {...defaultProps} durationOptions={[]} />
      );

      expect(container.firstChild).toBeNull();
    });

    it('renders all duration options when more than one', () => {
      render(<DurationButtons {...defaultProps} />);

      expect(screen.getByText('30 min ($30)')).toBeInTheDocument();
      expect(screen.getByText('60 min ($60)')).toBeInTheDocument();
      expect(screen.getByText('90 min ($85)')).toBeInTheDocument();
    });

    it('renders section label', () => {
      render(<DurationButtons {...defaultProps} />);

      expect(screen.getByText('Session duration:')).toBeInTheDocument();
    });
  });

  describe('selection', () => {
    it('marks selected duration as checked', () => {
      render(<DurationButtons {...defaultProps} selectedDuration={60} />);

      const radio60 = screen.getByRole('radio', { name: /60 min/i });
      expect(radio60).toBeChecked();
    });

    it('marks other durations as unchecked', () => {
      render(<DurationButtons {...defaultProps} selectedDuration={60} />);

      const radio30 = screen.getByRole('radio', { name: /30 min/i });
      const radio90 = screen.getByRole('radio', { name: /90 min/i });

      expect(radio30).not.toBeChecked();
      expect(radio90).not.toBeChecked();
    });

    it('calls onDurationSelect when option is clicked', async () => {
      const user = userEvent.setup();
      const onDurationSelect = jest.fn();

      render(
        <DurationButtons {...defaultProps} onDurationSelect={onDurationSelect} />
      );

      await user.click(screen.getByRole('radio', { name: /30 min/i }));

      expect(onDurationSelect).toHaveBeenCalledWith(30);
    });

    it('calls onDurationSelect via label click', async () => {
      const user = userEvent.setup();
      const onDurationSelect = jest.fn();

      render(
        <DurationButtons {...defaultProps} onDurationSelect={onDurationSelect} />
      );

      await user.click(screen.getByText('90 min ($85)'));

      expect(onDurationSelect).toHaveBeenCalledWith(90);
    });
  });

  describe('disabled durations', () => {
    it('disables specified durations', () => {
      render(
        <DurationButtons
          {...defaultProps}
          disabledDurations={[30, 90]}
        />
      );

      const radio30 = screen.getByRole('radio', { name: /30 min/i });
      const radio90 = screen.getByRole('radio', { name: /90 min/i });

      expect(radio30).toBeDisabled();
      expect(radio90).toBeDisabled();
    });

    it('does not disable non-specified durations', () => {
      render(
        <DurationButtons
          {...defaultProps}
          disabledDurations={[30]}
        />
      );

      const radio60 = screen.getByRole('radio', { name: /60 min/i });
      const radio90 = screen.getByRole('radio', { name: /90 min/i });

      expect(radio60).not.toBeDisabled();
      expect(radio90).not.toBeDisabled();
    });

    it('applies opacity styling to disabled options', () => {
      render(
        <DurationButtons
          {...defaultProps}
          disabledDurations={[30]}
        />
      );

      const label = screen.getByText('30 min ($30)').closest('label');
      expect(label).toHaveClass('opacity-50', 'cursor-not-allowed');
    });

    it('does not call onDurationSelect for disabled options', async () => {
      const user = userEvent.setup();
      const onDurationSelect = jest.fn();

      render(
        <DurationButtons
          {...defaultProps}
          disabledDurations={[30]}
          onDurationSelect={onDurationSelect}
        />
      );

      // Try to click disabled radio via label
      const label = screen.getByText('30 min ($30)');
      await user.click(label);

      expect(onDurationSelect).not.toHaveBeenCalled();
    });
  });

  describe('radio group behavior', () => {
    it('uses correct radio group name', () => {
      render(<DurationButtons {...defaultProps} />);

      const radios = screen.getAllByRole('radio');
      radios.forEach((radio) => {
        expect(radio).toHaveAttribute('name', 'duration-shared');
      });
    });

    it('has correct value attribute on radio inputs', () => {
      render(<DurationButtons {...defaultProps} />);

      const radio30 = screen.getByRole('radio', { name: /30 min/i });
      const radio60 = screen.getByRole('radio', { name: /60 min/i });
      const radio90 = screen.getByRole('radio', { name: /90 min/i });

      expect(radio30).toHaveAttribute('value', '30');
      expect(radio60).toHaveAttribute('value', '60');
      expect(radio90).toHaveAttribute('value', '90');
    });
  });

  describe('price display', () => {
    it('displays prices correctly formatted', () => {
      render(
        <DurationButtons
          {...defaultProps}
          durationOptions={[
            { duration: 30, price: 25 },
            { duration: 60, price: 50 },
          ]}
        />
      );

      expect(screen.getByText('30 min ($25)')).toBeInTheDocument();
      expect(screen.getByText('60 min ($50)')).toBeInTheDocument();
    });

    it('handles decimal prices', () => {
      render(
        <DurationButtons
          {...defaultProps}
          durationOptions={[
            { duration: 45, price: 37.5 },
            { duration: 60, price: 50 },
          ]}
        />
      );

      expect(screen.getByText('45 min ($37.5)')).toBeInTheDocument();
    });
  });

  describe('edge cases', () => {
    it('handles empty disabledDurations array', () => {
      render(
        <DurationButtons
          {...defaultProps}
          disabledDurations={[]}
        />
      );

      const radios = screen.getAllByRole('radio');
      radios.forEach((radio) => {
        expect(radio).not.toBeDisabled();
      });
    });

    it('handles exactly two options', () => {
      render(
        <DurationButtons
          {...defaultProps}
          durationOptions={[
            { duration: 30, price: 30 },
            { duration: 60, price: 60 },
          ]}
        />
      );

      expect(screen.getByText('30 min ($30)')).toBeInTheDocument();
      expect(screen.getByText('60 min ($60)')).toBeInTheDocument();
    });
  });
});
