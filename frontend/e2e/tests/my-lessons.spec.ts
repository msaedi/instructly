import { test, expect, Page } from '@playwright/test';

// Test data
const studentCredentials = {
  email: 'student@example.com',
  password: 'password123',
};

const upcomingLesson = {
  instructor: 'John Doe',
  service: 'Mathematics',
  date: 'Wed Dec 25',
  time: '2:00pm',
  price: '$60.00',
};

const completedLesson = {
  instructor: 'Jane Smith',
  service: 'Physics',
  date: 'Dec 20, 2024',
  time: '10:00 AM - 11:00 AM',
  price: '$80.00',
};

// Mock all necessary APIs before any page navigation
async function setupMocksAndAuth(page: Page) {
  // Set auth token in localStorage BEFORE any navigation
  await page.addInitScript(() => {
    localStorage.setItem('access_token', 'mock_access_token');
  });

  // Mock auth endpoint
  await page.route('http://localhost:8000/auth/me', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: 1,
        email: studentCredentials.email,
        full_name: 'Test Student',
        roles: ['student'],
        permissions: [],
        is_active: true,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      }),
    });
  });

  // Mock search history - this is required for homepage
  await page.route('http://localhost:8000/api/search-history*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    });
  });

  // Mock upcoming lessons for homepage (returns array directly)
  await page.route('http://localhost:8000/bookings/upcoming*limit=2*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          id: 1,
          instructor_name: upcomingLesson.instructor,
          service_name: upcomingLesson.service,
          booking_date: '2024-12-25',
          start_time: '14:00:00',
          end_time: '15:00:00',
          price: 60,
          status: 'confirmed',
          location_type: 'online',
          location_details: 'Zoom meeting',
        },
      ]),
    });
  });

  // Mock upcoming lessons for My Lessons page (returns object with bookings array)
  await page.route('http://localhost:8000/bookings/*', async (route) => {
    const url = new URL(route.request().url());

    // Check if this is a detail request
    const pathParts = url.pathname.split('/');
    const bookingId = pathParts[pathParts.length - 1];

    if (bookingId && /^\d+$/.test(bookingId)) {
      // This is a detail request for a specific booking
      const bookingDetails = {
        '1': {
          id: 1,
          instructor: {
            id: 1,
            full_name: upcomingLesson.instructor,
            email: 'john.doe@example.com',
            rating: 4.8,
            total_reviews: 156,
            bio: 'Experienced mathematics teacher with 10+ years of experience.',
          },
          service_name: upcomingLesson.service,
          booking_date: '2024-12-25',
          start_time: '14:00:00',
          end_time: '15:00:00',
          price: 60,
          status: 'confirmed',
          location_type: 'online',
          location_details: 'Zoom meeting',
          meeting_link: 'https://zoom.us/j/123456789',
          notes: 'Looking forward to our lesson!',
          student: {
            id: 1,
            full_name: 'Test Student',
            email: studentCredentials.email,
          },
        },
        '2': {
          id: 2,
          instructor: {
            id: 2,
            full_name: completedLesson.instructor,
            email: 'jane.smith@example.com',
            rating: 4.9,
            total_reviews: 89,
            bio: 'PhD in Physics, specializing in quantum mechanics.',
          },
          service_name: completedLesson.service,
          booking_date: '2024-12-20',
          start_time: '10:00:00',
          end_time: '11:00:00',
          price: 80,
          status: 'completed',
          location_type: 'in_person',
          location_details: 'Upper East Side, NYC',
          notes: 'Great session!',
          receipt: {
            subtotal: 80,
            platform_fee: 8,
            total: 88,
          },
          student: {
            id: 1,
            full_name: 'Test Student',
            email: studentCredentials.email,
          },
        },
      };

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(bookingDetails[bookingId] || bookingDetails['1']),
      });
    } else {
      // This is a list request
      const isUpcoming = url.searchParams.get('upcoming_only') === 'true';
      const status = url.searchParams.get('status');

      if (isUpcoming && status === 'CONFIRMED') {
        // Upcoming lessons
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            bookings: [
              {
                id: 1,
                instructor: {
                  id: 1,
                  full_name: upcomingLesson.instructor,
                  email: 'john.doe@example.com',
                  rating: 4.8,
                  total_reviews: 156,
                },
                service_name: upcomingLesson.service,
                booking_date: '2024-12-25',
                start_time: '14:00:00',
                end_time: '15:00:00',
                price: 60,
                total_price: 60,
                status: 'CONFIRMED',
                location_type: 'online',
                location_details: 'Zoom meeting',
              },
            ],
            total: 1,
            page: 1,
            per_page: 50,
          }),
        });
      } else {
        // History/completed lessons
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            bookings: [
              {
                id: 2,
                instructor: {
                  id: 2,
                  full_name: completedLesson.instructor,
                  email: 'jane.smith@example.com',
                  rating: 4.9,
                  total_reviews: 89,
                },
                service_name: completedLesson.service,
                booking_date: '2024-12-20',
                start_time: '10:00:00',
                end_time: '11:00:00',
                price: 80,
                total_price: 80,
                status: 'COMPLETED',
                location_type: 'in_person',
                location_details: 'Upper East Side, NYC',
              },
            ],
            total: 1,
            page: 1,
            per_page: 20,
          }),
        });
      }
    }
  });

  // Mock instructor profile
  await page.route('http://localhost:8000/instructors/*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: 2,
        full_name: 'Jane Smith',
        email: 'jane.smith@example.com',
        bio: 'PhD in Physics',
        rating: 4.9,
        total_reviews: 89,
        services: ['Physics', 'Mathematics'],
        hourly_rate: 80,
      }),
    });
  });

  // Mock login endpoint
  await page.route('http://localhost:8000/auth/login', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        access_token: 'mock_access_token',
        token_type: 'bearer',
        user: {
          id: 1,
          email: studentCredentials.email,
          full_name: 'Test Student',
          roles: ['student'],
          permissions: [],
          is_active: true,
        },
      }),
    });
  });

  // Mock categories for homepage
  await page.route('http://localhost:8000/categories*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        { id: 1, name: 'Music', description: 'Learn instruments' },
        { id: 2, name: 'Languages', description: 'Learn new languages' },
      ]),
    });
  });

  // Mock featured instructors for homepage
  await page.route('http://localhost:8000/instructors/featured*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    });
  });
}

