import { test, expect, Page } from '@playwright/test';

// Simple test to verify basic my-lessons functionality
test.describe('My Lessons Basic Tests', () => {
  // Setup authentication and mocks before each test
  test.beforeEach(async ({ page }) => {
    // Mock the auth check endpoint
    await page.route('**/api/auth/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 1,
          email: 'student@example.com',
          full_name: 'Test Student',
          roles: ['student'],
          permissions: [],
          is_active: true,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        }),
      });
    });

    // Mock upcoming lessons
    await page.route('**/api/bookings/upcoming', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          bookings: [
            {
              id: 1,
              instructor: { id: 1, full_name: 'John Doe' },
              service_name: 'Mathematics',
              booking_date: '2024-12-25',
              start_time: '14:00:00',
              end_time: '15:00:00',
              price: 60,
              status: 'confirmed',
            },
          ],
          total: 1,
        }),
      });
    });

    // Mock completed lessons
    await page.route('**/api/bookings/history', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          bookings: [
            {
              id: 2,
              instructor: { id: 2, full_name: 'Jane Smith' },
              service_name: 'Physics',
              booking_date: '2024-12-20',
              start_time: '10:00:00',
              end_time: '11:00:00',
              price: 80,
              status: 'completed',
            },
          ],
          total: 1,
        }),
      });
    });

    // Set authentication
    await page.goto('/');
    await page.evaluate(() => {
      localStorage.setItem('access_token', 'mock_access_token');
    });
    await page.reload();
  });

  test('should access My Lessons page', async ({ page }) => {
    await page.goto('/student/lessons');

    // Wait for content to load
    await page.waitForLoadState('networkidle');

    // Verify we're on the right page
    await expect(page).toHaveURL('/student/lessons');

    // Look for any content that indicates the page loaded
    const pageContent = await page.textContent('body');
    expect(pageContent).toBeTruthy();
  });

  test('should show lesson content', async ({ page }) => {
    await page.goto('/student/lessons');
    await page.waitForLoadState('networkidle');

    // Look for instructor name or service name
    const hasInstructor = (await page.locator('text=John Doe').count()) > 0;
    const hasService = (await page.locator('text=Mathematics').count()) > 0;

    // At least one should be visible
    expect(hasInstructor || hasService).toBeTruthy();
  });
});
