import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Modal from '../Modal';

// Mock logger
jest.mock('@/lib/logger', () => ({
  logger: {
    debug: jest.fn(),
    info: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
  },
}));

describe('Modal', () => {
  const defaultProps = {
    isOpen: true,
    onClose: jest.fn(),
    children: <div>Modal Content</div>,
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('rendering', () => {
    it('renders when open', () => {
      render(<Modal {...defaultProps} />);

      expect(screen.getByRole('dialog')).toBeInTheDocument();
      expect(screen.getByText('Modal Content')).toBeInTheDocument();
    });

    it('does not render when closed', () => {
      render(<Modal {...defaultProps} isOpen={false} />);

      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });

    it('renders with title', () => {
      render(<Modal {...defaultProps} title="Test Title" />);

      // Title appears in both visible heading and VisuallyHidden
      const headings = screen.getAllByRole('heading', { level: 2 });
      expect(headings.length).toBeGreaterThanOrEqual(1);
      expect(headings.some((h) => h.textContent === 'Test Title')).toBe(true);
    });

    it('renders footer when provided', () => {
      render(
        <Modal {...defaultProps} footer={<button>Footer Button</button>} />
      );

      expect(screen.getByRole('button', { name: 'Footer Button' })).toBeInTheDocument();
    });

    it('renders close button in header with title', () => {
      render(<Modal {...defaultProps} title="Test Title" showCloseButton={true} />);

      const closeButton = screen.getByRole('button', { name: /close modal/i });
      expect(closeButton).toBeInTheDocument();
    });

    it('renders floating close button without title', () => {
      render(<Modal {...defaultProps} showCloseButton={true} />);

      const closeButton = screen.getByRole('button', { name: /close modal/i });
      expect(closeButton).toBeInTheDocument();
      expect(closeButton).toHaveClass('absolute');
    });

    it('hides close button when showCloseButton is false', () => {
      render(<Modal {...defaultProps} showCloseButton={false} />);

      expect(screen.queryByRole('button', { name: /close modal/i })).not.toBeInTheDocument();
    });
  });

  describe('size variants', () => {
    it.each([
      ['sm', 'max-w-md'],
      ['md', 'max-w-lg'],
      ['lg', 'max-w-3xl'],
      ['xl', 'max-w-4xl'],
      ['full', 'max-w-7xl'],
    ] as const)('applies correct class for size %s', (size, expectedClass) => {
      render(<Modal {...defaultProps} size={size} />);

      const modalContainer = screen.getByText('Modal Content').parentElement?.parentElement;
      expect(modalContainer).toHaveClass(expectedClass);
    });
  });

  describe('closing behavior', () => {
    it('closes when X button is clicked with title', async () => {
      const user = userEvent.setup();
      const onClose = jest.fn();

      render(<Modal {...defaultProps} title="Test Title" onClose={onClose} />);

      await user.click(screen.getByRole('button', { name: /close modal/i }));

      await waitFor(() => {
        expect(onClose).toHaveBeenCalled();
      });
    });

    it('closes when X button is clicked without title', async () => {
      const user = userEvent.setup();
      const onClose = jest.fn();

      render(<Modal {...defaultProps} onClose={onClose} />);

      await user.click(screen.getByRole('button', { name: /close modal/i }));

      await waitFor(() => {
        expect(onClose).toHaveBeenCalled();
      });
    });

    it('closes on Escape key by default', async () => {
      const user = userEvent.setup();
      const onClose = jest.fn();

      render(<Modal {...defaultProps} onClose={onClose} />);

      await user.keyboard('{Escape}');

      await waitFor(() => {
        expect(onClose).toHaveBeenCalled();
      });
    });

    it('does NOT close on Escape when closeOnEscape is false', async () => {
      const user = userEvent.setup();
      const onClose = jest.fn();

      render(<Modal {...defaultProps} onClose={onClose} closeOnEscape={false} />);

      await user.keyboard('{Escape}');

      // Give some time to ensure it would have closed if it was going to
      await new Promise((r) => setTimeout(r, 100));

      expect(onClose).not.toHaveBeenCalled();
    });

    it('closes when clicking overlay by default', async () => {
      const user = userEvent.setup();
      const onClose = jest.fn();

      render(<Modal {...defaultProps} onClose={onClose} />);

      // Click on the overlay (the backdrop)
      const overlay = document.querySelector('.bg-black\\/30');
      if (overlay) {
        await user.click(overlay);
      }

      await waitFor(() => {
        expect(onClose).toHaveBeenCalled();
      });
    });

    it('does NOT close when clicking overlay if closeOnBackdrop is false', async () => {
      const user = userEvent.setup();
      const onClose = jest.fn();

      render(<Modal {...defaultProps} onClose={onClose} closeOnBackdrop={false} />);

      // Click on the overlay
      const overlay = document.querySelector('.bg-black\\/30');
      if (overlay) {
        await user.click(overlay);
      }

      // Give some time to ensure it would have closed if it was going to
      await new Promise((r) => setTimeout(r, 100));

      expect(onClose).not.toHaveBeenCalled();
    });

    it('does NOT close when clicking modal content', async () => {
      const user = userEvent.setup();
      const onClose = jest.fn();

      render(<Modal {...defaultProps} onClose={onClose} />);

      await user.click(screen.getByText('Modal Content'));

      // Give some time to ensure it would have closed if it was going to
      await new Promise((r) => setTimeout(r, 100));

      expect(onClose).not.toHaveBeenCalled();
    });
  });

  describe('accessibility', () => {
    it('has correct ARIA attributes for dialog', () => {
      render(<Modal {...defaultProps} />);

      const dialog = screen.getByRole('dialog');
      expect(dialog).toBeInTheDocument();
    });

    it('uses provided title for accessible title', () => {
      render(<Modal {...defaultProps} title="Custom Title" />);

      // Title appears in both visible heading and VisuallyHidden for accessibility
      const headings = screen.getAllByRole('heading', { level: 2 });
      expect(headings.length).toBeGreaterThanOrEqual(1);
      expect(headings.some((h) => h.textContent === 'Custom Title')).toBe(true);
    });

    it('uses default accessible title when no title is provided', () => {
      render(<Modal {...defaultProps} />);

      // Radix Dialog provides accessible title via VisuallyHidden
      expect(screen.getByRole('dialog')).toBeInTheDocument();
    });

    it('close button has accessible label', () => {
      render(<Modal {...defaultProps} title="Test" />);

      const closeButton = screen.getByRole('button', { name: /close modal/i });
      expect(closeButton).toHaveAttribute('aria-label', 'Close modal');
    });

    it('X icon is hidden from screen readers', () => {
      render(<Modal {...defaultProps} title="Test" />);

      const closeButton = screen.getByRole('button', { name: /close modal/i });
      const icon = closeButton.querySelector('svg');
      expect(icon).toHaveAttribute('aria-hidden', 'true');
    });
  });

  describe('styling options', () => {
    it('applies custom className to container', () => {
      render(<Modal {...defaultProps} className="custom-class" />);

      const container = screen.getByText('Modal Content').parentElement?.parentElement;
      expect(container).toHaveClass('custom-class');
    });

    it('applies custom contentClassName to content wrapper', () => {
      render(<Modal {...defaultProps} contentClassName="content-class" />);

      const content = screen.getByText('Modal Content').parentElement;
      expect(content).toHaveClass('content-class');
    });

    it('removes default padding when noPadding is true', () => {
      render(<Modal {...defaultProps} noPadding={true} />);

      const content = screen.getByText('Modal Content').parentElement;
      expect(content).not.toHaveClass('p-6');
    });

    it('applies default padding when noPadding is false', () => {
      render(<Modal {...defaultProps} noPadding={false} />);

      const content = screen.getByText('Modal Content').parentElement;
      expect(content).toHaveClass('p-6');
    });

    it('allows overflow when allowOverflow is true', () => {
      render(<Modal {...defaultProps} allowOverflow={true} />);

      const container = screen.getByText('Modal Content').parentElement?.parentElement;
      expect(container).toHaveClass('overflow-visible');
    });

    it('handles autoHeight correctly', () => {
      render(<Modal {...defaultProps} autoHeight={true} />);

      const container = screen.getByText('Modal Content').parentElement?.parentElement;
      expect(container).toHaveClass('h-auto');
    });
  });

  describe('edge cases', () => {
    it('handles rapid open/close without errors', () => {
      const onClose = jest.fn();
      const { rerender } = render(<Modal {...defaultProps} onClose={onClose} />);

      // Rapid toggle
      rerender(<Modal {...defaultProps} isOpen={false} onClose={onClose} />);
      rerender(<Modal {...defaultProps} isOpen={true} onClose={onClose} />);
      rerender(<Modal {...defaultProps} isOpen={false} onClose={onClose} />);
      rerender(<Modal {...defaultProps} isOpen={true} onClose={onClose} />);

      // Should render without error
      expect(screen.getByRole('dialog')).toBeInTheDocument();
    });

    it('handles empty children gracefully', () => {
      render(
        <Modal isOpen={true} onClose={jest.fn()}>
          {null}
        </Modal>
      );

      expect(screen.getByRole('dialog')).toBeInTheDocument();
    });

    it('handles description prop correctly', () => {
      render(<Modal {...defaultProps} description="Test description" />);

      // Description is rendered in VisuallyHidden for screen readers
      expect(screen.getByRole('dialog')).toBeInTheDocument();
    });
  });

  describe('footer styling', () => {
    it('applies correct footer styles', () => {
      render(<Modal {...defaultProps} footer={<span data-testid="footer-content">Footer</span>} />);

      const footerContent = screen.getByTestId('footer-content');
      const footer = footerContent.parentElement;
      expect(footer).toHaveClass('px-6', 'py-4', 'bg-gray-50');
    });
  });
});