test.describe('My Lessons Page', () => {
  test.beforeEach(async ({ page }) => {
    await setupMocksAndAuth(page);
  });

  test.skip('should navigate to My Lessons from homepage', async ({ page }) => {
    await page.goto('/');

    // Wait for page to load and handle any errors
    await page.waitForLoadState('domcontentloaded');

    // Click My Lessons link in header - using more specific selector
    const myLessonsLink = page.getByRole('link', { name: 'My Lessons' });
    await expect(myLessonsLink).toBeVisible({ timeout: 15000 });
    await myLessonsLink.click();

    // Verify navigation to correct URL
    await expect(page).toHaveURL('/student/lessons');

    // Verify page title
    await expect(page.locator('h1')).toContainText('My Lessons');
  });

  test('should display upcoming and history tabs', async ({ page }) => {
    await page.goto('/student/lessons');
    await page.waitForLoadState('networkidle');

    // Wait for tabs to be visible
    await expect(page.locator('text=Upcoming')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('text=History')).toBeVisible({ timeout: 10000 });

    // Verify Upcoming tab is active by default
    const upcomingTab = page.locator('button:has-text("Upcoming")');
    await expect(upcomingTab).toHaveClass(/text-primary/);
  });

  test('should switch between Upcoming and History tabs', async ({ page }) => {
    await page.goto('/student/lessons');
    await page.waitForLoadState('networkidle');

    // Wait for tabs
    await page.waitForSelector('button:has-text("History")', { timeout: 10000 });

    // Click History tab
    await page.click('text=History');

    // Verify History tab is now active
    const historyTab = page.locator('button:has-text("History")');
    await expect(historyTab).toHaveClass(/text-primary/);

    // Verify Upcoming tab is not active
    const upcomingTab = page.locator('button:has-text("Upcoming")');
    await expect(upcomingTab).not.toHaveClass(/text-primary/);

    // Switch back to Upcoming
    await page.click('text=Upcoming');
    await expect(upcomingTab).toHaveClass(/text-primary/);
  });

  test('should display lesson cards with correct information', async ({ page }) => {
    await page.goto('/student/lessons');
    await page.waitForLoadState('networkidle');

    // Wait for lesson cards to load
    await page.waitForSelector('h3', { timeout: 10000 });

    // Verify lesson card contains expected information
    const lessonCard = page.locator('[class*="border"][class*="rounded"]').first();
    await expect(lessonCard).toContainText(upcomingLesson.instructor);
    await expect(lessonCard).toContainText(upcomingLesson.service);
    await expect(lessonCard).toContainText(upcomingLesson.date);
    await expect(lessonCard).toContainText(upcomingLesson.time);
    await expect(lessonCard).toContainText(upcomingLesson.price);
  });

  test('should navigate to lesson details when card is clicked', async ({ page }) => {
    await page.goto('/student/lessons');
    await page.waitForLoadState('networkidle');

    // Wait for lesson cards
    await page.waitForSelector('h3', { timeout: 10000 });

    // Click on first lesson card
    await page.locator('[class*="border"][class*="rounded"]').first().click();

    // Verify navigation to lesson details
    await expect(page).toHaveURL(/\/student\/lessons\/\d+/);

    // Verify lesson details page elements
    await expect(page.locator('text=Back to My Lessons')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('h1')).toContainText(upcomingLesson.service);
  });

  test('should show empty state when no upcoming lessons', async ({ page }) => {
    // Override mock to return empty lessons
    await page.route('http://localhost:8000/bookings/*', async (route) => {
      const url = new URL(route.request().url());
      const isUpcoming = url.searchParams.get('upcoming_only') === 'true';
      const status = url.searchParams.get('status');

      if (isUpcoming && status === 'CONFIRMED') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ bookings: [], total: 0, page: 1, per_page: 50 }),
        });
      } else {
        // Keep history data
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            bookings: [
              {
                id: 2,
                instructor: { id: 2, full_name: completedLesson.instructor },
                service_name: completedLesson.service,
                booking_date: '2024-12-20',
                start_time: '10:00:00',
                status: 'COMPLETED',
              },
            ],
            total: 1,
            page: 1,
            per_page: 20,
          }),
        });
      }
    });

    await page.goto('/student/lessons');
    await page.waitForLoadState('networkidle');

    // Verify empty state
    await expect(page.locator("text=You don't have any upcoming lessons")).toBeVisible({
      timeout: 10000,
    });
    await expect(page.locator('text=Ready to learn something new?')).toBeVisible();
    await expect(page.locator('button:has-text("Find Instructors")')).toBeVisible();
  });

  test('should navigate to search when Find Instructors is clicked', async ({ page }) => {
    // Mock empty lessons
    await page.route('http://localhost:8000/bookings/*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ bookings: [], total: 0, page: 1, per_page: 50 }),
      });
    });

    await page.goto('/student/lessons');
    await page.waitForLoadState('networkidle');

    // Wait for and click Find Instructors button
    const findInstructorsBtn = page.locator('button:has-text("Find Instructors")');
    await expect(findInstructorsBtn).toBeVisible({ timeout: 10000 });
    await findInstructorsBtn.click();

    // Verify navigation to search
    await expect(page).toHaveURL('/search');
  });
});

