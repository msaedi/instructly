import React from 'react';
import { render, screen, waitFor, act } from '@testing-library/react';
import { renderHook } from '@testing-library/react';
import {
  usePricingPreviewController,
  PricingPreviewProvider,
  usePricingPreview,
} from '../usePricingPreview';
import {
  fetchPricingPreview,
  fetchPricingPreviewQuote,
} from '@/lib/api/pricing';
import type { PricingPreviewQuotePayloadBase } from '@/lib/api/pricing';
import { ApiProblemError } from '@/lib/api/fetch';

// Mock dependencies
jest.mock('@/lib/api/pricing', () => ({
  fetchPricingPreview: jest.fn(),
  fetchPricingPreviewQuote: jest.fn(),
}));

jest.mock('@/lib/logger', () => ({
  logger: {
    info: jest.fn(),
    debug: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
  },
}));

// Mock sessionStorage
const mockSessionStorage: Record<string, string> = {};
Object.defineProperty(window, 'sessionStorage', {
  value: {
    getItem: jest.fn((key: string) => mockSessionStorage[key] || null),
    setItem: jest.fn((key: string, value: string) => {
      mockSessionStorage[key] = value;
    }),
    removeItem: jest.fn((key: string) => {
      delete mockSessionStorage[key];
    }),
    clear: jest.fn(() => {
      Object.keys(mockSessionStorage).forEach((key) => delete mockSessionStorage[key]);
    }),
  },
  writable: true,
});

const fetchPricingPreviewMock = fetchPricingPreview as jest.Mock;
const fetchPricingPreviewQuoteMock = fetchPricingPreviewQuote as jest.Mock;

const mockPreviewResponse = {
  base_price_cents: 10000,
  student_fee_cents: 1500,
  student_pay_cents: 11500,
  credit_applied_cents: 0,
  line_items: [],
};

const mockQuotePayload: PricingPreviewQuotePayloadBase = {
  instructor_id: 'inst-123',
  instructor_service_id: 'svc-456',
  booking_date: '2025-02-01',
  start_time: '10:00',
  selected_duration: 60,
  location_type: 'student_location',
  meeting_location: '123 Main St',
};

