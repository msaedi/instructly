// ──────────────────────────────────────────────────────────────────────────────
// AUTH NOTE: No "student" Playwright project exists. All tests run under the
// "instructor" project (which provides storageState cookies), then we override
// the GET /api/v1/auth/me mock to return a student or instructor user as needed.
// Playwright routes are matched in LIFO (last-registered-wins) order, so the
// auth/me mock registered in setupVideoMocks() overrides the one registered
// earlier by mockAuthenticatedPageBackgroundApis().
// ──────────────────────────────────────────────────────────────────────────────

import { test, expect, type Page } from '@playwright/test';
import { mockAuthenticatedPageBackgroundApis } from '../utils/authenticatedPageMocks';
import { VideoLessonPage } from '../pages/VideoLessonPage';
import {
  STUDENT_USER,
  INSTRUCTOR_USER,
  VIDEO_SESSION_DATA,
  VIDEO_SESSION_EMPTY,
  bookingJoinable,
  bookingNotYetJoinable,
  bookingWindowClosed,
  bookingEndedWithStats,
  bookingEndedNoStats,
  bookingCancelled,
  paginatedResponse,
} from '../fixtures/video-lesson-mocks';
// ---------------------------------------------------------------------------
// Types for setup helpers
// ---------------------------------------------------------------------------

type JoinMode = 'success' | 'error' | 'hang';

interface VideoMockOptions {
  user: typeof STUDENT_USER | typeof INSTRUCTOR_USER;
  booking: Record<string, unknown>;
  bookingError?: number;
  joinResponse?: JoinMode;
  videoSession?: Record<string, unknown> | null;
}

// ---------------------------------------------------------------------------
// Setup helper: lesson room page (/lessons/{bookingId})
// ---------------------------------------------------------------------------

async function setupVideoMocks(page: Page, opts: VideoMockOptions) {
  const userId = (opts.user as { id: string }).id;
  const bookingId = (opts.booking as { id: string }).id;

  // 1. Background API scaffolding (auth, refresh, SSE, notifications, etc.)
  await mockAuthenticatedPageBackgroundApis(page, { userId });

  // 2. Override auth/me — registered AFTER background mocks, so LIFO wins
  await page.route('**/api/v1/auth/me', async (route) => {
    if (route.request().method() !== 'GET') {
      await route.fallback();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(opts.user),
    });
  });

  // 3. Booking detail
  await page.route(`**/api/v1/bookings/${bookingId}`, async (route) => {
    if (route.request().method() !== 'GET') {
      await route.fallback();
      return;
    }
    if (opts.bookingError) {
      await route.fulfill({
        status: opts.bookingError,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Forbidden' }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(opts.booking),
    });
  });

  // 4. Join API
  await page.route(`**/api/v1/lessons/${bookingId}/join`, async (route) => {
    if (route.request().method() !== 'POST') {
      await route.fallback();
      return;
    }
    const mode = opts.joinResponse ?? 'hang';
    if (mode === 'error') {
      await route.fulfill({
        status: 403,
        contentType: 'application/json',
        body: JSON.stringify({
          detail: 'You are not a participant in this lesson',
        }),
      });
    } else if (mode === 'hang') {
      // Never respond — Playwright cleans up when page context closes
    } else {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          auth_token: 'mock_hms_auth_token_e2e',
          room_id: 'room_test_e2e_001',
          role: 'guest',
          booking_id: bookingId,
        }),
      });
    }
  });

  // 5. Video session status
  await page.route(
    `**/api/v1/lessons/${bookingId}/video-session`,
    async (route) => {
      if (route.request().method() !== 'GET') {
        await route.fallback();
        return;
      }
      const session = opts.videoSession ?? VIDEO_SESSION_EMPTY;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(session),
      });
    },
  );

  // 6. Reviews (needed by student detail page)
  await page.route('**/api/v1/reviews/booking/**', async (route) => {
    if (route.request().method() !== 'GET') {
      await route.fallback();
      return;
    }
    await route.fulfill({
      status: 404,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Not found' }),
    });
  });
}

// ---------------------------------------------------------------------------
// Setup helper: list pages (student lessons / instructor bookings)
// ---------------------------------------------------------------------------

interface ListMockOptions {
  user: typeof STUDENT_USER | typeof INSTRUCTOR_USER;
  upcomingBookings: Record<string, unknown>[];
}

