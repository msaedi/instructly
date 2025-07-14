import { test, expect } from '@playwright/test';

test.describe('Smoke Tests', () => {
  test('homepage loads successfully', async ({ page }) => {
    await page.goto('/');

    // Check for the main heading
    const heading = page.getByRole('heading', { name: /Instant Learning with iNSTAiNSTRU/i });
    await expect(heading).toBeVisible();

    // Check for search input
    const searchInput = page.getByPlaceholder(/Ready to learn something new/i);
    await expect(searchInput).toBeVisible();
  });

  test('navigation links are visible', async ({ page }) => {
    await page.goto('/');

    // Check for the combined login/signup link
    const authLink = page.getByRole('link', { name: /Sign up \/ Log in/i });
    await expect(authLink).toBeVisible();

    // Check for become instructor link
    const instructorLink = page.getByRole('link', { name: /Become an Instructor/i });
    await expect(instructorLink).toBeVisible();
  });

  test('can navigate to login page', async ({ page }) => {
    await page.goto('/');

    const authLink = page.getByRole('link', { name: /Sign up \/ Log in/i });
    await authLink.click();

    // Verify we're on the login page
    await expect(page).toHaveURL(/\/login/);

    // Verify login page elements
    const signInHeading = page.getByRole('heading', { name: /Sign in to your account/i });
    await expect(signInHeading).toBeVisible();
  });

  test('can navigate to signup page from login', async ({ page }) => {
    await page.goto('/login');

    // Find the signup link on the login page
    const signupLink = page.getByRole('link', { name: /Sign up/i });
    await signupLink.click();

    // Verify we're on the signup page
    await expect(page).toHaveURL(/\/signup/);
  });
});
