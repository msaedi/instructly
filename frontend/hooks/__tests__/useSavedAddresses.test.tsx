import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';

jest.mock('@/hooks/useSavedAddresses', () => jest.requireActual('@/hooks/useSavedAddresses'));
jest.mock('@/lib/api', () => ({
  fetchWithAuth: jest.fn(),
}));

import { useSavedAddresses, formatAddress, getAddressLabel } from '../useSavedAddresses';
import { fetchWithAuth } from '@/lib/api';

const fetchWithAuthMock = fetchWithAuth as jest.Mock;

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children);
  return { wrapper, queryClient };
};

describe('useSavedAddresses', () => {
  beforeEach(() => {
    fetchWithAuthMock.mockReset();
  });

  it('fetches user addresses', async () => {
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: jest.fn().mockResolvedValue({
        items: [
          {
            id: 'addr-1',
            label: 'home',
            street_line1: '123 Main St',
            locality: 'New York',
            administrative_area: 'NY',
            postal_code: '10001',
          },
        ],
        total: 1,
      }),
    });

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useSavedAddresses(), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.addresses).toHaveLength(1);
  });

  it('returns empty array when user has no addresses', async () => {
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: jest.fn().mockResolvedValue({ items: [], total: 0 }),
    });

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useSavedAddresses(), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.addresses).toEqual([]);
  });

  it('caches results', async () => {
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: jest.fn().mockResolvedValue({ items: [], total: 0 }),
    });

    const { wrapper, queryClient } = createWrapper();
    const { result } = renderHook(() => useSavedAddresses(), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(fetchWithAuthMock).toHaveBeenCalledTimes(1);

    const { result: second } = renderHook(() => useSavedAddresses(), { wrapper });
    await waitFor(() => expect(second.current.isSuccess).toBe(true));
    expect(fetchWithAuthMock).toHaveBeenCalledTimes(1);

    queryClient.clear();
  });
});

describe('formatAddress', () => {
  it('formats address with all fields', () => {
    const value = formatAddress({
      id: 'addr-1',
      label: 'home',
      street_line1: '123 Main St',
      street_line2: 'Apt 4B',
      locality: 'New York',
      administrative_area: 'NY',
      postal_code: '10001',
      is_active: true,
    });

    expect(value).toBe('123 Main St, Apt 4B, New York, NY 10001');
  });

  it('handles missing street_line2', () => {
    const value = formatAddress({
      id: 'addr-2',
      label: 'work',
      street_line1: '456 Market St',
      locality: 'San Francisco',
      administrative_area: 'CA',
      postal_code: '94105',
      is_active: true,
    });

    expect(value).toBe('456 Market St, San Francisco, CA 94105');
  });
});

describe('getAddressLabel', () => {
  it('capitalizes home/work labels', () => {
    const homeLabel = getAddressLabel({
      id: 'addr-1',
      label: 'home',
      street_line1: '123 Main St',
      locality: 'New York',
      administrative_area: 'NY',
      postal_code: '10001',
      is_active: true,
    });
    const workLabel = getAddressLabel({
      id: 'addr-2',
      label: 'work',
      street_line1: '456 Market St',
      locality: 'San Francisco',
      administrative_area: 'CA',
      postal_code: '94105',
      is_active: true,
    });

    expect(homeLabel).toBe('Home');
    expect(workLabel).toBe('Work');
  });

  it('uses custom_label for other', () => {
    const label = getAddressLabel({
      id: 'addr-3',
      label: 'other',
      custom_label: 'Studio',
      street_line1: '789 Broadway',
      locality: 'New York',
      administrative_area: 'NY',
      postal_code: '10003',
      is_active: true,
    });

    expect(label).toBe('Studio');
  });

  it('falls back to "Other" when custom_label missing', () => {
    const label = getAddressLabel({
      id: 'addr-4',
      label: 'other',
      street_line1: '101 State St',
      locality: 'Boston',
      administrative_area: 'MA',
      postal_code: '02108',
      is_active: true,
    });

    expect(label).toBe('Other');
  });

  it('falls back to "Other" for unknown labels', () => {
    const label = getAddressLabel({
      id: 'addr-5',
      label: 'favorite',
      street_line1: '12 Elm St',
      locality: 'Boston',
      administrative_area: 'MA',
      postal_code: '02108',
      is_active: true,
    });

    expect(label).toBe('Other');
  });
});
