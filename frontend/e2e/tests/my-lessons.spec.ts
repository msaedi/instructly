import { test, expect } from '@playwright/test';

// Test data
const studentCredentials = {
  email: 'student@example.com',
  password: 'password123',
};

const upcomingLesson = {
  instructor: 'John Doe',
  service: 'Mathematics',
  date: 'Dec 25, 2024',
  time: '2:00 PM - 3:00 PM',
  price: '$60.00',
};

const completedLesson = {
  instructor: 'Jane Smith',
  service: 'Physics',
  date: 'Dec 20, 2024',
  time: '10:00 AM - 11:00 AM',
  price: '$80.00',
};

// Helper function to login
async function loginAsStudent(page: any) {
  await page.goto('/login');
  await page.fill('input[name="email"]', studentCredentials.email);
  await page.fill('input[name="password"]', studentCredentials.password);
  await page.click('button[type="submit"]');
  // Wait for successful navigation after login (expect redirect to dashboard or home)
  await page.waitForURL((url) => !url.pathname.includes('/login'), { timeout: 15000 });
}

test.describe('My Lessons Page', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsStudent(page);
  });

  test('should navigate to My Lessons from homepage', async ({ page }) => {
    await page.goto('/');

    // Click My Lessons link in header
    await page.click('text=My Lessons');

    // Verify navigation to correct URL
    await expect(page).toHaveURL('/student/lessons');

    // Verify page title
    await expect(page.locator('h1')).toContainText('My Lessons');
  });

  test('should display upcoming and history tabs', async ({ page }) => {
    await page.goto('/student/lessons');

    // Check both tabs are visible
    await expect(page.locator('text=Upcoming')).toBeVisible();
    await expect(page.locator('text=History')).toBeVisible();

    // Verify Upcoming tab is active by default
    const upcomingTab = page.locator('button:has-text("Upcoming")');
    await expect(upcomingTab).toHaveClass(/text-primary/);
  });

  test('should switch between Upcoming and History tabs', async ({ page }) => {
    await page.goto('/student/lessons');

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

    // Wait for lesson cards to load
    await page.waitForSelector('article');

    // Verify lesson card contains expected information
    const lessonCard = page.locator('article').first();
    await expect(lessonCard).toContainText(upcomingLesson.instructor);
    await expect(lessonCard).toContainText(upcomingLesson.service);
    await expect(lessonCard).toContainText(upcomingLesson.date);
    await expect(lessonCard).toContainText(upcomingLesson.time);
    await expect(lessonCard).toContainText(upcomingLesson.price);
  });

  test('should navigate to lesson details when card is clicked', async ({ page }) => {
    await page.goto('/student/lessons');

    // Click on first lesson card
    await page.locator('article').first().click();

    // Verify navigation to lesson details
    await expect(page).toHaveURL(/\/student\/lessons\/\d+/);

    // Verify lesson details page elements
    await expect(page.locator('text=Back to My Lessons')).toBeVisible();
    await expect(page.locator('h1')).toContainText(upcomingLesson.service);
  });

  test('should show empty state when no upcoming lessons', async ({ page }) => {
    // Mock API to return empty lessons
    await page.route('**/bookings/*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ bookings: [], total: 0 }),
      });
    });

    await page.goto('/student/lessons');

    // Verify empty state
    await expect(page.locator("text=You don't have any upcoming lessons")).toBeVisible();
    await expect(page.locator('text=Ready to learn something new?')).toBeVisible();
    await expect(page.locator('button:has-text("Find Instructors")')).toBeVisible();
  });

  test('should navigate to search when Find Instructors is clicked', async ({ page }) => {
    // Mock empty lessons
    await page.route('**/bookings/*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ bookings: [], total: 0 }),
      });
    });

    await page.goto('/student/lessons');

    // Click Find Instructors button
    await page.click('button:has-text("Find Instructors")');

    // Verify navigation to search
    await expect(page).toHaveURL('/search');
  });
});

test.describe('Lesson Details Page', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsStudent(page);
  });

  test('should display lesson details correctly', async ({ page }) => {
    await page.goto('/student/lessons/1');

    // Wait for page to load
    await page.waitForSelector('h1');

    // Verify lesson information
    await expect(page.locator('h1')).toContainText(upcomingLesson.service);
    await expect(page.locator('text=' + upcomingLesson.date)).toBeVisible();
    await expect(page.locator('text=' + upcomingLesson.time)).toBeVisible();
    await expect(page.locator('text=' + upcomingLesson.price)).toBeVisible();

    // Verify instructor info
    await expect(page.locator('text=' + upcomingLesson.instructor)).toBeVisible();
  });

  test('should show reschedule and cancel buttons for upcoming lessons', async ({ page }) => {
    await page.goto('/student/lessons/1');

    // Verify action buttons
    await expect(page.locator('button:has-text("Reschedule lesson")')).toBeVisible();
    await expect(page.locator('button:has-text("Cancel lesson")')).toBeVisible();
  });

  test('should open reschedule modal when reschedule button is clicked', async ({ page }) => {
    await page.goto('/student/lessons/1');

    // Click reschedule button
    await page.click('button:has-text("Reschedule lesson")');

    // Verify modal appears
    await expect(page.locator('text=Reschedule Lesson')).toBeVisible();
    await expect(page.locator('text=Select a new date and time')).toBeVisible();

    // Close modal
    await page.click('button:has-text("Cancel")');
    await expect(page.locator('text=Reschedule Lesson')).not.toBeVisible();
  });

  test('should show cancellation warning when cancel button is clicked', async ({ page }) => {
    await page.goto('/student/lessons/1');

    // Click cancel button
    await page.click('button:has-text("Cancel lesson")');

    // Verify warning modal
    await expect(page.locator('text=Cancel Lesson?')).toBeVisible();
    await expect(page.locator('text=Cancellation fee')).toBeVisible();

    // Verify action buttons
    await expect(page.locator('button:has-text("Keep lesson")')).toBeVisible();
    await expect(page.locator('button:has-text("Reschedule instead")')).toBeVisible();
    await expect(page.locator('button:has-text("Cancel lesson")')).toBeVisible();
  });

  test('should switch from cancel to reschedule modal', async ({ page }) => {
    await page.goto('/student/lessons/1');

    // Open cancel modal
    await page.click('button:has-text("Cancel lesson")');
    await expect(page.locator('text=Cancel Lesson?')).toBeVisible();

    // Click reschedule instead
    await page.click('button:has-text("Reschedule instead")');

    // Verify switched to reschedule modal
    await expect(page.locator('text=Cancel Lesson?')).not.toBeVisible();
    await expect(page.locator('text=Reschedule Lesson')).toBeVisible();
  });

  test('should navigate back to My Lessons', async ({ page }) => {
    await page.goto('/student/lessons/1');

    // Click back button
    await page.click('text=Back to My Lessons');

    // Verify navigation
    await expect(page).toHaveURL('/student/lessons');
  });
});

