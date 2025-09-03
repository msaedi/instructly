"use client";

import React, { useEffect, useMemo, useState } from 'react';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { getProfilePictureUrl } from '@/lib/api';
import { getUserInitials } from '@/features/shared/hooks/useAuth.helpers';

interface Props {
  user: { id: string; first_name?: string; last_name?: string; email?: string; has_profile_picture?: boolean; profile_picture_version?: number } | null;
  size?: number;
  className?: string;
  variant?: 'display' | 'thumb';
  fallbackBgColor?: string;
  fallbackTextColor?: string;
}

export function UserAvatar({ user, size = 40, className, variant = 'thumb', fallbackBgColor, fallbackTextColor }: Props) {
  const [url, setUrl] = useState<string | null>(null);
  const initials = useMemo(() => getUserInitials(user), [user]);
  // Use brand purple for fallback background
  const bgColor = fallbackBgColor ?? '#6A0DAD';
  const textColor = fallbackTextColor ?? '#ffffff';

  useEffect(() => {
    let mounted = true;
    async function load() {
      if (!user?.id || !user.has_profile_picture) {
        setUrl(null);
        return;
      }
      try {
        const safeUserId = String(user.id);
        const res = await getProfilePictureUrl(safeUserId, variant);
        if (mounted && res?.success) setUrl(res.data.url);
      } catch {
        if (mounted) setUrl(null);
      }
    }
    // Debounce slightly to allow backend to commit and cache bust
    const t0 = setTimeout(load, 150);
    const t = setInterval(load, 45 * 60 * 1000); // refresh before URL expiry
    return () => {
      mounted = false;
      clearTimeout(t0);
      clearInterval(t);
    };
  }, [user?.id, user?.has_profile_picture, user?.profile_picture_version, variant]);

  return (
    <Avatar className={className} style={{ width: size, height: size }}>
      {url ? (
        <AvatarImage src={url} alt="Avatar" />
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