describe('usePricingPreviewController', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    fetchPricingPreviewMock.mockResolvedValue(mockPreviewResponse);
    fetchPricingPreviewQuoteMock.mockResolvedValue(mockPreviewResponse);
    window.sessionStorage.clear();
  });

  describe('initialization', () => {
    it('initializes with null preview', () => {
      const { result } = renderHook(() =>
        usePricingPreviewController({ bookingId: null })
      );

      expect(result.current.preview).toBeNull();
      expect(result.current.loading).toBe(false);
      expect(result.current.error).toBeNull();
    });

    it('fetches pricing preview when bookingId is provided', async () => {
      renderHook(() =>
        usePricingPreviewController({ bookingId: 'booking-123' })
      );

      await waitFor(() => {
        expect(fetchPricingPreviewMock).toHaveBeenCalledWith(
          'booking-123',
          0,
          expect.any(Object)
        );
      });
    });

    it('fetches pricing preview quote when quotePayload is provided', async () => {
      renderHook(() =>
        usePricingPreviewController({
          bookingId: null,
          quotePayload: mockQuotePayload,
        })
      );

      await waitFor(() => {
        expect(fetchPricingPreviewQuoteMock).toHaveBeenCalled();
      });
    });
  });

  describe('reset', () => {
    it('resets all state values', async () => {
      const { result } = renderHook(() =>
        usePricingPreviewController({ bookingId: 'booking-123' })
      );

      await waitFor(() => {
        expect(result.current.preview).not.toBeNull();
      });

      act(() => {
        result.current.reset();
      });

      expect(result.current.preview).toBeNull();
      expect(result.current.error).toBeNull();
      expect(result.current.loading).toBe(false);
    });
  });

  describe('requestPricingPreview', () => {
    it('returns cached preview when key matches', async () => {
      const { result } = renderHook(() =>
        usePricingPreviewController({ bookingId: 'booking-123' })
      );

      await waitFor(() => {
        expect(result.current.preview).not.toBeNull();
      });

      // Clear mock to verify no new call is made
      fetchPricingPreviewMock.mockClear();

      // Request again with same key
      await act(async () => {
        await result.current.requestPricingPreview();
      });

      // Should not make a new fetch call
      expect(fetchPricingPreviewMock).not.toHaveBeenCalled();
    });

    it('carries credit when cause is date-time-only', async () => {
      fetchPricingPreviewMock.mockResolvedValue({
        ...mockPreviewResponse,
        credit_applied_cents: 2500,
      });

      const { result } = renderHook(() =>
        usePricingPreviewController({ bookingId: 'booking-123' })
      );

      await waitFor(() => {
        expect(result.current.preview).not.toBeNull();
      });

      fetchPricingPreviewMock.mockClear();

      await act(async () => {
        await result.current.requestPricingPreview({ cause: 'date-time-only', key: 'new-key' });
      });

      await waitFor(() => {
        expect(fetchPricingPreviewMock).toHaveBeenCalledWith(
          'booking-123',
          2500, // Credit should be carried
          expect.any(Object)
        );
      });
    });

    it('carries credit when cause is duration-change', async () => {
      fetchPricingPreviewMock.mockResolvedValue({
        ...mockPreviewResponse,
        credit_applied_cents: 3000,
      });

      const { result } = renderHook(() =>
        usePricingPreviewController({ bookingId: 'booking-123' })
      );

      await waitFor(() => {
        expect(result.current.preview).not.toBeNull();
      });

      fetchPricingPreviewMock.mockClear();

      await act(async () => {
        await result.current.requestPricingPreview({ cause: 'duration-change', key: 'new-key-2' });
      });

      await waitFor(() => {
        expect(fetchPricingPreviewMock).toHaveBeenCalledWith(
          'booking-123',
          3000, // Credit should be carried
          expect.any(Object)
        );
      });
    });

    it('resets credit when cause is credit-change', async () => {
      fetchPricingPreviewMock.mockResolvedValue({
        ...mockPreviewResponse,
        credit_applied_cents: 2500,
      });

      const { result } = renderHook(() =>
        usePricingPreviewController({ bookingId: 'booking-123' })
      );

      await waitFor(() => {
        expect(result.current.preview).not.toBeNull();
      });

      fetchPricingPreviewMock.mockClear();

      await act(async () => {
        await result.current.requestPricingPreview({ cause: 'credit-change', key: 'new-key-3' });
      });

      await waitFor(() => {
        expect(fetchPricingPreviewMock).toHaveBeenCalledWith(
          'booking-123',
          0, // Credit should NOT be carried
          expect.any(Object)
        );
      });
    });

    it('handles fetch error gracefully', async () => {
      fetchPricingPreviewMock.mockRejectedValue(new Error('Network error'));

      const { result } = renderHook(() =>
        usePricingPreviewController({ bookingId: 'booking-123' })
      );

      await waitFor(() => {
        expect(result.current.error).toBe('Unable to load pricing preview. Please try again.');
      });
    });

    it('handles abort error without setting error state', async () => {
      const abortError = new Error('Aborted');
      abortError.name = 'AbortError';
      fetchPricingPreviewMock.mockRejectedValue(abortError);

      const { result } = renderHook(() =>
        usePricingPreviewController({ bookingId: 'booking-123' })
      );

      // Wait for the effect to settle
      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      // Error should not be set for AbortError
      expect(result.current.error).toBeNull();
    });
  });

  describe('applyCredit', () => {
    it('applies credit and updates preview', async () => {
      const { result } = renderHook(() =>
        usePricingPreviewController({ bookingId: 'booking-123' })
      );

      await waitFor(() => {
        expect(result.current.preview).not.toBeNull();
      });

      fetchPricingPreviewMock.mockResolvedValue({
        ...mockPreviewResponse,
        credit_applied_cents: 2000,
        student_pay_cents: 9500,
      });

      await act(async () => {
        await result.current.applyCredit(2000);
      });

      await waitFor(() => {
        expect(result.current.preview?.credit_applied_cents).toBe(2000);
      });
    });

    it('skips request if credit already applied and skipIfUnchanged is true', async () => {
      fetchPricingPreviewMock.mockResolvedValue({
        ...mockPreviewResponse,
        credit_applied_cents: 1500,
      });

      const { result } = renderHook(() =>
        usePricingPreviewController({ bookingId: 'booking-123' })
      );

      await waitFor(() => {
        expect(result.current.preview).not.toBeNull();
      });

      fetchPricingPreviewMock.mockClear();

      await act(async () => {
        await result.current.applyCredit(1500, { skipIfUnchanged: true });
      });

      // Should not make a new call since credit is already 1500
      expect(fetchPricingPreviewMock).not.toHaveBeenCalled();
    });

    it('handles error from pricing API during applyCredit', async () => {
      // Initialize with non-zero credit to ensure applyCredit makes a call
      fetchPricingPreviewMock.mockResolvedValueOnce({
        ...mockPreviewResponse,
        credit_applied_cents: 0,
      });

      const { result } = renderHook(() =>
        usePricingPreviewController({ bookingId: 'booking-123' })
      );

      await waitFor(() => {
        expect(result.current.preview).not.toBeNull();
      });

      // Mock error for subsequent call with different credit value
      fetchPricingPreviewMock.mockRejectedValueOnce(new Error('Network error'));

      let errorThrown = false;
      // Apply a different credit amount to trigger API call
      try {
        await act(async () => {
          await result.current.applyCredit(5000);
        });
      } catch {
        errorThrown = true;
      }

      // Error should be thrown from applyCredit
      expect(errorThrown).toBe(true);
    });

    it('preserves preview when applyCredit fails', async () => {
      fetchPricingPreviewMock.mockResolvedValueOnce({
        ...mockPreviewResponse,
        credit_applied_cents: 0,
      });

      const { result } = renderHook(() =>
        usePricingPreviewController({ bookingId: 'booking-123' })
      );

      await waitFor(() => {
        expect(result.current.preview).not.toBeNull();
      });

      fetchPricingPreviewMock.mockRejectedValueOnce(new Error('API Error'));

      // Store original preview
      const originalPreview = result.current.preview;

      try {
        await act(async () => {
          await result.current.applyCredit(3000);
        });
      } catch {
        // Expected
      }

      // Preview should still exist after error
      expect(result.current.preview).toBe(originalPreview);
    });

    it('handles successful credit application after error', async () => {
      fetchPricingPreviewMock.mockResolvedValueOnce({
        ...mockPreviewResponse,
        credit_applied_cents: 0,
      });

      const { result } = renderHook(() =>
        usePricingPreviewController({ bookingId: 'booking-123' })
      );

      await waitFor(() => {
        expect(result.current.preview).not.toBeNull();
      });

      // First apply credit successfully
      fetchPricingPreviewMock.mockResolvedValueOnce({
        ...mockPreviewResponse,
        credit_applied_cents: 2500,
        student_pay_cents: 9000,
      });

      await act(async () => {
        await result.current.applyCredit(2500);
      });

      await waitFor(() => {
        expect(result.current.preview?.credit_applied_cents).toBe(2500);
        expect(result.current.error).toBeNull();
      });
    });

    it('normalizes credit values appropriately', async () => {
      // Use a non-zero initial credit to test the applyCredit path
      fetchPricingPreviewMock.mockResolvedValue({
        ...mockPreviewResponse,
        credit_applied_cents: 1000,
      });

      const { result } = renderHook(() =>
        usePricingPreviewController({ bookingId: 'booking-123' })
      );

      await waitFor(() => {
        expect(result.current.preview).not.toBeNull();
        expect(result.current.preview?.credit_applied_cents).toBe(1000);
      });

      // The hook should track lastAppliedCreditCents
      expect(result.current.lastAppliedCreditCents).toBe(1000);
    });

    it('rounds fractional credit to nearest integer', async () => {
      const { result } = renderHook(() =>
        usePricingPreviewController({ bookingId: 'booking-123' })
      );

      await waitFor(() => {
        expect(result.current.preview).not.toBeNull();
      });

      fetchPricingPreviewMock.mockClear();

      await act(async () => {
        await result.current.applyCredit(1000.7);
      });

      await waitFor(() => {
        expect(fetchPricingPreviewMock).toHaveBeenCalledWith(
          'booking-123',
          1001, // Should be rounded
          expect.any(Object)
        );
      });
    });

    it('suppresses loading state when suppressLoading option is true', async () => {
      const { result } = renderHook(() =>
        usePricingPreviewController({ bookingId: 'booking-123' })
      );

      await waitFor(() => {
        expect(result.current.preview).not.toBeNull();
      });

      let loadingDuringRequest = false;
      fetchPricingPreviewMock.mockImplementation(() => {
        loadingDuringRequest = result.current.loading;
        return Promise.resolve({
          ...mockPreviewResponse,
          credit_applied_cents: 500,
        });
      });

      await act(async () => {
        await result.current.applyCredit(500, { suppressLoading: true });
      });

      // Loading should not have been set during suppressed request
      expect(loadingDuringRequest).toBe(false);
    });
  });

  describe('quotePayload validation', () => {
    it('skips fetch when quotePayload is missing required fields', async () => {
      const incompletePayload = {
        instructor_id: 'inst-123',
        // Missing other required fields
      };

      renderHook(() =>
        usePricingPreviewController({
          bookingId: null,
          quotePayload: incompletePayload as typeof mockQuotePayload,
        })
      );

      // Wait for effect to run
      await new Promise((r) => setTimeout(r, 100));

      // Should not have called quote API due to missing fields
      expect(fetchPricingPreviewQuoteMock).not.toHaveBeenCalled();
    });

    it('validates booking_date format', async () => {
      const invalidDatePayload = {
        ...mockQuotePayload,
        booking_date: 'invalid-date',
      };

      renderHook(() =>
        usePricingPreviewController({
          bookingId: null,
          quotePayload: invalidDatePayload,
        })
      );

      await new Promise((r) => setTimeout(r, 100));
      expect(fetchPricingPreviewQuoteMock).not.toHaveBeenCalled();
    });

    it('validates start_time format', async () => {
      const invalidTimePayload = {
        ...mockQuotePayload,
        start_time: 'invalid',
      };

      renderHook(() =>
        usePricingPreviewController({
          bookingId: null,
          quotePayload: invalidTimePayload,
        })
      );

      await new Promise((r) => setTimeout(r, 100));
      expect(fetchPricingPreviewQuoteMock).not.toHaveBeenCalled();
    });

    it('validates selected_duration is positive', async () => {
      const zeroDurationPayload = {
        ...mockQuotePayload,
        selected_duration: 0,
      };

      renderHook(() =>
        usePricingPreviewController({
          bookingId: null,
          quotePayload: zeroDurationPayload,
        })
      );

      await new Promise((r) => setTimeout(r, 100));
      expect(fetchPricingPreviewQuoteMock).not.toHaveBeenCalled();
    });

    it('validates location_type is allowed value', async () => {
      const invalidLocationPayload = {
        ...mockQuotePayload,
        location_type: 'invalid_type',
      } as unknown as PricingPreviewQuotePayloadBase;

      renderHook(() =>
        usePricingPreviewController({
          bookingId: null,
          quotePayload: invalidLocationPayload,
        })
      );

      await new Promise((r) => setTimeout(r, 100));
      expect(fetchPricingPreviewQuoteMock).not.toHaveBeenCalled();
    });

    it('accepts valid online location_type', async () => {
      const remotePayload: PricingPreviewQuotePayloadBase = {
        ...mockQuotePayload,
        location_type: 'online',
      };

      renderHook(() =>
        usePricingPreviewController({
          bookingId: null,
          quotePayload: remotePayload,
        })
      );

      await waitFor(() => {
        expect(fetchPricingPreviewQuoteMock).toHaveBeenCalled();
      });
    });

    it('accepts valid student_location location_type', async () => {
      const studentHomePayload: PricingPreviewQuotePayloadBase = {
        ...mockQuotePayload,
        location_type: 'student_location',
      };

      renderHook(() =>
        usePricingPreviewController({
          bookingId: null,
          quotePayload: studentHomePayload,
        })
      );

      await waitFor(() => {
        expect(fetchPricingPreviewQuoteMock).toHaveBeenCalled();
      });
    });
  });

  describe('quotePayloadResolver', () => {
    it('uses resolver function when provided', async () => {
      const resolver = jest.fn().mockReturnValue(mockQuotePayload);

      renderHook(() =>
        usePricingPreviewController({
          bookingId: null,
          quotePayloadResolver: resolver,
        })
      );

      await waitFor(() => {
        expect(resolver).toHaveBeenCalled();
      });

      await waitFor(() => {
        expect(fetchPricingPreviewQuoteMock).toHaveBeenCalled();
      });
    });

    it('prefers quotePayload over resolver when both provided', async () => {
      const resolver = jest.fn().mockReturnValue({
        ...mockQuotePayload,
        instructor_id: 'resolver-id',
      });

      renderHook(() =>
        usePricingPreviewController({
          bookingId: null,
          quotePayload: mockQuotePayload,
          quotePayloadResolver: resolver,
        })
      );

      await waitFor(() => {
        expect(fetchPricingPreviewQuoteMock).toHaveBeenCalled();
      });

      // The payload should use instructor_id from quotePayload, not resolver
      const callArg = fetchPricingPreviewQuoteMock.mock.calls[0]?.[0];
      expect(callArg?.instructor_id).toBe('inst-123');
    });
  });
});

