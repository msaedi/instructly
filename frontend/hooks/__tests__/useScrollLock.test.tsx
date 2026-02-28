import { render } from '@testing-library/react';
import React from 'react';

import { useScrollLock } from '../useScrollLock';

function ScrollLockHarness({ locked }: { locked: boolean }) {
  useScrollLock(locked);
  return <div>Scroll lock</div>;
}

describe('useScrollLock', () => {
  afterEach(() => {
    document.body.style.overflow = '';
  });

  it('locks body scroll when locked is true', () => {
    render(<ScrollLockHarness locked={true} />);
    expect(document.body.style.overflow).toBe('hidden');
  });

  it('does not lock body scroll when locked is false', () => {
    render(<ScrollLockHarness locked={false} />);
    expect(document.body.style.overflow).toBe('');
  });

  it('restores previous overflow value on cleanup', () => {
    document.body.style.overflow = 'auto';
    const { unmount } = render(<ScrollLockHarness locked={true} />);
    expect(document.body.style.overflow).toBe('hidden');

    unmount();
    expect(document.body.style.overflow).toBe('auto');
  });

  it('restores overflow when lock toggles off', () => {
    document.body.style.overflow = 'scroll';
    const { rerender } = render(<ScrollLockHarness locked={true} />);
    expect(document.body.style.overflow).toBe('hidden');

    rerender(<ScrollLockHarness locked={false} />);
    expect(document.body.style.overflow).toBe('scroll');
  });
});