async function setupStudentListMocks(page: Page, opts: ListMockOptions) {
  const userId = (opts.user as { id: string }).id;

  await mockAuthenticatedPageBackgroundApis(page, { userId });

  // Override auth/me (LIFO)
  await page.route('**/api/v1/auth/me', async (route) => {
    if (route.request().method() !== 'GET') {
      await route.fallback();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(opts.user),
    });
  });

  // Upcoming bookings
  await page.route(
    '**/api/v1/bookings?*upcoming_only=true*',
    async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(paginatedResponse(opts.upcomingBookings)),
      });
    },
  );

  // History (empty)
  await page.route(
    '**/api/v1/bookings?*exclude_future_confirmed=true*',
    async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(paginatedResponse([])),
      });
    },
  );

  // Completed for BookAgain (empty)
  await page.route('**/api/v1/bookings?status=COMPLETED*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(paginatedResponse([])),
    });
  });

  // Individual booking detail catch-all
  await page.route('**/api/v1/bookings/*', async (route) => {
    const url = new URL(route.request().url());
    // Only intercept detail requests (no query params)
    if (
      !url.searchParams.get('upcoming_only') &&
      !url.searchParams.get('status') &&
      !url.searchParams.get('exclude_future_confirmed')
    ) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(opts.upcomingBookings[0] ?? {}),
      });
      return;
    }
    await route.fallback();
  });

  // Batch ratings
  await page.route('**/api/v1/reviews/ratings/batch', async (route) => {
    if (route.request().method() !== 'POST') {
      await route.fallback();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ results: [] }),
    });
  });

  // Existing reviews check
  await page.route('**/api/v1/reviews/booking/existing', async (route) => {
    if (route.request().method() !== 'POST') {
      await route.fallback();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    });
  });

  // Categories (empty)
  await page.route('**/categories*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    });
  });

  // Search history (empty)
  await page.route('**/api/v1/search-history*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    });
  });

  // Single review (for detail page)
  await page.route('**/api/v1/reviews/booking/**', async (route) => {
    if (route.request().method() !== 'GET') {
      await route.fallback();
      return;
    }
    await route.fulfill({
      status: 404,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Not found' }),
    });
  });
}

async function setupInstructorListMocks(page: Page, opts: ListMockOptions) {
  const userId = (opts.user as { id: string }).id;

  await mockAuthenticatedPageBackgroundApis(page, { userId });

  // Override auth/me (LIFO)
  await page.route('**/api/v1/auth/me', async (route) => {
    if (route.request().method() !== 'GET') {
      await route.fallback();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(opts.user),
    });
  });

  // Override instructor-bookings/upcoming with our bookings (LIFO wins over background mock)
  await page.route(
    '**/api/v1/instructor-bookings/upcoming**',
    async (route) => {
      if (route.request().method() !== 'GET') {
        await route.fallback();
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(paginatedResponse(opts.upcomingBookings)),
      });
    },
  );
}

// =============================================================================
// GROUP 1: Join button visibility (student) — /student/lessons
// =============================================================================

test.describe('Join button visibility (student)', () => {
  test('shows Join Lesson button when join window is open', async ({
    page,
  }) => {
    const booking = bookingJoinable();
    await setupStudentListMocks(page, {
      user: STUDENT_USER,
      upcomingBookings: [booking],
    });

    await page.goto('/student/lessons');
    await expect(page.getByTestId('join-lesson-button')).toBeVisible({
      timeout: 10_000,
    });
  });

  test('hides button when window not yet open', async ({ page }) => {
    const booking = bookingNotYetJoinable();
    await setupStudentListMocks(page, {
      user: STUDENT_USER,
      upcomingBookings: [booking],
    });

    await page.goto('/student/lessons');
    // Wait for page to load
    await expect(
      page.getByRole('heading', { name: 'My Lessons' }),
    ).toBeVisible({ timeout: 10_000 });
    await expect(page.getByTestId('join-lesson-button')).not.toBeVisible();
  });

  test('hides button for completed booking', async ({ page }) => {
    const booking = bookingJoinable({
      status: 'COMPLETED',
      join_opens_at: null,
      join_closes_at: null,
      can_join_lesson: false,
    });
    await setupStudentListMocks(page, {
      user: STUDENT_USER,
      upcomingBookings: [booking],
    });

    await page.goto('/student/lessons');
    await expect(
      page.getByRole('heading', { name: 'My Lessons' }),
    ).toBeVisible({ timeout: 10_000 });
    await expect(page.getByTestId('join-lesson-button')).not.toBeVisible();
  });

  test('hides button for cancelled booking', async ({ page }) => {
    const booking = bookingCancelled();
    await setupStudentListMocks(page, {
      user: STUDENT_USER,
      upcomingBookings: [booking],
    });

    await page.goto('/student/lessons');
    await expect(
      page.getByRole('heading', { name: 'My Lessons' }),
    ).toBeVisible({ timeout: 10_000 });
    await expect(page.getByTestId('join-lesson-button')).not.toBeVisible();
  });
});