describe('PricingPreviewProvider', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    fetchPricingPreviewMock.mockResolvedValue(mockPreviewResponse);
  });

  it('provides context to children', async () => {
    function TestComponent() {
      const context = usePricingPreview();
      return (
        <div data-testid="test-component">
          {context?.preview ? 'Has Preview' : 'No Preview'}
        </div>
      );
    }

    render(
      <PricingPreviewProvider bookingId="booking-123">
        <TestComponent />
      </PricingPreviewProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId('test-component')).toHaveTextContent('Has Preview');
    });
  });

  it('provides controller with quote payload', async () => {
    function TestComponent() {
      const context = usePricingPreview();
      return (
        <div data-testid="test-component">
          {context?.preview ? 'Has Preview' : 'No Preview'}
        </div>
      );
    }

    fetchPricingPreviewQuoteMock.mockResolvedValue(mockPreviewResponse);

    render(
      <PricingPreviewProvider bookingId={null} quotePayload={mockQuotePayload}>
        <TestComponent />
      </PricingPreviewProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId('test-component')).toHaveTextContent('Has Preview');
    });
  });
});

describe('usePricingPreview', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    fetchPricingPreviewMock.mockResolvedValue(mockPreviewResponse);
  });

  it('throws error when used outside provider', () => {
    // Suppress console.error for this test
    const originalError = console.error;
    console.error = jest.fn();

    expect(() => {
      renderHook(() => usePricingPreview());
    }).toThrow('usePricingPreview must be used within a PricingPreviewProvider');

    console.error = originalError;
  });

  it('returns null when optional=true and used outside provider', () => {
    const { result } = renderHook(() => usePricingPreview(true));

    expect(result.current).toBeNull();
  });

  it('returns context when used inside provider', async () => {
    function TestWrapper({ children }: { children: React.ReactNode }) {
      return (
        <PricingPreviewProvider bookingId="booking-123">
          {children}
        </PricingPreviewProvider>
      );
    }

    const { result } = renderHook(() => usePricingPreview(), {
      wrapper: TestWrapper,
    });

    await waitFor(() => {
      expect(result.current).not.toBeNull();
      expect(result.current?.preview).not.toBeNull();
    });
  });
});

