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
    this.instructorName = page.locator('[data-testid="instructor-profile-name"]').first().or(page.locator('h1, h2').first());
    this.instructorBio = page
      .locator('p')
      .filter({ hasText: /experience|teach|professional/i })
      .first();
    this.hourlyRate = page.locator('text=/\\$\\d+/');
    // Look for calendar or availability section
    this.availabilityCalendar = page
      .locator('section:has-text("Availability"), div:has-text("Available times")')
      .first();
    // Look for availability slot buttons (they're small squares in the grid)
    this.timeSlots = page.locator('[data-testid^="time-slot-"]').or(page.locator('button[aria-label*="Select"]'));
    // Prefer explicit testid on service cards; fallback to label variants
    this.bookButton = page
      .locator('[data-testid^="book-service-"]:visible')
      .first()
      .or(page.getByRole('button', { name: /Book (now|This)/i }).first());
    this.selectedTimeSlot = page.locator('button[aria-pressed="true"], button.selected');
  }

  async selectFirstAvailableSlot() {
    // Wait for any slot to appear; be tolerant to dynamic rendering
    // Prefer visible time slots (desktop grid) to avoid hidden mobile elements
    const visibleSlots = this.page.locator('[data-testid^="time-slot-"]:visible');
    if ((await visibleSlots.count()) > 0) {
      await visibleSlots.first().scrollIntoViewIfNeeded();
      await visibleSlots.first().click({ trial: false });
      return;
    }

    // Fallback: attempt to bring first slot into view and click
    const anySlot = this.page.locator('[data-testid^="time-slot-"]').first();
    await anySlot.waitFor({ state: 'attached', timeout: 20000 });
    await anySlot.scrollIntoViewIfNeeded();
    await anySlot.click({ trial: false });
  }

  async selectTimeSlot(time: string) {
    // Wait for time slots to be available
    await this.page.waitForSelector('[data-testid^="time-slot-"]', {
      state: 'visible',
      timeout: 10000
    });

    // Try multiple approaches to find the time slot
    let slot = this.page.locator(`[data-testid*="${time}"]`).first();

    // If not found by test-id, try by aria-label
    if (!(await slot.isVisible())) {
      slot = this.page.locator(`button[aria-label*="${time}"]`).first();
    }

    // If still not found, try by text content
    if (!(await slot.isVisible())) {
      slot = this.page.locator('button').filter({ hasText: time }).first();
    }

    // Click the slot if found
    if (await slot.isVisible()) {
      await slot.click();
    } else {
      throw new Error(`Time slot ${time} not found`);
    }
  }

  async proceedToBooking() {
    await this.bookButton.waitFor({ state: 'visible', timeout: 15000 });
    await this.bookButton.scrollIntoViewIfNeeded().catch(() => {});
    await this.bookButton.click();
  }

  async getSelectedSlotTime() {
    return await this.selectedTimeSlot.textContent();
  }

  async waitForAvailability() {
    // Wait for initial content
    await this.page.waitForLoadState('domcontentloaded');
    // Wait for header, then allow slots to render
    try {
      await this.page.locator('[data-testid="instructor-profile-name"]').first().waitFor({ timeout: 5000 });
      await this.page.locator('[data-testid^="time-slot-"]:visible').first().waitFor({ timeout: 15000 });
    } catch {
      // If we can't find basic elements, the page might not have loaded correctly
      console.log('Warning: Could not find expected elements on instructor profile page');
    }
  }
}
