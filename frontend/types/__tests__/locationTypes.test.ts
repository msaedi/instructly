import type { BookingLocationType, ServiceLocationType } from '../api';

describe('Location type definitions', () => {
  it('BookingLocationType accepts valid values', () => {
    const validTypes: BookingLocationType[] = [
      'student_location',
      'instructor_location',
      'online',
      'neutral_location',
    ];
    expect(validTypes).toHaveLength(4);
  });

  it('ServiceLocationType accepts valid values', () => {
    const validTypes: ServiceLocationType[] = ['in_person', 'online'];
    expect(validTypes).toHaveLength(2);
  });
});
