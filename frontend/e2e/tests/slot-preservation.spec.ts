import { test, expect } from '@playwright/test';
import { setupAllMocks } from '../fixtures/api-mocks';

test.describe('Slot Preservation on Back Navigation', () => {
  test.beforeEach(async ({ page, context }) => {
    await setupAllMocks(page, context);
  });

  test('should preserve selected slot when navigating back from payment', async ({ page }) => {
    // 1. Navigate to instructor profile
    await page.goto('/instructors/8');
    await page.waitForLoadState('networkidle');

    // Set up authentication after navigation to avoid login redirects
    await page.evaluate(() => {
      localStorage.setItem('access_token', 'mock_access_token_123456');
      localStorage.setItem('user', JSON.stringify({
        id: 1,
        email: 'john.smith@example.com',
        full_name: 'John Smith',
        role: 'student'
      }));
    });

    // 2. Wait for slots to be available
    await page.waitForSelector('[data-testid*="time-slot"]', { timeout: 10000 });
    await page.waitForTimeout(1000); // Let any auto-selection complete

    // 3. Get all available slots
    const allSlots = await page.locator('[data-testid*="time-slot"]').all();
    console.log(`Found ${allSlots.length} time slots`);

    if (allSlots.length < 2) {
      console.log('Not enough slots to test selection change');
      return;
    }

    // 4. Click the LAST slot (to ensure it's different from any auto-selection)
    const lastSlot = allSlots[allSlots.length - 1];
    const lastSlotId = await lastSlot.getAttribute('data-testid');
    console.log('Selecting slot:', lastSlotId);

    await lastSlot.click();
    await page.waitForTimeout(500); // Let state update

    // 5. Verify the slot is selected by checking for the black border
    await expect(lastSlot).toHaveClass(/border-black/);

    // 6. Simulate booking flow by setting session storage and navigating
    console.log('Setting up booking data and navigating to payment page...');

    // Create booking data in session storage
    await page.evaluate(() => {
      const bookingData = {
        instructorId: 8,
        instructorName: 'Sarah Chen',
        lessonType: 'Piano',
        date: new Date(Date.now() + 3 * 24 * 60 * 60 * 1000).toISOString(), // 3 days from now
        startTime: '19:00', // 7pm
        endTime: '20:00',
        duration: 60,
        location: 'Upper West Side',
        basePrice: 120,
        serviceFee: 12,
        totalAmount: 132,
        freeCancellationUntil: new Date(Date.now() + 2 * 24 * 60 * 60 * 1000).toISOString()
      };
      sessionStorage.setItem('bookingData', JSON.stringify(bookingData));
      sessionStorage.setItem('serviceId', '1');
    });

    // Navigate directly to payment page
    await page.goto('/student/booking/confirm');
    await page.waitForLoadState('networkidle');
    console.log('Reached payment page');

    // 8. Verify booking data was stored
    const bookingData = await page.evaluate(() => {
      return {
        hasBookingData: !!sessionStorage.getItem('bookingData'),
        hasNavState: !!sessionStorage.getItem('booking_navigation_state')
      };
    });
    console.log('Storage state:', bookingData);
    expect(bookingData.hasBookingData).toBe(true);

    // 9. Click back button using test ID
    const backButton = page.locator('[data-testid="payment-back-button"]');
    await backButton.click();

    // 10. Wait for return to instructor profile
    await page.waitForURL('**/instructors/8', { timeout: 10000 });
    console.log('Back at instructor profile');

    // 11. Wait for slots to load again
    await page.waitForSelector('[data-testid*="time-slot"]', { timeout: 10000 });
    await page.waitForTimeout(1000); // Let restoration complete

    // 12. Find the selected slot (has border-black class)
    const selectedSlot = page.locator('button.border-black[data-testid*="time-slot"]').first();

    // 13. Verify a slot is selected
    await expect(selectedSlot).toBeVisible();

    // 14. Get the ID of the selected slot
    const selectedId = await selectedSlot.getAttribute('data-testid');
    console.log('Selected after back navigation:', selectedId);
    console.log('Expected:', lastSlotId);

    // 15. The critical test - it should be the same slot we selected before
    expect(selectedId).toBe(lastSlotId);
    console.log('✅ Slot selection was preserved!');
  });
});
