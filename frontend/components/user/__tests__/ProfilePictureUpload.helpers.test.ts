import {
  buildCroppedProfileFile,
  getMeasuredOverlaySize,
  runWithCroppedProfileFile,
  shouldUseProxyProfileUpload,
} from '../ProfilePictureUpload.helpers';

describe('ProfilePictureUpload helpers', () => {
  it('uses proxy uploads locally or on the beta-local host', () => {
    expect(shouldUseProxyProfileUpload('local', null)).toBe(true);
    expect(shouldUseProxyProfileUpload('production', 'beta-local.instainstru.com')).toBe(true);
    expect(shouldUseProxyProfileUpload('production', 'app.instainstru.com')).toBe(false);
  });

  it('measures overlay size from the trigger circle and no-ops when no element exists', () => {
    expect(getMeasuredOverlaySize(null, 64)).toBeNull();

    const element = {
      querySelector: jest.fn(() => ({
        getBoundingClientRect: () => ({ width: 80, height: 76 }),
      })),
      getBoundingClientRect: () => ({ width: 90, height: 90 }),
    } as never;

    expect(getMeasuredOverlaySize(element, 64)).toBe(76);
    expect(getMeasuredOverlaySize(element, 76)).toBeNull();
  });

  it('swallows measurement errors and returns null', () => {
    const brokenElement = {
      querySelector: jest.fn(() => ({
        getBoundingClientRect: () => {
          throw new Error('layout unavailable');
        },
      })),
      getBoundingClientRect: () => ({ width: 90, height: 90 }),
    } as never;

    expect(getMeasuredOverlaySize(brokenElement, 64)).toBeNull();
  });

  it('builds cropped upload files and skips handlers when no pending file exists', async () => {
    const blob = new Blob(['crop'], { type: 'image/jpeg' });
    const createObjectUrl = jest.fn(() => 'blob:preview');
    const handler = jest.fn();

    expect(buildCroppedProfileFile(null, blob)).toBeNull();

    const file = buildCroppedProfileFile({ name: 'avatar.png' } as Pick<File, 'name'>, blob);
    expect(file?.name).toBe('avatar.jpg');

    await expect(
      runWithCroppedProfileFile(null, blob, createObjectUrl, handler),
    ).resolves.toBe(false);
    expect(handler).not.toHaveBeenCalled();

    await expect(
      runWithCroppedProfileFile(
        { name: 'avatar.png' } as Pick<File, 'name'>,
        blob,
        createObjectUrl,
        handler,
      ),
    ).resolves.toBe(true);
    expect(createObjectUrl).toHaveBeenCalled();
    expect(handler).toHaveBeenCalledWith({
      file: expect.any(File),
      url: 'blob:preview',
    });
  });
});