test.describe('Lesson Details Page', () => {
  test.beforeEach(async ({ page }) => {
    await setupMocksAndAuth(page);
  });

  test('should display lesson details correctly', async ({ page }) => {
    await page.goto('/student/lessons/1');
    await page.waitForLoadState('networkidle');

    // Wait for content to load
    await page.waitForSelector('h1', { timeout: 10000 });

    // Verify lesson information
    await expect(page.locator('h1')).toContainText(upcomingLesson.service);
    await expect(page.locator('text=December 25, 2024')).toBeVisible();
    await expect(page.locator('text=2:00 PM - 3:00 PM')).toBeVisible();
    await expect(page.locator('text=' + upcomingLesson.price)).toBeVisible();

    // Verify instructor info
    await expect(page.locator('text=' + upcomingLesson.instructor)).toBeVisible();
  });

  test('should show reschedule and cancel buttons for upcoming lessons', async ({ page }) => {
    await page.goto('/student/lessons/1');
    await page.waitForLoadState('networkidle');

    // Wait for buttons to appear
    await expect(page.locator('button:has-text("Reschedule lesson")')).toBeVisible({
      timeout: 10000,
    });
    await expect(page.locator('button:has-text("Cancel lesson")')).toBeVisible();
  });

  test('should open reschedule modal when reschedule button is clicked', async ({ page }) => {
    await page.goto('/student/lessons/1');
    await page.waitForLoadState('networkidle');

    // Wait for and click reschedule button
    const rescheduleBtn = page.locator('button:has-text("Reschedule lesson")');
    await expect(rescheduleBtn).toBeVisible({ timeout: 10000 });
    await rescheduleBtn.click();

    // Verify modal appears
    await expect(page.locator('text=Reschedule Lesson')).toBeVisible();
    await expect(page.locator('text=Select a new date and time')).toBeVisible();

    // Close modal
    await page.click('button:has-text("Cancel")');
    await expect(page.locator('text=Reschedule Lesson')).not.toBeVisible();
  });

  test('should show cancellation warning when cancel button is clicked', async ({ page }) => {
    await page.goto('/student/lessons/1');
    await page.waitForLoadState('networkidle');

    // Wait for and click cancel button
    const cancelBtn = page.locator('button:has-text("Cancel lesson")');
    await expect(cancelBtn).toBeVisible({ timeout: 10000 });
    await cancelBtn.click();

    // Verify warning modal
    await expect(page.locator('text=Cancel Lesson?')).toBeVisible();
    await expect(page.locator('text=Cancellation fee')).toBeVisible();

    // Verify action buttons
    await expect(page.locator('button:has-text("Keep lesson")')).toBeVisible();
    await expect(page.locator('button:has-text("Reschedule instead")')).toBeVisible();
    await expect(page.locator('button:has-text("Cancel lesson")').nth(1)).toBeVisible();
  });

  test('should switch from cancel to reschedule modal', async ({ page }) => {
    await page.goto('/student/lessons/1');
    await page.waitForLoadState('networkidle');

    // Open cancel modal
    const cancelBtn = page.locator('button:has-text("Cancel lesson")');
    await expect(cancelBtn).toBeVisible({ timeout: 10000 });
    await cancelBtn.click();

    await expect(page.locator('text=Cancel Lesson?')).toBeVisible();

    // Click reschedule instead
    await page.click('button:has-text("Reschedule instead")');

    // Verify switched to reschedule modal
    await expect(page.locator('text=Cancel Lesson?')).not.toBeVisible();
    await expect(page.locator('text=Reschedule Lesson')).toBeVisible();
  });

  test('should navigate back to My Lessons', async ({ page }) => {
    await page.goto('/student/lessons/1');
    await page.waitForLoadState('networkidle');

    // Wait for and click back button
    const backBtn = page.locator('text=Back to My Lessons');
    await expect(backBtn).toBeVisible({ timeout: 10000 });
    await backBtn.click();

    // Verify navigation
    await expect(page).toHaveURL('/student/lessons');
  });
});

