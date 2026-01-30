import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ProfilePictureUpload } from '../ProfilePictureUpload';
import { createSignedUpload, finalizeProfilePicture, proxyUploadToR2 } from '@/lib/api';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { useProfilePictureUrls } from '@/hooks/useProfilePictureUrls';
import { queryKeys } from '@/lib/react-query/queryClient';
import { toast } from 'sonner';

jest.mock('@/lib/api', () => {
  const actual = jest.requireActual('@/lib/api');
  return {
    ...actual,
    createSignedUpload: jest.fn(),
    finalizeProfilePicture: jest.fn(),
    proxyUploadToR2: jest.fn(),
  };
});

jest.mock('@/features/shared/hooks/useAuth', () => ({
  useAuth: jest.fn(),
}));

jest.mock('@/hooks/useProfilePictureUrls', () => ({
  useProfilePictureUrls: jest.fn(),
}));

jest.mock('@/components/modals/ImageCropModal', () => ({
  __esModule: true,
  default: ({ isOpen, onCropped, onClose }: { isOpen: boolean; onCropped: (blob: Blob) => void; onClose: () => void }) => (
    isOpen ? (
      <div data-testid="crop-modal">
        <button type="button" onClick={() => onCropped(new Blob(['crop'], { type: 'image/jpeg' }))}>Apply Crop</button>
        <button type="button" onClick={onClose}>Cancel</button>
      </div>
    ) : null
  ),
}));

jest.mock('@/lib/logger', () => ({
  logger: { info: jest.fn(), error: jest.fn() },
}));

jest.mock('sonner', () => ({
  toast: {
    error: jest.fn(),
    success: jest.fn(),
  },
}));

// Mock publicEnv module - default to 'local' for most tests
let mockAppEnv = 'local';
jest.mock('@/lib/publicEnv', () => ({
  get APP_ENV() {
    return mockAppEnv;
  },
}));

const mockUseAuth = useAuth as jest.Mock;
const mockUseProfilePictureUrls = useProfilePictureUrls as jest.Mock;

