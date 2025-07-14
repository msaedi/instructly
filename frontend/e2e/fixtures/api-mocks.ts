import { Page, Route } from '@playwright/test';
import { testData } from './test-data';

export async function mockSearchResults(page: Page) {
  await page.route('**/api/public/instructors/search*', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        instructors: [testData.mockInstructor],
        total: 1,
      }),
    });
  });
}

export async function mockInstructorProfile(page: Page) {
  await page.route('**/api/public/instructors/*', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(testData.mockInstructor),
    });
  });
}

export async function mockAvailability(page: Page) {
  await page.route('**/api/public/instructors/*/availability*', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        availability: testData.mockAvailability,
      }),
    });
  });
}

export async function mockBookingCreation(page: Page) {
  await page.route('**/api/bookings', async (route: Route) => {
    if (route.request().method() === 'POST') {
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 123,
          instructorId: testData.mockInstructor.id,
          studentId: 1,
          date: testData.mockAvailability[0].date,
          startTime: testData.mockAvailability[0].startTime,
          endTime: testData.mockAvailability[0].endTime,
          status: 'confirmed',
          createdAt: new Date().toISOString(),
        }),
      });
    } else {
      await route.continue();
    }
  });
}

export async function mockAuthentication(page: Page) {
  // Mock login endpoint
  await page.route('**/api/auth/login', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        access_token: 'mock_access_token',
        token_type: 'bearer',
        user: {
          id: 1,
          email: testData.student.email,
          firstName: testData.student.firstName,
          lastName: testData.student.lastName,
          role: 'student',
        },
      }),
    });
  });

  // Mock current user endpoint
  await page.route('**/api/auth/me', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: 1,
        email: testData.student.email,
        firstName: testData.student.firstName,
        lastName: testData.student.lastName,
        role: 'student',
      }),
    });
  });
}

export async function setupAllMocks(page: Page) {
  await mockSearchResults(page);
  await mockInstructorProfile(page);
  await mockAvailability(page);
  await mockBookingCreation(page);
  await mockAuthentication(page);
}
