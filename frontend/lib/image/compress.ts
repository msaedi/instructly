export type CompressOptions = {
  maxSizeMB?: number;
  maxWidthOrHeight?: number;
  quality?: number;
};

export type CompressResult = {
  file: File;
  originalSize: number;
  compressedSize: number;
  wasCompressed: boolean;
};

export class ImageCompressionError extends Error {
  override cause?: unknown;

  constructor(message: string, options?: { cause?: unknown }) {
    super(message);
    this.name = 'ImageCompressionError';
    this.cause = options?.cause;
  }
}

const DEFAULT_MAX_SIZE_MB = 1.5;
const DEFAULT_MAX_WIDTH_OR_HEIGHT = 2000;
const DEFAULT_QUALITY = 0.85;

function normalizeJpegFilename(filename: string): string {
  const trimmed = filename.trim();
  const stem = trimmed.replace(/\.[^.]+$/, '') || 'image';
  return `${stem}.jpg`;
}

export async function compressImage(
  input: File,
  options: CompressOptions = {}
): Promise<CompressResult> {
  const maxSizeMB = options.maxSizeMB ?? DEFAULT_MAX_SIZE_MB;
  const maxWidthOrHeight = options.maxWidthOrHeight ?? DEFAULT_MAX_WIDTH_OR_HEIGHT;
  const quality = options.quality ?? DEFAULT_QUALITY;

  try {
    const compressionModule = await import('browser-image-compression');
    const imageCompression = compressionModule.default;

    // Assumes browser-image-compression applies EXIF orientation during its
    // canvas pipeline before preserveExif: false strips metadata from output.
    const compressed = await imageCompression(input, {
      maxSizeMB,
      maxWidthOrHeight,
      initialQuality: quality,
      fileType: 'image/jpeg',
      useWebWorker: true,
      preserveExif: false,
    });

    const file = new File([compressed], normalizeJpegFilename(input.name), {
      type: 'image/jpeg',
      lastModified: compressed.lastModified || input.lastModified || Date.now(),
    });

    return {
      file,
      originalSize: input.size,
      compressedSize: file.size,
      wasCompressed:
        file.size !== input.size || file.type !== input.type || file.name !== input.name,
    };
  } catch (error) {
    throw new ImageCompressionError('Failed to compress image', { cause: error });
  }
}
