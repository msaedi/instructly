import imageCompression from 'browser-image-compression';
import {
  compressImage,
  ImageCompressionError,
} from '@/lib/image/compress';

jest.mock('browser-image-compression', () => ({
  __esModule: true,
  default: jest.fn(),
}));

const mockImageCompression = imageCompression as jest.MockedFunction<typeof imageCompression>;

describe('compressImage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('compresses a large jpeg and returns size metadata', async () => {
    const input = new File([new ArrayBuffer(2 * 1024 * 1024)], 'avatar.jpeg', {
      type: 'image/jpeg',
    });
    const output = new File([new ArrayBuffer(512 * 1024)], 'avatar.jpeg', {
      type: 'image/jpeg',
    });
    mockImageCompression.mockResolvedValue(output);

    const result = await compressImage(input);

    expect(result.file.name).toBe('avatar.jpg');
    expect(result.file.type).toBe('image/jpeg');
    expect(result.originalSize).toBe(input.size);
    expect(result.compressedSize).toBe(result.file.size);
    expect(result.wasCompressed).toBe(true);
  });

  it('converts png inputs to jpeg output and requests jpeg normalization', async () => {
    const input = new File(['png'], 'avatar.png', { type: 'image/png' });
    mockImageCompression.mockResolvedValue(
      new File(['jpeg'], 'avatar.png', { type: 'image/jpeg' })
    );

    const result = await compressImage(input, { maxSizeMB: 2, maxWidthOrHeight: 1600, quality: 0.7 });

    expect(mockImageCompression).toHaveBeenCalledWith(
      input,
      expect.objectContaining({
        maxSizeMB: 2,
        maxWidthOrHeight: 1600,
        initialQuality: 0.7,
        fileType: 'image/jpeg',
        preserveExif: false,
        useWebWorker: true,
      })
    );
    expect(result.file.name).toBe('avatar.jpg');
    expect(result.file.type).toBe('image/jpeg');
  });

  it('normalizes heic inputs to jpg filenames and jpeg output', async () => {
    const input = new File(['heic'], 'IMG_1234.HEIC', { type: 'image/heic' });
    mockImageCompression.mockResolvedValue(
      new File(['jpeg'], 'IMG_1234.HEIC', { type: 'image/jpeg' })
    );

    const result = await compressImage(input);

    expect(mockImageCompression).toHaveBeenCalledWith(
      input,
      expect.objectContaining({ fileType: 'image/jpeg', preserveExif: false })
    );
    expect(result.file.name).toBe('IMG_1234.jpg');
  });

  it('renames extensionless files to jpg', async () => {
    const input = new File(['jpeg'], 'avatar', { type: 'image/jpeg' });
    mockImageCompression.mockResolvedValue(
      new File(['jpeg'], 'avatar', { type: 'image/jpeg' })
    );

    const result = await compressImage(input);

    expect(result.file.name).toBe('avatar.jpg');
  });

  it('wraps compression failures in ImageCompressionError', async () => {
    const input = new File(['bad'], 'avatar.bmp', { type: 'image/bmp' });
    mockImageCompression.mockRejectedValue(new Error('boom'));

    await expect(compressImage(input)).rejects.toBeInstanceOf(ImageCompressionError);
    await expect(compressImage(input)).rejects.toMatchObject({
      message: 'Failed to compress image',
    });
  });
});
