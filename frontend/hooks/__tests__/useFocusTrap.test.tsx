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
    ...(onEscape ? { onEscape } : {}),
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

  it('ignores hidden and disabled elements when choosing initial focus', () => {
    function HiddenHarness() {
      const containerRef = useRef<HTMLDivElement | null>(null);
      useFocusTrap({
        isOpen: true,
        containerRef,
      });

      return (
        <div ref={containerRef} role="dialog" tabIndex={-1}>
          <button type="button" aria-hidden="true">
            Hidden
          </button>
          <button type="button" disabled>
            Disabled
          </button>
          <button type="button">Focusable</button>
        </div>
      );
    }

    render(<HiddenHarness />);
    expect(screen.getByRole('button', { name: 'Focusable' })).toHaveFocus();
  });

  it('skips elements hidden with the hidden attribute when choosing initial focus', () => {
    function HiddenAttributeHarness() {
      const containerRef = useRef<HTMLDivElement | null>(null);
      useFocusTrap({
        isOpen: true,
        containerRef,
      });

      return (
        <div ref={containerRef} role="dialog" tabIndex={-1}>
          <button type="button" hidden>
            Hidden by attribute
          </button>
          <button type="button">Visible focus target</button>
        </div>
      );
    }

    render(<HiddenAttributeHarness />);
    expect(screen.getByRole('button', { name: 'Visible focus target' })).toHaveFocus();
  });

  it('moves focus back inside the trap when Tab starts outside the container', () => {
    function OutsideTabHarness() {
      const containerRef = useRef<HTMLDivElement | null>(null);
      useFocusTrap({
        isOpen: true,
        containerRef,
      });

      return (
        <div>
          <button type="button">Outside</button>
          <div ref={containerRef} role="dialog" tabIndex={-1}>
            <button type="button">First</button>
            <button type="button">Last</button>
          </div>
        </div>
      );
    }

    render(<OutsideTabHarness />);
    const outside = screen.getByRole('button', { name: 'Outside' });
    const first = screen.getByRole('button', { name: 'First' });
    const last = screen.getByRole('button', { name: 'Last' });

    outside.focus();
    fireEvent.keyDown(document, { key: 'Tab' });
    expect(first).toHaveFocus();

    outside.focus();
    fireEvent.keyDown(document, { key: 'Tab', shiftKey: true });
    expect(last).toHaveFocus();
  });

  it('does nothing when the trap is open but no container is mounted yet', () => {
    function MissingContainerHarness() {
      const containerRef = useRef<HTMLDivElement | null>(null);
      useFocusTrap({
        isOpen: true,
        containerRef,
      });
      return null;
    }

    expect(() => render(<MissingContainerHarness />)).not.toThrow();
  });

  it('keeps focus on the container when tabbing inside a trap with no focusables', () => {
    render(<FocusTrapHarness isOpen={true} includeFocusable={false} />);
    const dialog = screen.getByRole('dialog');

    dialog.focus();
    fireEvent.keyDown(document, { key: 'Tab' });

    expect(dialog).toHaveFocus();
  });

  it('keeps the keydown handler safe if the container ref is cleared after mount', () => {
    function NullRefAfterMountHarness() {
      const containerRef = useRef<HTMLDivElement | null>(null);
      useFocusTrap({
        isOpen: true,
        containerRef,
      });

      React.useEffect(() => {
        containerRef.current = null;
      }, []);

      return (
        <div ref={containerRef} role="dialog" tabIndex={-1}>
          <button type="button">First</button>
        </div>
      );
    }

    render(<NullRefAfterMountHarness />);

    expect(() => {
      fireEvent.keyDown(document, { key: 'Tab' });
    }).not.toThrow();
  });

  it('stores null as the previous active element when no HTMLElement is focused', () => {
    const activeElementSpy = jest
      .spyOn(document, 'activeElement', 'get')
      .mockReturnValue(null);

    try {
      expect(() => render(<FocusTrapHarness isOpen={true} />)).not.toThrow();
      expect(screen.getByRole('button', { name: 'First' })).toBeInTheDocument();
    } finally {
      activeElementSpy.mockRestore();
    }
  });
});
