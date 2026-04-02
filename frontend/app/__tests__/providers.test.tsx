import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';

const mockToaster = jest.fn();
const mockUseGuestSessionCleanup = jest.fn();
const mockEnsureGuestOnce = jest.fn(() => Promise.resolve());
const mockInitializeSessionTracking = jest.fn();
const mockCleanupSessionTracking = jest.fn();

jest.mock('sonner', () => ({
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
      position: string;
      toastOptions: {
        style: Record<string, string | undefined>;
        classNames: Record<string, string>;
      };
    };

    expect(toasterProps.position).toBe('top-right');
    expect(toasterProps.toastOptions.style).toMatchObject({
      background: '#7C3AED',
      color: '#ffffff',
      padding: '12px 16px',
      borderRadius: '12px',
      minWidth: '260px',
      maxWidth: '360px',
      whiteSpace: 'normal',
      boxShadow: '0 12px 24px rgba(15, 23, 42, 0.45)',
    });
    expect(toasterProps.toastOptions.classNames).toMatchObject({
      title: 'inst-toast-title',
      description: 'inst-toast-description',
    });

    unmount();

    expect(mockCleanupSessionTracking).toHaveBeenCalledTimes(1);
  });
});
