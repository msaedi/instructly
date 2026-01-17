import { parseSearchQuery } from '../search-parser';

describe('parseSearchQuery', () => {
  it('extracts subject and max rate for under queries', () => {
    expect(parseSearchQuery('Math tutor under $50')).toEqual({
      subjects: ['math'],
      max_rate: 50,
    });
  });

  it('extracts a price range and subject', () => {
    expect(parseSearchQuery('Piano lessons $30-80')).toEqual({
      subjects: ['piano'],
      min_rate: 30,
      max_rate: 80,
    });
  });

  it('detects availability now and min rate', () => {
    expect(parseSearchQuery('Available now over 40')).toEqual({
      subjects: [],
      available_now: true,
      min_rate: 40,
    });
  });
});
