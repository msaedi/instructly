import React, { useState } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createPortal } from 'react-dom';
import { FilterButton } from '../FilterButton';

jest.mock('react-dom', () => {
  const actual = jest.requireActual('react-dom');
  return {
    ...actual,
    createPortal: jest.fn((element: React.ReactNode) => element),
  };
});

const mockCreatePortal = createPortal as jest.Mock;

/**
 * Harness wraps FilterButton with local state so we can control
 * isOpen/onClickOutside through stateful interactions.
 */
function Harness() {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div>
      <FilterButton
        label="Test Filter"
        isOpen={isOpen}
        isActive={false}
        onClick={() => setIsOpen((prev) => !prev)}
        onClickOutside={() => setIsOpen(false)}
      >
        <div data-testid="dropdown-content">Dropdown content</div>
      </FilterButton>
      <div data-testid="outside-area">Outside</div>
    </div>
  );
}

describe('FilterButton', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockCreatePortal.mockImplementation((element: React.ReactNode) => element);
  });

  it('renders the label text on the button', () => {
    render(<Harness />);
    expect(screen.getByRole('button', { name: 'Test Filter' })).toBeInTheDocument();
  });

  it('opens dropdown on click and shows children', async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(screen.getByRole('button', { name: 'Test Filter' }));

    expect(screen.getByTestId('dropdown-content')).toBeInTheDocument();
  });

  it('closes dropdown when clicking outside (exercises handleClickOutside)', async () => {
    const user = userEvent.setup();
    render(<Harness />);

    // Open dropdown
    await user.click(screen.getByRole('button', { name: 'Test Filter' }));
    expect(screen.getByTestId('dropdown-content')).toBeInTheDocument();

    // Click outside the button and dropdown
    fireEvent.mouseDown(screen.getByTestId('outside-area'));

    expect(screen.queryByTestId('dropdown-content')).not.toBeInTheDocument();
  });

  it('keeps dropdown open when clicking inside the dropdown', async () => {
    const user = userEvent.setup();
    render(<Harness />);

    // Open dropdown
    await user.click(screen.getByRole('button', { name: 'Test Filter' }));
    expect(screen.getByTestId('dropdown-content')).toBeInTheDocument();

    // Click inside the dropdown content
    fireEvent.mouseDown(screen.getByTestId('dropdown-content'));

    // Dropdown should remain open
    expect(screen.getByTestId('dropdown-content')).toBeInTheDocument();
  });

  it('keeps dropdown open when clicking the trigger button itself', async () => {
    const user = userEvent.setup();
    render(<Harness />);

    // Open dropdown
    await user.click(screen.getByRole('button', { name: 'Test Filter' }));
    expect(screen.getByTestId('dropdown-content')).toBeInTheDocument();

    // Mousedown on the button area (the button is inside the ref div)
    // This exercises the inButton check in handleClickOutside
    fireEvent.mouseDown(screen.getByRole('button', { name: 'Test Filter' }));

    // handleClickOutside should NOT close it since click is inside the button ref
    expect(screen.getByTestId('dropdown-content')).toBeInTheDocument();
  });

  it('does not attach mousedown listener when dropdown is closed', () => {
    const addEventSpy = jest.spyOn(document, 'addEventListener');
    render(<Harness />);

    // When not open, no mousedown listener should be registered for handleClickOutside
    const mousedownCalls = addEventSpy.mock.calls.filter(
      ([event]) => event === 'mousedown'
    );
    expect(mousedownCalls.length).toBe(0);

    addEventSpy.mockRestore();
  });

  it('cleans up mousedown listener on unmount while open', async () => {
    const removeEventSpy = jest.spyOn(document, 'removeEventListener');
    const user = userEvent.setup();
    const { unmount } = render(<Harness />);

    await user.click(screen.getByRole('button', { name: 'Test Filter' }));

    removeEventSpy.mockClear();
    unmount();

    const mousedownRemovals = removeEventSpy.mock.calls.filter(
      ([event]) => event === 'mousedown'
    );
    expect(mousedownRemovals.length).toBeGreaterThan(0);

    removeEventSpy.mockRestore();
  });

  it('sets aria-expanded correctly based on open state', async () => {
    const user = userEvent.setup();
    render(<Harness />);

    const button = screen.getByRole('button', { name: 'Test Filter' });
    expect(button).toHaveAttribute('aria-expanded', 'false');

    await user.click(button);
    expect(button).toHaveAttribute('aria-expanded', 'true');
  });

  it('does not portal dropdown when server snapshot returns false for isClient', async () => {
    const actualReact = jest.requireActual<typeof import('react')>('react');
    const spy = jest.spyOn(actualReact, 'useSyncExternalStore').mockImplementation(
      (_subscribe, _getSnapshot, getServerSnapshot) => {
        return getServerSnapshot ? getServerSnapshot() : _getSnapshot();
      }
    );

    const user = userEvent.setup();
    render(<Harness />);

    // Click to open -- the button onClick still fires and isOpen becomes true,
    // but the portal condition requires isClient && isOpen && position.
    // With isClient=false, the dropdown children should not be portaled.
    await user.click(screen.getByRole('button', { name: 'Test Filter' }));

    expect(screen.queryByTestId('dropdown-content')).not.toBeInTheDocument();

    spy.mockRestore();
  });

  it('applies active styles when isActive is true', () => {
    render(
      <FilterButton
        label="Active"
        isOpen={false}
        isActive={true}
        onClick={jest.fn()}
        onClickOutside={jest.fn()}
      >
        <div>content</div>
      </FilterButton>
    );

    const button = screen.getByRole('button', { name: 'Active' });
    expect(button.className).toContain('bg-purple-100');
  });
});
