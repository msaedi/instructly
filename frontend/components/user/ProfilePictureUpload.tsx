"use client";

import React, { useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/react-query/queryClient';
import ImageCropModal from '@/components/modals/ImageCropModal';
import { toast } from 'sonner';
import { createSignedUpload, finalizeProfilePicture } from '@/lib/api';
import { logger } from '@/lib/logger';
import { useAuth } from '@/features/shared/hooks/useAuth';

interface Props {
  onCompleted?: () => void;
  className?: string;
  size?: number;
  /**
   * Optional custom trigger to open the file chooser.
   * If provided, this element will be rendered as the clickable area instead of the default camera button.
   */
  trigger?: React.ReactNode;
  ariaLabel?: string;
}

export function ProfilePictureUpload({ onCompleted, className, size = 64, trigger, ariaLabel }: Props) {
  const { checkAuth } = useAuth(); // user available via hook if needed
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [showCrop, setShowCrop] = useState(false);

  // User initials available via: useMemo(() => getUserInitials(user), [user])
  // Avatar color available via: useMemo(() => (user?.id ? getAvatarColor(user.id) : '#999'), [user?.id])

  const onPick = () => fileInputRef.current?.click();

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    setError(null);
    const file = e.target.files?.[0];
    if (!file) return;

    if (!['image/png', 'image/jpeg'].includes(file.type)) {
      const msg = 'Please select a PNG or JPEG image.';
      setError(msg);
      toast.error(msg);
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      const msg = 'Image must be under 5MB.';
      setError(msg);
      toast.error(msg);
      return;
    }

    // Open crop modal first; upload happens after user saves crop
    setPendingFile(file);
    setShowCrop(true);
  };

  const handleCropped = async (blob: Blob) => {
    if (!pendingFile) return;
    // Use original filename but force .jpg since we export JPEG
    const filename = (pendingFile.name.split('.').slice(0, -1).join('.') || 'avatar') + '.jpg';
    const file = new File([blob], filename, { type: 'image/jpeg' });
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);

    try {
      setIsUploading(true);
      const signed = await createSignedUpload({
        filename: file.name,
        content_type: file.type,
        size_bytes: file.size,
        purpose: 'profile_picture',
      });

      const putRes = await fetch(signed.upload_url, {
        method: 'PUT',
        headers: signed.headers || { 'Content-Type': file.type },
        body: file,
      });
      if (!putRes.ok) throw new Error(`Upload failed: ${putRes.status}`);

      const fin = await finalizeProfilePicture(signed.object_key);
      if (!fin.success) throw new Error(fin.message || 'Finalize failed');

      logger.info('Profile picture uploaded successfully');
      try {
        await checkAuth();
        queryClient.invalidateQueries({ queryKey: queryKeys.user });
      } catch {}
      if (onCompleted) onCompleted();
    } catch (err: unknown) {
      logger.error('Profile picture upload error', err);
      const msg = (err as Record<string, unknown>)?.['message'] as string || 'Upload failed';
      setError(msg);
      toast.error(msg);
    } finally {
      setIsUploading(false);
      setShowCrop(false);
      setPendingFile(null);
    }
  };

  return (
    <div className={className}>
      {/* Hidden file input */}
      <input
        ref={fileInputRef}
        type="file"
        accept="image/png,image/jpeg"
        onChange={handleFileChange}
        className="hidden"
      />
      {trigger ? (
        <button
          type="button"
          onClick={onPick}
          disabled={isUploading}
          aria-label={ariaLabel || 'Change profile picture'}
          className="relative cursor-pointer disabled:cursor-not-allowed no-hover-effects group"
          title={ariaLabel || 'Change profile picture'}
          style={{ display: 'inline-block' }}
        >
          {/* underlying trigger */}
          <span className="block transition-transform group-hover:scale-105">{trigger}</span>
          {/* optimistic preview overlay */}
          {previewUrl && (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={previewUrl}
              alt="Preview"
              className="absolute inset-0 w-full h-full object-cover rounded-full"
              style={{ filter: isUploading ? 'grayscale(20%) opacity(0.9)' : undefined }}
            />
          )}
          {isUploading && (
            <span className="absolute inset-0 flex items-center justify-center">
              <span className="animate-spin rounded-full h-6 w-6 border-2 border-white border-t-transparent" />
            </span>
          )}
        </button>
      ) : (
        // Default camera-only trigger
        <button type="button" onClick={onPick} disabled={isUploading} title="Choose Image" className="cursor-pointer disabled:cursor-not-allowed no-hover-effects group">
          <div
            className="rounded-full flex items-center justify-center transition-transform group-hover:scale-105 group-hover:shadow-sm"
            style={{ width: size, height: size, backgroundColor: '#ffffff', border: '2px solid #d1d5db' }}
          >
            <svg xmlns="http://www.w3.org/2000/svg" width={Math.max(24, Math.floor(size * 0.4))} height={Math.max(24, Math.floor(size * 0.4))} viewBox="0 0 24 24" fill="none" stroke="#9ca3af" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"></path>
              <circle cx="12" cy="13" r="4"></circle>
            </svg>
          </div>
        </button>
      )}
      {error && <div className="mt-2 text-xs text-red-600">{error}</div>}

      {/* Crop modal */}
      <ImageCropModal
        isOpen={showCrop}
        file={pendingFile}
        onClose={() => { setShowCrop(false); setPendingFile(null); }}
        onCropped={handleCropped}
        viewportSize={320}
        outputSize={800}
      />
    </div>
  );
}
