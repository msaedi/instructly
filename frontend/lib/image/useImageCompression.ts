import { useCallback, useState } from 'react';
import {
  compressImage,
  type CompressOptions,
  type CompressResult,
} from '@/lib/image/compress';

export function useImageCompression(): {
  compress: (file: File, options?: CompressOptions) => Promise<CompressResult>;
  isCompressing: boolean;
  error: Error | null;
} {
  const [isCompressing, setIsCompressing] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const compress = useCallback(async (file: File, options?: CompressOptions) => {
    setIsCompressing(true);
    setError(null);
    try {
      const result = await compressImage(file, options);
      setError(null);
      return result;
    } catch (compressionError) {
      const normalizedError =
        compressionError instanceof Error
          ? compressionError
          : new Error('Failed to compress image');
      setError(normalizedError);
      throw normalizedError;
    } finally {
      setIsCompressing(false);
    }
  }, []);

  return { compress, isCompressing, error };
}
