import { Page, Route } from '@playwright/test';
import { testData } from './test-data';

export async function mockSearchResults(page: Page) {
  // Mock the natural language search endpoint - this is what the frontend actually calls
  await page.route('**/api/search/instructors*', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        query: 'piano',
        parsed: {
          services: ['piano'],
          location: null,
        },
        total_found: 1,
        results: [
          {
            instructor: {
              id: 8,
              name: 'Sarah Chen',
              bio: testData.mockInstructor.bio,
              profile_image_url: testData.mockInstructor.profileImageUrl,
              location: testData.mockInstructor.location,
              areas_of_service: 'Manhattan, Brooklyn',
              years_experience: 10,
            },
            service: {
              id: 1,
              name: 'Piano',
              actual_min_price: 120,
              description: 'Professional piano lessons',
            },
            offering: {
              hourly_rate: 120,
              description: 'Professional piano lessons',
              duration_options: [30, 60, 90],
            },
            match_score: 0.95,
            availability_summary: 'Available this week',
            rating: 4.9,
            total_reviews: 25,
            location: 'Manhattan',
            distance_miles: null,
          },
        ],
      }),
    });
  });

  // Also mock the public instructors endpoint for non-search queries
  await page.route('**/public/instructors*', async (route: Route) => {
    const url = route.request().url();
    if (url.includes('search')) {
      // For search queries
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          instructors: [
            {
              ...testData.mockInstructor,
              id: 1,
              full_name: 'John Doe',
              rating: 4.9,
              total_reviews: 25,
              services: testData.mockInstructor.instruments,
            },
          ],
          total: 1,
        }),
      });
    } else {
      await route.continue();
    }
  });
}

export async function mockInstructorProfile(page: Page) {
  // Mock both frontend routes
  await page.route('**/instructors/*', async (route: Route) => {
    const url = route.request().url();
    // Handle both /instructors/1 and /api/instructors/1 but not availability
    if (!url.includes('/availability') && !url.includes('/search')) {
      // Extract instructor ID from URL
      const idMatch = url.match(/instructors\/(\d+)/);
      const instructorId = idMatch ? parseInt(idMatch[1]) : 1;

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ...testData.mockInstructor,
          id: instructorId,
          full_name: instructorId === 8 ? 'Sarah Chen' : 'John Doe',
          rating: 4.9,
          total_reviews: 25,
          services: testData.mockInstructor.instruments,
          // Add availability_windows if needed
          availability_windows: [],
        }),
      });
    } else {
      await route.continue();
    }
  });
}

export async function mockAvailability(page: Page) {
  await page.route(
    'http://localhost:8000/public/instructors/*/availability*',
    async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          availability: testData.mockAvailability,
          instructor_id: 1,
          timezone: 'America/New_York',
        }),
      });
    }
  );

  // Also mock the /api/public/instructors endpoint for availability
  await page.route(
    'http://localhost:8000/api/public/instructors/*/availability*',
    async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          availability: testData.mockAvailability,
          instructor_id: 1,
          timezone: 'America/New_York',
        }),
      });
    }
  );
}

export async function mockBookingCreation(page: Page) {
  await page.route('http://localhost:8000/bookings', async (route: Route) => {
    if (route.request().method() === 'POST') {
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 123,
          instructorId: testData.mockInstructor.id,
          studentId: 1,
          date: testData.mockAvailability[0].date,
          startTime: testData.mockAvailability[0].startTime,
          endTime: testData.mockAvailability[0].endTime,
          status: 'confirmed',
          createdAt: new Date().toISOString(),
        }),
      });
    } else {
      await route.continue();
    }
  });
}

export async function mockAuthentication(page: Page) {
  // Mock login endpoint
  await page.route('http://localhost:8000/auth/login', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        access_token: 'mock_access_token',
        token_type: 'bearer',
        user: {
          id: 1,
          email: testData.student.email,
          firstName: testData.student.firstName,
          lastName: testData.student.lastName,
          role: 'student',
        },
      }),
    });
  });

  // Mock current user endpoint
  await page.route('http://localhost:8000/auth/me', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: 1,
        email: testData.student.email,
        firstName: testData.student.firstName,
        lastName: testData.student.lastName,
        role: 'student',
      }),
    });
  });
}

export async function setupAllMocks(page: Page, context: any = null) {
  // Use broader API pattern matching like in debug test
  const routeContext = context || page;

  await routeContext.route('**/*api*/**', async (route: Route) => {
    const url = route.request().url();
    console.log('Mock intercepting:', url);

    if (url.includes('/search/instructors')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          query: 'piano',
          parsed: {
            services: ['piano'],
            location: null,
          },
          total_found: 1,
          results: [
            {
              instructor: {
                id: 8,
                name: 'Sarah Chen',
                bio: 'Professional piano teacher with 10 years of experience',
                profile_image_url: null,
                location: 'Manhattan',
                areas_of_service: 'Manhattan, Brooklyn',
                years_experience: 10,
              },
              service: {
                id: 1,
                name: 'Piano',
                actual_min_price: 120,
                description: 'Professional piano lessons',
              },
              offering: {
                hourly_rate: 120,
                description: 'Professional piano lessons',
                duration_options: [30, 60, 90],
              },
              match_score: 0.95,
              availability_summary: 'Available this week',
              rating: 4.9,
              total_reviews: 25,
              location: 'Manhattan',
              distance_miles: null,
            },
          ],
        }),
      });
    } else if (url.includes('/public/instructors/') && !url.includes('search')) {
      const id = url.match(/instructors\/(\d+)/)?.[1] || '8';
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: parseInt(id),
          user_id: parseInt(id),
          full_name: 'Sarah Chen',
          hourly_rate: 120,
          bio: 'Professional pianist',
          services: ['Piano'],
          availability_windows: [],
        }),
      });
    } else if (url.includes('/availability')) {
      // Mock availability data
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          instructor_id: 8,
          instructor_name: 'Sarah Chen',
          availability_by_date: {
            '2025-08-01': {
              date: '2025-08-01',
              available_slots: [
                { start_time: '14:00', end_time: '15:00' },
                { start_time: '15:00', end_time: '16:00' },
                { start_time: '16:00', end_time: '17:00' },
              ],
              is_blackout: false,
            },
            '2025-08-02': {
              date: '2025-08-02',
              available_slots: [
                { start_time: '10:00', end_time: '11:00' },
                { start_time: '11:00', end_time: '12:00' },
                { start_time: '14:00', end_time: '15:00' },
              ],
              is_blackout: false,
            },
            '2025-08-08': {
              date: '2025-08-08',
              available_slots: [
                { start_time: '09:00', end_time: '10:00' },
                { start_time: '10:00', end_time: '11:00' },
                { start_time: '11:00', end_time: '12:00' },
              ],
              is_blackout: false,
            },
          },
          timezone: 'America/New_York',
          total_available_slots: 9,
          earliest_available_date: '2025-08-01',
        }),
      });
    } else if (url.includes('/auth/')) {
      await mockAuthentication(page);
      await route.continue();
    } else {
      await route.continue();
    }
  });
}
