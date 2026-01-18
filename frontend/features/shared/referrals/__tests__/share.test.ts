/**
 * @jest-environment jsdom
 */
import { shareOrCopy } from '../share';

describe('shareOrCopy', () => {
  // Save original navigator
  const originalNavigator = global.navigator;

  // Mock functions
  let mockShare: jest.Mock;
  let mockCanShare: jest.Mock;
  let mockWriteText: jest.Mock;

  beforeEach(() => {
    mockShare = jest.fn();
    mockCanShare = jest.fn();
    mockWriteText = jest.fn();

    // Reset navigator mock
    Object.defineProperty(global, 'navigator', {
      value: {
        share: mockShare,
        canShare: mockCanShare,
        clipboard: {
          writeText: mockWriteText,
        },
      },
      writable: true,
      configurable: true,
    });
  });

  afterEach(() => {
    Object.defineProperty(global, 'navigator', {
      value: originalNavigator,
      writable: true,
      configurable: true,
    });
  });

  describe('Web Share API', () => {
    it('returns "shared" when Web Share API succeeds', async () => {
      mockCanShare.mockReturnValue(true);
      mockShare.mockResolvedValue(undefined);

      const payload: ShareData = { title: 'Test', text: 'Hello', url: 'https://example.com' };
      const result = await shareOrCopy(payload, 'https://example.com');

      expect(result).toBe('shared');
      expect(mockShare).toHaveBeenCalledWith(payload);
    });

    it('uses Web Share API when canShare returns true', async () => {
      mockCanShare.mockReturnValue(true);
      mockShare.mockResolvedValue(undefined);

      const payload: ShareData = { title: 'Test' };
      await shareOrCopy(payload, 'fallback text');

      expect(mockCanShare).toHaveBeenCalledWith(payload);
      expect(mockShare).toHaveBeenCalled();
    });

    it('uses Web Share API when canShare is undefined', async () => {
      Object.defineProperty(global, 'navigator', {
        value: {
          share: mockShare,
          // canShare is undefined
          clipboard: { writeText: mockWriteText },
        },
        writable: true,
        configurable: true,
      });
      mockShare.mockResolvedValue(undefined);

      const payload: ShareData = { title: 'Test' };
      const result = await shareOrCopy(payload, 'fallback');

      expect(result).toBe('shared');
    });
  });

  describe('Clipboard fallback', () => {
    it('falls back to clipboard when Web Share is not available', async () => {
      Object.defineProperty(global, 'navigator', {
        value: {
          // share is undefined
          clipboard: { writeText: mockWriteText },
        },
        writable: true,
        configurable: true,
      });
      mockWriteText.mockResolvedValue(undefined);

      const result = await shareOrCopy({ title: 'Test' }, 'copy this text');

      expect(result).toBe('copied');
      expect(mockWriteText).toHaveBeenCalledWith('copy this text');
    });

    it('falls back to clipboard when canShare returns false', async () => {
      mockCanShare.mockReturnValue(false);
      mockWriteText.mockResolvedValue(undefined);

      const result = await shareOrCopy({ title: 'Test' }, 'copy text');

      expect(result).toBe('copied');
      expect(mockShare).not.toHaveBeenCalled();
    });

    it('falls back to clipboard when share throws an error', async () => {
      mockCanShare.mockReturnValue(true);
      mockShare.mockRejectedValue(new Error('User cancelled'));
      mockWriteText.mockResolvedValue(undefined);

      const result = await shareOrCopy({ title: 'Test' }, 'copy text');

      expect(result).toBe('copied');
    });
  });

  describe('execCommand fallback', () => {
    it('uses execCommand when clipboard.writeText is not available', async () => {
      const mockExecCommand = jest.fn().mockReturnValue(true);
      const mockAppendChild = jest.fn();
      const mockRemoveChild = jest.fn();
      const mockSelect = jest.fn();

      Object.defineProperty(global, 'navigator', {
        value: {
          // No share, no clipboard
        },
        writable: true,
        configurable: true,
      });

      // Mock document.createElement and body methods
      const mockTextarea = {
        value: '',
        setAttribute: jest.fn(),
        style: {},
        select: mockSelect,
      };

      jest.spyOn(document, 'createElement').mockReturnValue(mockTextarea as unknown as HTMLTextAreaElement);
      jest.spyOn(document.body, 'appendChild').mockImplementation(mockAppendChild);
      jest.spyOn(document.body, 'removeChild').mockImplementation(mockRemoveChild);
      Object.defineProperty(document, 'execCommand', {
        value: mockExecCommand,
        configurable: true,
      });

      const result = await shareOrCopy({ title: 'Test' }, 'copy this');

      expect(result).toBe('copied');
      expect(mockTextarea.value).toBe('copy this');
      expect(mockSelect).toHaveBeenCalled();
      expect(mockExecCommand).toHaveBeenCalledWith('copy');
    });
  });

  // Note: SSR test (window is undefined) cannot be tested in jsdom environment
  // The shareOrCopy function handles this case by returning 'skipped';

  describe('error handling', () => {
    it('returns "skipped" when all methods fail', async () => {
      Object.defineProperty(global, 'navigator', {
        value: {
          clipboard: {
            writeText: jest.fn().mockRejectedValue(new Error('Failed')),
          },
        },
        writable: true,
        configurable: true,
      });

      const result = await shareOrCopy({ title: 'Test' }, 'text');

      expect(result).toBe('skipped');
    });
  });
});