test.describe('Completed Lessons', () => {
  test.beforeEach(async ({ page }) => {
    await setupMocksAndAuth(page);
  });

  test('should display completed lesson with correct status', async ({ page }) => {
    await page.goto('/student/lessons');
    await page.waitForLoadState('networkidle');

    // Switch to History tab
    await page.waitForSelector('button:has-text("History")', { timeout: 10000 });
    await page.click('text=History');

    // Wait for completed lessons to load
    await page.waitForSelector('h3', { timeout: 10000 });

    // Verify completed lesson appears
    const lessonCard = page.locator('[class*="border"][class*="rounded"]').first();
    await expect(lessonCard).toContainText('Completed');
  });

  test('should show Book Again button for completed lessons', async ({ page }) => {
    await page.goto('/student/lessons/2');
    await page.waitForLoadState('networkidle');

    // Wait for completed status
    await expect(page.locator('text=COMPLETED')).toBeVisible({ timeout: 10000 });

    // Verify action buttons
    await expect(page.locator('button:has-text("Review & tip")')).toBeVisible();
    await expect(page.locator('button:has-text("Chat history")')).toBeVisible();
    await expect(page.locator('button:has-text("Book Again")')).toBeVisible();

    // Should not show reschedule/cancel
    await expect(page.locator('button:has-text("Reschedule lesson")')).not.toBeVisible();
    await expect(page.locator('button:has-text("Cancel lesson")')).not.toBeVisible();
  });

  test('should navigate to instructor profile when Book Again is clicked', async ({ page }) => {
    await page.goto('/student/lessons/2');
    await page.waitForLoadState('networkidle');

    // Wait for and click Book Again button
    const bookAgainBtn = page.locator('button:has-text("Book Again")');
    await expect(bookAgainBtn).toBeVisible({ timeout: 10000 });
    await bookAgainBtn.click();

    // Verify navigation to instructor profile
    await expect(page).toHaveURL(/\/instructors\/\d+/);
  });

  test('should display receipt for completed lessons', async ({ page }) => {
    await page.goto('/student/lessons/2');
    await page.waitForLoadState('networkidle');

    // Wait for receipt section
    await expect(page.locator('text=Receipt')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('text=Date of Lesson')).toBeVisible();
    await expect(page.locator('text=Platform Fee')).toBeVisible();
    await expect(page.locator('text=Total')).toBeVisible();
  });
});

