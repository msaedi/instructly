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
        first_name: 'John',
        last_name: 'Smith',
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

    // 4. Click the FIRST slot (more predictable for testing)
    const firstSlot = allSlots[0];
    const firstSlotId = await firstSlot.getAttribute('data-testid');
    console.log('Selecting slot:', firstSlotId);

    // Parse the slot ID to extract day and time
    // Format is like: time-slot-Wed-9am
    const slotParts = firstSlotId?.split('-') || [];
    const slotDay = slotParts[2]; // e.g., "Wed"
    const slotTimeDisplay = slotParts[3]; // e.g., "9am"

    // Convert display time (9am) to 24-hour format (09:00) for storage
    const convertTo24Hour = (timeStr: string) => {
      const match = timeStr.match(/(\d+)(am|pm)/i);
      if (!match) return timeStr;
      let hour = parseInt(match[1]);
      const isPM = match[2].toLowerCase() === 'pm';
      if (isPM && hour !== 12) hour += 12;
      if (!isPM && hour === 12) hour = 0;
      return `${hour.toString().padStart(2, '0')}:00`;
    };
    const slotTime = convertTo24Hour(slotTimeDisplay);

    await firstSlot.click();
    await page.waitForTimeout(500); // Let state update

    // 5. Verify the slot is selected by checking for the black border
    await expect(firstSlot).toHaveClass(/border-black/);

    // 6. Simulate booking flow by setting session storage and navigating
    console.log('Setting up booking data and navigating to payment page...');

    // Create booking data and navigation state in session storage
    await page.evaluate((slotInfo) => {
      // Map day names to our fixed test dates
      const dayToDateMap: Record<string, string> = {
        'Wed': '2025-08-13',
        'Thu': '2025-08-14',
        'Fri': '2025-08-15'
      };

      const slotDate = dayToDateMap[slotInfo.day] || '2025-08-13';
      const targetDate = new Date(slotDate);

      const bookingData = {
        instructorId: 8,
        instructorName: 'Sarah C.',
        lessonType: 'Piano',
        date: targetDate.toISOString(),
        startTime: slotInfo.time, // Use the actual selected time
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

      // Save navigation state for slot preservation
      const navState = {
        selectedSlot: {
          date: slotDate,
          time: slotInfo.time, // Use the actual selected time
          duration: 60,
          instructorId: '8'
        },
        timestamp: Date.now(),
        source: 'profile',
        flowId: `flow_${Date.now()}_test`
      };
      sessionStorage.setItem('booking_navigation_state', JSON.stringify(navState));
    }, { day: slotDay, time: slotTime });

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
    console.log('Expected:', firstSlotId);

    // 15. The critical test - it should be the same slot we selected before
    expect(selectedId).toBe(firstSlotId);
    console.log('✅ Slot selection was preserved!');
  });
});