// =============================================================================
// GROUP 2: Join button visibility (instructor) — /instructor/bookings
// =============================================================================

test.describe('Join button visibility (instructor)', () => {
  test('shows Join Lesson button when window is open', async ({ page }) => {
    const booking = bookingJoinable({ instructor_id: INSTRUCTOR_USER.id });
    await setupInstructorListMocks(page, {
      user: INSTRUCTOR_USER,
      upcomingBookings: [booking],
    });

    await page.goto('/instructor/bookings');
    await expect(page.getByTestId('join-lesson-button')).toBeVisible({
      timeout: 10_000,
    });
  });

  test('hides button when window not open', async ({ page }) => {
    const booking = bookingNotYetJoinable({
      instructor_id: INSTRUCTOR_USER.id,
    });
    await setupInstructorListMocks(page, {
      user: INSTRUCTOR_USER,
      upcomingBookings: [booking],
    });

    await page.goto('/instructor/bookings');
    // Wait for page content
    await expect(page.getByText('Piano Lesson')).toBeVisible({
      timeout: 10_000,
    });
    await expect(page.getByTestId('join-lesson-button')).not.toBeVisible();
  });
});

// =============================================================================
// GROUP 3: Pre-lesson waiting room (student) — /lessons/{bookingId}
// =============================================================================

test.describe('Pre-lesson waiting room (student)', () => {
  test('shows Join Lesson button when window is open', async ({ page }) => {
    const booking = bookingJoinable();
    await setupVideoMocks(page, {
      user: STUDENT_USER,
      booking,
    });

    const lessonPage = new VideoLessonPage(page);
    await lessonPage.goto(booking.id);

    await expect(lessonPage.joinButton).toBeVisible({ timeout: 10_000 });
    await expect(lessonPage.windowClosesPill).toBeVisible();
  });

  test('shows Connecting state during join', async ({ page }) => {
    test.setTimeout(15_000);

    const booking = bookingJoinable();
    await setupVideoMocks(page, {
      user: STUDENT_USER,
      booking,
      joinResponse: 'hang',
    });

    const lessonPage = new VideoLessonPage(page);
    await lessonPage.goto(booking.id);

    await expect(lessonPage.joinButton).toBeVisible({ timeout: 10_000 });
    await lessonPage.joinButton.click();

    await expect(lessonPage.connectingText).toBeVisible({ timeout: 5_000 });
    await expect(
      page.locator('button[aria-busy="true"]'),
    ).toBeVisible();
  });

  test('shows countdown timer when window not yet open', async ({ page }) => {
    const booking = bookingNotYetJoinable();
    await setupVideoMocks(page, {
      user: STUDENT_USER,
      booking,
    });

    const lessonPage = new VideoLessonPage(page);
    await lessonPage.goto(booking.id);

    await expect(lessonPage.joinOpensText).toBeVisible({ timeout: 10_000 });
    await expect(lessonPage.countdownTimer).toBeVisible();
    await expect(lessonPage.countdownTimer).toHaveAttribute(
      'aria-live',
      'polite',
    );
  });

  test('shows window closed message', async ({ page }) => {
    const booking = bookingWindowClosed();
    await setupVideoMocks(page, {
      user: STUDENT_USER,
      booking,
    });

    const lessonPage = new VideoLessonPage(page);
    await lessonPage.goto(booking.id);

    await expect(lessonPage.windowClosedText).toBeVisible({ timeout: 10_000 });
  });
});

// =============================================================================
// GROUP 4: Pre-lesson waiting room — not yet joinable
// =============================================================================