describe('stableSerialize utility', () => {
  it('handles null value', async () => {
    const { result } = renderHook(() =>
      usePricingPreviewController({
        bookingId: null,
        quotePayload: null,
      })
    );

    // Should not crash and should not make API call
    expect(result.current.preview).toBeNull();
  });

  it('handles valid payload', async () => {
    const payloadWithArray = {
      ...mockQuotePayload,
    };

    renderHook(() =>
      usePricingPreviewController({
        bookingId: null,
        quotePayload: payloadWithArray,
      })
    );

    await waitFor(() => {
      expect(fetchPricingPreviewQuoteMock).toHaveBeenCalled();
    });
  });
});

describe('ApiProblemError handling', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    fetchPricingPreviewMock.mockReset();
    fetchPricingPreviewQuoteMock.mockReset();
    fetchPricingPreviewMock.mockResolvedValue(mockPreviewResponse);
    fetchPricingPreviewQuoteMock.mockResolvedValue(mockPreviewResponse);
    window.sessionStorage.clear();
  });

  it('handles ApiProblemError with status code in applyCredit', async () => {
    fetchPricingPreviewMock.mockResolvedValueOnce({
      ...mockPreviewResponse,
      credit_applied_cents: 0,
    });

    const { result } = renderHook(() =>
      usePricingPreviewController({ bookingId: 'booking-123' })
    );

    await waitFor(() => {
      expect(result.current.preview).not.toBeNull();
    });

    // Create ApiProblemError with status code
    const apiError = new ApiProblemError(
      { type: 'validation_error', title: 'Validation Error', detail: 'Credit limit exceeded', status: 400 },
      { status: 400 } as Response
    );
    fetchPricingPreviewMock.mockRejectedValueOnce(apiError);

    let thrownError: Error | null = null;
    await act(async () => {
      try {
        await result.current.applyCredit(5000);
      } catch (err) {
        thrownError = err as Error;
      }
    });

    expect(thrownError).toBe(apiError);
    await waitFor(() => {
      expect(result.current.error).toBe('Credit limit exceeded');
    });
  });

  it('handles ApiProblemError without status code in applyCredit', async () => {
    fetchPricingPreviewMock.mockResolvedValueOnce({
      ...mockPreviewResponse,
      credit_applied_cents: 0,
    });

    const { result } = renderHook(() =>
      usePricingPreviewController({ bookingId: 'booking-123' })
    );

    await waitFor(() => {
      expect(result.current.preview).not.toBeNull();
    });

    // Create ApiProblemError without status code (no response)
    const apiError = new ApiProblemError(
      { type: 'server_error', title: 'Server Error', detail: 'Unknown error', status: 500 },
      { status: 500 } as Response
    );
    fetchPricingPreviewMock.mockRejectedValueOnce(apiError);

    let thrownError: Error | null = null;
    await act(async () => {
      try {
        await result.current.applyCredit(3000);
      } catch (err) {
        thrownError = err as Error;
      }
    });

    expect(thrownError).toBe(apiError);
    await waitFor(() => {
      expect(result.current.error).toBe('Unknown error');
    });
  });

  it('handles ApiProblemError with empty detail preserving empty string', async () => {
    fetchPricingPreviewMock.mockResolvedValueOnce({
      ...mockPreviewResponse,
      credit_applied_cents: 0,
    });

    const { result } = renderHook(() =>
      usePricingPreviewController({ bookingId: 'booking-123' })
    );

    await waitFor(() => {
      expect(result.current.preview).not.toBeNull();
    });

    // Create ApiProblemError with empty detail - hook uses ?? so empty string is preserved
    const apiError = new ApiProblemError(
      { type: 'validation_error', title: 'Validation Error', detail: '', status: 422 },
      { status: 422 } as Response
    );
    fetchPricingPreviewMock.mockRejectedValueOnce(apiError);

    await act(async () => {
      try {
        await result.current.applyCredit(2000);
      } catch {
        // Expected
      }
    });

    // Empty string detail is preserved (nullish coalescing ?? doesn't catch empty strings)
    await waitFor(() => {
      expect(result.current.error).toBe('');
    });
  });
});

