import { Page, Locator } from '@playwright/test';

export class HomePage {
  readonly page: Page;
  readonly searchInput: Locator;
  readonly authLink: Locator;
  readonly becomeInstructorLink: Locator;

  constructor(page: Page) {
    this.page = page;
    // The placeholder text changes based on auth status
    this.searchInput = page.locator('input[type="text"][placeholder*="learn"]');
    this.authLink = page.getByRole('link', { name: /Sign up \/ Log in/i });
    this.becomeInstructorLink = page.getByRole('link', { name: /Become an Instructor/i });
  }

  async goto() {
    await this.page.goto('/');
  }

  async searchForInstrument(instrument: string) {
    await this.searchInput.fill(instrument);
    // Submit the form by pressing Enter
    await this.searchInput.press('Enter');
  }

  async navigateToAuth() {
    await this.authLink.click();
  }

  async navigateToBecomeInstructor() {
    await this.becomeInstructorLink.click();
  }
}