test.describe('Pre-lesson waiting room — not yet joinable', () => {
  test('shows countdown with correct Joining as name', async ({ page }) => {
    const booking = bookingNotYetJoinable();
    await setupVideoMocks(page, {
      user: STUDENT_USER,
      booking,
    });

    const lessonPage = new VideoLessonPage(page);
    await lessonPage.goto(booking.id);

    await expect(lessonPage.joinOpensText).toBeVisible({ timeout: 10_000 });
    await expect(
      page.getByText(`Joining as ${STUDENT_USER.first_name} ${STUDENT_USER.last_name}`),
    ).toBeVisible();
  });

  test('does not show join button before window opens', async ({ page }) => {
    const booking = bookingNotYetJoinable();
    await setupVideoMocks(page, {
      user: STUDENT_USER,
      booking,
    });

    const lessonPage = new VideoLessonPage(page);
    await lessonPage.goto(booking.id);

    await expect(lessonPage.joinOpensText).toBeVisible({ timeout: 10_000 });
    await expect(lessonPage.joinButton).not.toBeVisible();
  });
});

// =============================================================================
// GROUP 5: Lesson ended summary (student) — /lessons/{bookingId}
// =============================================================================

test.describe('Lesson ended summary (student)', () => {
  test('shows Lesson Complete heading and session stats', async ({ page }) => {
    const booking = bookingEndedWithStats();
    await setupVideoMocks(page, {
      user: STUDENT_USER,
      booking,
      videoSession: VIDEO_SESSION_DATA,
    });

    const lessonPage = new VideoLessonPage(page);
    await lessonPage.goto(booking.id);

    await expect(lessonPage.lessonCompleteHeading).toBeVisible({
      timeout: 10_000,
    });
    await expect(lessonPage.sessionSummary).toBeVisible();

    // Duration: 2712s = 45m 12s
    await expect(page.getByText('45m 12s')).toBeVisible();

    // Join times should not be dashes
    await expect(lessonPage.instructorJoinedLabel).toBeVisible();
    await expect(lessonPage.studentJoinedLabel).toBeVisible();
  });

  test('shows Back to My Lessons and Book Again links', async ({ page }) => {
    const booking = bookingEndedWithStats();
    await setupVideoMocks(page, {
      user: STUDENT_USER,
      booking,
      videoSession: VIDEO_SESSION_DATA,
    });

    const lessonPage = new VideoLessonPage(page);
    await lessonPage.goto(booking.id);

    await expect(lessonPage.lessonCompleteHeading).toBeVisible({
      timeout: 10_000,
    });
    await expect(lessonPage.backToLessonsLink).toBeVisible();
    await expect(lessonPage.bookAgainLink).toBeVisible();
  });

  test('Back to My Lessons links to /student/lessons', async ({ page }) => {
    const booking = bookingEndedWithStats();
    await setupVideoMocks(page, {
      user: STUDENT_USER,
      booking,
      videoSession: VIDEO_SESSION_DATA,
    });

    const lessonPage = new VideoLessonPage(page);
    await lessonPage.goto(booking.id);

    await expect(lessonPage.backToLessonsLink).toBeVisible({
      timeout: 10_000,
    });
    await expect(lessonPage.backToLessonsLink).toHaveAttribute(
      'href',
      '/student/lessons',
    );
  });

  test('shows dashes when session data missing', async ({ page }) => {
    const booking = bookingEndedNoStats();
    await setupVideoMocks(page, {
      user: STUDENT_USER,
      booking,
      videoSession: null,
    });

    const lessonPage = new VideoLessonPage(page);
    await lessonPage.goto(booking.id);

    await expect(lessonPage.lessonCompleteHeading).toBeVisible({
      timeout: 10_000,
    });

    // All stats should show "--"
    const dashes = page.getByText('--');
    await expect(dashes.first()).toBeVisible();
  });
});

// =============================================================================
// GROUP 6: Lesson ended summary (instructor) — /lessons/{bookingId}
// =============================================================================