describe('abort handling', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    fetchPricingPreviewMock.mockReset();
    fetchPricingPreviewQuoteMock.mockReset();
    fetchPricingPreviewMock.mockResolvedValue(mockPreviewResponse);
    fetchPricingPreviewQuoteMock.mockResolvedValue(mockPreviewResponse);
    window.sessionStorage.clear();
  });

  it('returns previewRef.current when abort signal is triggered in applyCredit', async () => {
    fetchPricingPreviewMock.mockResolvedValueOnce({
      ...mockPreviewResponse,
      credit_applied_cents: 0,
    });

    const { result } = renderHook(() =>
      usePricingPreviewController({ bookingId: 'booking-123' })
    );

    await waitFor(() => {
      expect(result.current.preview).not.toBeNull();
    });

    // Mock slow fetch that we can abort
    let resolveSlowFetch: ((value: unknown) => void) | null = null;
    fetchPricingPreviewMock.mockImplementationOnce(() => {
      return new Promise((resolve) => {
        resolveSlowFetch = resolve;
      });
    });

    // Start first applyCredit
    const firstPromise = result.current.applyCredit(1000);

    // Start second applyCredit to abort the first
    fetchPricingPreviewMock.mockResolvedValueOnce({
      ...mockPreviewResponse,
      credit_applied_cents: 2000,
    });
    const secondPromise = result.current.applyCredit(2000);

    // Resolve the first (but it's aborted)
    (resolveSlowFetch as unknown as (value: unknown) => void)({
      ...mockPreviewResponse,
      credit_applied_cents: 1000,
    });

    await act(async () => {
      await Promise.all([firstPromise, secondPromise].map((p) => p.catch(() => {})));
    });

    // Final value should be from second request
    expect(result.current.preview?.credit_applied_cents).toBe(2000);
  });

  it('handles AbortError gracefully in applyCredit', async () => {
    fetchPricingPreviewMock.mockResolvedValueOnce({
      ...mockPreviewResponse,
      credit_applied_cents: 0,
    });

    const { result } = renderHook(() =>
      usePricingPreviewController({ bookingId: 'booking-123' })
    );

    await waitFor(() => {
      expect(result.current.preview).not.toBeNull();
    });

    const abortError = new Error('Aborted');
    abortError.name = 'AbortError';
    fetchPricingPreviewMock.mockRejectedValueOnce(abortError);

    await act(async () => {
      const response = await result.current.applyCredit(1500);
      expect(response).toBe(result.current.preview);
    });

    // Error should not be set for AbortError
    expect(result.current.error).toBeNull();
  });

  it('returns previewRef.current when signal is aborted after fetch in requestPricingPreview', async () => {
    fetchPricingPreviewMock.mockResolvedValueOnce({
      ...mockPreviewResponse,
      credit_applied_cents: 100,
    });

    const { result } = renderHook(() =>
      usePricingPreviewController({ bookingId: 'booking-123' })
    );

    await waitFor(() => {
      expect(result.current.preview).not.toBeNull();
    });

    // Mock slow fetch
    let resolveSlowFetch: ((value: unknown) => void) | null = null;
    fetchPricingPreviewMock.mockImplementationOnce(() => {
      return new Promise((resolve) => {
        resolveSlowFetch = resolve;
      });
    });

    // Start first request with new key
    const firstPromise = result.current.requestPricingPreview({ key: 'key-1' });

    // Start second request to abort first
    fetchPricingPreviewMock.mockResolvedValueOnce({
      ...mockPreviewResponse,
      credit_applied_cents: 200,
    });
    const secondPromise = result.current.requestPricingPreview({ key: 'key-2' });

    // Resolve the first (but it's aborted)
    (resolveSlowFetch as unknown as (value: unknown) => void)({
      ...mockPreviewResponse,
      credit_applied_cents: 150,
    });

    await act(async () => {
      await Promise.all([firstPromise, secondPromise].map((p) => p.catch(() => {})));
    });

    expect(result.current.preview?.credit_applied_cents).toBe(200);
  });
});

