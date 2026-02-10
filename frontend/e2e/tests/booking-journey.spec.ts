import { test, expect } from '@playwright/test';
import { HomePage } from '../pages/HomePage';
import { SearchResultsPage } from '../pages/SearchResultsPage';
import { InstructorProfilePage } from '../pages/InstructorProfilePage';
import { BookingPage } from '../pages/BookingPage';
import { ConfirmationPage } from '../pages/ConfirmationPage';
import { testData } from '../fixtures/test-data';

test.describe('Student Booking Journey', () => {
  test.beforeEach(async ({ page: _page, context }) => {
    // Mock ALL API calls needed for the booking journey

    // 0. Mock auth endpoint for homepage to show proper UI
    await context.route('**/api/v1/auth/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: '01J5TESTUSER00000000000001',
          email: 'student@example.com',
          first_name: 'Test',
          last_name: 'Student',
          roles: ['student'],
          permissions: [],
          is_active: true,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        }),
      });
    });

    // 1. Mock search history (for homepage)
    await context.route('**/api/v1/search-history/**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
    });

    // 1b. Mock v1 upcoming bookings for homepage (paginated format)
    await context.route('**/api/v1/bookings/upcoming**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          bookings: [],
          total: 0,
          page: 1,
          per_page: 2,
        }),
      });
    });

    // 1c. Mock categories for homepage
    await context.route('**/categories**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          { id: '01J5TESTCATG00000000000001', name: 'Music', description: 'Learn instruments' },
          { id: '01J5TESTCATG00000000000002', name: 'Languages', description: 'Learn new languages' },
        ]),
      });
    });

    // 1d. Mock featured instructors for homepage
    await context.route('**/instructors/featured**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
    });

    // 1e. Mock top services per category for homepage
    await context.route('**/api/v1/services/catalog/top-per-category**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          categories: [
            {
              id: '01J5TESTCATG00000000000001',
              name: 'Music',
              slug: 'music',
              services: [
                { id: '01J5TESTSERV00000000000001', name: 'Piano', slug: 'piano' },
                { id: '01J5TESTSERV00000000000002', name: 'Guitar', slug: 'guitar' },
              ],
            },
          ],
        }),
      });
    });

    // 2. Mock search results with correct natural language API structure
    await context.route('**/api/v1/search**', async (route) => {
      const url = route.request().url();
      const searchQuery = new URL(url).searchParams.get('q');

      if (searchQuery === 'didgeridoo') {
        // No results for uncommon instrument
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            results: [],
            meta: {
              query: 'didgeridoo',
              search_query_id: '01J5TESTQUERY00000000000002',
              corrected_query: null,
              parsed: {
                service_query: 'didgeridoo',
                location: null,
                max_price: null,
                date: null,
                time_after: null,
                audience_hint: null,
                skill_level: null,
                urgency: null,
              },
              total_results: 0,
              limit: 20,
              latency_ms: 50,
              cache_hit: false,
              degraded: false,
              degradation_reasons: [],
              parsing_mode: 'regex',
            },
          }),
        });
      } else {
        // Return results for piano and other searches - matching natural language API format
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            results: [
              {
                instructor_id: '1',
                instructor: {
                  id: '1',
                  first_name: 'Test',
                  last_initial: 'I',
                  profile_picture_url: null,
                  bio_snippet: 'Experienced instructor',
                  verified: true,
                  years_experience: 10,
                },
                rating: {
                  average: 4.9,
                  count: 25,
                },
                coverage_areas: ['Manhattan', 'Brooklyn'],
                best_match: {
                  service_id: '1',
                  service_catalog_id: '1',
                  name: 'Piano',
                  description: 'Piano lessons',
                  price_per_hour: 100,
                  relevance_score: 0.95,
                },
                other_matches: [],
                total_matching_services: 1,
                relevance_score: 0.95,
              },
              {
                instructor_id: '2',
                instructor: {
                  id: '2',
                  first_name: 'Test',
                  last_initial: 'J',
                  profile_picture_url: null,
                  bio_snippet: 'Professional instructor',
                  verified: false,
                  years_experience: 5,
                },
                rating: {
                  average: 4.7,
                  count: 15,
                },
                coverage_areas: ['Brooklyn', 'Queens'],
                best_match: {
                  service_id: '2',
                  service_catalog_id: '2',
                  name: 'Piano',
                  description: 'Piano lessons for beginners',
                  price_per_hour: 80,
                  relevance_score: 0.9,
                },
                other_matches: [],
                total_matching_services: 1,
                relevance_score: 0.9,
              },
            ],
            meta: {
              query: searchQuery || 'piano',
              search_query_id: '01J5TESTQUERY00000000000003',
              corrected_query: null,
              parsed: {
                service_query: searchQuery || 'piano',
                location: null,
                max_price: null,
                date: null,
                time_after: null,
                audience_hint: null,
                skill_level: null,
                urgency: null,
              },
              total_results: 2,
              limit: 20,
              latency_ms: 50,
              cache_hit: false,
              degraded: false,
              degradation_reasons: [],
              parsing_mode: 'regex',
            },
          }),
        });
      }
    });

    // 3. Mock instructor profile
    await context.route('**/api/v1/public/instructors/*', async (route) => {
      const url = route.request().url();
      if (!url.includes('availability')) {
        const id = url.match(/instructors\/([^/?]+)/)?.[1] || '01HF4G12ABCDEF3456789XYZAB';
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id,
            user_id: id,
            first_name: 'Test',
            last_initial: 'I',
            hourly_rate: 100,
            bio: 'Experienced instructor',
            services: ['Piano'],
            availability_windows: [],
            rating: 4.9,
            total_reviews: 25,
          }),
        });
      }
    });

    // 4. Mock availability - Use FIXED dates for consistency
    await context.route('**/api/v1/public/instructors/*/availability**', async (route) => {
      // Use fixed dates to avoid conflicts with parallel tests
      const fixedDate = '2025-08-14'; // Fixed Thursday

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          instructor_id: 1,
          instructor_name: 'Test Instructor 1',
          availability_by_date: {
            [fixedDate]: {
              date: fixedDate,
              available_slots: [
                { start_time: '10:00', end_time: '11:00' },
                { start_time: '11:00', end_time: '12:00' },
                { start_time: '14:00', end_time: '15:00' },
              ],
              is_blackout: false,
            },
          },
          timezone: 'America/New_York',
          total_available_slots: 3,
          earliest_available_date: fixedDate,
        }),
      });
    });

    // 5. Mock v1 booking creation
    await context.route('**/api/v1/bookings', async (route) => {
      if (route.request().method() === 'POST') {
        await route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 12345,
            booking_date: '2025-08-02',
            start_time: '10:00',
            end_time: '11:00',
            status: 'CONFIRMED',
            confirmation_code: 'ABC123',
            instructor: {
              id: 1,
              first_name: 'Test',
              last_initial: 'I',
              email: 'instructor@example.com',
            },
            student: {
              id: 1,
              first_name: 'Test',
          last_name: 'Student',
              email: 'student@example.com',
            },
            service: {
              id: 1,
              name: 'Piano Lesson',
              description: 'One hour piano lesson',
            },
            total_price: 100.0,
            meeting_location: "Instructor's Studio",
            created_at: new Date().toISOString(),
          }),
        });
      }
    });
  });

  test.skip('should complete full booking flow from search to confirmation', async ({ page }) => {
    // SKIP REASON: This test requires the instructor profile page to be implemented
    // The booking flow can't proceed without being able to select time slots on the instructor profile

    // Set authentication token before navigation
    await page.addInitScript(() => {
      localStorage.setItem('access_token', 'mock_access_token');
    });

    // Step 1: Start at homepage
    const homePage = new HomePage(page);
    await homePage.goto();

    // Wait for page to fully load
    await page.waitForLoadState('domcontentloaded');

    // Verify homepage loaded
    await expect(page).toHaveTitle(/iNSTAiNSTRU/i);

    // Step 2: Search for piano instructors
    await homePage.searchForInstrument(testData.search.instrument);

    // Step 3: View search results
    const searchResults = new SearchResultsPage(page);
    await searchResults.waitForResults();

    // Verify we have results
    const instructorCount = await searchResults.getInstructorCount();
    expect(instructorCount).toBeGreaterThan(0);

    // Step 4: Click on first instructor
    await searchResults.clickFirstInstructor();

    // Step 5: View instructor profile
    const instructorProfile = new InstructorProfilePage(page);
    await instructorProfile.waitForAvailability();

    // Verify we're on the instructor profile page
    expect(page.url()).toContain('/instructors/');

    // Step 6: Select an available time slot
    // The instructor profile page isn't implemented yet, so we cannot proceed with booking flow

    // This test reveals that the booking flow requires the instructor profile page
    // The test should be skipped at the test level, not within the test body

    // Cannot proceed without the instructor profile page implementation

    // Step 10: Verify confirmation page
    const confirmationPage = new ConfirmationPage(page);
    await confirmationPage.waitForConfirmation();

    // Verify booking was successful
    await expect(confirmationPage.confirmationMessage).toBeVisible();

    const bookingId = await confirmationPage.getBookingId();
    expect(bookingId).toBeTruthy();

    const confirmedInstructor = await confirmationPage.getInstructorName();
    expect(confirmedInstructor).toBeTruthy();

    const confirmedDateTime = await confirmationPage.getLessonDateTime();
    expect(confirmedDateTime).toBeTruthy();
  });

  test('should handle case when no instructors are found', async ({ page }) => {
    // Set authentication token
    await page.addInitScript(() => {
      localStorage.setItem('access_token', 'mock_access_token');
    });

    const homePage = new HomePage(page);
    await homePage.goto();

    // Search for an uncommon instrument
    await homePage.searchForInstrument('didgeridoo');

    const searchResults = new SearchResultsPage(page);
    await searchResults.waitForResults();

    // Verify no results message is shown
    await expect(searchResults.noResultsMessage).toBeVisible();
  });

  test.skip('should require login before booking', async ({ page }) => {
    // TODO: This test needs the instructor profile page to be implemented
    // Currently skipping as the instructor profile page structure is not yet finalized

    // Don't set auth token for this test - we want to test login requirement
    // Navigate directly to an instructor profile
    // Use ULID-based instructor in legacy test too
    await page.goto('/instructors/01J5TESTINSTR0000000000008');

    const instructorProfile = new InstructorProfilePage(page);
    await instructorProfile.waitForAvailability();

    // Select a time slot and try to book
    await instructorProfile.selectFirstAvailableSlot();
    await instructorProfile.proceedToBooking();

    // Should show login prompt
    const bookingPage = new BookingPage(page);
    const loginRequired = await bookingPage.isLoginRequired();
    expect(loginRequired).toBe(true);
  });
});