test.describe('Mobile Responsiveness', () => {
  test.use({
    viewport: { width: 375, height: 667 }, // iPhone SE
  });

  test.beforeEach(async ({ page }) => {
    await setupMocksAndAuth(page);
  });

  test('should work on mobile viewport', async ({ page }) => {
    await page.goto('/student/lessons');
    await page.waitForLoadState('networkidle');

    // Verify page loads correctly
    await expect(page.locator('h1:has-text("My Lessons")')).toBeVisible({ timeout: 10000 });

    // Verify tabs are visible and functional
    await expect(page.locator('text=Upcoming')).toBeVisible();
    await expect(page.locator('text=History')).toBeVisible();

    // Click History tab
    await page.click('text=History');
    const historyTab = page.locator('button:has-text("History")');
    await expect(historyTab).toHaveClass(/text-primary/);

    // Verify lesson cards stack vertically
    const lessonCards = page.locator('[class*="border"][class*="rounded"]');
    const count = await lessonCards.count();
    if (count > 0) {
      // Check that cards are full width on mobile
      const firstCard = lessonCards.first();
      const box = await firstCard.boundingBox();
      expect(box?.width).toBeGreaterThan(300); // Most of viewport width
    }
  });

  test('should show mobile-friendly lesson details', async ({ page }) => {
    await page.goto('/student/lessons/1');
    await page.waitForLoadState('networkidle');

    // Wait for content
    await expect(page.locator('h1')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('text=Back to My Lessons')).toBeVisible();

    // Verify action buttons stack on mobile
    const manageSection = page.locator('text=Manage Booking').locator('..');
    await expect(manageSection.locator('button')).toHaveCount(2);

    // Verify buttons are full width on mobile
    const rescheduleButton = page.locator('button:has-text("Reschedule lesson")');
    const box = await rescheduleButton.boundingBox();
    expect(box?.width).toBeGreaterThan(150);
  });
});

