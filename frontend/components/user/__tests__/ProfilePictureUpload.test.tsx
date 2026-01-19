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
});
