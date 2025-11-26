import { test, expect, type BrowserContext, type ConsoleMessage, type Page, type Route } from '@playwright/test';
import { buildSessionCookie } from '../support/cookies';

const DEBUG_E2E_LOGIN = process.env.DEBUG_E2E_LOGIN === '1';

const escapeRegex = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const regexFromPath = (path: string) =>
  new RegExp(`^https?://[^/]+${escapeRegex(path)}(?:$|[/?#])`);

const USERS = {
  admin: { email: 'admin@instainstru.com', password: 'ChangeMeSuperSecure123!' },
  instructor: { email: 'sarah.chen@example.com', password: 'Test1234' },
  student: { email: 'john.smith@example.com', password: 'Test1234' },
  instructor2fa: { email: 'emma.johnson@example.com', password: 'Test1234' },
};

const LOGIN_URL = '/login';

const primeGuestSession = async (page: Page) => {
  await page.addInitScript(() => {
    try {
      const expiry = String(Date.now() + 30 * 24 * 60 * 60 * 1000);
      localStorage.setItem('guest_session_id', 'e2e-guest-123');
      localStorage.setItem('guest_session_expiry', expiry);
    } catch {
      // ignore
    }
  });
};

type ConsoleMatcher = string | RegExp | ((text: string) => boolean);

const waitForConsoleMessage = (page: Page, matcher: ConsoleMatcher, timeout = 8000) => {
  const predicate =
    typeof matcher === 'function'
      ? matcher
      : (text: string) => (typeof matcher === 'string' ? text.includes(matcher) : matcher.test(text));

  return new Promise<void>((resolve) => {
    let settled = false;
    const cleanup = () => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      page.off('console', handleConsole);
    };

    const handleConsole = (msg: ConsoleMessage) => {
      const text = msg.text();
      if (predicate(text)) {
        cleanup();
        resolve();
      }
    };

    const timer = setTimeout(() => {
      cleanup();
      resolve();
    }, timeout);

    page.on('console', handleConsole);
  });
};

const waitForLoginHydration = (page: Page) => waitForConsoleMessage(page, 'Login page loaded');

const waitForFormInteractivity = async (page: Page) => {
  await expect(page.getByLabel(/email/i)).toBeEnabled();
  await expect(page.getByRole('button', { name: /sign in/i })).toBeEnabled();
};

const buildCorsHeaders = (route: Route) => {
  const origin = route.request().headers()['origin'] ?? 'http://localhost:3100';
  return {
    'Access-Control-Allow-Origin': origin,
    'Access-Control-Allow-Credentials': 'true',
    'Access-Control-Allow-Headers':
      'Content-Type, Authorization, X-Guest-Session-ID, X-Trust-Browser',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    Vary: 'Origin',
  };
};

const handlePreflight = async (route: Route) => {
  if (route.request().method() === 'OPTIONS') {
    await route.fulfill({ status: 204, headers: buildCorsHeaders(route) });
    return true;
  }
  return false;
};

const respondJson = async (
  route: Route,
  body: Record<string, unknown>,
  status = 200,
  extraHeaders: Record<string, string> = {}
) => {
  await route.fulfill({
    status,
    contentType: 'application/json',
    headers: { ...buildCorsHeaders(route), ...extraHeaders },
    body: JSON.stringify(body),
  });
};

const cookieHeaderForOrigin = (origin: string, value = 'fake.jwt.value') => {
  const secure = origin.startsWith('https');
  return `access_token=${value}; Path=/; HttpOnly; SameSite=Lax${secure ? '; Secure' : ''}`;
};

const setSessionCookieHeaders = (origin: string, value = 'fake.jwt.value') => ({
  'set-cookie': cookieHeaderForOrigin(origin, value),
});

const persistSessionCookie = async (context: BrowserContext, value = 'fake.jwt.value') => {
  const base = process.env.PLAYWRIGHT_BASE_URL ?? process.env.BASE_URL ?? 'http://localhost:3100';
  const cookie = buildSessionCookie({
    baseURL: base,
    nameFromEnv: process.env.SESSION_COOKIE_NAME,
    token: value,
  });
  await context.addCookies([cookie]);
};

type RouteCallback = (route: Route) => Promise<void>;

