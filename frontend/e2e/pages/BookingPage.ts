import { Page, Locator } from '@playwright/test';

export class BookingPage {
  readonly page: Page;
  readonly lessonDetails: Locator;
  readonly notesTextarea: Locator;
  readonly confirmButton: Locator;
  readonly cancelButton: Locator;
  readonly priceDisplay: Locator;
  readonly dateTimeDisplay: Locator;
  readonly loginPrompt: Locator;

  constructor(page: Page) {
    this.page = page;
    this.lessonDetails = page.locator('[data-testid="lesson-details"]');
    this.notesTextarea = page.getByLabel(/notes|message/i);
    this.confirmButton = page.getByRole('button', { name: /confirm.*booking/i });
    this.cancelButton = page.getByRole('button', { name: /cancel/i });
    this.priceDisplay = page.locator('[data-testid="booking-price"]');
    this.dateTimeDisplay = page.locator('[data-testid="booking-datetime"]');
    this.loginPrompt = page.getByText(/please.*log.*in.*book/i);
  }

  async fillNotes(notes: string) {
    await this.notesTextarea.fill(notes);
  }

  async confirmBooking() {
    await this.confirmButton.click();
  }

  async cancelBooking() {
    await this.cancelButton.click();
  }

  async getBookingPrice() {
    return await this.priceDisplay.textContent();
  }

  async getBookingDateTime() {
    return await this.dateTimeDisplay.textContent();
  }

  async isLoginRequired() {
    return await this.loginPrompt.isVisible();
  }
}
