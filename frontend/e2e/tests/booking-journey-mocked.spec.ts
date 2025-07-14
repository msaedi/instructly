import { test, expect } from '@playwright/test';
import { HomePage } from '../pages/HomePage';
import { SearchResultsPage } from '../pages/SearchResultsPage';
import { InstructorProfilePage } from '../pages/InstructorProfilePage';
import { BookingPage } from '../pages/BookingPage';
import { ConfirmationPage } from '../pages/ConfirmationPage';
import { testData } from '../fixtures/test-data';
import { setupAllMocks } from '../fixtures/api-mocks';

test.describe('Student Booking Journey (Mocked)', () => {
  test.beforeEach(async ({ page }) => {
    // Set up all API mocks before each test
    await setupAllMocks(page);
  });

  test('should complete full booking flow with mocked API', async ({ page }) => {
    // Step 1: Start at homepage
    const homePage = new HomePage(page);
    await homePage.goto();

    // Step 2: Search for piano instructors
    await homePage.searchForInstrument(testData.search.instrument);

    // Step 3: View search results
    const searchResults = new SearchResultsPage(page);
    await searchResults.waitForResults();

    // Verify we have results
    const instructorCount = await searchResults.getInstructorCount();
    expect(instructorCount).toBe(1);

    // Step 4: Click on first instructor
    await searchResults.clickFirstInstructor();

    // Step 5: View instructor profile
    const instructorProfile = new InstructorProfilePage(page);
    await instructorProfile.waitForAvailability();

    // Step 6: Select an available time slot
    await instructorProfile.selectFirstAvailableSlot();

    // Step 7: Proceed to booking
    await instructorProfile.proceedToBooking();

    // Step 8: Complete booking form
    const bookingPage = new BookingPage(page);

    // Set mock authentication
    await page.evaluate(() => {
      localStorage.setItem('auth_token', 'mock_access_token');
    });

    await bookingPage.fillNotes(testData.booking.notes);

    // Step 9: Confirm booking
    await bookingPage.confirmBooking();

    // Step 10: Verify confirmation page
    const confirmationPage = new ConfirmationPage(page);
    await confirmationPage.waitForConfirmation();

    // Verify booking was successful
    await expect(confirmationPage.confirmationMessage).toBeVisible();
  });

  test('should navigate through multiple instructors', async ({ page }) => {
    const homePage = new HomePage(page);
    await homePage.goto();

    await homePage.searchForInstrument(testData.search.instrument);

    const searchResults = new SearchResultsPage(page);
    await searchResults.waitForResults();

    // Get instructor name from search results
    const instructorName = await searchResults.getInstructorName(0);
    expect(instructorName).toContain('John Doe');

    // Get instructor price
    const instructorPrice = await searchResults.getInstructorPrice(0);
    expect(instructorPrice).toContain('75');
  });

  test('should display correct booking details', async ({ page }) => {
    // Navigate directly to instructor profile
    await page.goto('/instructors/1');

    const instructorProfile = new InstructorProfilePage(page);
    await instructorProfile.waitForAvailability();

    // Select specific time slot
    await instructorProfile.selectTimeSlot('14:00');
    await instructorProfile.proceedToBooking();

    const bookingPage = new BookingPage(page);

    // Set mock authentication
    await page.evaluate(() => {
      localStorage.setItem('auth_token', 'mock_access_token');
    });

    // Verify booking details
    const price = await bookingPage.getBookingPrice();
    expect(price).toContain('75'); // $75/hour

    const dateTime = await bookingPage.getBookingDateTime();
    expect(dateTime).toContain('14:00');
  });
});