const routeOnce = async (context: BrowserContext, url: string | RegExp, handler: RouteCallback) => {
  const wrapped = async (route: Route) => {
    await handler(route);
    if (route.request().method() !== 'OPTIONS') {
      await context.unroute(url, wrapped);
    }
  };
  await context.route(url, wrapped);
};

const routeAlways = async (
  context: BrowserContext,
  url: string | RegExp,
  handler: RouteCallback
) => {
  await context.route(url, handler);
};

const stubGuestSessionEndpoint = async (context: BrowserContext) => {
  await routeOnce(context, '**/api/public/session/guest', async (route) => {
    if (await handlePreflight(route)) return;
    await respondJson(route, { ok: true });
  });
};

const stubAuthMe = async (
  context: BrowserContext,
  rolesProvider: () => ReadonlyArray<string>,
  isReady: () => boolean
) => {
  await routeAlways(context, '**/api/v1/auth/me', async (route) => {
    if (await handlePreflight(route)) return;
    if (!isReady()) {
      await respondJson(route, { detail: 'Not authenticated' }, 401);
      return;
    }
    await respondJson(route, { roles: rolesProvider() });
  });
};

const stubInstructorProfile = async (
  context: BrowserContext,
  profile: { is_live: boolean }
) => {
  await routeOnce(context, '**/instructors/me', async (route) => {
    if (await handlePreflight(route)) return;
    await respondJson(route, profile);
  });
};

const stubInstructorProfileNotCalled = async (context: BrowserContext) => {
  await routeAlways(context, '**/instructors/me', async (route) => {
    if (await handlePreflight(route)) return;
    await route.fulfill({ status: 404, body: '{}' });
  });
};

const logDebug = (...args: unknown[]) => {
  if (DEBUG_E2E_LOGIN) {
    console.log('[login-2fa-spec]', ...args);
  }
};

test.afterEach(async ({ page }, testInfo) => {
  if (testInfo.status !== testInfo.expectedStatus) {
    await testInfo.attach('login-2fa-screenshot', {
      body: await page.screenshot(),
      contentType: 'image/png',
    });
    const video = page.video();
    if (video) {
      await testInfo.attach('login-2fa-video', {
        path: await video.path(),
        contentType: 'video/webm',
      });
    }
  }
});

test.beforeEach(async ({ context }) => {
  if (DEBUG_E2E_LOGIN) {
    context.on('request', (request) => {
      console.log('[login-2fa-spec] request', request.method(), request.url());
    });
  }
});

type RoutingScenario = {
  name: string;
  roles: string[];
  expected: string;
  user: { email: string; password: string };
  profile?: { is_live: boolean };
};

test.describe('Login routing without 2FA', () => {
  const scenarios: RoutingScenario[] = [
    { name: 'admin', roles: ['admin'], expected: '/admin/engineering/codebase', user: USERS.admin },
    {
      name: 'instructor live',
      roles: ['instructor'],
      expected: '/instructor/dashboard',
      user: USERS.instructor,
      profile: { is_live: true },
    },
    {
      name: 'instructor onboarding',
      roles: ['instructor'],
      expected: '/instructor/onboarding/status',
      user: USERS.instructor,
      profile: { is_live: false },
    },
    { name: 'student fallback', roles: [], expected: '/', user: USERS.student },
  ];

  for (const scenario of scenarios) {
    test(scenario.name, async ({ page, context }) => {
      await stubGuestSessionEndpoint(context);
      await primeGuestSession(page);

      let sessionReady = false;

      await routeOnce(context, '**/api/v1/auth/login-with-session', async (route) => {
        if (await handlePreflight(route)) return;
        const responseBody = {
          access_token: 'fake.jwt.value',
          token_type: 'bearer',
          requires_2fa: false,
        };
        logDebug('login-with-session response', responseBody);
        const requestOrigin = new URL(route.request().url()).origin;
        await respondJson(route, responseBody, 200, setSessionCookieHeaders(requestOrigin));
        await persistSessionCookie(context, 'fake.jwt.value');
        sessionReady = true;
      });

      await stubAuthMe(context, () => scenario.roles, () => sessionReady);

      if (scenario.roles.includes('instructor') && scenario.profile) {
        await stubInstructorProfile(context, scenario.profile);
      } else {
        await stubInstructorProfileNotCalled(context);
      }

      const hydrationReady = waitForLoginHydration(page);
      await page.goto(LOGIN_URL);
      await page.waitForLoadState('networkidle');
      await hydrationReady;
      await waitForFormInteractivity(page);
      await page.getByLabel(/email/i).fill(scenario.user.email);
      await page.getByLabel(/password/i).fill(scenario.user.password);
      await Promise.all([
        page.waitForURL(regexFromPath(scenario.expected), { timeout: 10000 }),
        page.getByRole('button', { name: /sign in/i }).click(),
      ]);
    });
  }
});

