import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { CatalogServicePicker, type SelectedService } from '../CatalogServicePicker';
import { publicApi } from '@/features/shared/api/client';

jest.mock('@/features/shared/api/client', () => ({
  publicApi: {
    getCategoriesWithSubcategories: jest.fn(),
    getCategoryTree: jest.fn(),
  },
}));

const getCategoriesMock = publicApi.getCategoriesWithSubcategories as jest.Mock;
const getCategoryTreeMock = publicApi.getCategoryTree as jest.Mock;

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

const MOCK_CATEGORIES = [
  {
    id: 'cat-1',
    name: 'Music',
    display_order: 1,
    icon_name: 'music',
    subtitle: 'Instruments',
    subcategories: [
      { id: 'sub-1', name: 'Piano', service_count: 3 },
      { id: 'sub-2', name: 'Guitar', service_count: 2 },
    ],
  },
  {
    id: 'cat-2',
    name: 'Arts',
    display_order: 2,
    icon_name: 'palette',
    subtitle: 'Creative',
    subcategories: [
      { id: 'sub-3', name: 'Drawing', service_count: 1 },
    ],
  },
];

const MOCK_TREE = {
  id: 'cat-1',
  name: 'Music',
  display_order: 1,
  icon_name: 'music',
  subtitle: 'Instruments',
  subcategories: [
    {
      id: 'sub-1',
      name: 'Piano',
      category_id: 'cat-1',
      display_order: 1,
      services: [
        { id: 'svc-1', name: 'Classical Piano' },
        { id: 'svc-2', name: 'Jazz Piano' },
      ],
    },
    {
      id: 'sub-2',
      name: 'Guitar',
      category_id: 'cat-1',
      display_order: 2,
      services: [
        { id: 'svc-3', name: 'Acoustic Guitar' },
      ],
    },
  ],
};