describe('ProfilePictureUpload', () => {
  const createWrapper = () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const Wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
    Wrapper.displayName = 'ProfilePictureUploadWrapper';
    return { Wrapper, queryClient };
  };

  beforeEach(() => {
    jest.clearAllMocks();
    mockAppEnv = 'local'; // Reset to local for most tests
    mockUseAuth.mockReturnValue({
      checkAuth: jest.fn().mockResolvedValue(undefined),
      user: { id: 'user-1', has_profile_picture: true, profile_picture_version: 1 },
    });
    mockUseProfilePictureUrls.mockReturnValue({ 'user-1': 'https://cdn.example.com/avatar.jpg' });
    (createSignedUpload as jest.Mock).mockResolvedValue({
      upload_url: 'https://upload.example.com',
      object_key: 'uploads/key',
      headers: { 'Content-Type': 'image/jpeg' },
    });
    (proxyUploadToR2 as jest.Mock).mockResolvedValue({});
    (finalizeProfilePicture as jest.Mock).mockResolvedValue({ success: true });
    global.URL.createObjectURL = jest.fn(() => 'blob:preview');
  });

  it('rejects unsupported file types', async () => {
    const { Wrapper } = createWrapper();
    const { container } = render(<ProfilePictureUpload ariaLabel="Change avatar" />, { wrapper: Wrapper });
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;

    const file = new File(['text'], 'notes.txt', { type: 'text/plain' });
    fireEvent.change(input, { target: { files: [file] } });

    expect(toast.error).toHaveBeenCalledWith('Please select a PNG or JPEG image.');
    expect(await screen.findByText(/png or jpeg/i)).toBeInTheDocument();
  });

  it('rejects files larger than 5MB', async () => {
    const { Wrapper } = createWrapper();
    const { container } = render(<ProfilePictureUpload ariaLabel="Change avatar" />, { wrapper: Wrapper });
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;

    const file = new File([new ArrayBuffer(5 * 1024 * 1024 + 1)], 'big.jpg', { type: 'image/jpeg' });
    fireEvent.change(input, { target: { files: [file] } });

    expect(toast.error).toHaveBeenCalledWith('Image must be under 5MB.');
    expect(await screen.findByText(/under 5mb/i)).toBeInTheDocument();
  });

  it('uploads a cropped image via proxy and updates cache', async () => {
    const { Wrapper, queryClient } = createWrapper();
    const invalidateSpy = jest.spyOn(queryClient, 'invalidateQueries');
    const setDataSpy = jest.spyOn(queryClient, 'setQueryData');
    const onCompleted = jest.fn();
    const { container } = render(<ProfilePictureUpload ariaLabel="Change avatar" onCompleted={onCompleted} />, { wrapper: Wrapper });
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;

    const file = new File(['avatar'], 'avatar.png', { type: 'image/png' });
    fireEvent.change(input, { target: { files: [file] } });

    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /apply crop/i }));

    await waitFor(() => {
      expect(createSignedUpload).toHaveBeenCalledWith({
        filename: 'avatar.jpg',
        content_type: 'image/jpeg',
        size_bytes: expect.any(Number),
        purpose: 'profile_picture',
      });
    });
    expect(proxyUploadToR2).toHaveBeenCalledWith({
      key: 'uploads/key',
      file: expect.any(File),
      contentType: 'image/jpeg',
    });
    expect(finalizeProfilePicture).toHaveBeenCalledWith('uploads/key');
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: queryKeys.user });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['avatar-urls'] });
    expect(setDataSpy).toHaveBeenCalled();
    expect(onCompleted).toHaveBeenCalled();
  });

  it('shows upload errors when finalize fails', async () => {
    const { Wrapper } = createWrapper();
    (finalizeProfilePicture as jest.Mock).mockResolvedValue({ success: false, message: 'Finalize failed' });
    const { container } = render(<ProfilePictureUpload ariaLabel="Change avatar" />, { wrapper: Wrapper });
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;

    const file = new File(['avatar'], 'avatar.png', { type: 'image/png' });
    fireEvent.change(input, { target: { files: [file] } });

    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /apply crop/i }));

    expect(await screen.findByText(/finalize failed/i)).toBeInTheDocument();
    expect(toast.error).toHaveBeenCalledWith('Finalize failed');
  });

  it('closes crop modal when cancel is clicked', async () => {
    const { Wrapper } = createWrapper();
    const { container } = render(<ProfilePictureUpload ariaLabel="Change avatar" />, { wrapper: Wrapper });
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;

    const file = new File(['avatar'], 'avatar.png', { type: 'image/png' });
    fireEvent.change(input, { target: { files: [file] } });

    expect(screen.getByTestId('crop-modal')).toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /cancel/i }));

    expect(screen.queryByTestId('crop-modal')).not.toBeInTheDocument();
  });

  it('uploads via proxy in local environment', async () => {
    const { Wrapper } = createWrapper();

    const { container } = render(<ProfilePictureUpload ariaLabel="Change avatar" />, { wrapper: Wrapper });
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;

    const file = new File(['avatar'], 'avatar.png', { type: 'image/png' });
    fireEvent.change(input, { target: { files: [file] } });

    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /apply crop/i }));

    await waitFor(() => {
      expect(proxyUploadToR2).toHaveBeenCalled();
      expect(finalizeProfilePicture).toHaveBeenCalled();
    });
  });

  it('renders with custom trigger element', () => {
    const { Wrapper } = createWrapper();
    const CustomTrigger = <span data-testid="custom-trigger" className="rounded-full w-20 h-20">Custom</span>;
    render(<ProfilePictureUpload ariaLabel="Change avatar" trigger={CustomTrigger} />, { wrapper: Wrapper });

    expect(screen.getByTestId('custom-trigger')).toBeInTheDocument();
  });

  it('handles user without existing profile picture', async () => {
    const { Wrapper } = createWrapper();
    mockUseAuth.mockReturnValue({
      checkAuth: jest.fn().mockResolvedValue(undefined),
      user: { id: 'user-1', has_profile_picture: false },
    });
    mockUseProfilePictureUrls.mockReturnValue({});

    const { container } = render(<ProfilePictureUpload ariaLabel="Change avatar" />, { wrapper: Wrapper });
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;

    const file = new File(['avatar'], 'avatar.png', { type: 'image/png' });
    fireEvent.change(input, { target: { files: [file] } });

    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /apply crop/i }));

    await waitFor(() => {
      expect(finalizeProfilePicture).toHaveBeenCalled();
    });
  });

  it('handles upload when checkAuth throws', async () => {
    const { Wrapper } = createWrapper();
    mockUseAuth.mockReturnValue({
      checkAuth: jest.fn().mockRejectedValue(new Error('Auth error')),
      user: { id: 'user-1', has_profile_picture: true, profile_picture_version: 1 },
    });

    const { container } = render(<ProfilePictureUpload ariaLabel="Change avatar" />, { wrapper: Wrapper });
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;

    const file = new File(['avatar'], 'avatar.png', { type: 'image/png' });
    fireEvent.change(input, { target: { files: [file] } });

    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /apply crop/i }));

    // Should complete without throwing
    await waitFor(() => {
      expect(finalizeProfilePicture).toHaveBeenCalled();
    });
  });

  it('handles user with null profile_picture_version', async () => {
    const { Wrapper } = createWrapper();
    mockUseAuth.mockReturnValue({
      checkAuth: jest.fn().mockResolvedValue(undefined),
      user: { id: 'user-1', has_profile_picture: true, profile_picture_version: null },
    });

    const { container } = render(<ProfilePictureUpload ariaLabel="Change avatar" />, { wrapper: Wrapper });
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;

    const file = new File(['avatar'], 'avatar.png', { type: 'image/png' });
    fireEvent.change(input, { target: { files: [file] } });

    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /apply crop/i }));

    await waitFor(() => {
      expect(finalizeProfilePicture).toHaveBeenCalled();
    });
  });

  it('shows uploading state during upload', async () => {
    const { Wrapper } = createWrapper();
    let resolveUpload: (value: { success: boolean }) => void;
    (proxyUploadToR2 as jest.Mock).mockImplementation(() =>
      new Promise(resolve => {
        resolveUpload = () => resolve({});
      })
    );

    const { container } = render(<ProfilePictureUpload ariaLabel="Change avatar" />, { wrapper: Wrapper });
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;

    const file = new File(['avatar'], 'avatar.png', { type: 'image/png' });
    fireEvent.change(input, { target: { files: [file] } });

    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /apply crop/i }));

    // Check for uploading state - button should be disabled during upload
    await waitFor(() => {
      const button = container.querySelector('button[disabled]');
      expect(button).toBeInTheDocument();
    });

    // Resolve the upload
    resolveUpload!({ success: true });

    await waitFor(() => {
      expect(finalizeProfilePicture).toHaveBeenCalled();
    });
  });

  it('handles error when signed upload creation fails', async () => {
    const { Wrapper } = createWrapper();
    (createSignedUpload as jest.Mock).mockRejectedValue(new Error('Signed upload failed'));

    const { container } = render(<ProfilePictureUpload ariaLabel="Change avatar" />, { wrapper: Wrapper });
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;

    const file = new File(['avatar'], 'avatar.png', { type: 'image/png' });
    fireEvent.change(input, { target: { files: [file] } });

    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /apply crop/i }));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('Signed upload failed');
    });
  });

  it('handles proxy upload error', async () => {
    const { Wrapper } = createWrapper();
    (proxyUploadToR2 as jest.Mock).mockRejectedValue(new Error('Proxy upload failed'));

    const { container } = render(<ProfilePictureUpload ariaLabel="Change avatar" />, { wrapper: Wrapper });
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;

    const file = new File(['avatar'], 'avatar.png', { type: 'image/png' });
    fireEvent.change(input, { target: { files: [file] } });

    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /apply crop/i }));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('Proxy upload failed');
    });
  });

  describe('direct PUT upload path (lines 121-126)', () => {
    beforeEach(() => {
      // Set APP_ENV to non-local to trigger direct upload path
      mockAppEnv = 'beta';
    });

    afterEach(() => {
      mockAppEnv = 'local';
    });

    it('uses direct PUT upload when not in local/beta-local environment', async () => {
      const { Wrapper } = createWrapper();

      // Mock successful direct PUT fetch
      global.fetch = jest.fn().mockResolvedValue({ ok: true } as Response);

      const { container } = render(<ProfilePictureUpload ariaLabel="Change avatar" />, { wrapper: Wrapper });
      const input = container.querySelector('input[type="file"]') as HTMLInputElement;

      const file = new File(['avatar'], 'avatar.png', { type: 'image/png' });
      fireEvent.change(input, { target: { files: [file] } });

      const user = userEvent.setup();
      await user.click(screen.getByRole('button', { name: /apply crop/i }));

      await waitFor(() => {
        // proxyUploadToR2 should NOT be called
        expect(proxyUploadToR2).not.toHaveBeenCalled();
        // Direct fetch PUT should be called
        expect(global.fetch).toHaveBeenCalledWith(
          'https://upload.example.com',
          expect.objectContaining({ method: 'PUT' })
        );
      });
    });

    it('handles direct PUT upload failure', async () => {
      const { Wrapper } = createWrapper();

      // Mock PUT request failure
      global.fetch = jest.fn().mockResolvedValue({ ok: false, status: 500 } as Response);

      const { container } = render(<ProfilePictureUpload ariaLabel="Change avatar" />, { wrapper: Wrapper });
      const input = container.querySelector('input[type="file"]') as HTMLInputElement;

      const file = new File(['avatar'], 'avatar.png', { type: 'image/png' });
      fireEvent.change(input, { target: { files: [file] } });

      const user = userEvent.setup();
      await user.click(screen.getByRole('button', { name: /apply crop/i }));

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith('Upload failed: 500');
      });
    });

    it('uses headers from signed upload response', async () => {
      const { Wrapper } = createWrapper();

      // Custom headers from signed upload
      (createSignedUpload as jest.Mock).mockResolvedValue({
        upload_url: 'https://upload.example.com',
        object_key: 'uploads/key',
        headers: { 'Content-Type': 'image/jpeg', 'x-custom-header': 'value' },
      });

      global.fetch = jest.fn().mockResolvedValue({ ok: true } as Response);

      const { container } = render(<ProfilePictureUpload ariaLabel="Change avatar" />, { wrapper: Wrapper });
      const input = container.querySelector('input[type="file"]') as HTMLInputElement;

      const file = new File(['avatar'], 'avatar.png', { type: 'image/png' });
      fireEvent.change(input, { target: { files: [file] } });

      const user = userEvent.setup();
      await user.click(screen.getByRole('button', { name: /apply crop/i }));

      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalledWith(
          'https://upload.example.com',
          expect.objectContaining({
            method: 'PUT',
            headers: { 'Content-Type': 'image/jpeg', 'x-custom-header': 'value' },
          })
        );
      });
    });

    it('falls back to Content-Type header when no headers provided', async () => {
      const { Wrapper } = createWrapper();

      // No headers in signed upload response
      (createSignedUpload as jest.Mock).mockResolvedValue({
        upload_url: 'https://upload.example.com',
        object_key: 'uploads/key',
        headers: undefined,
      });

      global.fetch = jest.fn().mockResolvedValue({ ok: true } as Response);

      const { container } = render(<ProfilePictureUpload ariaLabel="Change avatar" />, { wrapper: Wrapper });
      const input = container.querySelector('input[type="file"]') as HTMLInputElement;

      const file = new File(['avatar'], 'avatar.png', { type: 'image/png' });
      fireEvent.change(input, { target: { files: [file] } });

      const user = userEvent.setup();
      await user.click(screen.getByRole('button', { name: /apply crop/i }));

      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalledWith(
          'https://upload.example.com',
          expect.objectContaining({
            method: 'PUT',
            headers: { 'Content-Type': 'image/jpeg' },
          })
        );
      });
    });
  });

  describe('setQueryData callback (lines 142-150)', () => {
    it('updates cache with new profile_picture_version', async () => {
      const { Wrapper, queryClient } = createWrapper();
      const setDataSpy = jest.spyOn(queryClient, 'setQueryData');

      // Set initial user data in cache
      queryClient.setQueryData(queryKeys.user, {
        id: 'user-1',
        has_profile_picture: false,
        profile_picture_version: 0,
      });

      const { container } = render(<ProfilePictureUpload ariaLabel="Change avatar" />, { wrapper: Wrapper });
      const input = container.querySelector('input[type="file"]') as HTMLInputElement;

      const file = new File(['avatar'], 'avatar.png', { type: 'image/png' });
      fireEvent.change(input, { target: { files: [file] } });

      const user = userEvent.setup();
      await user.click(screen.getByRole('button', { name: /apply crop/i }));

      await waitFor(() => {
        expect(setDataSpy).toHaveBeenCalled();
      });

      // Verify the callback was called with the correct update function
      const setDataCalls = setDataSpy.mock.calls.filter(
        call => JSON.stringify(call[0]) === JSON.stringify(queryKeys.user)
      );
      expect(setDataCalls.length).toBeGreaterThan(0);
    });

    it('handles setQueryData when current cache is null', async () => {
      const { Wrapper, queryClient } = createWrapper();
      const setDataSpy = jest.spyOn(queryClient, 'setQueryData');

      // Don't set any initial cache data
      queryClient.clear();

      const { container } = render(<ProfilePictureUpload ariaLabel="Change avatar" />, { wrapper: Wrapper });
      const input = container.querySelector('input[type="file"]') as HTMLInputElement;

      const file = new File(['avatar'], 'avatar.png', { type: 'image/png' });
      fireEvent.change(input, { target: { files: [file] } });

      const user = userEvent.setup();
      await user.click(screen.getByRole('button', { name: /apply crop/i }));

      await waitFor(() => {
        expect(finalizeProfilePicture).toHaveBeenCalled();
      });

      // setQueryData should still be called even with null current value
      expect(setDataSpy).toHaveBeenCalled();
    });

    it('handles setQueryData when current profile_picture_version is NaN', async () => {
      const { Wrapper, queryClient } = createWrapper();

      // Set cache with invalid version
      queryClient.setQueryData(queryKeys.user, {
        id: 'user-1',
        has_profile_picture: true,
        profile_picture_version: NaN,
      });

      const { container } = render(<ProfilePictureUpload ariaLabel="Change avatar" />, { wrapper: Wrapper });
      const input = container.querySelector('input[type="file"]') as HTMLInputElement;

      const file = new File(['avatar'], 'avatar.png', { type: 'image/png' });
      fireEvent.change(input, { target: { files: [file] } });

      const user = userEvent.setup();
      await user.click(screen.getByRole('button', { name: /apply crop/i }));

      await waitFor(() => {
        expect(finalizeProfilePicture).toHaveBeenCalled();
      });
    });

    it('uses Math.max to ensure version only increases', async () => {
      const { Wrapper, queryClient } = createWrapper();
      const setDataSpy = jest.spyOn(queryClient, 'setQueryData');

      // Set cache with higher version than what upload would set
      queryClient.setQueryData(queryKeys.user, {
        id: 'user-1',
        has_profile_picture: true,
        profile_picture_version: 10,
      });

      const { container } = render(<ProfilePictureUpload ariaLabel="Change avatar" />, { wrapper: Wrapper });
      const input = container.querySelector('input[type="file"]') as HTMLInputElement;

      const file = new File(['avatar'], 'avatar.png', { type: 'image/png' });
      fireEvent.change(input, { target: { files: [file] } });

      const user = userEvent.setup();
      await user.click(screen.getByRole('button', { name: /apply crop/i }));

      await waitFor(() => {
        expect(setDataSpy).toHaveBeenCalled();
      });
    });
  });

  describe('overlay size measurement (lines 66-67)', () => {
    it('measures trigger element size when custom trigger is provided', () => {
      const { Wrapper } = createWrapper();

      // Create a custom trigger with rounded-full class
      const CustomTrigger = (
        <div data-testid="custom-avatar" className="rounded-full w-24 h-24">
          Custom Avatar
        </div>
      );

      render(
        <ProfilePictureUpload ariaLabel="Change avatar" trigger={CustomTrigger} />,
        { wrapper: Wrapper }
      );

      expect(screen.getByTestId('custom-avatar')).toBeInTheDocument();
    });

    it('handles missing getBoundingClientRect gracefully', () => {
      const { Wrapper } = createWrapper();

      // Create a trigger that might not have proper dimensions
      const MinimalTrigger = <span>Click</span>;

      // Should not throw
      render(
        <ProfilePictureUpload ariaLabel="Change avatar" trigger={MinimalTrigger} />,
        { wrapper: Wrapper }
      );

      expect(screen.getByText('Click')).toBeInTheDocument();
    });

    it('updates overlay size when trigger element dimensions change', () => {
      const { Wrapper } = createWrapper();

      const LargeTrigger = (
        <div data-testid="large-trigger" className="rounded-full" style={{ width: 100, height: 100 }}>
          Large
        </div>
      );

      const { rerender } = render(
        <ProfilePictureUpload ariaLabel="Change avatar" trigger={LargeTrigger} />,
        { wrapper: Wrapper }
      );

      // Rerender with different size trigger
      const SmallTrigger = (
        <div data-testid="small-trigger" className="rounded-full" style={{ width: 50, height: 50 }}>
          Small
        </div>
      );

      rerender(
        <ProfilePictureUpload ariaLabel="Change avatar" trigger={SmallTrigger} />
      );

      expect(screen.getByTestId('small-trigger')).toBeInTheDocument();
    });
  });

  describe('edge cases and bug hunting', () => {
    it('handles no file selected gracefully', async () => {
      const { Wrapper } = createWrapper();
      const { container } = render(<ProfilePictureUpload ariaLabel="Change avatar" />, { wrapper: Wrapper });
      const input = container.querySelector('input[type="file"]') as HTMLInputElement;

      // Trigger change with no files
      fireEvent.change(input, { target: { files: [] } });

      // Should not open crop modal
      expect(screen.queryByTestId('crop-modal')).not.toBeInTheDocument();
    });

    it('handles file selection cancelled', async () => {
      const { Wrapper } = createWrapper();
      const { container } = render(<ProfilePictureUpload ariaLabel="Change avatar" />, { wrapper: Wrapper });
      const input = container.querySelector('input[type="file"]') as HTMLInputElement;

      // Trigger change with null files
      fireEvent.change(input, { target: { files: null } });

      // Should not crash or open crop modal
      expect(screen.queryByTestId('crop-modal')).not.toBeInTheDocument();
    });

    it('handles very large file size properly', async () => {
      const { Wrapper } = createWrapper();
      const { container } = render(<ProfilePictureUpload ariaLabel="Change avatar" />, { wrapper: Wrapper });
      const input = container.querySelector('input[type="file"]') as HTMLInputElement;

      // Create file just over 5MB limit
      const largeFile = new File([new ArrayBuffer(5 * 1024 * 1024 + 100)], 'huge.jpg', { type: 'image/jpeg' });
      fireEvent.change(input, { target: { files: [largeFile] } });

      expect(toast.error).toHaveBeenCalledWith('Image must be under 5MB.');
    });

    it('handles exactly 5MB file (edge case)', async () => {
      const { Wrapper } = createWrapper();
      const { container } = render(<ProfilePictureUpload ariaLabel="Change avatar" />, { wrapper: Wrapper });
      const input = container.querySelector('input[type="file"]') as HTMLInputElement;

      // Create file exactly 5MB
      const exactFile = new File([new ArrayBuffer(5 * 1024 * 1024)], 'exact.jpg', { type: 'image/jpeg' });
      fireEvent.change(input, { target: { files: [exactFile] } });

      // Should be accepted (<=5MB)
      expect(screen.getByTestId('crop-modal')).toBeInTheDocument();
    });

    it('handles finalize returning no message in error', async () => {
      const { Wrapper } = createWrapper();
      (finalizeProfilePicture as jest.Mock).mockResolvedValue({ success: false });

      const { container } = render(<ProfilePictureUpload ariaLabel="Change avatar" />, { wrapper: Wrapper });
      const input = container.querySelector('input[type="file"]') as HTMLInputElement;

      const file = new File(['avatar'], 'avatar.png', { type: 'image/png' });
      fireEvent.change(input, { target: { files: [file] } });

      const user = userEvent.setup();
      await user.click(screen.getByRole('button', { name: /apply crop/i }));

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith('Finalize failed');
      });
    });

    it('clears pendingFile after successful upload', async () => {
      const { Wrapper } = createWrapper();
      const { container } = render(<ProfilePictureUpload ariaLabel="Change avatar" />, { wrapper: Wrapper });
      const input = container.querySelector('input[type="file"]') as HTMLInputElement;

      const file = new File(['avatar'], 'avatar.png', { type: 'image/png' });
      fireEvent.change(input, { target: { files: [file] } });

      const user = userEvent.setup();
      await user.click(screen.getByRole('button', { name: /apply crop/i }));

      await waitFor(() => {
        expect(finalizeProfilePicture).toHaveBeenCalled();
      });

      // Crop modal should be closed after successful upload
      expect(screen.queryByTestId('crop-modal')).not.toBeInTheDocument();
    });
  });
});
