'use client';

import type { MouseEvent } from 'react';

export default function SkipToMainLink() {
  const handleActivate = (event: MouseEvent<HTMLAnchorElement>) => {
    const href = event.currentTarget.getAttribute('href') ?? '';
    if (!href.startsWith('#')) return;

    const targetId = href.slice(1);
    const target = document.getElementById(targetId);
    if (!target) return;

    event.preventDefault();
    target.focus();
  };

  return (
    <a href="#main-content" className="skip-to-main" onClick={handleActivate}>
      Skip to main content
    </a>
  );
}
