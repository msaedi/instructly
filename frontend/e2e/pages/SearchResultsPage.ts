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
    // Use more generic selectors that match the actual page structure
    // The instructor cards are in main and have h3 headers
    this.instructorCards = page
      .locator('main')
      .locator(':has(h3)')
      .filter({ has: page.locator('a') });
    this.firstInstructorCard = this.instructorCards.first();
    this.noResultsMessage = page.getByText(/no instructors found|Failed to load/i);
    this.filterByPrice = page.getByLabel(/price/i);
    this.filterByLocation = page.getByLabel(/location/i);
  }

  async clickFirstInstructor() {
    // Click on "View Profile" link instead of the card
    const viewProfileLink = this.firstInstructorCard.locator('a:has-text("View Profile")');
    await viewProfileLink.click();
  }

  async getInstructorCount() {
    return await this.instructorCards.count();
  }

  async waitForResults() {
    // Wait for either results or error message
    await this.page.waitForLoadState('networkidle');
    // Wait for main content to load - handle both success and error states
    // Use Playwright's or() for multiple selectors
    await this.page
      .locator('main h3, :text("Failed to load search results"), [data-testid="no-results"]')
      .first()
      .waitFor({ state: 'visible' });
  }

  async getInstructorName(index: number = 0) {
    const card = this.instructorCards.nth(index);
    // Get the instructor name from the h3 heading
    const heading = await card.locator('h3').textContent();
    return heading || '';
  }

  async getInstructorPrice(index: number = 0) {
    const card = this.instructorCards.nth(index);
    // Extract price from the text content that contains the hourly rate
    const text = await card.textContent();
    const match = text?.match(/\$(\d+)\/hour/);
    return match ? match[0] : '';
  }
}