test.describe('Error Handling', () => {
  test('should redirect to login when unauthorized', async ({ page }) => {
    // Don't set up auth for this test
    await page.goto('/student/lessons', { waitUntil: 'domcontentloaded' });

    // Should redirect to login with return URL
    await expect(page).toHaveURL('/login?redirect=%2Fstudent%2Flessons');
  });

  test('should show error state when API fails', async ({ page }) => {
    // Set up auth first
    await page.addInitScript(() => {
      localStorage.setItem('access_token', 'mock_access_token');
    });

    await page.route('http://localhost:8000/auth/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 1,
          email: studentCredentials.email,
          full_name: 'Test Student',
          roles: ['student'],
          permissions: [],
          is_active: true,
        }),
      });
    });

    // Override the mock to return error
    await page.route('http://localhost:8000/bookings/*', async (route) => {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ error: 'Server error' }),
      });
    });

    await page.goto('/student/lessons');
    await page.waitForLoadState('networkidle');

    // Verify error state
    await expect(page.locator('text=Failed to load lessons')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('text=There was an error loading your lessons')).toBeVisible();
    await expect(page.locator('button:has-text("Retry")')).toBeVisible();
  });

  test('should return to My Lessons after login', async ({ page }) => {
    // Set up login mock
    await page.route('http://localhost:8000/auth/login', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          access_token: 'mock_access_token',
          token_type: 'bearer',
          user: {
            id: 1,
            email: studentCredentials.email,
            full_name: 'Test Student',
            roles: ['student'],
            permissions: [],
            is_active: true,
          },
        }),
      });
    });

    // Mock auth endpoint to return 401 initially, then success after login
    let loginCompleted = false;
    await page.route('http://localhost:8000/auth/me', async (route) => {
      if (loginCompleted) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 1,
            email: studentCredentials.email,
            full_name: 'Test Student',
            roles: ['student'],
            permissions: [],
            is_active: true,
          }),
        });
      } else {
        await route.fulfill({ status: 401 });
      }
    });

    // Also mock the bookings for after login
    await page.route('http://localhost:8000/bookings/*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          bookings: [
            {
              id: 1,
              instructor: {
                id: 1,
                full_name: upcomingLesson.instructor,
                email: 'john.doe@example.com',
                rating: 4.8,
                total_reviews: 156,
              },
              service_name: upcomingLesson.service,
              booking_date: '2024-12-25',
              start_time: '14:00:00',
              end_time: '15:00:00',
              price: 60,
              total_price: 60,
              status: 'CONFIRMED',
              location_type: 'online',
              location_details: 'Zoom meeting',
            },
          ],
          total: 1,
        }),
      });
    });

    // Try to access My Lessons without auth
    await page.goto('/student/lessons');

    // Should be on login page
    await expect(page).toHaveURL('/login?redirect=%2Fstudent%2Flessons');

    // Fill login form
    await page.fill('input[name="email"]', studentCredentials.email);
    await page.fill('input[name="password"]', studentCredentials.password);

    // Mark login as completed
    loginCompleted = true;

    // Click submit and wait for navigation
    await Promise.all([page.waitForURL('**/student/lessons'), page.click('button[type="submit"]')]);

    // Verify we're on My Lessons page
    await expect(page).toHaveURL('/student/lessons');
    await expect(page.locator('h1')).toContainText('My Lessons');
  });
});