test.describe('2FA flows', () => {
  test('TOTP path sets session after verify', async ({ page, context }) => {
    await stubGuestSessionEndpoint(context);
    await primeGuestSession(page);

    let sessionReady = false;

    await routeOnce(context, '**/api/v1/auth/login-with-session', async (route) => {
      if (await handlePreflight(route)) return;
      const responseBody = {
        access_token: null,
        token_type: null,
        requires_2fa: true,
        temp_token: 'temp-123',
      };
      logDebug('2fa challenge response', responseBody);
      await respondJson(route, responseBody);
    });

    await routeOnce(context, '**/api/v1/2fa/verify-login', async (route) => {
      if (await handlePreflight(route)) return;
      const payload = { access_token: 'fake.jwt.2', token_type: 'bearer' };
      const requestOrigin = new URL(route.request().url()).origin;
      await respondJson(route, payload, 200, setSessionCookieHeaders(requestOrigin, 'fake.jwt.2'));
      await persistSessionCookie(context, 'fake.jwt.2');
      sessionReady = true;
    });

    await stubAuthMe(context, () => ['instructor'], () => sessionReady);
    await stubInstructorProfile(context, { is_live: true });

    const hydrationReady = waitForLoginHydration(page);
    await page.goto(LOGIN_URL);
    await page.waitForLoadState('networkidle');
    await hydrationReady;
    await waitForFormInteractivity(page);
    await page.getByLabel(/email/i).fill(USERS.instructor2fa.email);
    await page.getByLabel(/password/i).fill(USERS.instructor2fa.password);
    await page.getByRole('button', { name: /sign in/i }).click();
    await expect(page.getByLabel(/6-digit code/i)).toBeVisible();

    // Input enforces maxLength=6 and pattern="[0-9]*", so spaces are disallowed; trimming is
    // already covered by the backup-code path below.
    await page.getByLabel(/6-digit code/i).fill('123456');
    await Promise.all([
      page.waitForURL(regexFromPath('/instructor/dashboard'), { timeout: 10000 }),
      page.getByRole('button', { name: /verify/i }).click(),
    ]);
  });

  test('Backup code path trims input', async ({ page, context }) => {
    await stubGuestSessionEndpoint(context);
    await primeGuestSession(page);

    let sessionReady = false;

    await routeOnce(context, '**/api/v1/auth/login-with-session', async (route) => {
      if (await handlePreflight(route)) return;
      const responseBody = {
        access_token: null,
        token_type: null,
        requires_2fa: true,
        temp_token: 'temp-456',
      };
      await respondJson(route, responseBody);
    });

    await routeOnce(context, '**/api/v1/2fa/verify-login', async (route) => {
      if (await handlePreflight(route)) return;
      const payload = { access_token: 'fake.jwt.3', token_type: 'bearer' };
      const requestOrigin = new URL(route.request().url()).origin;
      await respondJson(route, payload, 200, setSessionCookieHeaders(requestOrigin, 'fake.jwt.3'));
      await persistSessionCookie(context, 'fake.jwt.3');
      sessionReady = true;
    });

    await stubAuthMe(context, () => [], () => sessionReady);
    await stubInstructorProfileNotCalled(context);

    const hydrationReady = waitForLoginHydration(page);
    await page.goto(LOGIN_URL);
    await page.waitForLoadState('networkidle');
    await hydrationReady;
    await waitForFormInteractivity(page);
    await page.getByLabel(/email/i).fill(USERS.instructor2fa.email);
    await page.getByLabel(/password/i).fill(USERS.instructor2fa.password);
    await page.getByRole('button', { name: /sign in/i }).click();
    await expect(page.getByLabel(/Backup code/i)).toBeVisible();

    await page.getByLabel(/Backup code/i).fill('  BACKUP-CODE-1234  ');
    await Promise.all([
      page.waitForURL(regexFromPath('/login'), { timeout: 10000 }),
      page.getByRole('button', { name: /verify/i }).click(),
    ]);
  });
});
