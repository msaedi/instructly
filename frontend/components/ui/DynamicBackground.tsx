// frontend/components/ui/DynamicBackground.tsx
"use client";
import React from 'react';
import { getActivityBackground } from '@/lib/services/assetService';

type Props = {
  activity?: string;
  overlayOpacity?: number; // 0..1
  className?: string;
};

export default function DynamicBackground({ activity, overlayOpacity = 0.6, className }: Props) {
  const [bgUrl, setBgUrl] = React.useState<string | null>(null);

  React.useEffect(() => {
    // rudimentary viewport selection; could be enhanced with ResizeObserver
    const vw = typeof window !== 'undefined' ? window.innerWidth : 1024;
    const viewport: 'mobile' | 'tablet' | 'desktop' = vw < 640 ? 'mobile' : vw < 1024 ? 'tablet' : 'desktop';
    setBgUrl(getActivityBackground(activity, viewport));
  }, [activity]);

  return (
    <div
      className={className}
      style={{
        backgroundImage: bgUrl ? `url('${bgUrl}')` : undefined,
        backgroundSize: 'cover',
        backgroundPosition: 'center',
        backgroundRepeat: 'no-repeat',
      }}
    >
      <div
        aria-hidden="true"
        style={{
          position: 'absolute',
          inset: 0,
          background: `rgba(0,0,0,${overlayOpacity})`,
        }}
      />
    </div>
  );
}
