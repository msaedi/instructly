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
    this.instructorName = page.locator('[data-testid="instructor-name"]');
    this.instructorBio = page.locator('[data-testid="instructor-bio"]');
    this.hourlyRate = page.locator('[data-testid="hourly-rate"]');
    this.availabilityCalendar = page.locator('[data-testid="availability-calendar"]');
    this.timeSlots = page.locator('[data-testid="time-slot"]');
    this.bookButton = page.getByRole('button', { name: /book.*lesson/i });
    this.selectedTimeSlot = page.locator('[data-testid="time-slot"][data-selected="true"]');
  }

  async selectFirstAvailableSlot() {
    // Click on the first available time slot
    const availableSlot = this.timeSlots.filter({ hasText: /available/i }).first();
    await availableSlot.click();
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
    await this.availabilityCalendar.waitFor({ state: 'visible' });
    // Wait for time slots to load
    await this.timeSlots.first().waitFor({ state: 'visible' });
  }
}
