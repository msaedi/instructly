import { renderHook, waitFor } from '@testing-library/react';
import { usePricingFloors } from '../usePricingFloors';
import { fetchPricingConfig } from '@/lib/api/pricing';

jest.mock('@/lib/api/pricing', () => ({
  fetchPricingConfig: jest.fn(),
}));

const mockFloors = { private_in_person: 8500, private_remote: 6500 };

describe('usePricingFloors', () => {
  beforeEach(() => {
    jest.resetAllMocks();
  });

  it('fetches pricing floors and exposes them to consumers', async () => {
    (fetchPricingConfig as jest.Mock).mockResolvedValue({
      config: { price_floor_cents: mockFloors },
      updated_at: null,
    });

    const { result } = renderHook(() => usePricingFloors());

    expect(result.current.isLoading).toBe(true);

    await waitFor(() => {
      expect(result.current.floors).toEqual(mockFloors);
      expect(result.current.isLoading).toBe(false);
      expect(result.current.error).toBeNull();
    });
  });

  it('reuses cached floors without refetching on re-render', async () => {
    (fetchPricingConfig as jest.Mock).mockResolvedValue({
      config: { price_floor_cents: mockFloors },
      updated_at: '2024-01-01T00:00:00Z',
    });

    const { result, rerender } = renderHook(() => usePricingFloors());

    await waitFor(() => {
      expect(result.current.floors).toEqual(mockFloors);
    });

    rerender();

    expect(fetchPricingConfig).toHaveBeenCalledTimes(1);
    expect(result.current.floors).toEqual(mockFloors);
  });
});
