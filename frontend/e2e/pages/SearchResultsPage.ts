import { Page, Locator } from '@playwright/test';

export class SearchResultsPage {
  readonly page: Page;
  readonly instructorCards: Locator;
  readonly firstInstructorCard: Locator;
  readonly noResultsMessage: Locator;
  readonly filterByPrice: Locator;
  readonly filterByLocation: Locator;

  constructor(page: Page) {
    this.page = page;
    this.instructorCards = page.locator('[data-testid="instructor-card"]');
    this.firstInstructorCard = this.instructorCards.first();
    this.noResultsMessage = page.getByText(/no instructors found/i);
    this.filterByPrice = page.getByLabel(/price/i);
    this.filterByLocation = page.getByLabel(/location/i);
  }

  async clickFirstInstructor() {
    await this.firstInstructorCard.click();
  }

  async getInstructorCount() {
    return await this.instructorCards.count();
  }

  async waitForResults() {
    // Wait for either results or no results message
    await this.page.waitForSelector('[data-testid="instructor-card"], [data-testid="no-results"]');
  }

  async getInstructorName(index: number = 0) {
    const card = this.instructorCards.nth(index);
    return await card.locator('[data-testid="instructor-name"]').textContent();
  }

  async getInstructorPrice(index: number = 0) {
    const card = this.instructorCards.nth(index);
    return await card.locator('[data-testid="instructor-price"]').textContent();
  }
}
