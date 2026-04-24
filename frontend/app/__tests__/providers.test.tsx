import { render, screen, waitFor } from '@testing-library/react';
import type { ReactElement, ReactNode } from 'react';
import {
  ACCOUNT_DELETED_TOAST_KEY,
  ACCOUNT_DELETED_TOAST_MESSAGE,
} from '@/lib/accountDeletedToast';

const mockToaster = jest.fn();
const mockToastSuccess = jest.fn();
const mockUseGuestSessionCleanup = jest.fn();
const mockEnsureGuestOnce = jest.fn(() => Promise.resolve());
const mockInitializeSessionTracking = jest.fn();
const mockCleanupSessionTracking = jest.fn();

jest.mock('sonner', () => ({
  toast: {
    success: (...args: unknown[]) => mockToastSuccess(...args),
  },
  Toaster: (props: unknown) => {
    mockToaster(props);
    return <div data-testid="mock-toaster" />;
  },
}));

jest.mock('@tanstack/react-query-devtools', () => ({
  ReactQueryDevtools: () => null,
}));

jest.mock('@/features/shared/hooks/useAuth', () => ({
  AuthProvider: ({ children }: { children: ReactNode }) => <>{children}</>,
}));

jest.mock('@/hooks/useGuestSessionCleanup', () => ({
  useGuestSessionCleanup: () => mockUseGuestSessionCleanup(),
}));

jest.mock('@/lib/searchTracking', () => ({
  ensureGuestOnce: () => mockEnsureGuestOnce(),
}));

jest.mock('@/lib/sessionTracking', () => ({
  initializeSessionTracking: () => mockInitializeSessionTracking(),
  cleanupSessionTracking: () => mockCleanupSessionTracking(),
}));

import { Providers } from '../providers';

describe('Providers', () => {
  beforeEach(() => {
    mockToaster.mockClear();
    mockToastSuccess.mockClear();
    mockUseGuestSessionCleanup.mockClear();
    mockEnsureGuestOnce.mockClear();
    mockInitializeSessionTracking.mockClear();
    mockCleanupSessionTracking.mockClear();
    window.sessionStorage.clear();
    window.history.pushState({}, '', '/');
  });

  it('configures the toaster with the corrected solid brand styling', () => {
    const { unmount } = render(
      <Providers>
        <div>hello</div>
      </Providers>
    );

    expect(screen.getByText('hello')).toBeInTheDocument();
    expect(screen.getByTestId('mock-toaster')).toBeInTheDocument();
    expect(mockUseGuestSessionCleanup).toHaveBeenCalledTimes(1);
    expect(mockInitializeSessionTracking).toHaveBeenCalledTimes(1);
    expect(mockEnsureGuestOnce).toHaveBeenCalledTimes(1);

    expect(mockToaster).toHaveBeenCalledTimes(1);
    const toasterProps = mockToaster.mock.calls[0][0] as {
      expand: boolean;
      position: string;
      toastOptions: {
        style: Record<string, string | undefined>;
        classNames: Record<string, string>;
      };
      icons: Record<string, ReactElement>;
    };

    expect(toasterProps.expand).toBe(true);
    expect(toasterProps.position).toBe('top-right');
    expect(toasterProps.toastOptions.style).toMatchObject({
      padding: '12px 16px',
      borderRadius: '12px',
      minWidth: '260px',
      maxWidth: '360px',
      whiteSpace: 'normal',
      boxShadow: '0 12px 24px rgba(15, 23, 42, 0.45)',
    });
    expect(toasterProps.toastOptions.classNames).toMatchObject({
      default: 'inst-toast-brand',
      success: 'inst-toast-brand',
      info: 'inst-toast-brand',
      loading: 'inst-toast-brand',
      error: 'inst-toast-brand',
      warning: 'inst-toast-brand',
      icon: 'inst-toast-icon',
      title: 'inst-toast-title',
      description: 'inst-toast-description',
    });
    expect(Object.keys(toasterProps.icons).sort()).toEqual([
      'error',
      'info',
      'loading',
      'success',
      'warning',
    ]);

    const { container: iconsContainer } = render(
      <>
        {toasterProps.icons['success']}
        {toasterProps.icons['error']}
        {toasterProps.icons['warning']}
        {toasterProps.icons['info']}
        {toasterProps.icons['loading']}
      </>
    );
    expect(iconsContainer.querySelectorAll('.inst-toast-icon-circle')).toHaveLength(5);

    unmount();

    expect(mockCleanupSessionTracking).toHaveBeenCalledTimes(1);
  });

  it('fires and clears the account-deleted homepage toast on /', async () => {
    window.sessionStorage.setItem(ACCOUNT_DELETED_TOAST_KEY, '1');
    const removeItemSpy = jest.spyOn(Storage.prototype, 'removeItem');

    render(
      <Providers>
        <div>home</div>
      </Providers>
    );

    await waitFor(() => {
      expect(mockToastSuccess).toHaveBeenCalledWith(ACCOUNT_DELETED_TOAST_MESSAGE);
    });
    expect(removeItemSpy).toHaveBeenCalledWith(ACCOUNT_DELETED_TOAST_KEY);
    const removeCallOrder = removeItemSpy.mock.invocationCallOrder[0];
    const toastCallOrder = mockToastSuccess.mock.invocationCallOrder[0];
    expect(removeCallOrder).toBeDefined();
    expect(toastCallOrder).toBeDefined();
    expect(removeCallOrder!).toBeLessThan(toastCallOrder!);

    removeItemSpy.mockRestore();
  });
});
