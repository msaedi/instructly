import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import { AddressModal } from '../page';

const mockFetchWithAuth = jest.fn();

jest.mock('@/lib/api', () => ({
  API_ENDPOINTS: {},
  fetchAPI: jest.fn(),
  fetchWithAuth: (...args: unknown[]) => mockFetchWithAuth(...args),
}));

jest.mock('@/lib/logger', () => ({
  logger: {
    info: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
    debug: jest.fn(),
    time: jest.fn(),
    timeEnd: jest.fn(),
  },
}));

jest.mock('sonner', () => ({
  toast: {
    success: jest.fn(),
    error: jest.fn(),
    info: jest.fn(),
  },
}));

describe('AddressModal custom labels', () => {
  beforeEach(() => {
    mockFetchWithAuth.mockReset();
  });

  it('requires a custom label when label is other', () => {
    render(
      <AddressModal
        mode="create"
        onClose={jest.fn()}
        onSaved={jest.fn()}
      />,
    );

    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'other' } });

    expect(screen.getByPlaceholderText('e.g., Parent, Studio, School')).toBeInTheDocument();
    expect(screen.getByText(/custom label is required/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /save/i })).toBeDisabled();
  });

  it('submits a trimmed custom label when label is other', async () => {
    mockFetchWithAuth.mockResolvedValue({ ok: true });
    const onSaved = jest.fn();

    render(
      <AddressModal
        mode="create"
        onClose={jest.fn()}
        onSaved={onSaved}
      />,
    );

    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'other' } });
    fireEvent.change(screen.getByPlaceholderText('e.g., Parent, Studio, School'), {
      target: { value: '  Studio  ' },
    });

    fireEvent.click(screen.getByRole('button', { name: /save/i }));

    await waitFor(() => expect(mockFetchWithAuth).toHaveBeenCalled());

    const [endpoint, options] = mockFetchWithAuth.mock.calls[0] as [
      string,
      { method?: string; body?: string },
    ];

    expect(endpoint).toBe('/api/v1/addresses/me');
    expect(options.method).toBe('POST');
    const body = JSON.parse(options.body || '{}') as Record<string, unknown>;
    expect(body.label).toBe('other');
    expect(body.custom_label).toBe('Studio');

    await waitFor(() => expect(onSaved).toHaveBeenCalled());
  });
});