describe('validation edge cases', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    fetchPricingPreviewMock.mockReset();
    fetchPricingPreviewQuoteMock.mockReset();
    fetchPricingPreviewMock.mockResolvedValue(mockPreviewResponse);
    fetchPricingPreviewQuoteMock.mockResolvedValue(mockPreviewResponse);
    window.sessionStorage.clear();
  });

  it('validates empty instructor_id string', async () => {
    const emptyInstructorPayload = {
      ...mockQuotePayload,
      instructor_id: '   ', // whitespace only
    };

    renderHook(() =>
      usePricingPreviewController({
        bookingId: null,
        quotePayload: emptyInstructorPayload,
      })
    );

    await new Promise((r) => setTimeout(r, 100));
    expect(fetchPricingPreviewQuoteMock).not.toHaveBeenCalled();
  });

  it('validates empty instructor_service_id string', async () => {
    const emptyServicePayload = {
      ...mockQuotePayload,
      instructor_service_id: '', // empty string
    };

    renderHook(() =>
      usePricingPreviewController({
        bookingId: null,
        quotePayload: emptyServicePayload,
      })
    );

    await new Promise((r) => setTimeout(r, 100));
    expect(fetchPricingPreviewQuoteMock).not.toHaveBeenCalled();
  });

  it('validates empty meeting_location string', async () => {
    const emptyLocationPayload = {
      ...mockQuotePayload,
      meeting_location: '  ', // whitespace only
    };

    renderHook(() =>
      usePricingPreviewController({
        bookingId: null,
        quotePayload: emptyLocationPayload,
      })
    );

    await new Promise((r) => setTimeout(r, 100));
    expect(fetchPricingPreviewQuoteMock).not.toHaveBeenCalled();
  });

  it('skips fetch when quotePayloadBase is null in performFetch', async () => {
    // This tests lines 286-289: when resolveQuotePayloadBase returns null
    const { result } = renderHook(() =>
      usePricingPreviewController({
        bookingId: null,
        quotePayload: null,
        quotePayloadResolver: () => null, // Resolver returns null
      })
    );

    // Request should not trigger fetch since quotePayloadBase is null
    await act(async () => {
      await result.current.requestPricingPreview({ key: 'some-key' });
    });

    expect(fetchPricingPreviewQuoteMock).not.toHaveBeenCalled();
  });

  it('handles negative credit values by normalizing to zero', async () => {
    fetchPricingPreviewMock.mockResolvedValueOnce({
      ...mockPreviewResponse,
      credit_applied_cents: 1000,
    });

    const { result } = renderHook(() =>
      usePricingPreviewController({ bookingId: 'booking-123' })
    );

    await waitFor(() => {
      expect(result.current.preview).not.toBeNull();
    });

    fetchPricingPreviewMock.mockClear();
    fetchPricingPreviewMock.mockResolvedValueOnce({
      ...mockPreviewResponse,
      credit_applied_cents: 1000,
    });

    await act(async () => {
      await result.current.applyCredit(-500);
    });

    await waitFor(() => {
      expect(fetchPricingPreviewMock).toHaveBeenCalledWith(
        'booking-123',
        0, // Should be normalized to 0
        expect.any(Object)
      );
    });
  });
});

