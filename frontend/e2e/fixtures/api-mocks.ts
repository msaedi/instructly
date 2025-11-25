import { Page, Route } from '@playwright/test';
import { testData } from './test-data';

// Test ULIDs for consistent E2E testing (single source of truth)
import { TEST_ULIDS } from './ulids';
export { TEST_ULIDS };

export async function mockInstructorProfile(page: Page) {
  // Mock the instructor profile endpoint - matches /instructors/[id]
  await page.route('**/instructors/*', async (route: Route) => {
    const url = route.request().url();
    // Do NOT intercept frontend page navigations (Next.js route on :3100)
    if (url.includes('://localhost:3100') || url.includes(':3100')) {
      await route.continue();
      return;
    }
    // Handle /instructors/[id] but not availability or search endpoints
    if (!url.includes('/availability') && !url.includes('/search') && !url.includes('/services')) {
      // Extract instructor ID from URL
      const idMatch = url.match(/instructors\/([^\/]+)$/);
      const instructorIdStr = idMatch ? idMatch[1] : TEST_ULIDS.instructor1;
      console.log('Mock intercepting instructors API:', url);
      console.log('Extracted instructor ID:', instructorIdStr);

      // Determine which instructor profile to return based on ID
      // Only support ULID now - no backward compatibility with numeric IDs
      const isInstructor8 = instructorIdStr === TEST_ULIDS.instructor8;

      // Always use ULID in response - this is what the real API would return
      const userId = isInstructor8 ? TEST_ULIDS.user8 : TEST_ULIDS.user1;

      // Create the response without spreading testData.mockInstructor
      // to avoid any numeric ID conflicts
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          // Real API doesn't return 'id', only 'user_id'
          user_id: userId,
          user: {
            first_name: isInstructor8 ? 'Sarah' : 'John',
            last_initial: isInstructor8 ? 'C' : 'D',
            // No email for privacy
          },
          bio: 'Professional piano teacher with 10 years of experience',
          service_area_summary: 'Upper West Side, Midtown',
          service_area_boroughs: ['Manhattan'],
          service_area_neighborhoods: [
            {
              neighborhood_id: 'upper-west-side',
              name: 'Upper West Side',
              borough: 'Manhattan',
              ntacode: null,
            },
            {
              neighborhood_id: 'midtown',
              name: 'Midtown',
              borough: 'Manhattan',
              ntacode: null,
            },
          ],
          years_experience: 10,
          rating: 4.9,
          total_reviews: 25,
          services: [
            {
              id: TEST_ULIDS.service1,
              service_catalog_id: TEST_ULIDS.service1,
              name: 'Piano',  // Added 'name' field
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
  await page.route('**/api/v1/bookings', async (route: Route) => {
    if (route.request().method() === 'POST') {
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 123,
          instructorId: testData.mockInstructor.id,
          studentId: 1,
          date: testData.mockAvailability[0]?.date || '',
          startTime: testData.mockAvailability[0]?.startTime || '',
          endTime: testData.mockAvailability[0]?.endTime || '',
          status: 'confirmed',
          createdAt: new Date().toISOString(),
        }),
      });
    } else {
      await route.continue();
    }
  });
}

export async function mockAuthentication(routeContext: Page | { route: (pattern: string, handler: (route: Route) => Promise<void>) => Promise<void> }) {
  // Track auth state per test run (cookie is primary, this helps where cookies are flaky in headless)
  let isAuthenticated = false;

  // Mock login endpoint
  await routeContext.route('**/auth/login', async (route: Route) => {
    // For POST requests, check credentials if needed
    if (route.request().method() === 'POST') {
      // Parse form data or JSON based on content type
      const contentType = route.request().headers()['content-type'] || '';
      let email = '';
      let password = '';

      if (contentType.includes('application/x-www-form-urlencoded')) {
        // Parse URLSearchParams format (regular login)
        const formData = route.request().postData();
        if (formData) {
          const params = new URLSearchParams(formData);
          email = params.get('username') || ''; // Note: field is 'username' not 'email'
          password = params.get('password') || '';
          console.log('Login attempt (form data):', { email, password });
        }
      } else if (contentType.includes('application/json')) {
        // Parse JSON format (login with session)
        try {
          const postData = await route.request().postDataJSON();
          email = postData.email || postData.username || '';
          password = postData.password || '';
          console.log('Login attempt (JSON):', { email, password });
        } catch (e) {
          console.error('Failed to parse JSON login data:', e);
        }
      }

      // Check credentials - be lenient for test
      if ((email === 'john.smith@example.com' || email === 'test@example.com') &&
          (password === 'Test1234' || password === 'test123')) {
        // Return successful login response and simulate backend cookie
        isAuthenticated = true;
        const origin = route.request().headers()['origin'] || 'http://localhost:3100';
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          headers: {
            'Access-Control-Allow-Origin': origin,
            'Access-Control-Allow-Credentials': 'true',
            'Vary': 'Origin',
            // SameSite=Lax works for same-site (localhost:3100 -> localhost:8000)
            'Set-Cookie': 'access_token=mock_access_token_123456; Path=/; HttpOnly; SameSite=Lax'
          },
          body: JSON.stringify({
            access_token: 'mock_access_token_123456',
            token_type: 'bearer',
            user: {
              id: 1,
              email: 'john.smith@example.com',
              first_name: 'John',
              last_name: 'Smith',
              role: 'student',
              roles: ['student'],
              permissions: [],
              is_active: true,
              created_at: new Date().toISOString(),
              updated_at: new Date().toISOString()
            },
          }),
        });
      } else {
        // Return login failure
        console.log('Login failed - invalid credentials');
        await route.fulfill({
          status: 401,
          contentType: 'application/json',
          body: JSON.stringify({
            detail: 'Invalid email or password'
          }),
        });
      }
    } else {
      await route.fulfill({
        status: 405,
        body: 'Method not allowed'
      });
    }
  });

  // Mock login-with-session endpoint
  await routeContext.route('**/auth/login-with-session', async (route: Route) => {
    // For POST requests
    if (route.request().method() === 'POST') {
      // Parse JSON data
      try {
        const postData = await route.request().postDataJSON();
        const email = postData.email || '';
        const password = postData.password || '';
        const guestSessionId = postData.guest_session_id || '';
        console.log('Login with session attempt:', { email, guestSessionId });

        // Check credentials - be lenient for test
        if ((email === 'john.smith@example.com' || email === 'test@example.com') &&
            (password === 'Test1234' || password === 'test123')) {
          // Return successful login response and set cookie
          isAuthenticated = true;
          const origin = route.request().headers()['origin'] || 'http://localhost:3100';
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            headers: {
              'Access-Control-Allow-Origin': origin,
              'Access-Control-Allow-Credentials': 'true',
              'Vary': 'Origin',
              'Set-Cookie': 'access_token=mock_access_token_123456; Path=/; HttpOnly; SameSite=Lax'
            },
            body: JSON.stringify({
              access_token: 'mock_access_token_123456',
              token_type: 'bearer',
              user: {
                id: 1,
                email: 'john.smith@example.com',
                first_name: 'John',
                last_name: 'Smith',
                role: 'student',
                roles: ['student'],
                permissions: [],
                is_active: true,
                created_at: new Date().toISOString(),
                updated_at: new Date().toISOString()
              },
            }),
          });
        } else {
          // Return login failure
          console.log('Login with session failed - invalid credentials');
          await route.fulfill({
            status: 401,
            contentType: 'application/json',
            body: JSON.stringify({
              detail: 'Invalid email or password'
            }),
          });
        }
      } catch (e) {
        console.error('Failed to parse login-with-session data:', e);
        await route.fulfill({
          status: 400,
          contentType: 'application/json',
          body: JSON.stringify({
            detail: 'Invalid request data'
          }),
        });
      }
    } else {
      await route.fulfill({
        status: 405,
        body: 'Method not allowed'
      });
    }
  });

  // Mock current user endpoint - succeed only if cookie (or prior login) present
  await routeContext.route('**/auth/me', async (route: Route) => {
    const origin = route.request().headers()['origin'] || 'http://localhost:3100';
    const cookieHeader = route.request().headers()['cookie'] || '';
    const hasCookie = /(?:^|;\s*)access_token=/.test(cookieHeader);
    if (isAuthenticated || hasCookie) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        headers: {
          'Access-Control-Allow-Origin': origin,
          'Access-Control-Allow-Credentials': 'true',
          'Vary': 'Origin'
        },
        body: JSON.stringify({
          id: TEST_ULIDS.user1,
          email: 'john.smith@example.com',
          first_name: 'John',
          last_name: 'Smith',
          role: 'student',
          roles: ['student'],
          permissions: [],
          is_active: true,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString()
        }),
      });
    } else {
      await route.fulfill({
        status: 401,
        contentType: 'application/json',
        headers: {
          'Access-Control-Allow-Origin': origin,
          'Access-Control-Allow-Credentials': 'true',
          'Vary': 'Origin'
        },
        body: JSON.stringify({ detail: 'Not authenticated' }),
      });
    }
  });
}

