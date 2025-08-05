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
  // Mock the instructor profile endpoint - matches /instructors/[id]
  await page.route('**/instructors/*', async (route: Route) => {
    const url = route.request().url();
    // Handle /instructors/[id] but not availability or search endpoints
    if (!url.includes('/availability') && !url.includes('/search') && !url.includes('/services')) {
      // Extract instructor ID from URL
      const idMatch = url.match(/instructors\/(\d+)/);
      const instructorId = idMatch ? parseInt(idMatch[1]) : 1;

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ...testData.mockInstructor,
          id: instructorId,
          user_id: instructorId,
          user: {
            full_name: instructorId === 8 ? 'Sarah Chen' : 'John Doe',
            email: 'instructor@example.com'
          },
          bio: 'Professional piano teacher with 10 years of experience',
          areas_of_service: ['Upper West Side', 'Midtown'],
          years_experience: 10,
          rating: 4.9,
          total_reviews: 25,
          services: [
            {
              id: 1,
              skill: 'Piano',
              hourly_rate: 120,
              description: 'Professional piano lessons',
              duration_options: [30, 45, 60, 90],
              is_active: true
            }
          ],
          background_check_completed: true,
          is_verified: true,
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
  // Mock login endpoint - handle both with and without /api prefix
  await page.route('**/auth/login', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        access_token: 'mock_access_token',
        token_type: 'bearer',
        user: {
          id: 1,
          email: 'john.smith@example.com',
          full_name: 'John Smith',
          firstName: 'John',
          lastName: 'Smith',
          role: 'student',
        },
      }),
    });
  });

  // Mock current user endpoint
  await page.route('**/auth/me', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: 1,
        email: 'john.smith@example.com',
        full_name: 'John Smith',
        firstName: 'John',
        lastName: 'Smith',
        role: 'student',
      }),
    });
  });
}

export async function setupAllMocks(page: Page, context: any = null) {
  // Use broader API pattern matching like in debug test
  const routeContext = context || page;

  // Set up authentication mocks first
  await mockAuthentication(routeContext);

  // First set up search-history mock (called on homepage load)
  await routeContext.route('**/search-history**', async (route: Route) => {
    console.log('Mock intercepting search-history:', route.request().url());
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([])
    });
  });

  // Set up route handler for instructor API endpoints
  // Only match API calls (port 8000 or /api prefix), not frontend routes (port 3000)
  await routeContext.route('**/instructors/**', async (route: Route) => {
    const url = route.request().url();

    // Skip frontend page routes (port 3000)
    if (url.includes(':3000')) {
      await route.continue();
      return;
    }

    console.log('Mock intercepting instructors API:', url);

    // Handle instructor profile API endpoint (must come before other instructor checks)
    if (url.match(/\/instructors\/\d+$/) && !url.includes('/availability') && !url.includes('/search')) {
      const idMatch = url.match(/instructors\/(\d+)/);
      const instructorId = idMatch ? parseInt(idMatch[1]) : 1;

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: instructorId,
          user_id: instructorId,
          user: {
            full_name: instructorId === 8 ? 'Sarah Chen' : 'John Doe',
            email: 'instructor@example.com'
          },
          bio: 'Professional piano teacher with 10 years of experience',
          areas_of_service: ['Upper West Side', 'Midtown'],
          years_experience: 10,
          rating: 4.9,
          total_reviews: 25,
          services: [
            {
              id: 1,
              service_catalog_id: 1,
              name: 'Piano',
              skill: 'Piano',
              hourly_rate: 120,
              description: 'Professional piano lessons',
              duration_options: [30, 45, 60, 90],
              is_active: true
            }
          ],
          background_check_completed: true,
          is_verified: true,
          verified: true,
          availability_windows: [],
        }),
      });
    } else if (url.includes('/search')) {
      // Handle search endpoint
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
    } else if (url.includes('/services/catalog')) {
      // Mock catalog services
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: 1,
            name: 'Piano',
            slug: 'piano',
            description: 'Learn to play the piano',
            category_id: 1
          }
        ])
      });
    } else if (url.includes('/availability')) {
      // Mock availability data with dynamic dates (starting from tomorrow)
      const tomorrow = new Date();
      tomorrow.setDate(tomorrow.getDate() + 1);
      const dayAfter = new Date();
      dayAfter.setDate(dayAfter.getDate() + 2);
      const nextWeek = new Date();
      nextWeek.setDate(nextWeek.getDate() + 7);

      const formatDate = (date: Date) => date.toISOString().split('T')[0];

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          instructor_id: 8,
          instructor_name: 'Sarah Chen',
          availability_by_date: {
            [formatDate(tomorrow)]: {
              date: formatDate(tomorrow),
              available_slots: [
                { start_time: '14:00', end_time: '15:00' },
                { start_time: '15:00', end_time: '16:00' },
                { start_time: '16:00', end_time: '17:00' },
              ],
              is_blackout: false,
            },
            [formatDate(dayAfter)]: {
              date: formatDate(dayAfter),
              available_slots: [
                { start_time: '10:00', end_time: '11:00' },
                { start_time: '11:00', end_time: '12:00' },
                { start_time: '14:00', end_time: '15:00' },
              ],
              is_blackout: false,
            },
            [formatDate(nextWeek)]: {
              date: formatDate(nextWeek),
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
          earliest_available_date: formatDate(tomorrow),
        }),
      });
    } else if (url.includes('/auth/')) {
      // Auth is already handled, just continue
      await route.continue();
    } else {
      await route.continue();
    }
  });

  // Set up route handler for other API endpoints
  await routeContext.route('**/api/**', async (route: Route) => {
    const url = route.request().url();
    console.log('Mock intercepting api:', url);

    if (url.includes('/search-history/interaction')) {
      // Mock search interaction tracking
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true })
      });
    } else if (url.includes('/search-history')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([])
      });
    } else if (url.includes('/auth/')) {
      // Auth is already handled, just continue
      await route.continue();
    } else {
      await route.continue();
    }
  });

  // Set up route handler for services endpoints
  await routeContext.route('**/services/**', async (route: Route) => {
    const url = route.request().url();
    console.log('Mock intercepting services:', url);

    if (url.includes('/services/catalog/top-per-category')) {
      // Mock top services per category for homepage
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          categories: [
            {
              id: 1,
              name: 'Music',
              slug: 'music',
              services: [
                {
                  id: 1,
                  name: 'Piano',
                  slug: 'piano',
                  min_price: 75,
                  instructor_count: 5
                }
              ]
            }
          ]
        })
      });
    } else if (url.includes('/services/catalog')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: 1,
            name: 'Piano',
            slug: 'piano',
            description: 'Learn to play the piano',
            category_id: 1
          }
        ])
      });
    } else {
      await route.continue();
    }
  });
}