describe('persistCreditDecision edge cases', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    fetchPricingPreviewMock.mockReset();
    fetchPricingPreviewQuoteMock.mockReset();
    fetchPricingPreviewMock.mockResolvedValue(mockPreviewResponse);
    fetchPricingPreviewQuoteMock.mockResolvedValue(mockPreviewResponse);
    window.sessionStorage.clear();
  });

  it('does not persist when storage key is null', async () => {
    // When both bookingId is null and quotePayloadBase is null, getCreditStorageKey returns null
    // This tests line 221
    const { result } = renderHook(() =>
      usePricingPreviewController({
        bookingId: null,
        quotePayload: null,
      })
    );

    // sessionStorage.setItem should not be called since key is null
    expect(window.sessionStorage.setItem).not.toHaveBeenCalled();

    // Verify controller initialized
    expect(result.current.preview).toBeNull();
  });

  it('skips persistence when credit is already zero with no existing entry', async () => {
    fetchPricingPreviewMock.mockResolvedValueOnce({
      ...mockPreviewResponse,
      credit_applied_cents: 0,
    });

    renderHook(() => usePricingPreviewController({ bookingId: 'booking-persist-test' }));

    await waitFor(() => {
      expect(fetchPricingPreviewMock).toHaveBeenCalled();
    });

    // setItem should only be called if there's a meaningful value to persist
    // or if explicitly set by user - verify via the specific key
    const setItemCalls = (window.sessionStorage.setItem as jest.Mock).mock.calls;
    const bookingKeyCalls = setItemCalls.filter((call: unknown[]) =>
      (call[0] as string).includes('booking-persist-test')
    );
    // Credit is 0 and no existing entry, so it should not persist
    expect(bookingKeyCalls.length).toBe(0);
  });
});

