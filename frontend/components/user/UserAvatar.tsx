"use client";

import { useMemo } from 'react';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { useProfilePictureUrls } from '@/hooks/useProfilePictureUrls';
import { getUserInitials } from '@/features/shared/hooks/useAuth.helpers';

interface Props {
  user: {
    id: string;
    first_name?: string;
    last_name?: string;
    email?: string;
    has_profile_picture?: boolean;
    profile_picture_version?: number;
  } | null;
  size?: number;
  className?: string;
  variant?: 'display' | 'thumb';
  fallbackBgColor?: string;
  fallbackTextColor?: string;
  prefetchedUrl?: string | null;
}

const buildRawId = (id: string, version?: number) =>
  typeof version === 'number' && Number.isFinite(version) ? `${id}::v=${version}` : id;

export function UserAvatar({
  user,
  size = 40,
  className,
  variant = 'thumb',
  fallbackBgColor,
  fallbackTextColor,
  prefetchedUrl,
}: Props) {
  const initials = useMemo(() => getUserInitials(user), [user]);
  const bgColor = fallbackBgColor ?? '#7E22CE';
  const textColor = fallbackTextColor ?? '#ffffff';

  const shouldFetch = Boolean(user?.id && user.has_profile_picture !== false);
  const rawId = shouldFetch ? buildRawId(String(user?.id), user?.profile_picture_version) : null;
  const fetchedUrls = useProfilePictureUrls(rawId ? [rawId] : [], variant);
  const resolvedUrl = prefetchedUrl ?? (rawId ? fetchedUrls[user?.id ?? ''] ?? null : null);

  return (
    <Avatar className={className} style={{ width: size, height: size }}>
      {resolvedUrl ? (
        <AvatarImage src={resolvedUrl} alt="Avatar" />
      ) : (
        <AvatarFallback
          className="flex items-center justify-center font-semibold uppercase"
          style={{ backgroundColor: bgColor, color: textColor }}
        >
          {initials || '👤'}
        </AvatarFallback>
      )}
    </Avatar>
  );
}
