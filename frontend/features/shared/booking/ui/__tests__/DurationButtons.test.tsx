import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import DurationButtons from '../DurationButtons';

jest.mock('@/lib/logger', () => ({
  logger: {
    info: jest.fn(),
    debug: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
  },
}));

describe('DurationButtons', () => {
  const defaultProps = {
    durationOptions: [
      { duration: 30, price: 30 },
      { duration: 45, price: 45 },
      { duration: 60, price: 60 },
    ],
    selectedDuration: 30,
    onDurationSelect: jest.fn(),
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('Visibility', () => {
    it('renders when multiple duration options available', () => {
      render(<DurationButtons {...defaultProps} />);
      expect(screen.getByText('Session duration:')).toBeInTheDocument();
    });

    it('returns null when single duration option', () => {
      const { container } = render(
        <DurationButtons
          {...defaultProps}
          durationOptions={[{ duration: 60, price: 60 }]}
        />
      );
      expect(container).toBeEmptyDOMElement();
    });

    it('returns null when no duration options', () => {
      const { container } = render(
        <DurationButtons {...defaultProps} durationOptions={[]} />
      );
      expect(container).toBeEmptyDOMElement();
    });
  });

  describe('Option rendering', () => {
    it('renders all duration options', () => {
      render(<DurationButtons {...defaultProps} />);
      expect(screen.getByText('30 min ($30)')).toBeInTheDocument();
      expect(screen.getByText('45 min ($45)')).toBeInTheDocument();
      expect(screen.getByText('60 min ($60)')).toBeInTheDocument();
    });

    it('renders radio inputs for each option', () => {
      render(<DurationButtons {...defaultProps} />);
      const radios = screen.getAllByRole('radio');
      expect(radios).toHaveLength(3);
    });

    it('checks selected duration radio', () => {
      render(<DurationButtons {...defaultProps} selectedDuration={45} />);
      const radios = screen.getAllByRole('radio') as HTMLInputElement[];
      expect(radios[1]?.checked).toBe(true);
    });
  });

  describe('Selection behavior', () => {
    it('calls onDurationSelect when option is clicked', () => {
      const onDurationSelect = jest.fn();
      render(
        <DurationButtons {...defaultProps} onDurationSelect={onDurationSelect} />
      );

      fireEvent.click(screen.getByText('45 min ($45)'));
      expect(onDurationSelect).toHaveBeenCalledWith(45);
    });

    it('calls onDurationSelect when radio is changed', () => {
      const onDurationSelect = jest.fn();
      render(
        <DurationButtons {...defaultProps} onDurationSelect={onDurationSelect} />
      );

      const radios = screen.getAllByRole('radio');
      const thirdRadio = radios[2];
      expect(thirdRadio).toBeDefined();
      if (thirdRadio) {
        fireEvent.click(thirdRadio);
      }
      expect(onDurationSelect).toHaveBeenCalledWith(60);
    });
  });

  describe('Disabled durations', () => {
    it('disables specified durations', () => {
      render(
        <DurationButtons {...defaultProps} disabledDurations={[45, 60]} />
      );

      const radios = screen.getAllByRole('radio') as HTMLInputElement[];
      expect(radios[0]?.disabled).toBe(false);
      expect(radios[1]?.disabled).toBe(true);
      expect(radios[2]?.disabled).toBe(true);
    });

    it('applies opacity to disabled options', () => {
      render(
        <DurationButtons {...defaultProps} disabledDurations={[45]} />
      );

      const label45 = screen.getByText('45 min ($45)').closest('label');
      expect(label45).toBeInTheDocument();
      expect(label45).toHaveClass('opacity-50', 'cursor-not-allowed');
    });

    it('does not call onDurationSelect for disabled options', () => {
      const onDurationSelect = jest.fn();
      render(
        <DurationButtons
          {...defaultProps}
          onDurationSelect={onDurationSelect}
          disabledDurations={[45]}
        />
      );

      fireEvent.click(screen.getByText('45 min ($45)'));
      expect(onDurationSelect).not.toHaveBeenCalled();
    });

    it('allows selecting non-disabled options', () => {
      const onDurationSelect = jest.fn();
      render(
        <DurationButtons
          {...defaultProps}
          onDurationSelect={onDurationSelect}
          disabledDurations={[45]}
        />
      );

      fireEvent.click(screen.getByText('60 min ($60)'));
      expect(onDurationSelect).toHaveBeenCalledWith(60);
    });
  });

  describe('Different price formats', () => {
    it('handles integer prices', () => {
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
            { duration: 30, price: 27.5 },
            { duration: 60, price: 55 },
          ]}
        />
      );
      expect(screen.getByText('30 min ($27.5)')).toBeInTheDocument();
    });
  });

  describe('Unique radio name', () => {
    it('assigns unique name to radio group', () => {
      render(<DurationButtons {...defaultProps} />);
      const radios = screen.getAllByRole('radio') as HTMLInputElement[];
      const firstRadio = radios[0];
      expect(firstRadio).toBeDefined();
      const name = firstRadio?.name;

      // All radios should have the same name (form a group)
      radios.forEach((radio) => {
        expect(radio.name).toBe(name);
      });

      // Name should be unique (contain modal-specific identifier)
      expect(name).toContain('duration-modal-');
    });
  });

  describe('Two duration options', () => {
    it('renders with exactly two options', () => {
      render(
        <DurationButtons
          {...defaultProps}
          durationOptions={[
            { duration: 30, price: 35 },
            { duration: 60, price: 70 },
          ]}
        />
      );
      expect(screen.getByText('30 min ($35)')).toBeInTheDocument();
      expect(screen.getByText('60 min ($70)')).toBeInTheDocument();
      expect(screen.getAllByRole('radio')).toHaveLength(2);
    });
  });

  describe('Accessibility', () => {
    it('has clickable labels', () => {
      const onDurationSelect = jest.fn();
      render(
        <DurationButtons {...defaultProps} onDurationSelect={onDurationSelect} />
      );

      // Click on label text should trigger selection
      fireEvent.click(screen.getByText('60 min ($60)'));
      expect(onDurationSelect).toHaveBeenCalledWith(60);
    });

    it('radio inputs have proper type', () => {
      render(<DurationButtons {...defaultProps} />);
      const radios = screen.getAllByRole('radio') as HTMLInputElement[];
      radios.forEach((radio) => {
        expect(radio.type).toBe('radio');
      });
    });
  });
});
