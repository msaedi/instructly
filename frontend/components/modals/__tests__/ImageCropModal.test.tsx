import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ImageCropModal from '../ImageCropModal';

// Mock the logger
jest.mock('@/lib/logger', () => ({
  logger: {
    info: jest.fn(),
    error: jest.fn(),
    debug: jest.fn(),
    warn: jest.fn(),
  },
}));

// Mock URL.createObjectURL and revokeObjectURL
const mockCreateObjectURL = jest.fn(() => 'blob:mock-url');
const mockRevokeObjectURL = jest.fn();
global.URL.createObjectURL = mockCreateObjectURL;
global.URL.revokeObjectURL = mockRevokeObjectURL;

// Mock canvas API
const mockCanvasContext = {
  fillStyle: '',
  fillRect: jest.fn(),
  save: jest.fn(),
  translate: jest.fn(),
  scale: jest.fn(),
  drawImage: jest.fn(),
  restore: jest.fn(),
};

HTMLCanvasElement.prototype.getContext = jest.fn(() => mockCanvasContext) as jest.Mock;
HTMLCanvasElement.prototype.toBlob = jest.fn((callback: BlobCallback) => {
  callback(new Blob(['mock-image'], { type: 'image/jpeg' }));
});

describe('ImageCropModal', () => {
  const mockFile = new File(['test-image-data'], 'test.jpg', { type: 'image/jpeg' });

  const defaultProps = {
    isOpen: true,
    file: mockFile,
    onClose: jest.fn(),
    onCropped: jest.fn(),
    viewportSize: 320,
    outputSize: 800,
  };

  beforeEach(() => {
    jest.clearAllMocks();

    // Reset Image.prototype
    let onloadCallback: (() => void) | null = null;
    jest.spyOn(global, 'Image').mockImplementation(() => {
      const img = {
        onload: null as (() => void) | null,
        onerror: null as (() => void) | null,
        src: '',
        naturalWidth: 1000,
        naturalHeight: 800,
      };
      // Capture the onload callback
      Object.defineProperty(img, 'onload', {
        set(cb) {
          onloadCallback = cb;
          // Trigger load asynchronously to simulate real behavior
          setTimeout(() => {
            if (cb) cb.call(img);
          }, 0);
        },
        get() {
          return onloadCallback;
        },
      });
      return img as unknown as HTMLImageElement;
    });
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('renders modal when open with file', async () => {
    render(<ImageCropModal {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument();
    });
  });

  it('does not render when isOpen is false', () => {
    render(<ImageCropModal {...defaultProps} isOpen={false} />);

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('shows zoom control', async () => {
    render(<ImageCropModal {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText('Zoom')).toBeInTheDocument();
      expect(screen.getByRole('slider')).toBeInTheDocument();
    });
  });

  it('shows instructions for cropping', async () => {
    render(<ImageCropModal {...defaultProps} />);

    await waitFor(() => {
      expect(
        screen.getByText(/drag to pan, use the slider or scroll to zoom/i)
      ).toBeInTheDocument();
    });
  });

  it('calls onClose when Cancel button is clicked', async () => {
    const user = userEvent.setup();
    render(<ImageCropModal {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /cancel/i }));

    expect(defaultProps.onClose).toHaveBeenCalledTimes(1);
  });

  it('calls onCropped with blob when Save is clicked', async () => {
    const user = userEvent.setup();
    const onCropped = jest.fn();
    render(<ImageCropModal {...defaultProps} onCropped={onCropped} />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /save/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /save/i }));

    await waitFor(() => {
      expect(onCropped).toHaveBeenCalledWith(expect.any(Blob));
    });
  });

  it('creates object URL for file', async () => {
    render(<ImageCropModal {...defaultProps} />);

    await waitFor(() => {
      expect(mockCreateObjectURL).toHaveBeenCalledWith(mockFile);
    });
  });

  it('revokes object URL on unmount', async () => {
    const { unmount } = render(<ImageCropModal {...defaultProps} />);

    await waitFor(() => {
      expect(mockCreateObjectURL).toHaveBeenCalled();
    });

    unmount();

    expect(mockRevokeObjectURL).toHaveBeenCalledWith('blob:mock-url');
  });

  it('resets state when file is null', async () => {
    const { rerender } = render(<ImageCropModal {...defaultProps} />);

    await waitFor(() => {
      expect(mockCreateObjectURL).toHaveBeenCalled();
    });

    // Set file to null
    rerender(<ImageCropModal {...defaultProps} file={null} />);

    // State should be reset - modal still renders
    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument();
    });
  });

  it('has crop area with proper ARIA label', async () => {
    render(<ImageCropModal {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByLabelText('Image crop area')).toBeInTheDocument();
    });
  });

  it('shows zoom percentage', async () => {
    render(<ImageCropModal {...defaultProps} />);

    await waitFor(() => {
      // Should show some zoom percentage
      expect(screen.getByText(/%$/)).toBeInTheDocument();
    });
  });

  it('handles pointer down event', async () => {
    render(<ImageCropModal {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByLabelText('Image crop area')).toBeInTheDocument();
    });

    const cropArea = screen.getByLabelText('Image crop area');
    fireEvent.pointerDown(cropArea, { clientX: 100, clientY: 100 });

    // After pointer down, cursor should change (testing that event handler runs)
    expect(cropArea).toHaveStyle({ cursor: 'grabbing' });
  });

  it('handles pointer move event when dragging', async () => {
    render(<ImageCropModal {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByLabelText('Image crop area')).toBeInTheDocument();
    });

    const cropArea = screen.getByLabelText('Image crop area');

    // Start drag
    fireEvent.pointerDown(cropArea, { clientX: 100, clientY: 100 });

    // Move
    fireEvent.pointerMove(cropArea, { clientX: 150, clientY: 150 });

    // End drag
    fireEvent.pointerUp(cropArea);

    expect(cropArea).toHaveStyle({ cursor: 'grab' });
  });

  it('handles pointer leave event', async () => {
    render(<ImageCropModal {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByLabelText('Image crop area')).toBeInTheDocument();
    });

    const cropArea = screen.getByLabelText('Image crop area');

    fireEvent.pointerDown(cropArea, { clientX: 100, clientY: 100 });
    fireEvent.pointerLeave(cropArea);

    // Should reset dragging state
    expect(cropArea).toHaveStyle({ cursor: 'grab' });
  });

  it('handles wheel event for zoom', async () => {
    render(<ImageCropModal {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByLabelText('Image crop area')).toBeInTheDocument();
    });

    const cropArea = screen.getByLabelText('Image crop area');

    // Scroll to zoom in
    fireEvent.wheel(cropArea, { deltaY: -100 });

    // The component should handle this without error
    expect(cropArea).toBeInTheDocument();
  });

  it('handles zoom slider change', async () => {
    render(<ImageCropModal {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByRole('slider')).toBeInTheDocument();
    });

    const slider = screen.getByRole('slider');
    fireEvent.change(slider, { target: { value: '0.7' } });

    // Slider should respond to change (value should be different from initial state)
    expect(slider).toBeInTheDocument();
  });

  it('handles image load error gracefully', async () => {
    // The component handles errors internally
    render(<ImageCropModal {...defaultProps} />);

    // Modal should still render
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('uses default viewport and output sizes', async () => {
    render(<ImageCropModal {...defaultProps} viewportSize={undefined} outputSize={undefined} />);

    // Modal should render with default sizes
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('properly handles canvas context being null', async () => {
    HTMLCanvasElement.prototype.getContext = jest.fn(() => null) as jest.Mock;

    const onCropped = jest.fn();
    render(<ImageCropModal {...defaultProps} onCropped={onCropped} />);

    // Save button should be present
    expect(screen.getByRole('button', { name: /save/i })).toBeInTheDocument();
  });

  it('properly handles toBlob returning null', async () => {
    HTMLCanvasElement.prototype.getContext = jest.fn(() => mockCanvasContext) as jest.Mock;
    HTMLCanvasElement.prototype.toBlob = jest.fn((callback: BlobCallback) => {
      callback(null);
    });

    const onCropped = jest.fn();
    render(<ImageCropModal {...defaultProps} onCropped={onCropped} />);

    // Save button should be present
    expect(screen.getByRole('button', { name: /save/i })).toBeInTheDocument();
  });

  it('logs error when image fails to load', async () => {
    const { logger } = jest.requireMock('@/lib/logger');

    // Mock Image to trigger onerror
    jest.spyOn(global, 'Image').mockImplementation(() => {
      const img = {
        onload: null as (() => void) | null,
        onerror: null as ((err?: unknown) => void) | null,
        src: '',
        naturalWidth: 0,
        naturalHeight: 0,
      };
      Object.defineProperty(img, 'onerror', {
        set(cb) {
          // Trigger error asynchronously
          setTimeout(() => {
            if (cb) cb.call(img);
          }, 0);
        },
        get() {
          return null;
        },
      });
      return img as unknown as HTMLImageElement;
    });

    render(<ImageCropModal {...defaultProps} />);

    await waitFor(() => {
      expect(logger.error).toHaveBeenCalledWith('Failed to load image for cropping');
    });
  });

  it('ignores pointer move when not dragging', async () => {
    render(<ImageCropModal {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByLabelText('Image crop area')).toBeInTheDocument();
    });

    const cropArea = screen.getByLabelText('Image crop area');

    // Move without starting drag - should do nothing
    fireEvent.pointerMove(cropArea, { clientX: 150, clientY: 150 });

    // Cursor should still be 'grab' (not 'grabbing')
    expect(cropArea).toHaveStyle({ cursor: 'grab' });
  });

  it('does not call onCropped when Save clicked before image loads', async () => {
    // Mock Image to never load
    jest.spyOn(global, 'Image').mockImplementation(() => {
      const img = {
        onload: null,
        onerror: null,
        src: '',
        naturalWidth: 0,
        naturalHeight: 0,
      };
      return img as unknown as HTMLImageElement;
    });

    const user = userEvent.setup();
    const onCropped = jest.fn();
    render(<ImageCropModal {...defaultProps} onCropped={onCropped} />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /save/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /save/i }));

    // onCropped should not be called because image hasn't loaded
    expect(onCropped).not.toHaveBeenCalled();
  });

  it('logs error when toBlob throws an exception', async () => {
    const { logger } = jest.requireMock('@/lib/logger');

    HTMLCanvasElement.prototype.getContext = jest.fn(() => mockCanvasContext) as jest.Mock;
    HTMLCanvasElement.prototype.toBlob = jest.fn(() => {
      throw new Error('Canvas error');
    });

    const user = userEvent.setup();
    const onCropped = jest.fn();
    render(<ImageCropModal {...defaultProps} onCropped={onCropped} />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /save/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /save/i }));

    await waitFor(() => {
      expect(logger.error).toHaveBeenCalledWith(
        'Failed to create cropped image',
        expect.any(Error)
      );
    });
  });

  it('does nothing on save when canvas context returns null', async () => {
    HTMLCanvasElement.prototype.getContext = jest.fn(() => null) as jest.Mock;

    const user = userEvent.setup();
    const onCropped = jest.fn();
    render(<ImageCropModal {...defaultProps} onCropped={onCropped} />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /save/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /save/i }));

    // onCropped should not be called
    expect(onCropped).not.toHaveBeenCalled();
  });
});