export async function setupAllMocks(page: Page, context: { route: (pattern: string, handler: (route: Route) => Promise<void>) => Promise<void> } | null = null) {
  // Use broader API pattern matching like in debug test
  const routeContext = context || page;

  // Set up authentication mocks first
  await mockAuthentication(routeContext);

  // Ensure guest session bootstrap does not hit real backend (avoid CORS flakes)
  await routeContext.route('**/api/public/session/guest', async (route: Route) => {
    const req = route.request();
    const origin = req.headers()['origin'] || 'http://localhost:3100';
    if (req.method() === 'OPTIONS') {
      await route.fulfill({
        status: 204,
        headers: {
          'Access-Control-Allow-Origin': origin,
          'Access-Control-Allow-Credentials': 'true',
          'Access-Control-Allow-Methods': 'POST, OPTIONS',
          'Access-Control-Allow-Headers': 'Content-Type, X-Session-ID, X-Search-Origin, X-Guest-Session-ID, Authorization',
          'Vary': 'Origin'
        }
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      headers: {
        'Access-Control-Allow-Origin': origin,
        'Access-Control-Allow-Credentials': 'true',
        'Vary': 'Origin'
      },
      body: JSON.stringify({ ok: true })
    });
  });

  // Mock the search endpoint FIRST (before the general instructors handler)
  await routeContext.route('**/api/search/instructors**', async (route: Route) => {
    // Reduce noisy logs
    const origin = route.request().headers()['origin'] || 'http://localhost:3100';
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      headers: {
        'Access-Control-Allow-Origin': origin,
        'Access-Control-Allow-Credentials': 'true',
        'Access-Control-Allow-Methods': 'GET, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, X-Session-ID, X-Search-Origin, X-Guest-Session-ID, Authorization',
        'Vary': 'Origin'
      },
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
              id: TEST_ULIDS.instructor8,
              first_name: 'Sarah',
              last_initial: 'C',
              bio: 'Professional piano teacher with 10 years of experience',
              profile_image_url: null,
              location: 'Manhattan',
              service_area_summary: 'Manhattan, Brooklyn',
              service_area_boroughs: ['Manhattan', 'Brooklyn'],
              service_area_neighborhoods: [],
              years_experience: 10,
            },
            service: {
              id: TEST_ULIDS.service1,
              name: 'Piano',
              actual_min_price: 120,
              description: 'Professional piano lessons',
            },
            offering: {
              hourly_rate: 120,
              description: 'Professional piano lessons',
              duration_options: [30, 60, 90],
            },
            link: `/instructors/${TEST_ULIDS.instructor8}`,
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

  // Mock services catalog endpoints (consistent response shapes) - v1 API
  await routeContext.route('**/api/v1/services/catalog**', async (route: Route) => {
    const req = route.request();
    const url = req.url();
    const origin = req.headers()['origin'] || 'http://localhost:3100';
    if (req.method() === 'OPTIONS') {
      await route.fulfill({
        status: 204,
        headers: {
          'Access-Control-Allow-Origin': origin,
          'Access-Control-Allow-Credentials': 'true',
          'Access-Control-Allow-Methods': 'GET, OPTIONS',
          'Access-Control-Allow-Headers': 'Content-Type, X-Session-ID, X-Search-Origin, X-Guest-Session-ID, Authorization',
          'Vary': 'Origin'
        }
      });
      return;
    }
    if (url.includes('top-per-category')) {
      // Return TopServicesResponse with categories array
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        headers: {
          'Access-Control-Allow-Origin': origin,
          'Access-Control-Allow-Credentials': 'true',
          'Vary': 'Origin'
        },
        body: JSON.stringify({
          categories: [
            {
              id: 1,
              name: 'Music',
              slug: 'music',
              services: [
                { id: 1, name: 'Piano', slug: 'piano', demand_score: 90, active_instructors: 5, is_trending: false, display_order: 1 },
                { id: 2, name: 'Guitar', slug: 'guitar', demand_score: 70, active_instructors: 3, is_trending: true, display_order: 2 },
              ]
            },
            {
              id: 2,
              name: 'Fitness',
              slug: 'fitness',
              services: [
                { id: 97, name: 'Personal Training', slug: 'personal-training', demand_score: 85, active_instructors: 2, is_trending: true, display_order: 1 },
              ]
            }
          ]
        })
      });
      return;
    }
    if (url.includes('kids-available')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        headers: {
          'Access-Control-Allow-Origin': origin,
          'Access-Control-Allow-Credentials': 'true',
          'Vary': 'Origin'
        },
        body: JSON.stringify([
          { id: TEST_ULIDS.service1, name: 'Piano', slug: 'piano' }
        ])
      });
      return;
    }
    // Default services catalog list
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      headers: {
        'Access-Control-Allow-Origin': origin,
        'Access-Control-Allow-Credentials': 'true',
        'Vary': 'Origin'
      },
      body: JSON.stringify([
        { id: TEST_ULIDS.service1, name: 'Piano', category_id: '1' },
        { id: '01J5TESTSERV00000000000002', name: 'Guitar', category_id: '1' },
        { id: 97, name: 'Personal Training', category_id: 2 }
      ])
    });
  });

  // Mock service categories (homepage depends on this) - v1 API
  await routeContext.route('**/api/v1/services/categories', async (route: Route) => {
    const req = route.request();
    const origin = req.headers()['origin'] || 'http://localhost:3100';
    if (req.method() === 'OPTIONS') {
      await route.fulfill({
        status: 204,
        headers: {
          'Access-Control-Allow-Origin': origin,
          'Access-Control-Allow-Credentials': 'true',
          'Access-Control-Allow-Methods': 'GET, OPTIONS',
          'Access-Control-Allow-Headers': 'Content-Type, X-Session-ID, X-Search-Origin, X-Guest-Session-ID, Authorization',
          'Vary': 'Origin'
        }
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      headers: {
        'Access-Control-Allow-Origin': origin,
        'Access-Control-Allow-Credentials': 'true',
        'Vary': 'Origin'
      },
      body: JSON.stringify([
        {
          id: 1,
          name: 'Music',
          slug: 'music',
          subtitle: 'Instrument Voice Theory',
          description: 'Learn instruments',
          icon_name: 'music',
        },
        {
          id: 2,
          name: 'Languages',
          slug: 'language',
          subtitle: '',
          description: 'Learn new languages',
          icon_name: 'globe',
        },
      ]),
    });
  });

  // First set up search-history mock (called on homepage load)
  await routeContext.route('**/search-history**', async (route: Route) => {
    const req = route.request();
    const origin = req.headers()['origin'] || 'http://localhost:3100';
    if (req.method() === 'OPTIONS') {
      await route.fulfill({
        status: 204,
        headers: {
          'Access-Control-Allow-Origin': origin,
          'Access-Control-Allow-Credentials': 'true',
          'Access-Control-Allow-Methods': 'GET, OPTIONS',
          'Access-Control-Allow-Headers': 'Content-Type, X-Session-ID, X-Search-Origin, X-Guest-Session-ID, Authorization',
          'Vary': 'Origin'
        }
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      headers: {
        'Access-Control-Allow-Origin': origin,
        'Access-Control-Allow-Credentials': 'true',
        'Vary': 'Origin'
      },
      body: JSON.stringify([])
    });
  });

  // Mock availability endpoint for the alternative pattern
  await routeContext.route('**/availability/instructor/**', async (route: Route) => {

    // This is the format used by some other parts of the app
    // Always return successful availability data
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        instructor_id: TEST_ULIDS.instructor8,
        availability: []  // Simple empty response for this endpoint
      })
    });
  });

  // IMPORTANT: Make sure availability handlers run before any generic **/api/** handler
  // Match both /api/public/instructors and just /instructors availability endpoints
  await routeContext.route('**/api/public/instructors/*/availability**', async (route: Route) => {
    // Extract instructor ID from URL
    const currentUrl = route.request().url();
    const idMatch = currentUrl.match(/instructors\/([^\/\?]+)/i);
    const instructorId = idMatch ? idMatch[1] : TEST_ULIDS.instructor8;
    console.log('Extracted instructor ID for availability:', instructorId);


    // Use dynamic future dates for stability relative to today
    const base = new Date();
    base.setHours(0,0,0,0);
    const addDaysDyn = (offset: number) => {
      const d = new Date(base);
      d.setDate(base.getDate() + offset);
      return d;
    };
    const thu = addDaysDyn(1);
    const fri = addDaysDyn(2);
    const mon = addDaysDyn(5);
    const tue = addDaysDyn(6);

    const formatDate = (date: Date): string => {
      const parts = date.toISOString().split('T');
      return parts[0] || '';
    };

    // Always return a successful response with availability data
    // This prevents "Instructor not found" errors
    const origin = route.request().headers()['origin'] || 'http://localhost:3100';
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      headers: {
        'Access-Control-Allow-Origin': origin,
        'Access-Control-Allow-Credentials': 'true',
        'Vary': 'Origin'
      },
      body: JSON.stringify({
        instructor_id: TEST_ULIDS.instructor8,  // Always use the test ULID
        instructor_first_name: 'Sarah',
        instructor_last_initial: 'C',
        availability_by_date: {
          // Thursday slots
          [formatDate(thu)]: {
            date: formatDate(thu),
            available_slots: [
              { start_time: '10:00:00', end_time: '11:00:00' },
              { start_time: '14:00:00', end_time: '15:00:00' },
            ],
            is_blackout: false,
          },
          // Friday slots
          [formatDate(fri)]: {
            date: formatDate(fri),
            available_slots: [
              { start_time: '09:00:00', end_time: '10:00:00' },
              { start_time: '14:00:00', end_time: '15:00:00' },
              { start_time: '17:00:00', end_time: '18:00:00' },
            ],
            is_blackout: false,
          },
          // Monday slots
          [formatDate(mon)]: {
            date: formatDate(mon),
            available_slots: [
              { start_time: '08:00:00', end_time: '09:00:00' },
              { start_time: '09:00:00', end_time: '10:00:00' },
              { start_time: '10:00:00', end_time: '11:00:00' },
              { start_time: '14:00:00', end_time: '15:00:00' },
              { start_time: '17:00:00', end_time: '18:00:00' },
            ],
            is_blackout: false,
          },
          // Tuesday slots
          [formatDate(tue)]: {
            date: formatDate(tue),
            available_slots: [
              { start_time: '06:00:00', end_time: '07:00:00' },
              { start_time: '08:00:00', end_time: '09:00:00' },
              { start_time: '11:00:00', end_time: '12:00:00' },
              { start_time: '17:00:00', end_time: '18:00:00' },
            ],
            is_blackout: false,
          },
        },
      }),
    });
  });

  // Secondary catch-all for any other instructors availability patterns, but let the above take precedence
  await routeContext.route('**/instructors/*/availability**', async (route: Route) => {
    const url = route.request().url();
    console.log('Mock intercepting availability (fallback):', url);
    // Dynamic dates matching the handler above
    const base = new Date();
    base.setHours(0,0,0,0);
    const addDaysDyn = (offset: number) => {
      const d = new Date(base);
      d.setDate(base.getDate() + offset);
      return d;
    };
    const thu = addDaysDyn(1);
    const fri = addDaysDyn(2);
    const mon = addDaysDyn(5);
    const tue = addDaysDyn(6);
    const formatDate = (date: Date): string => {
      const parts = date.toISOString().split('T');
      return parts[0] || '';
    };
    const origin = route.request().headers()['origin'] || 'http://localhost:3100';
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      headers: {
        'Access-Control-Allow-Origin': origin,
        'Access-Control-Allow-Credentials': 'true',
        'Vary': 'Origin'
      },
      body: JSON.stringify({
        instructor_id: TEST_ULIDS.instructor8,
        instructor_first_name: 'Sarah',
        instructor_last_initial: 'C',
        availability_by_date: {
          [formatDate(thu)]: { date: formatDate(thu), available_slots: [
            { start_time: '10:00:00', end_time: '11:00:00' },
            { start_time: '14:00:00', end_time: '15:00:00' },
          ], is_blackout: false },
          [formatDate(fri)]: { date: formatDate(fri), available_slots: [
            { start_time: '09:00:00', end_time: '10:00:00' },
            { start_time: '14:00:00', end_time: '15:00:00' },
            { start_time: '17:00:00', end_time: '18:00:00' },
          ], is_blackout: false },
          [formatDate(mon)]: { date: formatDate(mon), available_slots: [
            { start_time: '08:00:00', end_time: '09:00:00' },
            { start_time: '09:00:00', end_time: '10:00:00' },
            { start_time: '10:00:00', end_time: '11:00:00' },
            { start_time: '14:00:00', end_time: '15:00:00' },
            { start_time: '17:00:00', end_time: '18:00:00' },
          ], is_blackout: false },
          [formatDate(tue)]: { date: formatDate(tue), available_slots: [
            { start_time: '06:00:00', end_time: '07:00:00' },
            { start_time: '08:00:00', end_time: '09:00:00' },
            { start_time: '11:00:00', end_time: '12:00:00' },
            { start_time: '17:00:00', end_time: '18:00:00' },
          ], is_blackout: false },
        },
      }),
    });
  });

  // Set up route handler for instructor API endpoints
  // Only match API calls (port 8000 or /api prefix), not frontend routes (port 3000)
  await routeContext.route('**/instructors/**', async (route: Route) => {
    const url = route.request().url();

    // Skip frontend page routes (port 3000)
    if (url.includes(':3000') || url.includes(':3100')) {
      await route.continue();
      return;
    }

    console.log('Mock intercepting instructors API:', url);

    // Handle instructor profile API endpoint - ULID format only
    if (url.match(/\/instructors\/[0-9A-Z]{26}$/i) && !url.includes('/availability') && !url.includes('/search')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          // Always return our canonical test instructor to keep tests stable
          user_id: TEST_ULIDS.user8,
          user: {
            first_name: 'Sarah',
            last_initial: 'C',
          },
          bio: 'Professional piano teacher with 10 years of experience',
          service_area_summary: 'Upper West Side, Midtown',
          service_area_boroughs: ['Manhattan'],
          service_area_neighborhoods: [
            {
              neighborhood_id: 'upper-west-side',
              name: 'Upper West Side',
              borough: 'Manhattan',
              ntacode: null,
            },
            {
              neighborhood_id: 'midtown',
              name: 'Midtown',
              borough: 'Manhattan',
              ntacode: null,
            },
          ],
          years_experience: 10,
          rating: 4.9,
          total_reviews: 127,
          services: [
            {
              id: TEST_ULIDS.service1,
              service_catalog_id: TEST_ULIDS.service1,
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
    } else if (url.includes('/auth/')) {
      // Auth is already handled, just continue
      await route.continue();
    } else {
      await route.continue();
    }
  });

  // NOTE: Removed generic '**/api/**' catch-all to avoid double-handling routes.
  // Specific mocks above handle needed endpoints; others will fall through to network.

  // Mock v1 booking creation to allow confirmation step to proceed
  await routeContext.route('**/api/v1/bookings**', async (route: Route) => {
    const req = route.request();
    if (req.method() === 'POST') {
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'BK_TEST_1',
          status: 'confirmed',
          instructor_id: TEST_ULIDS.instructor8,
          student_id: TEST_ULIDS.user1,
          booking_date: new Date().toISOString().split('T')[0],
          start_time: '10:00',
          end_time: '11:00',
          total_price: 72,
        }),
      });
      return;
    }
    if (req.method() === 'POST' && req.url().includes('/cancel')) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true }) });
      return;
    }
    await route.continue();
  });

  // Also register page-level v1 booking route to ensure interception regardless of context routing
  await page.route('**/api/v1/bookings*', async (route: Route) => {
    const req = route.request();
    if (req.method() === 'POST') {
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'BK_TEST_2',
          status: 'confirmed',
          instructor_id: TEST_ULIDS.instructor8,
          student_id: TEST_ULIDS.user1,
          booking_date: new Date().toISOString().split('T')[0],
          start_time: '10:00',
          end_time: '11:00',
          total_price: 72,
        }),
      });
      return;
    }
    await route.continue();
  });

  // Set up route handler for services endpoints - v1 API
  await routeContext.route('**/api/v1/services/**', async (route: Route) => {
    const req = route.request();
    const url = req.url();
    const origin = req.headers()['origin'] || 'http://localhost:3100';
    if (req.method() === 'OPTIONS') {
      await route.fulfill({
        status: 204,
        headers: {
          'Access-Control-Allow-Origin': origin,
          'Access-Control-Allow-Credentials': 'true',
          'Access-Control-Allow-Methods': 'GET, OPTIONS',
          'Access-Control-Allow-Headers': 'Content-Type, X-Session-ID, X-Search-Origin, X-Guest-Session-ID, Authorization',
          'Vary': 'Origin'
        }
      });
      return;
    }
    console.log('Mock intercepting services:', url);
    if (url.includes('/services/catalog/top-per-category')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        headers: { 'Access-Control-Allow-Origin': origin, 'Access-Control-Allow-Credentials': 'true', 'Vary': 'Origin' },
        body: JSON.stringify({
          categories: [
            { id: 1, name: 'Music', slug: 'music', services: [ { id: 1, name: 'Piano', slug: 'piano', min_price: 75, instructor_count: 5 } ] }
          ]
        })
      });
      return;
    }
    if (url.includes('/services/catalog/kids-available')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        headers: { 'Access-Control-Allow-Origin': origin, 'Access-Control-Allow-Credentials': 'true', 'Vary': 'Origin' },
        body: JSON.stringify([ { id: TEST_ULIDS.service1, name: 'Piano', slug: 'piano' } ])
      });
      return;
    }
    if (url.includes('/services/categories')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        headers: { 'Access-Control-Allow-Origin': origin, 'Access-Control-Allow-Credentials': 'true', 'Vary': 'Origin' },
        body: JSON.stringify([
          { id: 1, name: 'Music', slug: 'music', subtitle: 'Instrument Voice Theory', description: 'Learn instruments', icon_name: 'music' },
          { id: 2, name: 'Languages', slug: 'language', subtitle: '', description: 'Learn new languages', icon_name: 'globe' },
        ])
      });
      return;
    }
    if (url.includes('/services/catalog')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        headers: { 'Access-Control-Allow-Origin': origin, 'Access-Control-Allow-Credentials': 'true', 'Vary': 'Origin' },
        body: JSON.stringify([
          { id: 1, name: 'Piano', slug: 'piano', description: 'Learn to play the piano', category_id: 1 }
        ])
      });
      return;
    }
    await route.continue();
  });

  // Re-register availability mocks LAST so they win when multiple handlers match
  await routeContext.route('**/api/public/instructors/*/availability**', async (route: Route) => {
    const currentUrl = route.request().url();
    const idMatch = currentUrl.match(/instructors\/([^\/\?]+)/i);
    const instructorId = idMatch ? idMatch[1] : TEST_ULIDS.instructor8;

    const base = new Date();
    base.setHours(0,0,0,0);
    const addDaysDyn = (offset: number) => {
      const d = new Date(base);
      d.setDate(base.getDate() + offset);
      return d;
    };
    const thu = addDaysDyn(1);
    const fri = addDaysDyn(2);
    const mon = addDaysDyn(5);
    const tue = addDaysDyn(6);
    const formatDate = (date: Date): string => {
      const parts = date.toISOString().split('T');
      return parts[0] || '';
    };

    const origin = route.request().headers()['origin'] || 'http://localhost:3100';
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      headers: {
        'Access-Control-Allow-Origin': origin,
        'Access-Control-Allow-Credentials': 'true',
        'Vary': 'Origin'
      },
      body: JSON.stringify({
        instructor_id: instructorId,
        instructor_first_name: 'Sarah',
        instructor_last_initial: 'C',
        availability_by_date: {
          [formatDate(thu)]: { date: formatDate(thu), available_slots: [
            { start_time: '10:00', end_time: '11:00' },
            { start_time: '14:00', end_time: '15:00' },
          ], is_blackout: false },
          [formatDate(fri)]: { date: formatDate(fri), available_slots: [
            { start_time: '09:00', end_time: '10:00' },
            { start_time: '14:00', end_time: '15:00' },
            { start_time: '17:00', end_time: '18:00' },
          ], is_blackout: false },
          [formatDate(mon)]: { date: formatDate(mon), available_slots: [
            { start_time: '08:00', end_time: '09:00' },
            { start_time: '09:00', end_time: '10:00' },
            { start_time: '10:00', end_time: '11:00' },
            { start_time: '14:00', end_time: '15:00' },
            { start_time: '17:00', end_time: '18:00' },
          ], is_blackout: false },
          [formatDate(tue)]: { date: formatDate(tue), available_slots: [
            { start_time: '06:00', end_time: '07:00' },
            { start_time: '08:00', end_time: '09:00' },
            { start_time: '11:00', end_time: '12:00' },
            { start_time: '17:00', end_time: '18:00' },
          ], is_blackout: false },
        },
      }),
    });
  });

  await routeContext.route('**/instructors/*/availability**', async (route: Route) => {
    const base = new Date();
    base.setHours(0,0,0,0);
    const addDaysDyn = (offset: number) => {
      const d = new Date(base);
      d.setDate(base.getDate() + offset);
      return d;
    };
    const thu = addDaysDyn(1);
    const fri = addDaysDyn(2);
    const mon = addDaysDyn(5);
    const tue = addDaysDyn(6);
    const formatDate = (date: Date): string => {
      const parts = date.toISOString().split('T');
      return parts[0] || '';
    };
    const origin = route.request().headers()['origin'] || 'http://localhost:3100';
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      headers: {
        'Access-Control-Allow-Origin': origin,
        'Access-Control-Allow-Credentials': 'true',
        'Vary': 'Origin'
      },
      body: JSON.stringify({
        instructor_id: TEST_ULIDS.instructor8,
        instructor_first_name: 'Sarah',
        instructor_last_initial: 'C',
        availability_by_date: {
          [formatDate(thu)]: { date: formatDate(thu), available_slots: [
            { start_time: '10:00', end_time: '11:00' },
            { start_time: '14:00', end_time: '15:00' },
          ], is_blackout: false },
          [formatDate(fri)]: { date: formatDate(fri), available_slots: [
            { start_time: '09:00', end_time: '10:00' },
            { start_time: '14:00', end_time: '15:00' },
            { start_time: '17:00', end_time: '18:00' },
          ], is_blackout: false },
          [formatDate(mon)]: { date: formatDate(mon), available_slots: [
            { start_time: '08:00', end_time: '09:00' },
            { start_time: '09:00', end_time: '10:00' },
            { start_time: '10:00', end_time: '11:00' },
            { start_time: '14:00', end_time: '15:00' },
            { start_time: '17:00', end_time: '18:00' },
          ], is_blackout: false },
          [formatDate(tue)]: { date: formatDate(tue), available_slots: [
            { start_time: '06:00', end_time: '07:00' },
            { start_time: '08:00', end_time: '09:00' },
            { start_time: '11:00', end_time: '12:00' },
            { start_time: '17:00', end_time: '18:00' },
          ], is_blackout: false },
        },
      }),
    });
  });

  // Reviews endpoints (ratings, recent, search-rating)
  await routeContext.route('**/api/v1/reviews/instructor/**', async (route: Route) => {
    const url = route.request().url();
    const origin = route.request().headers()['origin'] || 'http://localhost:3100';
    if (url.includes('/ratings')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        headers: { 'Access-Control-Allow-Origin': origin, 'Access-Control-Allow-Credentials': 'true', 'Vary': 'Origin' },
        body: JSON.stringify({
          overall: { rating: 4.9, total_reviews: 127, display_rating: '4.9' },
          by_service: [ { instructor_service_id: TEST_ULIDS.service1, rating: 4.9, review_count: 127 } ],
          confidence_level: 'trusted'
        })
      });
      return;
    }
    if (url.includes('/recent')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        headers: { 'Access-Control-Allow-Origin': origin, 'Access-Control-Allow-Credentials': 'true', 'Vary': 'Origin' },
        body: JSON.stringify({ reviews: [], total: 0, page: 1, per_page: 12, has_next: false, has_prev: false })
      });
      return;
    }
    if (url.includes('/search-rating')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        headers: { 'Access-Control-Allow-Origin': origin, 'Access-Control-Allow-Credentials': 'true', 'Vary': 'Origin' },
        body: JSON.stringify({ primary_rating: 4.9, review_count: 127, is_service_specific: true })
      });
      return;
    }
    await route.continue();
  });

  // Address coverage bulk
  await routeContext.route('**/api/addresses/coverage/bulk**', async (route: Route) => {
    const origin = route.request().headers()['origin'] || 'http://localhost:3100';
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      headers: { 'Access-Control-Allow-Origin': origin, 'Access-Control-Allow-Credentials': 'true', 'Vary': 'Origin' },
      body: JSON.stringify({ results: [] })
    });
  });
}
