import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { FilterSelectionForm } from '../FilterSelectionForm';
import { publicApi } from '@/features/shared/api/client';

jest.mock('@/features/shared/api/client', () => ({
  publicApi: {
    getSubcategoryFilters: jest.fn(),
  },
}));

const getFiltersMock = publicApi.getSubcategoryFilters as jest.Mock;

let queryClient: QueryClient;

beforeEach(() => {
  jest.clearAllMocks();
  queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
});

afterEach(() => {
  queryClient.clear();
});

function Wrapper({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

const MOCK_FILTERS = [
  {
    filter_key: 'level',
    filter_display_name: 'Skill Level',
    filter_type: 'single_select',
    options: [
      { id: 'opt-1', display_name: 'Beginner', value: 'beginner', display_order: 1 },
      { id: 'opt-2', display_name: 'Intermediate', value: 'intermediate', display_order: 2 },
      { id: 'opt-3', display_name: 'Advanced', value: 'advanced', display_order: 3 },
    ],
  },
  {
    filter_key: 'style',
    filter_display_name: 'Music Style',
    filter_type: 'multi_select',
    options: [
      { id: 'opt-4', display_name: 'Classical', value: 'classical', display_order: 1 },
      { id: 'opt-5', display_name: 'Jazz', value: 'jazz', display_order: 2 },
    ],
  },
];

describe('FilterSelectionForm', () => {
  it('renders filter groups when data loads', async () => {
    getFiltersMock.mockResolvedValue({ data: MOCK_FILTERS, status: 200 });
    const onChange = jest.fn();

    render(
      <FilterSelectionForm subcategoryId="sub-1" selections={{}} onChange={onChange} />,
      { wrapper: Wrapper },
    );

    expect(await screen.findByText('Skill Level')).toBeInTheDocument();
    expect(screen.getByText('Music Style')).toBeInTheDocument();
    expect(screen.getByText('Beginner')).toBeInTheDocument();
    expect(screen.getByText('Classical')).toBeInTheDocument();
  });

  it('shows (select one) hint for single_select filters', async () => {
    getFiltersMock.mockResolvedValue({ data: MOCK_FILTERS, status: 200 });
    render(
      <FilterSelectionForm subcategoryId="sub-1" selections={{}} onChange={jest.fn()} />,
      { wrapper: Wrapper },
    );

    expect(await screen.findByText('(select one)')).toBeInTheDocument();
  });

  it('calls onChange when an option is clicked', async () => {
    getFiltersMock.mockResolvedValue({ data: MOCK_FILTERS, status: 200 });
    const onChange = jest.fn();

    render(
      <FilterSelectionForm subcategoryId="sub-1" selections={{}} onChange={onChange} />,
      { wrapper: Wrapper },
    );

    const beginnerBtn = await screen.findByText('Beginner');
    fireEvent.click(beginnerBtn);

    expect(onChange).toHaveBeenCalledWith({ level: ['beginner'] });
  });

  it('toggles off a selected single_select option', async () => {
    getFiltersMock.mockResolvedValue({ data: MOCK_FILTERS, status: 200 });
    const onChange = jest.fn();

    render(
      <FilterSelectionForm
        subcategoryId="sub-1"
        selections={{ level: ['beginner'] }}
        onChange={onChange}
      />,
      { wrapper: Wrapper },
    );

    const beginnerBtn = await screen.findByText('Beginner');
    fireEvent.click(beginnerBtn);

    expect(onChange).toHaveBeenCalledWith({ level: [] });
  });

  it('supports multi_select by adding values', async () => {
    getFiltersMock.mockResolvedValue({ data: MOCK_FILTERS, status: 200 });
    const onChange = jest.fn();

    render(
      <FilterSelectionForm
        subcategoryId="sub-1"
        selections={{ style: ['classical'] }}
        onChange={onChange}
      />,
      { wrapper: Wrapper },
    );

    const jazzBtn = await screen.findByText('Jazz');
    fireEvent.click(jazzBtn);

    expect(onChange).toHaveBeenCalledWith({ style: ['classical', 'jazz'] });
  });

  it('removes value from multi_select when toggled off', async () => {
    getFiltersMock.mockResolvedValue({ data: MOCK_FILTERS, status: 200 });
    const onChange = jest.fn();

    render(
      <FilterSelectionForm
        subcategoryId="sub-1"
        selections={{ style: ['classical', 'jazz'] }}
        onChange={onChange}
      />,
      { wrapper: Wrapper },
    );

    const classicalBtn = await screen.findByText('Classical');
    fireEvent.click(classicalBtn);

    expect(onChange).toHaveBeenCalledWith({ style: ['jazz'] });
  });

  it('renders nothing when subcategoryId is empty', () => {
    const { container } = render(
      <FilterSelectionForm subcategoryId="" selections={{}} onChange={jest.fn()} />,
      { wrapper: Wrapper },
    );

    expect(container.innerHTML).toBe('');
  });

  it('renders nothing when no filters available', async () => {
    getFiltersMock.mockResolvedValue({ data: [], status: 200 });
    const { container } = render(
      <FilterSelectionForm subcategoryId="sub-1" selections={{}} onChange={jest.fn()} />,
      { wrapper: Wrapper },
    );

    // Wait for query to settle
    await screen.findByText(() => false).catch(() => {});
    // Give time for the empty result to render
    await new Promise((r) => setTimeout(r, 50));

    // Should render nothing (no filter groups)
    expect(container.querySelector('[class*="space-y"]')).toBeNull();
  });
});