describe('CatalogServicePicker', () => {
  it('renders category list when data loads', async () => {
    getCategoriesMock.mockResolvedValue({ data: MOCK_CATEGORIES, status: 200 });
    const onChange = jest.fn();

    render(
      <CatalogServicePicker selected={[]} onChange={onChange} />,
      { wrapper: Wrapper },
    );

    expect(await screen.findByText('Music')).toBeInTheDocument();
    expect(screen.getByText('Arts')).toBeInTheDocument();
  });

  it('shows subcategory counts', async () => {
    getCategoriesMock.mockResolvedValue({ data: MOCK_CATEGORIES, status: 200 });

    render(
      <CatalogServicePicker selected={[]} onChange={jest.fn()} />,
      { wrapper: Wrapper },
    );

    expect(await screen.findByText('2 subcategories')).toBeInTheDocument();
    expect(screen.getByText('1 subcategory')).toBeInTheDocument();
  });

  it('expands a category to show services', async () => {
    getCategoriesMock.mockResolvedValue({ data: MOCK_CATEGORIES, status: 200 });
    getCategoryTreeMock.mockResolvedValue({ data: MOCK_TREE, status: 200 });

    render(
      <CatalogServicePicker selected={[]} onChange={jest.fn()} />,
      { wrapper: Wrapper },
    );

    const musicBtn = await screen.findByText('Music');
    fireEvent.click(musicBtn);

    expect(await screen.findByText('Classical Piano')).toBeInTheDocument();
    expect(screen.getByText('Jazz Piano')).toBeInTheDocument();
    expect(screen.getByText('Acoustic Guitar')).toBeInTheDocument();
  });

  it('selects a service when clicked', async () => {
    getCategoriesMock.mockResolvedValue({ data: MOCK_CATEGORIES, status: 200 });
    getCategoryTreeMock.mockResolvedValue({ data: MOCK_TREE, status: 200 });
    const onChange = jest.fn();

    render(
      <CatalogServicePicker selected={[]} onChange={onChange} />,
      { wrapper: Wrapper },
    );

    fireEvent.click(await screen.findByText('Music'));
    fireEvent.click(await screen.findByText('Classical Piano'));

    expect(onChange).toHaveBeenCalledWith([
      expect.objectContaining({
        serviceId: 'svc-1',
        serviceName: 'Classical Piano',
        subcategoryId: 'sub-1',
        subcategoryName: 'Piano',
        categoryId: 'cat-1',
        categoryName: 'Music',
      }),
    ]);
  });

  it('deselects a service when clicked again', async () => {
    getCategoriesMock.mockResolvedValue({ data: MOCK_CATEGORIES, status: 200 });
    getCategoryTreeMock.mockResolvedValue({ data: MOCK_TREE, status: 200 });
    const onChange = jest.fn();

    const existing: SelectedService[] = [
      {
        serviceId: 'svc-1',
        serviceName: 'Classical Piano',
        subcategoryId: 'sub-1',
        subcategoryName: 'Piano',
        categoryId: 'cat-1',
        categoryName: 'Music',
      },
    ];

    render(
      <CatalogServicePicker selected={existing} onChange={onChange} />,
      { wrapper: Wrapper },
    );

    fireEvent.click(await screen.findByText('Music'));
    // Click service in the tree (not the pill)
    const serviceButtons = await screen.findAllByText('Classical Piano');
    const treeButton = serviceButtons.find(
      (el) => el.closest('button[type="button"]')?.closest('.bg-gray-50, [class*="bg-gray-"]') != null,
    ) ?? serviceButtons[serviceButtons.length - 1]!;
    fireEvent.click(treeButton);

    expect(onChange).toHaveBeenCalledWith([]);
  });

  it('shows selected services as pills', async () => {
    getCategoriesMock.mockResolvedValue({ data: MOCK_CATEGORIES, status: 200 });

    const existing: SelectedService[] = [
      {
        serviceId: 'svc-1',
        serviceName: 'Classical Piano',
        subcategoryId: 'sub-1',
        subcategoryName: 'Piano',
        categoryId: 'cat-1',
        categoryName: 'Music',
      },
    ];

    render(
      <CatalogServicePicker selected={existing} onChange={jest.fn()} />,
      { wrapper: Wrapper },
    );

    expect(await screen.findByText('Classical Piano')).toBeInTheDocument();
  });

  it('has a search filter input', async () => {
    getCategoriesMock.mockResolvedValue({ data: MOCK_CATEGORIES, status: 200 });

    render(
      <CatalogServicePicker selected={[]} onChange={jest.fn()} />,
      { wrapper: Wrapper },
    );

    const searchInput = await screen.findByPlaceholderText('Search skills...');
    expect(searchInput).toBeInTheDocument();
  });

  it('filters services by search term', async () => {
    getCategoriesMock.mockResolvedValue({ data: MOCK_CATEGORIES, status: 200 });
    getCategoryTreeMock.mockResolvedValue({ data: MOCK_TREE, status: 200 });

    render(
      <CatalogServicePicker selected={[]} onChange={jest.fn()} />,
      { wrapper: Wrapper },
    );

    // Expand Music
    fireEvent.click(await screen.findByText('Music'));
    await screen.findByText('Classical Piano');

    // Type in search
    const searchInput = screen.getByPlaceholderText('Search skills...');
    fireEvent.change(searchInput, { target: { value: 'jazz' } });

    // Jazz Piano should be visible, Classical Piano and Acoustic Guitar should not
    await waitFor(() => {
      expect(screen.getByText('Jazz Piano')).toBeInTheDocument();
      expect(screen.queryByText('Classical Piano')).not.toBeInTheDocument();
      expect(screen.queryByText('Acoustic Guitar')).not.toBeInTheDocument();
    });
  });

  it('shows empty state when no categories', async () => {
    getCategoriesMock.mockResolvedValue({ data: [], status: 200 });

    render(
      <CatalogServicePicker selected={[]} onChange={jest.fn()} />,
      { wrapper: Wrapper },
    );

    expect(await screen.findByText(/no categories available/i)).toBeInTheDocument();
  });

  it('respects maxSelections limit', async () => {
    getCategoriesMock.mockResolvedValue({ data: MOCK_CATEGORIES, status: 200 });
    getCategoryTreeMock.mockResolvedValue({ data: MOCK_TREE, status: 200 });
    const onChange = jest.fn();

    const existing: SelectedService[] = [
      {
        serviceId: 'svc-1',
        serviceName: 'Classical Piano',
        subcategoryId: 'sub-1',
        subcategoryName: 'Piano',
        categoryId: 'cat-1',
        categoryName: 'Music',
      },
    ];

    render(
      <CatalogServicePicker selected={existing} onChange={onChange} maxSelections={1} />,
      { wrapper: Wrapper },
    );

    fireEvent.click(await screen.findByText('Music'));
    fireEvent.click(await screen.findByText('Jazz Piano'));

    // Should not be called because we're at max
    expect(onChange).not.toHaveBeenCalled();
  });
});
