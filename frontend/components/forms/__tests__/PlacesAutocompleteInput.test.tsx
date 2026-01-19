import { render, screen, waitFor, fireEvent, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { PlacesAutocompleteInput } from '../PlacesAutocompleteInput';
import { createRef } from 'react';

// Mock the API base helper
jest.mock('@/lib/apiBase', () => ({
  withApiBase: (path: string) => `http://test${path}`,
}));

// Mock fetch
const mockFetch = jest.fn();
global.fetch = mockFetch;

describe('PlacesAutocompleteInput', () => {
  const mockSuggestions = {
    items: [
      { place_id: 'place-1', description: '123 Main St, New York, NY', provider: 'google' },
      { place_id: 'place-2', description: '456 Oak Ave, Brooklyn, NY', provider: 'google' },
      { place_id: 'place-3', description: '789 Elm Rd, Manhattan, NY', provider: 'google' },
    ],
  };

  const defaultProps = {
    value: '',
    onValueChange: jest.fn(),
  };

  beforeEach(() => {
    jest.clearAllMocks();
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => mockSuggestions,
    });
  });

  describe('rendering', () => {
    it('renders an input field', () => {
      render(<PlacesAutocompleteInput {...defaultProps} />);

      expect(screen.getByRole('combobox')).toBeInTheDocument();
    });

    it('renders with custom placeholder', () => {
      render(<PlacesAutocompleteInput {...defaultProps} placeholder="Enter address" />);

      expect(screen.getByPlaceholderText('Enter address')).toBeInTheDocument();
    });

    it('renders with custom className', () => {
      render(<PlacesAutocompleteInput {...defaultProps} inputClassName="custom-input" />);

      expect(screen.getByRole('combobox')).toHaveClass('custom-input');
    });

    it('renders with container className', () => {
      const { container } = render(
        <PlacesAutocompleteInput {...defaultProps} containerClassName="custom-container" />
      );

      expect(container.firstChild).toHaveClass('custom-container');
    });

    it('forwards ref to input element', () => {
      const ref = createRef<HTMLInputElement>();
      render(<PlacesAutocompleteInput {...defaultProps} ref={ref} />);

      expect(ref.current).toBeInstanceOf(HTMLInputElement);
    });
  });

  describe('value handling', () => {
    it('displays the current value', () => {
      render(<PlacesAutocompleteInput {...defaultProps} value="123 Test St" />);

      expect(screen.getByRole('combobox')).toHaveValue('123 Test St');
    });

    it('calls onValueChange when typing', async () => {
      const onValueChange = jest.fn();
      const user = userEvent.setup();

      render(<PlacesAutocompleteInput {...defaultProps} onValueChange={onValueChange} />);

      await user.type(screen.getByRole('combobox'), 'a');

      expect(onValueChange).toHaveBeenCalledWith('a');
    });
  });

  describe('suggestions fetching', () => {
    it('fetches suggestions after minimum query length', async () => {
      jest.useFakeTimers();

      const { rerender } = render(
        <PlacesAutocompleteInput {...defaultProps} value="" />
      );

      // Update with longer value
      rerender(
        <PlacesAutocompleteInput {...defaultProps} value="123 Main" />
      );

      // Advance past debounce
      await act(async () => {
        jest.advanceTimersByTime(300);
      });

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/addresses/places/autocomplete'),
        expect.objectContaining({ method: 'GET' })
      );

      jest.useRealTimers();
    });

    it('does not fetch for short queries', async () => {
      jest.useFakeTimers();

      const { rerender } = render(
        <PlacesAutocompleteInput {...defaultProps} value="" minQueryLength={3} />
      );

      rerender(
        <PlacesAutocompleteInput {...defaultProps} value="ab" minQueryLength={3} />
      );

      await act(async () => {
        jest.advanceTimersByTime(300);
      });

      expect(mockFetch).not.toHaveBeenCalled();

      jest.useRealTimers();
    });

    it('respects custom minQueryLength', async () => {
      jest.useFakeTimers();

      const { rerender } = render(
        <PlacesAutocompleteInput {...defaultProps} value="" minQueryLength={5} />
      );

      rerender(
        <PlacesAutocompleteInput {...defaultProps} value="1234" minQueryLength={5} />
      );

      await act(async () => {
        jest.advanceTimersByTime(300);
      });

      expect(mockFetch).not.toHaveBeenCalled();

      rerender(
        <PlacesAutocompleteInput {...defaultProps} value="12345" minQueryLength={5} />
      );

      await act(async () => {
        jest.advanceTimersByTime(300);
      });

      expect(mockFetch).toHaveBeenCalled();

      jest.useRealTimers();
    });

    it('debounces fetch calls', async () => {
      jest.useFakeTimers();

      const { rerender } = render(
        <PlacesAutocompleteInput {...defaultProps} value="" debounceMs={500} />
      );

      // Multiple rapid changes
      rerender(<PlacesAutocompleteInput {...defaultProps} value="123" debounceMs={500} />);
      rerender(<PlacesAutocompleteInput {...defaultProps} value="1234" debounceMs={500} />);
      rerender(<PlacesAutocompleteInput {...defaultProps} value="12345" debounceMs={500} />);

      // Only final value should trigger fetch after debounce
      await act(async () => {
        jest.advanceTimersByTime(600);
      });

      // Fetch should be called once with final value
      const fetchCalls = mockFetch.mock.calls.filter((call) =>
        call[0].includes('12345')
      );
      expect(fetchCalls.length).toBeGreaterThan(0);

      jest.useRealTimers();
    });
  });

  describe('suggestions display', () => {
    it('shows suggestions dropdown when results arrive', async () => {
      jest.useFakeTimers();

      render(
        <PlacesAutocompleteInput {...defaultProps} value="123 Main" />
      );

      await act(async () => {
        jest.advanceTimersByTime(300);
      });

      await waitFor(() => {
        expect(screen.getByRole('listbox')).toBeInTheDocument();
      });

      jest.useRealTimers();
    });

    it('displays suggestion items', async () => {
      jest.useFakeTimers();

      render(<PlacesAutocompleteInput {...defaultProps} value="123 Main" />);

      await act(async () => {
        jest.advanceTimersByTime(300);
      });

      await waitFor(() => {
        expect(screen.getByText('123 Main St, New York, NY')).toBeInTheDocument();
        expect(screen.getByText('456 Oak Ave, Brooklyn, NY')).toBeInTheDocument();
      });

      jest.useRealTimers();
    });

    it('shows loading indicator while fetching', async () => {
      jest.useFakeTimers();

      // Make fetch take longer
      mockFetch.mockImplementation(
        () =>
          new Promise((resolve) =>
            setTimeout(
              () =>
                resolve({
                  ok: true,
                  json: async () => mockSuggestions,
                }),
              100
            )
          )
      );

      render(<PlacesAutocompleteInput {...defaultProps} value="123 Main" />);

      await act(async () => {
        jest.advanceTimersByTime(260); // After debounce but before fetch completes
      });

      expect(screen.getByText('Loading…')).toBeInTheDocument();

      await act(async () => {
        jest.advanceTimersByTime(150); // Let fetch complete
      });

      jest.useRealTimers();
    });

    it('limits suggestions to suggestionLimit', async () => {
      jest.useFakeTimers();

      mockFetch.mockResolvedValue({
        ok: true,
        json: async () => ({
          items: Array.from({ length: 10 }, (_, i) => ({
            place_id: `place-${i}`,
            description: `Address ${i}`,
            provider: 'google',
          })),
        }),
      });

      render(
        <PlacesAutocompleteInput {...defaultProps} value="123 Main" suggestionLimit={3} />
      );

      await act(async () => {
        jest.advanceTimersByTime(300);
      });

      await waitFor(() => {
        const options = screen.getAllByRole('option');
        expect(options.length).toBeLessThanOrEqual(3);
      });

      jest.useRealTimers();
    });
  });

  describe('suggestion selection', () => {
    it('calls onSelectSuggestion when clicking a suggestion', async () => {
      jest.useFakeTimers();
      const onSelectSuggestion = jest.fn();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });

      render(
        <PlacesAutocompleteInput
          {...defaultProps}
          value="123 Main"
          onSelectSuggestion={onSelectSuggestion}
        />
      );

      await act(async () => {
        jest.advanceTimersByTime(300);
      });

      await waitFor(() => {
        expect(screen.getByText('123 Main St, New York, NY')).toBeInTheDocument();
      });

      await user.click(screen.getByText('123 Main St, New York, NY'));

      expect(onSelectSuggestion).toHaveBeenCalledWith(
        expect.objectContaining({
          place_id: 'place-1',
          description: '123 Main St, New York, NY',
        })
      );

      jest.useRealTimers();
    });

    it('updates value when suggestion is selected', async () => {
      jest.useFakeTimers();
      const onValueChange = jest.fn();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });

      render(
        <PlacesAutocompleteInput
          {...defaultProps}
          value="123 Main"
          onValueChange={onValueChange}
        />
      );

      await act(async () => {
        jest.advanceTimersByTime(300);
      });

      await waitFor(() => {
        expect(screen.getByText('123 Main St, New York, NY')).toBeInTheDocument();
      });

      await user.click(screen.getByText('123 Main St, New York, NY'));

      expect(onValueChange).toHaveBeenCalledWith('123 Main St, New York, NY');

      jest.useRealTimers();
    });

    it('closes dropdown after selection', async () => {
      jest.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });

      render(<PlacesAutocompleteInput {...defaultProps} value="123 Main" />);

      await act(async () => {
        jest.advanceTimersByTime(300);
      });

      await waitFor(() => {
        expect(screen.getByRole('listbox')).toBeInTheDocument();
      });

      await user.click(screen.getByText('123 Main St, New York, NY'));

      await waitFor(() => {
        expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
      });

      jest.useRealTimers();
    });
  });

  describe('keyboard navigation', () => {
    it('navigates down with ArrowDown', async () => {
      jest.useFakeTimers();

      render(<PlacesAutocompleteInput {...defaultProps} value="123 Main" />);

      await act(async () => {
        jest.advanceTimersByTime(300);
      });

      await waitFor(() => {
        expect(screen.getByRole('listbox')).toBeInTheDocument();
      });

      const input = screen.getByRole('combobox');
      fireEvent.keyDown(input, { key: 'ArrowDown' });

      const options = screen.getAllByRole('option');
      expect(options[0]).toHaveAttribute('aria-selected', 'true');

      jest.useRealTimers();
    });

    it('navigates up with ArrowUp', async () => {
      jest.useFakeTimers();

      render(<PlacesAutocompleteInput {...defaultProps} value="123 Main" />);

      await act(async () => {
        jest.advanceTimersByTime(300);
      });

      await waitFor(() => {
        expect(screen.getByRole('listbox')).toBeInTheDocument();
      });

      const input = screen.getByRole('combobox');
      fireEvent.keyDown(input, { key: 'ArrowDown' }); // Move to first
      fireEvent.keyDown(input, { key: 'ArrowDown' }); // Move to second
      fireEvent.keyDown(input, { key: 'ArrowUp' }); // Move back to first

      const options = screen.getAllByRole('option');
      expect(options[0]).toHaveAttribute('aria-selected', 'true');

      jest.useRealTimers();
    });

    it('selects with Enter key', async () => {
      jest.useFakeTimers();
      const onSelectSuggestion = jest.fn();

      render(
        <PlacesAutocompleteInput
          {...defaultProps}
          value="123 Main"
          onSelectSuggestion={onSelectSuggestion}
        />
      );

      await act(async () => {
        jest.advanceTimersByTime(300);
      });

      await waitFor(() => {
        expect(screen.getByRole('listbox')).toBeInTheDocument();
      });

      const input = screen.getByRole('combobox');
      fireEvent.keyDown(input, { key: 'ArrowDown' });
      fireEvent.keyDown(input, { key: 'Enter' });

      expect(onSelectSuggestion).toHaveBeenCalled();

      jest.useRealTimers();
    });

    it('closes dropdown with Escape key', async () => {
      jest.useFakeTimers();

      render(<PlacesAutocompleteInput {...defaultProps} value="123 Main" />);

      await act(async () => {
        jest.advanceTimersByTime(300);
      });

      await waitFor(() => {
        expect(screen.getByRole('listbox')).toBeInTheDocument();
      });

      const input = screen.getByRole('combobox');
      fireEvent.keyDown(input, { key: 'Escape' });

      await waitFor(() => {
        expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
      });

      jest.useRealTimers();
    });

    it('wraps around when navigating past last item', async () => {
      jest.useFakeTimers();

      render(<PlacesAutocompleteInput {...defaultProps} value="123 Main" />);

      await act(async () => {
        jest.advanceTimersByTime(300);
      });

      await waitFor(() => {
        expect(screen.getByRole('listbox')).toBeInTheDocument();
      });

      const input = screen.getByRole('combobox');
      // Navigate to each item and wrap
      fireEvent.keyDown(input, { key: 'ArrowDown' }); // 1
      fireEvent.keyDown(input, { key: 'ArrowDown' }); // 2
      fireEvent.keyDown(input, { key: 'ArrowDown' }); // 3
      fireEvent.keyDown(input, { key: 'ArrowDown' }); // wrap to 1

      const options = screen.getAllByRole('option');
      expect(options[0]).toHaveAttribute('aria-selected', 'true');

      jest.useRealTimers();
    });
  });

  describe('focus and blur', () => {
    it('shows suggestions on focus if available', async () => {
      jest.useFakeTimers();

      render(
        <PlacesAutocompleteInput {...defaultProps} value="123 Main" />
      );

      await act(async () => {
        jest.advanceTimersByTime(300);
      });

      // Blur to close
      const input = screen.getByRole('combobox');
      fireEvent.blur(input);

      await act(async () => {
        jest.advanceTimersByTime(150);
      });

      expect(screen.queryByRole('listbox')).not.toBeInTheDocument();

      // Focus to reopen
      fireEvent.focus(input);

      expect(screen.getByRole('listbox')).toBeInTheDocument();

      jest.useRealTimers();
    });

    it('calls onBlur callback', () => {
      const onBlur = jest.fn();
      render(<PlacesAutocompleteInput {...defaultProps} onBlur={onBlur} />);

      const input = screen.getByRole('combobox');
      fireEvent.blur(input);

      expect(onBlur).toHaveBeenCalled();
    });

    it('calls onFocus callback', () => {
      const onFocus = jest.fn();
      render(<PlacesAutocompleteInput {...defaultProps} onFocus={onFocus} />);

      const input = screen.getByRole('combobox');
      fireEvent.focus(input);

      expect(onFocus).toHaveBeenCalled();
    });
  });

  describe('disabled state', () => {
    it('disables the input when disabled prop is true', () => {
      render(<PlacesAutocompleteInput {...defaultProps} disabled />);

      expect(screen.getByRole('combobox')).toBeDisabled();
    });

    it('does not fetch when disabled', async () => {
      jest.useFakeTimers();

      render(
        <PlacesAutocompleteInput {...defaultProps} value="123 Main" disabled />
      );

      await act(async () => {
        jest.advanceTimersByTime(300);
      });

      expect(mockFetch).not.toHaveBeenCalled();

      jest.useRealTimers();
    });

    it('does not call onValueChange when disabled', async () => {
      const onValueChange = jest.fn();
      const user = userEvent.setup();

      render(
        <PlacesAutocompleteInput
          {...defaultProps}
          onValueChange={onValueChange}
          disabled
        />
      );

      const input = screen.getByRole('combobox');
      await user.type(input, 'test');

      expect(onValueChange).not.toHaveBeenCalled();
    });
  });

  describe('error handling', () => {
    it('handles API error gracefully', async () => {
      jest.useFakeTimers();

      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
      });

      render(<PlacesAutocompleteInput {...defaultProps} value="123 Main" />);

      await act(async () => {
        jest.advanceTimersByTime(300);
      });

      // Should not show suggestions on error
      expect(screen.queryByRole('listbox')).not.toBeInTheDocument();

      jest.useRealTimers();
    });

    it('handles network error gracefully', async () => {
      jest.useFakeTimers();

      mockFetch.mockRejectedValueOnce(new Error('Network error'));

      render(<PlacesAutocompleteInput {...defaultProps} value="123 Main" />);

      await act(async () => {
        jest.advanceTimersByTime(300);
      });

      // Should not crash and not show suggestions
      expect(screen.queryByRole('listbox')).not.toBeInTheDocument();

      jest.useRealTimers();
    });
  });

  describe('accessibility', () => {
    it('has correct aria-expanded attribute', async () => {
      jest.useFakeTimers();

      render(<PlacesAutocompleteInput {...defaultProps} value="123 Main" />);

      const input = screen.getByRole('combobox');
      expect(input).toHaveAttribute('aria-expanded', 'false');

      await act(async () => {
        jest.advanceTimersByTime(300);
      });

      await waitFor(() => {
        expect(input).toHaveAttribute('aria-expanded', 'true');
      });

      jest.useRealTimers();
    });

    it('has aria-autocomplete attribute', () => {
      render(<PlacesAutocompleteInput {...defaultProps} />);

      expect(screen.getByRole('combobox')).toHaveAttribute('aria-autocomplete', 'list');
    });

    it('has aria-controls linking to listbox', async () => {
      jest.useFakeTimers();

      render(<PlacesAutocompleteInput {...defaultProps} value="123 Main" />);

      await act(async () => {
        jest.advanceTimersByTime(300);
      });

      await waitFor(() => {
        const input = screen.getByRole('combobox');
        const listboxId = input.getAttribute('aria-controls');
        expect(listboxId).toBeTruthy();
        expect(screen.getByRole('listbox')).toHaveAttribute('id', listboxId);
      });

      jest.useRealTimers();
    });
  });

  describe('suggestion scope', () => {
    it('sends scope parameter when specified', async () => {
      jest.useFakeTimers();

      render(
        <PlacesAutocompleteInput
          {...defaultProps}
          value="123 Main"
          suggestionScope="us"
        />
      );

      await act(async () => {
        jest.advanceTimersByTime(300);
      });

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('scope=us'),
        expect.any(Object)
      );

      jest.useRealTimers();
    });

    it('does not send scope for default value', async () => {
      jest.useFakeTimers();

      render(
        <PlacesAutocompleteInput
          {...defaultProps}
          value="123 Main"
          suggestionScope="default"
        />
      );

      await act(async () => {
        jest.advanceTimersByTime(300);
      });

      expect(mockFetch).toHaveBeenCalledWith(
        expect.not.stringContaining('scope='),
        expect.any(Object)
      );

      jest.useRealTimers();
    });
  });

  describe('onKeyDown passthrough', () => {
    it('calls onKeyDown callback', () => {
      const onKeyDown = jest.fn();
      render(<PlacesAutocompleteInput {...defaultProps} onKeyDown={onKeyDown} />);

      const input = screen.getByRole('combobox');
      fireEvent.keyDown(input, { key: 'a' });

      expect(onKeyDown).toHaveBeenCalled();
    });
  });

  describe('input props forwarding', () => {
    it('forwards inputProps to input element', () => {
      render(
        <PlacesAutocompleteInput
          {...defaultProps}
          inputProps={{ 'data-custom': 'value' }}
        />
      );

      expect(screen.getByRole('combobox')).toHaveAttribute('data-custom', 'value');
    });

    it('allows overriding autoComplete via inputProps', () => {
      render(
        <PlacesAutocompleteInput
          {...defaultProps}
          inputProps={{ autoComplete: 'on' }}
        />
      );

      expect(screen.getByRole('combobox')).toHaveAttribute('autocomplete', 'on');
    });
  });
});
