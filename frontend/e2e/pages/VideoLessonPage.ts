import type { Page, Locator } from '@playwright/test';

/**
 * Page object for the lesson room at /lessons/{bookingId}.
 *
 * Covers three visual phases: pre-lesson, ended, and not-joinable.
 * The "active" phase (HMSPrebuilt SDK) is never reached in E2E tests.
 */
export class VideoLessonPage {
  readonly page: Page;

  // Pre-lesson waiting room
  readonly joinButton: Locator;
  readonly countdownTimer: Locator;
  readonly joinOpensText: Locator;
  readonly windowClosesPill: Locator;
  readonly windowClosedText: Locator;
  readonly connectingText: Locator;
  readonly joiningAsText: Locator;

  // Lesson ended
  readonly lessonCompleteHeading: Locator;
  readonly sessionSummary: Locator;
  readonly durationLabel: Locator;
  readonly instructorJoinedLabel: Locator;
  readonly studentJoinedLabel: Locator;
  readonly backToLessonsLink: Locator;
  readonly bookAgainLink: Locator;

  // Not joinable / errors
  readonly alertRegion: Locator;
  readonly inPersonMessage: Locator;
  readonly cancelledMessage: Locator;
  readonly notAvailableMessage: Locator;

  // Booking load error
  readonly failedToLoadText: Locator;
  readonly lessonNotFoundText: Locator;

  constructor(page: Page) {
    this.page = page;

    // Pre-lesson
    this.joinButton = page.getByRole('button', { name: 'Join video lesson' });
    this.countdownTimer = page.getByRole('timer');
    this.joinOpensText = page.getByText('Join opens in');
    this.windowClosesPill = page.getByText(/Window closes in/);
    this.windowClosedText = page.getByText('Join window has closed.');
    this.connectingText = page.getByText('Connecting...');
    this.joiningAsText = page.getByText(/Joining as/);

    // Ended
    this.lessonCompleteHeading = page.getByRole('heading', {
      name: 'Lesson Complete',
    });
    this.sessionSummary = page.getByRole('status', {
      name: 'Session summary',
    });
    this.durationLabel = page.getByText('Duration');
    this.instructorJoinedLabel = page.getByText('Instructor joined');
    this.studentJoinedLabel = page.getByText('Student joined');
    this.backToLessonsLink = page.getByRole('link', {
      name: 'Back to My Lessons',
    });
    this.bookAgainLink = page.getByRole('link', { name: 'Book Again' });

    // Not joinable — exclude Next.js __next-route-announcer__ (also role="alert").
    // Use CSS :not() because the announcer IS the alert element, not a descendant.
    this.alertRegion = page.locator('[role="alert"]:not(#__next-route-announcer__)');
    this.inPersonMessage = page.getByText(
      'This is an in-person lesson. Video is not available.',
    );
    this.cancelledMessage = page.getByText('This lesson was cancelled.');
    this.notAvailableMessage = page.getByText(
      'Video is not available for this lesson.',
    );

    // Error
    this.failedToLoadText = page.getByText('Failed to load lesson details.');
    this.lessonNotFoundText = page.getByText('Lesson not found.');
  }

  async goto(bookingId: string) {
    await this.page.goto(`/lessons/${bookingId}`);
  }
}
