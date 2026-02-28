import { fireEvent, render, screen } from '@testing-library/react';
import React, { useRef } from 'react';

import { useFocusTrap } from '../useFocusTrap';

function FocusTrapHarness({
  isOpen,
  onEscape,
  includeFocusable = true,
}: {
  isOpen: boolean;
  onEscape?: () => void;
  includeFocusable?: boolean;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  useFocusTrap({
    isOpen,
    containerRef,
    onEscape,
  });

  if (!isOpen) return null;
  const titleId = 'focus-trap-title';

  return (
    <div ref={containerRef} role="dialog" aria-modal="true" aria-labelledby={titleId} tabIndex={-1}>
      <h2 id={titleId} className="sr-only">
        Focus trap test dialog
      </h2>
      {includeFocusable ? (
        <>
          <button type="button">First</button>
          <button type="button">Last</button>
        </>
      ) : (
        <span>No focusables</span>
      )}
    </div>
  );
}

describe('useFocusTrap', () => {
  it('moves initial focus to the first focusable element', () => {
    render(<FocusTrapHarness isOpen={true} />);
    expect(screen.getByRole('button', { name: 'First' })).toHaveFocus();
  });

  it('falls back to focusing the container when no focusables are present', () => {
    render(<FocusTrapHarness isOpen={true} includeFocusable={false} />);
    expect(screen.getByRole('dialog')).toHaveFocus();
  });

  it('wraps focus from last to first on Tab', () => {
    render(<FocusTrapHarness isOpen={true} />);
    const first = screen.getByRole('button', { name: 'First' });
    const last = screen.getByRole('button', { name: 'Last' });

    last.focus();
    fireEvent.keyDown(document, { key: 'Tab' });
    expect(first).toHaveFocus();
  });

  it('wraps focus from first to last on Shift+Tab', () => {
    render(<FocusTrapHarness isOpen={true} />);
    const first = screen.getByRole('button', { name: 'First' });
    const last = screen.getByRole('button', { name: 'Last' });

    first.focus();
    fireEvent.keyDown(document, { key: 'Tab', shiftKey: true });
    expect(last).toHaveFocus();
  });

  it('calls onEscape when Escape key is pressed', () => {
    const onEscape = jest.fn();
    render(<FocusTrapHarness isOpen={true} onEscape={onEscape} />);

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onEscape).toHaveBeenCalledTimes(1);
  });

  it('restores focus to opener when trap closes', () => {
    function RestoreHarness() {
      const [open, setOpen] = React.useState(false);
      return (
        <div>
          <button type="button" onClick={() => setOpen(true)}>
            Open
          </button>
          <button type="button">Outside</button>
          <FocusTrapHarness isOpen={open} onEscape={() => setOpen(false)} />
        </div>
      );
    }

    render(<RestoreHarness />);
    const opener = screen.getByRole('button', { name: 'Open' });
    opener.focus();

    fireEvent.click(opener);
    expect(screen.getByRole('button', { name: 'First' })).toHaveFocus();

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(opener).toHaveFocus();
  });
});