test.describe('Lesson ended summary (instructor)', () => {
  test('shows Lesson Complete for instructor', async ({ page }) => {
    const booking = bookingEndedWithStats({
      instructor_id: INSTRUCTOR_USER.id,
    });
    await setupVideoMocks(page, {
      user: INSTRUCTOR_USER,
      booking,
      videoSession: VIDEO_SESSION_DATA,
    });

    const lessonPage = new VideoLessonPage(page);
    await lessonPage.goto(booking.id);

    await expect(lessonPage.lessonCompleteHeading).toBeVisible({
      timeout: 10_000,
    });
  });

  test('does not show Book Again for instructor', async ({ page }) => {
    const booking = bookingEndedWithStats({
      instructor_id: INSTRUCTOR_USER.id,
    });
    await setupVideoMocks(page, {
      user: INSTRUCTOR_USER,
      booking,
      videoSession: VIDEO_SESSION_DATA,
    });

    const lessonPage = new VideoLessonPage(page);
    await lessonPage.goto(booking.id);

    await expect(lessonPage.lessonCompleteHeading).toBeVisible({
      timeout: 10_000,
    });
    await expect(lessonPage.bookAgainLink).not.toBeVisible();
  });

  test('Back to My Lessons links to /instructor/bookings', async ({
    page,
  }) => {
    const booking = bookingEndedWithStats({
      instructor_id: INSTRUCTOR_USER.id,
    });
    await setupVideoMocks(page, {
      user: INSTRUCTOR_USER,
      booking,
      videoSession: VIDEO_SESSION_DATA,
    });

    const lessonPage = new VideoLessonPage(page);
    await lessonPage.goto(booking.id);

    await expect(lessonPage.backToLessonsLink).toBeVisible({
      timeout: 10_000,
    });
    await expect(lessonPage.backToLessonsLink).toHaveAttribute(
      'href',
      '/instructor/bookings',
    );
  });
});

// =============================================================================
// GROUP 7: Video session stats on student detail — /student/lessons/{id}
// =============================================================================

test.describe('Video session stats on student detail', () => {
  test('shows Video Session section with duration and join times', async ({
    page,
  }) => {
    const booking = bookingEndedWithStats();
    await setupVideoMocks(page, {
      user: STUDENT_USER,
      booking,
    });

    await page.goto(`/student/lessons/${booking.id}`);

    await expect(
      page.getByRole('heading', { name: 'Video Session' }),
    ).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText('Duration')).toBeVisible();
    await expect(page.getByText('45m 12s')).toBeVisible();
    await expect(page.getByText('You joined')).toBeVisible();
    await expect(page.getByText('Instructor joined')).toBeVisible();
  });

  test('displays correct formatted values', async ({ page }) => {
    const booking = bookingEndedWithStats();
    await setupVideoMocks(page, {
      user: STUDENT_USER,
      booking,
    });

    await page.goto(`/student/lessons/${booking.id}`);

    await expect(
      page.getByRole('heading', { name: 'Video Session' }),
    ).toBeVisible({ timeout: 10_000 });

    // Duration should be 45m 12s
    await expect(page.getByText('45m 12s')).toBeVisible();

    // Join times should not be "--"
    const videoSection = page.locator('h2:has-text("Video Session") + div');
    const dashCount = await videoSection.getByText('--').count();
    expect(dashCount).toBe(0);
  });

  test('hides Video Session section when no stats', async ({ page }) => {
    const booking = bookingEndedWithStats({
      video_session_duration_seconds: null,
    });
    await setupVideoMocks(page, {
      user: STUDENT_USER,
      booking,
    });

    await page.goto(`/student/lessons/${booking.id}`);

    // Wait for page to load
    await expect(page.getByText('Piano Lesson')).toBeVisible({
      timeout: 10_000,
    });
    await expect(
      page.getByRole('heading', { name: 'Video Session' }),
    ).not.toBeVisible();
  });
});

// =============================================================================
// GROUP 8: Video session stats on instructor detail — /instructor/bookings/{id}
// =============================================================================

test.describe('Video session stats on instructor detail', () => {
  test('shows Video Session with correct role labels', async ({ page }) => {
    const booking = bookingEndedWithStats({
      instructor_id: INSTRUCTOR_USER.id,
    });
    await setupVideoMocks(page, {
      user: INSTRUCTOR_USER,
      booking,
    });

    await page.goto(`/instructor/bookings/${booking.id}`);

    // Instructor detail uses h3 for "Video Session"
    await expect(page.getByText('Video Session')).toBeVisible({
      timeout: 10_000,
    });
    await expect(page.getByText('Duration', { exact: true })).toBeVisible();
    await expect(page.getByText('45m 12s')).toBeVisible();

    // Role labels: "You joined" = instructor time, "Student joined" = student time
    await expect(page.getByText('You joined')).toBeVisible();
    await expect(page.getByText('Student joined')).toBeVisible();
  });

  test('hides section when no stats', async ({ page }) => {
    const booking = bookingEndedWithStats({
      instructor_id: INSTRUCTOR_USER.id,
      video_session_duration_seconds: null,
    });
    await setupVideoMocks(page, {
      user: INSTRUCTOR_USER,
      booking,
    });

    await page.goto(`/instructor/bookings/${booking.id}`);

    // Wait for page to load (look for booking content)
    await expect(page.getByText('Piano Lesson')).toBeVisible({
      timeout: 10_000,
    });
    // The "Video Session" heading should not appear
    await expect(page.getByText('Video Session')).not.toBeVisible();
  });
});

