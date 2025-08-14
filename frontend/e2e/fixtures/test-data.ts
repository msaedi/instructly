import TEST_ULIDS from './ulids';

export const testData = {
  search: {
    instrument: 'piano',
    location: 'New York',
  },

  student: {
    email: 'test.student@example.com',
    password: 'Test123!',
    firstName: 'Test',
    lastName: 'Student',
  },

  booking: {
    duration: 60, // minutes
    notes: 'Looking forward to the lesson!',
  },

  // Mock instructor data that matches what we expect from the API
  mockInstructor: {
    id: TEST_ULIDS.instructor8,
    user: {
      firstName: 'John',
      lastName: 'Doe',
      email: 'john.doe@example.com',
    },
    bio: 'Professional piano teacher with 10 years of experience',
    hourlyRate: 75,
    instruments: ['Piano'],
    location: 'New York, NY',
    profileImageUrl: null,
  },

  // Mock availability slots
  mockAvailability: [
    {
      id: 1,
      date: new Date().toISOString().split('T')[0], // Today
      startTime: '14:00',
      endTime: '15:00',
      isAvailable: true,
    },
    {
      id: 2,
      date: new Date().toISOString().split('T')[0], // Today
      startTime: '15:00',
      endTime: '16:00',
      isAvailable: true,
    },
    {
      id: 3,
      date: new Date(Date.now() + 86400000).toISOString().split('T')[0], // Tomorrow
      startTime: '10:00',
      endTime: '11:00',
      isAvailable: true,
    },
  ],
};
