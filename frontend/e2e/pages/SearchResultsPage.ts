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
    // Prefer explicit InstructorCard testids for stability
    this.instructorCards = page.locator('[data-testid="instructor-card"]');
    this.firstInstructorCard = this.instructorCards.first();
    this.noResultsMessage = page.getByText(/no instructors found|Failed to load/i);
    this.filterByPrice = page.getByLabel(/price/i);
    this.filterByLocation = page.getByLabel(/location/i);
  }

  async clickFirstInstructor() {
    // Prefer explicit test id if available within the first card
    const testIdLink = this.firstInstructorCard.locator('[data-testid="instructor-link"]').first();
    if (await testIdLink.isVisible().catch(() => false)) {
      await testIdLink.click();
      return;
    }
    // Click a profile link in the first card; fall back to any /instructors/{id} link
    const link = this.firstInstructorCard.locator('a[href^="/instructors/"]').first();
    if (await link.isVisible().catch(() => false)) {
      await link.click();
      return;
    }
    const anyLink = this.page.locator('a[href^="/instructors/"]').first();
    if (await anyLink.isVisible().catch(() => false)) {
      await anyLink.click();
      return;
    }
    // Fallback: click the first instructor card to trigger navigation if it has onClick behavior
    await this.firstInstructorCard.click();
  }

  async getInstructorCount() {
    return await this.instructorCards.count();
  }

  async waitForResults() {
    // Ensure navigation to search page completed before checking content
    await this.page.waitForURL(/\/search/, { timeout: 10000 });
    await this.page.waitForLoadState('domcontentloaded');
    // Wait for either results or error/empty states
    await this.page
      .locator('[data-testid="instructor-card"], :text("Failed to load search results"), [data-testid="no-results"]')
      .first()
      .waitFor({ state: 'visible' });
  }

  async getInstructorName(index: number = 0) {
    const card = this.instructorCards.nth(index);
    // Prefer explicit test id on instructor card; fall back to first heading
    const byTestId = await card.locator('[data-testid="instructor-name"]').first().textContent().catch(() => null);
    const heading = byTestId || (await card.locator('h3, h2').first().textContent());
    return heading || '';
  }

  async getInstructorPrice(index: number = 0) {
    const card = this.instructorCards.nth(index);
    // Extract price from data-testid or fallback
    const priceByTestId = await card.locator('[data-testid="instructor-price"]').first().textContent().catch(() => null);
    const text = priceByTestId || (await card.textContent());
    const match = text?.match(/\$(\d+)/);
    return match ? match[0] : '';
  }
}
