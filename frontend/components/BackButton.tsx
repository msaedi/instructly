'use client';

import { useRouter } from 'next/navigation';

interface BackButtonProps {
  children: React.ReactNode;
  className?: string;
}

export default function BackButton({ children, className }: BackButtonProps) {
  const router = useRouter();

  const handleClick = () => {
    router.back();
  };

  return (
    <button onClick={handleClick} className={className}>
      {children}
    </button>
  );
}