test.describe('Completed Lessons', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsStudent(page);
  });

  test('should display completed lesson with correct status', async ({ page }) => {
    await page.goto('/student/lessons');

    // Switch to History tab
    await page.click('text=History');

    // Wait for completed lessons to load
    await page.waitForSelector('article');

    // Verify completed lesson appears
    const lessonCard = page.locator('article').first();
    await expect(lessonCard).toContainText('Completed');
  });

  test('should show Book Again button for completed lessons', async ({ page }) => {
    // Navigate to completed lesson details
    await page.goto('/student/lessons/3'); // Assuming ID 3 is completed

    // Verify completed status
    await expect(page.locator('text=COMPLETED')).toBeVisible();

    // Verify action buttons
    await expect(page.locator('button:has-text("Review & tip")')).toBeVisible();
    await expect(page.locator('button:has-text("Chat history")')).toBeVisible();
    await expect(page.locator('button:has-text("Book Again")')).toBeVisible();

    // Should not show reschedule/cancel
    await expect(page.locator('button:has-text("Reschedule lesson")')).not.toBeVisible();
    await expect(page.locator('button:has-text("Cancel lesson")')).not.toBeVisible();
  });

  test('should navigate to instructor profile when Book Again is clicked', async ({ page }) => {
    await page.goto('/student/lessons/3');

    // Click Book Again button
    await page.click('button:has-text("Book Again")');

    // Verify navigation to instructor profile
    await expect(page).toHaveURL(/\/instructors\/\d+/);
  });

  test('should display receipt for completed lessons', async ({ page }) => {
    await page.goto('/student/lessons/3');

    // Verify receipt section
    await expect(page.locator('text=Receipt')).toBeVisible();
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
    await loginAsStudent(page);
  });

  test('should work on mobile viewport', async ({ page }) => {
    await page.goto('/student/lessons');

    // Verify page loads correctly
    await expect(page.locator('h1:has-text("My Lessons")')).toBeVisible();

    // Verify tabs are visible and functional
    await expect(page.locator('text=Upcoming')).toBeVisible();
    await expect(page.locator('text=History')).toBeVisible();

    // Click History tab
    await page.click('text=History');
    const historyTab = page.locator('button:has-text("History")');
    await expect(historyTab).toHaveClass(/text-primary/);

    // Verify lesson cards stack vertically
    const lessonCards = page.locator('article');
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

    // Verify content is visible on mobile
    await expect(page.locator('h1')).toBeVisible();
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
  test.beforeEach(async ({ page }) => {
    await loginAsStudent(page);
  });

  test('should show error state when API fails', async ({ page }) => {
    // Mock API error
    await page.route('**/bookings/*', async (route) => {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ error: 'Server error' }),
      });
    });

    await page.goto('/student/lessons');

    // Verify error state
    await expect(page.locator('text=Failed to load lessons')).toBeVisible();
    await expect(page.locator('text=There was an error loading your lessons')).toBeVisible();
    await expect(page.locator('button:has-text("Retry")')).toBeVisible();
  });

  test('should redirect to login when unauthorized', async ({ page }) => {
    // Clear auth token
    await page.evaluate(() => localStorage.removeItem('access_token'));

    // Try to access My Lessons
    await page.goto('/student/lessons');

    // Should redirect to login with return URL
    await expect(page).toHaveURL('/login?redirect=%2Fstudent%2Flessons');
  });

  test('should return to My Lessons after login', async ({ page }) => {
    // Clear auth token
    await page.evaluate(() => localStorage.removeItem('access_token'));

    // Try to access My Lessons
    await page.goto('/student/lessons');

    // Should be on login page
    await expect(page).toHaveURL('/login?redirect=%2Fstudent%2Flessons');

    // Login
    await page.fill('input[name="email"]', studentCredentials.email);
    await page.fill('input[name="password"]', studentCredentials.password);
    await page.click('button[type="submit"]');

    // Should return to My Lessons
    await expect(page).toHaveURL('/student/lessons');
  });
});
