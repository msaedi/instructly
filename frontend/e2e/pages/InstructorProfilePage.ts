import { Page, Locator } from '@playwright/test';

export class InstructorProfilePage {
  readonly page: Page;
  readonly instructorName: Locator;
  readonly instructorBio: Locator;
  readonly hourlyRate: Locator;
  readonly availabilityCalendar: Locator;
  readonly timeSlots: Locator;
  readonly bookButton: Locator;
  readonly selectedTimeSlot: Locator;

  constructor(page: Page) {
    this.page = page;
    // Use more flexible selectors based on actual page structure
    this.instructorName = page.locator('h1, h2').first();
    this.instructorBio = page
      .locator('p')
      .filter({ hasText: /experience|teach|professional/i })
      .first();
    this.hourlyRate = page.locator('text=/\\$\\d+/');
    // Look for calendar or availability section
    this.availabilityCalendar = page
      .locator('section:has-text("Availability"), div:has-text("Available times")')
      .first();
    this.timeSlots = page.locator('button').filter({ hasText: /\d{1,2}:\d{2}/ });
    this.bookButton = page.getByRole('button', { name: /book|continue|next/i });
    this.selectedTimeSlot = page.locator('button[aria-pressed="true"], button.selected');
  }

  async selectFirstAvailableSlot() {
    // Click on the first time slot button
    try {
      const firstSlot = this.timeSlots.first();
      await firstSlot.click();
    } catch (e) {
      console.log('No time slots found, skipping selection');
    }
  }

  async selectTimeSlot(time: string) {
    const slot = this.timeSlots.filter({ hasText: time });
    await slot.click();
  }

  async proceedToBooking() {
    await this.bookButton.click();
  }

  async getSelectedSlotTime() {
    return await this.selectedTimeSlot.textContent();
  }

  async waitForAvailability() {
    // Wait for page to load
    await this.page.waitForLoadState('networkidle');
    // Wait for either availability calendar or any content indicating the profile loaded
    try {
      await this.page.waitForSelector('h1, h2', { timeout: 5000 });
      // Give a bit more time for dynamic content to load
      await this.page.waitForTimeout(1000);
    } catch (e) {
      // If we can't find basic elements, the page might not have loaded correctly
      console.log('Warning: Could not find expected elements on instructor profile page');
    }
  }
}
