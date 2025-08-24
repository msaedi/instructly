import { Page, Route } from '@playwright/test';
import { testData } from './test-data';

// Test ULIDs for consistent E2E testing (single source of truth)
import TEST_ULIDS from './ulids';
export { TEST_ULIDS };

export async function mockInstructorProfile(page: Page) {
  // Mock the instructor profile endpoint - matches /instructors/[id]
  await page.route('**/instructors/*', async (route: Route) => {
    const url = route.request().url();
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
      const responseId = isInstructor8 ? TEST_ULIDS.instructor8 : TEST_ULIDS.instructor1;
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
          areas_of_service: ['Upper West Side', 'Midtown'],
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

export async function mockAuthentication(routeContext: Page | any) {
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
        // Return successful login response
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
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
          // Return successful login response
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
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

  // Mock current user endpoint
  await routeContext.route('**/auth/me', async (route: Route) => {
    // Check if user has auth token
    const authHeader = route.request().headers()['authorization'];
    if (authHeader && authHeader.includes('Bearer')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
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
      // Not authenticated
      await route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({
          detail: 'Not authenticated'
        }),
      });
    }
  });
}

export async function setupAllMocks(page: Page, context: any = null) {
  // Use broader API pattern matching like in debug test
  const routeContext = context || page;

  // Set up authentication mocks first
  await mockAuthentication(routeContext);

  // Mock the search endpoint FIRST (before the general instructors handler)
  await routeContext.route('**/api/search/instructors**', async (route: Route) => {
    // Reduce noisy logs
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      headers: {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type'
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
              areas_of_service: 'Manhattan, Brooklyn',
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

  // Mock services catalog endpoints (consistent response shapes)
  await routeContext.route('**/services/catalog**', async (route: Route) => {
    const url = route.request().url();
    if (url.includes('top-per-category')) {
      // Return TopServicesResponse with categories array
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
    } else {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          { id: TEST_ULIDS.service1, name: 'Piano', category_id: '1' },
          { id: '01J5TESTSERV00000000000002', name: 'Guitar', category_id: '1' },
          { id: 97, name: 'Personal Training', category_id: 2 }
        ])
      });
    }
  });

  // First set up search-history mock (called on homepage load)
  await routeContext.route('**/search-history**', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
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

    // Check if this is our test instructor - be flexible with the ID format
    const isTestInstructor = instructorId === TEST_ULIDS.instructor8 ||
                            instructorId === '01J5TESTINSTR0000000000008' ||
                            instructorId === '8';
    // keep silent

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

    const formatDate = (date: Date) => date.toISOString().split('T')[0];

    // Always return a successful response with availability data
    // This prevents "Instructor not found" errors
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      headers: {
        'Access-Control-Allow-Origin': '*',
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
    const formatDate = (date: Date) => date.toISOString().split('T')[0];
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      headers: {
        'Access-Control-Allow-Origin': '*',
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
    if (url.includes(':3000')) {
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
          areas_of_service: ['Upper West Side', 'Midtown'],
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

  // Set up route handler for other API endpoints (register BEFORE generic instructors to avoid overrides)
  await routeContext.route('**/api/**', async (route: Route) => {
    const url = route.request().url();
    console.log('Mock intercepting api:', url);

    // Never override availability mocks
    if (url.includes('/api/public/instructors/') && url.includes('/availability')) {
      await route.continue();
      return;
    }

    // Mock payments endpoints to prevent 401s in tests
    if (url.includes('/api/payments/methods')) {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            { id: 'card_test_1', last4: '4242', brand: 'visa', is_default: true, created_at: new Date().toISOString() },
          ]),
        });
        return;
      }
      if (route.request().method() === 'POST') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ id: 'card_test_new', last4: '4242', brand: 'visa', is_default: false, created_at: new Date().toISOString() }),
        });
        return;
      }
    }
    if (url.includes('/api/payments/credits')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ available: 0, expires_at: null, pending: 0 }),
      });
      return;
    }

    if (url.includes('/api/payments/checkout')) {
      if (route.request().method() === 'POST') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            success: true,
            payment_intent_id: 'pi_test_123',
            status: 'succeeded',
            amount: 7200,
            application_fee: 0
          }),
        });
        return;
      }
    }

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

  // Mock booking creation to allow confirmation step to proceed
  await routeContext.route('**/bookings**', async (route: Route) => {
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

  // Also register page-level booking route to ensure interception regardless of context routing
  await page.route('**/bookings*', async (route: Route) => {
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
    const formatDate = (date: Date) => date.toISOString().split('T')[0];

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      headers: { 'Access-Control-Allow-Origin': '*' },
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
    const formatDate = (date: Date) => date.toISOString().split('T')[0];
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      headers: { 'Access-Control-Allow-Origin': '*' },
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
}