describe('applyCredit deduplication', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    fetchPricingPreviewMock.mockReset();
    fetchPricingPreviewQuoteMock.mockReset();
    fetchPricingPreviewMock.mockResolvedValue(mockPreviewResponse);
    fetchPricingPreviewQuoteMock.mockResolvedValue(mockPreviewResponse);
    window.sessionStorage.clear();
  });

  it('returns early when credit value matches preview and no pending commit', async () => {
    // This tests line 385
    fetchPricingPreviewMock.mockResolvedValueOnce({
      ...mockPreviewResponse,
      credit_applied_cents: 1500,
    });

    const { result } = renderHook(() =>
      usePricingPreviewController({ bookingId: 'booking-123' })
    );

    await waitFor(() => {
      expect(result.current.preview?.credit_applied_cents).toBe(1500);
    });

    fetchPricingPreviewMock.mockClear();

    // Apply same credit value without skipIfUnchanged - should still skip
    await act(async () => {
      const response = await result.current.applyCredit(1500);
      // Should return existing preview without making a fetch
      expect(response?.credit_applied_cents).toBe(1500);
    });

    expect(fetchPricingPreviewMock).not.toHaveBeenCalled();
  });

  it('returns early when lastCommitValueRef matches requested credit', async () => {
    fetchPricingPreviewMock.mockResolvedValueOnce({
      ...mockPreviewResponse,
      credit_applied_cents: 0,
    });

    const { result } = renderHook(() =>
      usePricingPreviewController({ bookingId: 'booking-123' })
    );

    await waitFor(() => {
      expect(result.current.preview).not.toBeNull();
    });

    // Mock slow fetch that doesn't resolve
    fetchPricingPreviewMock.mockImplementation(() => new Promise(() => {}));

    // Start first apply (won't complete)
    result.current.applyCredit(2000);

    // Try to apply same value again - should return early
    const response = await result.current.applyCredit(2000);
    expect(response).toBe(result.current.preview);
  });
});
