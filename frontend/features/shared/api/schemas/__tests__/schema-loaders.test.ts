import { loadBookingListSchema } from '../bookingList';
import { loadInstructorProfileSchema } from '../instructorProfile';
import { loadMeSchema } from '../me';
import { loadSearchListSchema } from '../searchList';

describe('schema loaders production guard', () => {
  const originalEnv = process.env.NODE_ENV;
  const setNodeEnv = (value: string) => {
    (process.env as Record<string, string | undefined>)['NODE_ENV'] = value;
  };

  afterEach(() => {
    setNodeEnv(originalEnv ?? '');
  });

  it('throws in production for booking list schema', async () => {
    setNodeEnv('production');
    await expect(loadBookingListSchema()).rejects.toThrow(
      'loadBookingListSchema should not be used in production'
    );
  });

  it('throws in production for instructor profile schema', async () => {
    setNodeEnv('production');
    await expect(loadInstructorProfileSchema()).rejects.toThrow(
      'loadInstructorProfileSchema should not be used in production'
    );
  });

  it('throws in production for me schema', async () => {
    setNodeEnv('production');
    await expect(loadMeSchema()).rejects.toThrow(
      'loadMeSchema should not be used in production'
    );
  });

  it('throws in production for search list schema', async () => {
    setNodeEnv('production');
    await expect(loadSearchListSchema()).rejects.toThrow(
      'loadSearchListSchema should not be used in production'
    );
  });
});
