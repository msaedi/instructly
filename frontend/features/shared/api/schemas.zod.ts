// Dev/test-only Zod schemas aggregated here. Do not import directly in prod code.
export { loadBookingListSchema } from './schemas/bookingList';
export { loadInstructorProfileSchema } from './schemas/instructorProfile';
export { loadSearchListSchema } from './schemas/searchList';

// Helper to lazily load a schema only in dev/test
export function lazySchema<T>(importer: () => Promise<{ schema: unknown }>) {
  return importer as () => Promise<{ schema: unknown } & { __type?: T } >;
}