// =============================================================================
// GROUP 9: Error — cancelled booking
// =============================================================================

test.describe('Error — cancelled booking', () => {
  test('shows cancelled message', async ({ page }) => {
    const booking = bookingCancelled();
    await setupVideoMocks(page, {
      user: STUDENT_USER,
      booking,
    });

    const lessonPage = new VideoLessonPage(page);
    await lessonPage.goto(booking.id);

    await expect(lessonPage.alertRegion).toBeVisible({ timeout: 10_000 });
    await expect(lessonPage.cancelledMessage).toBeVisible();
  });
});

// =============================================================================
// GROUP 10: Error — join API failure
// =============================================================================

test.describe('Error — join API failure', () => {
  test('shows error alert on join failure', async ({ page }) => {
    const booking = bookingJoinable();
    await setupVideoMocks(page, {
      user: STUDENT_USER,
      booking,
      joinResponse: 'error',
    });

    const lessonPage = new VideoLessonPage(page);
    await lessonPage.goto(booking.id);

    await expect(lessonPage.joinButton).toBeVisible({ timeout: 10_000 });
    await lessonPage.joinButton.click();

    // After error, the page falls back to pre-lesson phase with an error alert.
    // Use CSS :not() because __next-route-announcer__ IS the alert, not a descendant.
    await expect(
      page.locator('[role="alert"]:not(#__next-route-announcer__)'),
    ).toBeVisible({ timeout: 10_000 });
  });
});

// =============================================================================
// GROUP 11: Error — non-participant access
// =============================================================================

test.describe('Error — non-participant access', () => {
  test('shows error when booking returns 403', async ({ page }) => {
    const booking = bookingJoinable();
    await setupVideoMocks(page, {
      user: STUDENT_USER,
      booking,
      bookingError: 403,
    });

    const lessonPage = new VideoLessonPage(page);
    await lessonPage.goto(booking.id);

    await expect(lessonPage.failedToLoadText).toBeVisible({
      timeout: 10_000,
    });
    await expect(
      page.getByRole('link', { name: 'Back to My Lessons' }),
    ).toBeVisible();
  });
});

// =============================================================================
// GROUP 12: Navigate away and return
// =============================================================================

test.describe('Navigate away and return', () => {
  test('re-enters pre-lesson phase when returning to lesson page', async ({
    page,
  }) => {
    const booking = bookingJoinable();
    await setupVideoMocks(page, {
      user: STUDENT_USER,
      booking,
    });

    // Also mock the student list page deps so navigation doesn't break
    await page.route(
      '**/api/v1/bookings?*upcoming_only=true*',
      async (route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(paginatedResponse([booking])),
        });
      },
    );
    await page.route(
      '**/api/v1/bookings?*exclude_future_confirmed=true*',
      async (route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(paginatedResponse([])),
        });
      },
    );
    await page.route(
      '**/api/v1/bookings?status=COMPLETED*',
      async (route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(paginatedResponse([])),
        });
      },
    );
    await page.route('**/api/v1/reviews/ratings/batch', async (route) => {
      if (route.request().method() === 'POST') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ results: [] }),
        });
        return;
      }
      await route.fallback();
    });
    await page.route('**/api/v1/reviews/booking/existing', async (route) => {
      if (route.request().method() === 'POST') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([]),
        });
        return;
      }
      await route.fallback();
    });

    const lessonPage = new VideoLessonPage(page);

    // First visit: verify pre-lesson phase
    await lessonPage.goto(booking.id);
    await expect(lessonPage.joinButton).toBeVisible({ timeout: 10_000 });

    // Navigate away
    await page.goto('/student/lessons');
    await expect(
      page.getByRole('heading', { name: 'My Lessons' }),
    ).toBeVisible({ timeout: 10_000 });

    // Return to lesson room
    await lessonPage.goto(booking.id);
    await expect(lessonPage.joinButton).toBeVisible({ timeout: 10_000 });
    await expect(lessonPage.windowClosesPill).toBeVisible();
  });
});
