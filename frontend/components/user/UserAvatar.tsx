"use client";

import React, { useEffect, useMemo, useState } from 'react';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { getProfilePictureUrl } from '@/lib/api';
import { getUserInitials, getAvatarColor } from '@/features/shared/hooks/useAuth';

interface Props {
  user: { id: string; first_name?: string; last_name?: string; email?: string; has_profile_picture?: boolean; profile_picture_version?: number } | null;
  size?: number;
  className?: string;
  variant?: 'display' | 'thumb';
}

export function UserAvatar({ user, size = 40, className, variant = 'thumb' }: Props) {
  const [url, setUrl] = useState<string | null>(null);
  const initials = useMemo(() => getUserInitials(user), [user]);
  const color = useMemo(() => {
    const safeUserId = user?.id != null ? String(user.id) : '';
    return safeUserId ? getAvatarColor(safeUserId) : '#999';
  }, [user?.id]);

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
        <AvatarFallback className="bg-transparent p-0">
          <div
            className="bg-gray-200 rounded-full flex items-center justify-center text-gray-500"
            style={{ width: size, height: size }}
          >
            <span className="text-2xl">👤</span>
          </div>
        </AvatarFallback>
      )}
    </Avatar>
  );
}
