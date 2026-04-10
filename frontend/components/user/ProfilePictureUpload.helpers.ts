type MeasureElement = Pick<HTMLElement, 'getBoundingClientRect' | 'querySelector'>;

export const MAX_PROFILE_PICTURE_INPUT_BYTES = 50 * 1024 * 1024;
export const PROFILE_PICTURE_TOO_LARGE_MESSAGE =
  'Please choose a smaller image (under 50MB).';
export const PROFILE_PICTURE_PROCESS_ERROR_MESSAGE =
  "We couldn't process this image. Please try a different file.";

export const shouldUseProxyProfileUpload = (
  appEnv: string,
  hostname?: string | null,
): boolean => {
  if (appEnv === 'local') {
    return true;
  }
  return hostname === 'beta-local.instainstru.com';
};

export const getMeasuredOverlaySize = (
  element: MeasureElement | null,
  currentSize: number,
): number | null => {
  if (!element) {
    return null;
  }
  try {
    const circle = element.querySelector('.rounded-full') as HTMLElement | null;
    const rect = (circle || element).getBoundingClientRect();
    const width = Math.round(rect.width);
    const height = Math.round(rect.height);
    if (!width || !height) {
      return null;
    }
    const nextSize = Math.min(width, height);
    return Math.abs(nextSize - currentSize) > 1 ? nextSize : null;
  } catch {
    return null;
  }
};

export const buildCroppedProfileFile = (
  pendingFile: Pick<File, 'name'> | null,
  blob: Blob,
): File | null => {
  if (!pendingFile) {
    return null;
  }
  const filename = (pendingFile.name.split('.').slice(0, -1).join('.') || 'avatar') + '.jpg';
  return new File([blob], filename, { type: 'image/jpeg' });
};

export const runWithCroppedProfileFile = async (
  pendingFile: Pick<File, 'name'> | null,
  blob: Blob,
  createObjectUrl: (file: File) => string,
  handler: (payload: { file: File; url: string }) => Promise<void> | void,
): Promise<boolean> => {
  const file = buildCroppedProfileFile(pendingFile, blob);
  if (!file) {
    return false;
  }
  const url = createObjectUrl(file);
  await handler({ file, url });
  return true;
};
