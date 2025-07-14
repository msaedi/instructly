import { Page, Locator } from '@playwright/test';

export class ConfirmationPage {
  readonly page: Page;
  readonly confirmationMessage: Locator;
  readonly bookingId: Locator;
  readonly instructorInfo: Locator;
  readonly lessonDateTime: Locator;
  readonly viewBookingsButton: Locator;
  readonly bookAnotherButton: Locator;

  constructor(page: Page) {
    this.page = page;
    this.confirmationMessage = page.getByRole('heading', { name: /booking.*confirmed/i });
    this.bookingId = page.locator('[data-testid="booking-id"]');
    this.instructorInfo = page.locator('[data-testid="confirmation-instructor"]');
    this.lessonDateTime = page.locator('[data-testid="confirmation-datetime"]');
    this.viewBookingsButton = page.getByRole('link', { name: /view.*bookings/i });
    this.bookAnotherButton = page.getByRole('link', { name: /book.*another/i });
  }

  async getBookingId() {
    return await this.bookingId.textContent();
  }

  async getInstructorName() {
    return await this.instructorInfo.textContent();
  }

  async getLessonDateTime() {
    return await this.lessonDateTime.textContent();
  }

  async navigateToBookings() {
    await this.viewBookingsButton.click();
  }

  async bookAnotherLesson() {
    await this.bookAnotherButton.click();
  }

  async waitForConfirmation() {
    await this.confirmationMessage.waitFor({ state: 'visible' });
  }
}
